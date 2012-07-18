# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Asynchronous operations based on threading.

We define the AsyncOperation class to wrap a function that can be
executed asynchronous. AsyncOperation wraps the function in a thread
so it can run in parallel with the main program.

The idea is to only do low level actions in separate threads, e.g.
blocking I/O. In the main thread we have the gtk or gobject main loop
and there we also have "gobject.idle_add()" to queue actions that run
in between gui updates etc. The reason to do it like this is that it
gives headaches trying to get things right if gobject or gtk signals
can fire in a separate thread. Also the sqlite index is not thread
save either.

The AsyncLock class can be used for locking a resource. The lock is
always acquired in the main thread before the async operation starts and
is released when the operation finishes. THis way race conditions can
be avoided in case you queue the same operation several times. Using
the lock enforces that the async actions are still run in the same
order as they are spawned from the main thread.

So typical usage in zim is to spawn worker threads from the main thread
but only one at a time for a specific resource. E.g. file system
actions can be done async, but there is a global lock that ensures we
do only one file system action at a time. This is a simple way of
dealing with the complexity of dealing with asynchronous operation
on shared resources. (This example is implemented in L{zim.fs}, see
the various "async_*" methods.)
'''

import sys
import logging

import gobject


logger = logging.getLogger('zim.async')


try:
	import threading
except ImportError:
	logger.warn('No threading support - this may reduce performance')
	import dummy_threading as threading


def call_in_main_thread(cb_func, args=()):
	'''This function will cause a callback to be called in the main thread

	@param cb_func: the function to call in the main thread
	@keyword args: optional arguments to pass the function
	'''

	# Originally I thought this would require a queue that is
	# filled from the worker queues and emptied from the main loop,
	# however idle_add() does this for us

	def callback():
		cb_func(*args)
		return False # cause the timeout to be destroyed

	gobject.idle_add(callback)


class AsyncOperation(threading.Thread):
	'''Wrapper class for a C{threading.Thread} object'''

	def __init__(self, function, args=(), kwargs={}, lock=None, callback=None, data=None):
		'''Constructor for a new thread

		@param function: the main function for this thread
		@keyword args: optional arguments for the function
		@keyword kwargs: optional keyword parameters for the function
		@keyword lock: an L{AsyncLock}

		If a lock object is provided L{start()} will block until the lock
		is available and we will release the lock once the operation is
		done.

		@keyword callback: function to call in the main thread once the
		main function in this thread is finished
		@keyword data: optional arguments for the callback function

		If you add a callback function it will be called in the main
		thread after the function is finished. This is typically used
		for error handling, e.g. you want to throw an error dialog from
		the main thread when the operation failed.
		The callback is called like::

			callback(value, error, exc_info, data)

		With the arguments:
		  - C{value}: is the return value of the function
		  - C{error}: is an Exception object or None
		  - C{exc_info}: is a 3 tuple of sys.exc_info() or None
		  - C{data}: is the data given to the constructor
		'''
		self.result = None

		def wrapper(function, args, kwargs, lock, callback, data):
			try:
				self.result = function(*args, **kwargs)
			except Exception, error:
				if lock:
					lock.release()

				if callback:
					exc_info = sys.exc_info()
					call_in_main_thread(
						callback, (self.result, error, exc_info, data) )
				else:
					logger.exception('Error in AsyncOperation')
			else:
				if lock:
					lock.release()

				if callback:
					call_in_main_thread(
						callback, (self.result, None, None, data) )

		myargs = (function, args, kwargs, lock, callback, data)
		threading.Thread.__init__(self, target=wrapper, args=myargs)
		self.lock = lock

	def start(self):
		'''Start the operation

		If a lock is used this will block until the lock is acquired
		and then return one the operation is running
		'''
		if self.lock:
			self.lock.acquire()
		threading.Thread.start(self)

	def wait(self):
		'''Wait for this thread to exit

		@returns: the result of the function handled by this thread
		'''
		self.join()
		return self.result


class AsyncLock(object):
	'''This class wraps a C{threading.Lock} object.

	This class also functions as a context manager, so you can use::

		lock = AsyncLock()

		with lock:
			....
	'''

	# Not sure why we can not subclass threading.Lock, but it throws
	# an error, so we wrap it.

	__slots__ = ('_lock',)

	def __init__(self):
		self._lock = threading.Lock()

	def __enter__(self):
		self._lock.acquire()

	def __exit__(self, *a):
		self._lock.release()
		return False # propagate any errors

	def acquire(self, blocking=True):
		self._lock.acquire(blocking)

	def release(self):
		self._lock.release()


