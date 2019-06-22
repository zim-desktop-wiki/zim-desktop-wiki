
# Copyright 2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This module contains classes and functions needed for concurrent use
of the notebook data.

Summary:

  - Notebook, page and related data structures are *not* thread safe
  - Concurrency in the Gtk/Glib main loop is handled by generator
	functions wrapped in "NotebookOperation" objects

The notebook and page objects are *not* thread safe, so threaded usage
needs to be managed carefully. Full thread safe design has been
investigated but deemed too complicated. Key here is that all
changes need to be communicated to the Gtk widgets of the interface
by signals and Gtk does not support threaded usage on all platforms.
There are ways to combine threaded usage with Gtk (e.g. by using an
idle event in the main loop to update widget) however this quickly
becomes a source of potential race conditions between threads.

Therefore the concurrency model chosen is the Gtk/Glib main loop. This
loop operates in a single thread, but allows interweaving actions by
breaking up long running actions and using idle events in the loop to
execute blocks. Implementation of this style is typically to have a
generator function to do the work and attach it to the idle event such
that it executes one step of the generator every time. When the generator
yields, other actions can be done in the mainloop.

This style does not necessarily mean that a lot of application logic is
done in parallel, but at least the interface is re-drawn, e.g. when the
user moves the window during the operation, and e.g. progress dialogs
can be used.

Limited use of threads is made, e.g. for blocking I/O and for indexing,
but these are specific uses that are made thread safe, this does not
generalize to the public APIs.

To make the use of the "generator style" concurrency more convenient
we introduce the concept of a notebook "operation". By this we mean
any type of action that needs a consistent notebook state over multiple
iterations. Examples are updating the index, moving a page and updating
links to the page, but also exporting the notebook. All these examples
would use a progress dialog of some kind.

Such an operations is attached to the notebook object, such that no
other operation can start at the same time. So only one operation can
be active for a given notebook at the same time. Also methods that
change the notebook cannot be used by other events while an operation
is active. In case of conflicts an error is raised that can be shown
to the user.

So apart from re-drawing the interface also other actions can happen
in the application while the operation is running, but these should be
limited to "read-only" access to the notebook.

See also:

  - For more information about threading and the generator style
	concurency with Gtk/GLib, see
	https://wiki.gnome.org/Projects/PyGObject/Threading


Examples
--------

Move page and update links (or other multi-part change):

  - show progress dialog
  - use operation with notebook.move_page_iter()


Export notebook (or other multi-part notebook access):

  - show progress dialog
  - use operation with exporter.export_iter()


Save page with asynchronous I/O:

  - Modify page object & update index based on the page object
  - Sync to disk in separate thread, use operation to monitor thread
  - Update index with file info after write (to avoid re-indexing later)

This is a special case using a thread to handle the asynchronous I/O.
Here it is allowed because the thread does not use the notebook objects.
However it does not use a generator to do work in the main loop, just
to monitor the thread. An operation is still used because we want the
thread to finish before the next thing happens.

Index updates:

  - If index is out-of-date at start, run update as operation with
	progress dialog
  - Else start thread to find out-of-date records (this is not an operation!)
  - If out-of-date records are found queue an trigger on idle to start
	updating (if another operation is active, delay with a timeout
	until notebook is unlocked)
  - Run update as operation with progress bar in window, but not
	blocking the window (assume updates are small)

  - When the user selects "update index" in the menu, or another action
	that explicitly asks to ensure index up to date (e.g. export)
  - If index operation is ongoing, attach progress dialog
  - Else start new update with progress dialog

The use of a thread here is allowed because it only acts on the index,
not on the notebook. However index updates in the operation or index
updates due to e.g. a page save should not conflict with the indexer
thread. To avoid this, the index must have a thread lock that allows
switching control of the database between the two threads.

The background index will also iterate and aquire & release again the
lock for each iteration. The operation start will block to aquire the
lock (thus putting the indexer on hold if it did not finish yet).
Also index updates e.g. because of a page save or page move will block
to aquire the lock. (Since such actions also require the operation
"lock" this will never happen while an update is prepared.)
'''

# Implementation notes:
#
#   The notebook attribute "_operation_check" is effectively used as
#   a lock. For threading support the access of this attribute should
#   be guarded by a real threading.Lock object. However this would also
#   requires each and every method of the Notebook, Index, Page and
#   ParseTree objects to be protected with an RLock to avoid changes
#   half-way accessing the notebook or a page.
#   Given that our Gtk interface does not use this, it is
#   over-engineering.
#

import threading
import logging

logger = logging.getLogger('zim.notebook')


try:
	from gi.repository import GObject
except ImportError:
	GObject = None


from zim.signals import SignalEmitter
from zim.errors import Error

NOOP = lambda: None


class NotebookOperationOngoing(Error):
	pass


class NotebookOperation(SignalEmitter):
	'''This class is used to wrap generators that execute multiple
	steps of an operation.

	Intended usage:

		op = NotebookOperation(
			notebook,
			_('Updating index'),
			notebook.index.update_iter
		)
		op.run_on_idle()

	This will start the operation using 'idle' events in the main loop
	to iterate through to operation steps.

	If you want to wait for the operation to finish, use a progress
	dialog like this:

		dialog = ProgressDialog(window, op)
		dialog.run()

	When using the progress dialog the values yielded by the inner
	iterator will be passed on via the 'step' signal. This should be a
	3-tuple of C{(i, total, msg)} where C{i} and C{total} are integers for the
	current step and the total number of steps expected (or C{None} if the step
	count is not known).

	'''

	# Signals are used by the progress dialog to monitor activity
	__signals__ = {
		'step': (None, None, (object,)),
		'started': (None, None, ()),
		'finished': (None, None, ()),
	}

	def __init__(self, notebook, message, iterator):
		'''Constructor
		@param notebook: the L{Notebook} object
		@param message: a message string for L{NotebookOperationOngoing}
		errors and for the heading of progress dialogs
		@param iterator: iterator that yields for chunks of work
		'''
		self.notebook = notebook
		self.message = message
		self.finished = False
		self.cancelled = False
		self.exception = None
		self._do_work = iterator
		self._block = True

	def is_running(self):
		return self.notebook._operation_check == self

	def __call__(self):
		'''This method is called when another operation tries to start
		while we are running. When called either finish quickly or
		raise L{NotebookOperationOngoing}.
		'''
		if self._block:
			if self.message:
				raise NotebookOperationOngoing(self.message)
			else:
				raise NotImplementedError

	def run_on_idle(self):
		'''Start the operation by setting up the main loop event handler.

		May raise L{NotebookOperationOngoing} if another operation is
		already ongoing.
		'''
		assert GObject, "No mainloop available to run this operation"

		if self.notebook._operation_check == self:
			raise AssertionError('Already running')
		else:
			self.notebook._operation_check() # can raise

		self.notebook._operation_check = self # start blocking
		GObject.idle_add(self._start) # ensure start happens in main thread

	def is_running(self):
		return self.notebook._operation_check == self

	def _start(self):
		my_iter = iter(self)
		GObject.idle_add(lambda: next(my_iter, False), priority=GObject.PRIORITY_LOW)
		return False # run once

	def cancel(self):
		logger.debug('Operation cancelled')
		self.notebook._operation_check = NOOP # stop blocking
		self.cancelled = True
		self.emit('finished')

	def __iter__(self):
		if self.finished:
			return False

		if not self.notebook._operation_check == self:
			self.notebook._operation_check() # can raise
			self.notebook._operation_check = self # start blocking

		self.emit('started')
		try:
			while self.notebook._operation_check == self:
				# while covers cancelled, but also any other op overwriting the "lock"
				# unblock api to do work, block again before yielding to main loop
				self._block = False
				progress = next(self._do_work)
				if isinstance(progress, tuple):
					self.emit('step', progress)
				else:
					self.emit('step', (None, None, progress))
				self._block = True
				yield True # keep going
		except StopIteration:
			pass
		except Exception as err:
			self.cancelled = True
			self.exception = err
			raise
		finally:
			if self.notebook._operation_check == self:
				self.notebook._operation_check = NOOP # stop blocking
				self.finished = True
				self.emit('finished')


class SimpleAsyncOperation(NotebookOperation):
	'''Variant of NotebookOperation that monitors a thread.
	Key difference is that instead of raising an exception when another
	operation tries to start it will wait for the thread. So only
	useful for short run time threads, like async file write.
	'''

	def __init__(self, notebook, message, thread, post_handler=None):
		'''Constructor
		@param notebook: the L{Notebook} object
		@param message: a message string for the heading of
		progress dialogs
		@param thread: a {threading.Thread} object
		@param post_handler: optional function to call in main after
		the thread has finished
		'''
		self._thread = thread

		def generator():
			while self._thread.is_alive():
				yield
			if post_handler:
				post_handler()

		NotebookOperation.__init__(self, notebook, message, generator())

	def __call__(self):
		if self._block and self._thread != threading.current_thread():
			self._join()

	def cancel(self):
		if self._thread == threading.current_thread():
			raise AssertionError('Can not cancel from thread')
		self._join()
		NotebookOperation.cancel(self)

	def _join(self):
		self._thread.join()
		for i in self:
			pass # exhaust iter to call the post-handler


class NotebookState(object):
	'''Context manager that can be used to wrap code that does not
	allow for operations to run in parallel fashion.

	All notebook methods that modify the notebook are protected by
	default with this context. However if you for some reason want to
	find out earlier whether or not an error will happen you can use
	this context explicitly.

	Entering the context may raise L{NotebookOperationOngoing} if an
	operation is ongoing.

	Intended usage:

		with NotebookState(notebook):
			page = notebook.get_page(path)
			# modify ...
			notebook.store_page(page)

	'''

	def __init__(self, notebook):
		self.notebook = notebook

	def __enter__(self):
		# only check whether api is blocked, don't block it ourselves
		self.notebook._operation_check()

	def __exit__(self, *a):
		pass


def notebook_state(method):
	'''Decorator for notebook API methods that behaves
	like the L{NotebookState} context.

	Intended only for methods that change the notebook.
	'''
	def wrapper(notebook, *arg, **kwarg):
		notebook._operation_check()
		return method(notebook, *arg, **kwarg)

	return wrapper


def ongoing_operation(notebook):
	op = notebook._operation_check
	return op if op != NOOP else None
