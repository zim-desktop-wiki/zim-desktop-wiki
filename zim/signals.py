# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import weakref
import logging
import gobject
import os


logger = logging.getLogger('zim')


if os.environ.get('ZIM_TEST_RUNNING'):
	TEST_MODE = True
else:
	TEST_MODE = False


# Constants for signal order
SIGNAL_NORMAL = 1
SIGNAL_AFTER = 2
SIGNAL_OBJECT = 4


class SignalHandler(object):
	'''Wrapper for a signal handler method that allows blocking the
	handler for incoming signals. To be used as function decorator.

	The method will be replaced by a L{BoundSignalHandler} object that
	supports a C{blocked()} method which returns a context manager
	to temporarily block a callback.

	Intended to be used as::

		class Foo():

			@SignalHandler
			def on_changed(self):
				...

			def update(self):
				with self.on_changed.blocked():
					... # do something that results in a "changed" signal

	'''

	def __init__(self, func):
		self._func = func

	def __get__(self, instance, klass):
		if instance is None:
			# class access
			return self
		else:
			# instance acces, return bound version
			name = '_bound_' + self._func.__name__
			if not hasattr(instance, name) \
			or getattr(instance, name) is None:
				bound_obj = BoundSignalHandler(instance, self._func)
				setattr(instance, name, bound_obj)

			return getattr(instance, name)


class BoundSignalHandler(object):

	def __init__(self, instance, func):
		self._instance = instance
		self._func = func
		self._blocked = 0

	def __call__(self, *args, **kwargs):
		if self._blocked == 0:
			return self._func(self._instance, *args, **kwargs)

	def _block(self):
		self._blocked += 1

	def _unblock(self):
		if self._blocked > 0:
			self._blocked -= 1

	def blocked(self):
		'''Returns a context manager that can be used to temporarily
		block a callback.
		'''
		return SignalHandlerBlockContextManager(self)


class SignalHandlerBlockContextManager(object):

	def __init__(self, handler):
		self.handler = handler

	def __enter__(self):
		self.handler._block()

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.handler._unblock()




class ConnectorMixin(object):
	'''Mixin class that has convenience methods for objects that
	want to connect to signals of other objects.
	'''

	# TODO connectto with whole set of signals
	# TODO connect variant that wraps with a handler that catches
	#  unwanted arguments

	def connectto(self, obj, signal, handler=None, userdata=None, order=SIGNAL_NORMAL):
		'''Connect to signals of another object
		E.g.::

			self.connectto(button, 'clicked', self.on_button_clicked)

		@param obj: the object to connect to
		@param signal: the signal name
		@param handler: the callback function, or C{None} to map to
		a method prefixed with "on_".
		@param userdata: optional user data
		@param order: if order is C{NORMAL} then C{GObject.connect()}
		is used, if order is C{AFTER} then C{GObject.connect_after()}
		is used.
		@returns: the handler id
		'''
		if handler is None:
			name = "on_" + signal.replace('-', '_')
			handler = getattr(self, name)
			if handler is None:
				raise NotImplementedError, 'No method "%s"' % name

		if order == SIGNAL_NORMAL:
			if userdata is None:
				i = obj.connect(signal, handler)
			else:
				i = obj.connect(signal, handler, userdata)
		else: # SIGNAL_AFTER
			if userdata is None:
				i = obj.connect_after(signal, handler)
			else:
				i = obj.connect_after(signal, handler, userdata)

		if not hasattr(self, '_connected_signals'):
			self._connected_signals = {}
			# We might want a dict here that is cleaned up
			# when references disappear, but for now this will do

		key = id(obj)
		if not key in self._connected_signals:
			self._connected_signals[key] = (weakref.ref(obj), [])
		self._connected_signals[key][1].append(i)

		return i

	def connectto_all(self, obj, signals, handler=None, userdata=None, order=SIGNAL_NORMAL):
		'''Convenience method to combine multiple calls to
		L{connectto()}.

		@param obj: the object to connect to
		@param signals: a list of signals. Elements can either be signal
		names or tuples where the sub-elements are the parameters
		for L{connectto()}. For example::

			self.connectto_all(self.ui (
				'open-page' # defaults to on_open_page
				('open-notebook', on_open_notebook, None, SIGNAL_AFTER),
			))

		The optional parameters are used as default values when these
		parameters are not specified explicitly per signal.

		@param handler: optional parameter
		@param userdata: optional parameter
		@param order: optional parameter
		'''
		default = (None, handler, userdata, order)
		for signal in signals:
			if isinstance(signal, basestring):
				self.connectto(obj, signal, handler, userdata, order)
			else:
				arg = signal + default[len(signal):]
					# fill in missing positional arguments
				self.connectto(obj, *arg)

	def disconnect_from(self, obj):
		'''Disc all signals that have been connected with
		L{connectto} and friends to a specific object.
		'''
		key = id(obj)
		if hasattr(self, '_connected_signals') \
		and key in self._connected_signals:
			self._disconnect_from(key)

	def disconnect_all(self):
		'''Disconnect all signals that have been connected with
		L{connectto} and friends. Typically called when you want to
		destroy this object.
		'''
		if hasattr(self, '_connected_signals'):
			for key in self._connected_signals.keys():
				try:
					self._disconnect_from(key)
				except:
					logger.exception('Exception in disconnect_all()')

	def _disconnect_from(self, key):
		ref, signals = self._connected_signals[key]
		obj = ref()
		if obj is not None:
			for i in signals:
				obj.disconnect(i)
		del self._connected_signals[key]


def call_default(obj, signal, args):
	name = 'do_' + signal.replace('-', '_')
	if hasattr(obj, name):
		method = getattr(obj, name)
		return method(*args)
	else:
		return None


def call_handlers(obj, signal, handlers, args):
	for handler in handlers:
		const, callback, userdata = handler
		if userdata is not None:
			if const & SIGNAL_OBJECT:
				myargs = (userdata,) + args
			else:
				myargs = args + (userdata,)
		else:
			myargs = args

		try:
			if const & SIGNAL_OBJECT:
				r = callback(*myargs)
			else:
				r = callback(obj, *myargs)
		except:
			logger.exception('Exception in signal handler for %s on %s', signal, obj)
			if TEST_MODE:
				raise
		else:
			yield r


class BlockSignalsContextManager(object):

	def __init__(self, obj, signals):
		self.obj = obj
		self.signals = signals

	def __enter__(self):
		for signal in self.signals:
			self.obj.block_signal(signal)

	def __exit__(self, exc_type, exc_val, exc_tb):
		for signal in self.signals:
			self.obj.unblock_signal(signal)


class SignalEmitter(object):
	'''Replacement for C{GObject} to make objects emit signals.
	API should be backward compatible with API offered by GObject.
	'''

	__signals__ = {} #: signals supported by this class

	# define signals we want to use - (closure type, return type and arg types)
	# E.g. {signal: (gobject.SIGNAL_RUN_LAST, None, (object, object))}

	__hooks__ = ()
	# name of signals that return first result


	def _get_signal(self, name):
		if name in self.__signals__:
			return self.__signals__[name]
		else:
			return None
		# TODO: iterate base classes as well

	def connect(self, signal, handler, userdata=None):
		'''Register a handler for a specific object.

		Note that connecting makes a hard reference to the connected
		object. So connecting an bound method will prevent the
		object the method belongs to to be destroyed untill the
		signal is disconnected.

		@param signal: the signal name
		@param handler: callback to be called upon the signal,
		first object to the callback will be the emitting object,
		other params are signal specific.
		@param userdata: optional data to provide to the callback
		@returns: an id for the registered handler
		'''
		return self._connect(SIGNAL_NORMAL, signal, handler, userdata)

	def connect_after(self, signal, handler, userdata=None):
		'''Like L{connect()} but handler will be called after default handler'''
		return self._connect(SIGNAL_AFTER, signal, handler, userdata)

	def connect_object(self, signal, handler, obj):
		'''Like L{connect()} but handler will be called with C{obj} as main object'''
		return self._connect(SIGNAL_NORMAL | SIGNAL_OBJECT, signal, handler, obj)

	def connect_object_after(self, signal, handler, obj):
		'''Like L{connect()} but handler will be called with C{obj} as main object'''
		return self._connect(SIGNAL_AFTER | SIGNAL_OBJECT, signal, handler, obj)

	def _connect(self, order, signal, callback, userdata):
		#if self._get_signal(signal) is None:
		#	raise ValueError, 'No such signal: %s' % signal
		assert not '_' in signal, 'Signal names use "-"'

		if not hasattr(self, '_signal_handlers'):
			self._signal_handlers = {}

		if not signal in self._signal_handlers:
			self._setup_signal(signal)
			self._signal_handlers[signal] = []

		handler = (order, callback, userdata)
		self._signal_handlers[signal].append(handler)
		handlerid = id(handler) # unique object id since we construct the tuple
		return handlerid

	def disconnect(self, handlerid):
		if not hasattr(self, '_signal_handlers'):
			return

		for signal, handlers in self._signal_handlers.items():
			# unique id, so when we find it, stop searching
			ids = map(id, handlers)
			try:
				i = ids.index(handlerid)
			except ValueError:
				continue
			else:
				handlers.pop(i)
				if not handlers:
					self._signal_handlers.pop(signal)
					self._teardown_signal(signal)
				break

	def _setup_signal(self, signal):
		# Called first time a signal is registered - for subclasses
		pass

	def _teardown_signal(self, signal):
		# Called after last handler is disconnected - for subclasses
		pass

	def emit(self, signal, *args):
		#signal_spec = self._get_signal(signal)
		#if signal_spec is None:
		#	raise ValueError, 'No such signal: %s' % signal
		#else:
		#	pass # TODO check arguments

		return_first = signal in self.__hooks__ # XXX

		if hasattr(self, '_blocked_signals') \
		and self._blocked_signals.get(signal):
			return # ignore emit

		if not hasattr(self, '_signal_handlers') \
		or not signal in self._signal_handlers:
			return call_default(self, signal, args)
		else:
			before = [h for h in self._signal_handlers[signal] if h[0] & SIGNAL_NORMAL]
			for r in call_handlers(self, signal, before, args):
				if return_first and r is not None:
					return r

			r = call_default(self, signal, args)
			if return_first and r is not None:
					return r

			if not signal in self._signal_handlers:
				return None # Yes I have seen a case where default resulted in all handlers disconnected here ...

			after = [h for h in self._signal_handlers[signal] if h[0] & SIGNAL_AFTER]
			for r in call_handlers(self, signal, after, args):
				if return_first and r is not None:
					return r

	def blocked_signals(self, *signals):
		'''Returns a context manager for blocking one or more signals'''
		return BlockSignalsContextManager(self, signals)

	def block_signal(self, signal):
		'''Block signal emition by signal name'''
		assert signal not in self.__hooks__, 'Cannot block a hook'
		#if self._get_signal(signal) is None:
		#	raise ValueError, 'No such signal: %s' % signal

		if not hasattr(self, '_blocked_signals'):
			self._blocked_signals = {}

		self._blocked_signals.setdefault(signal, 0)
		self._blocked_signals[signal] += 1

	def unblock_signal(self, signal):
		'''Unblock signal emition by signal name'''
		#if self._get_signal(signal) is None:
		#	raise ValueError, 'No such signal: %s' % signal

		if hasattr(self, '_blocked_signals') \
		and signal in self._blocked_signals \
		and self._blocked_signals[signal] > 0:
			self._blocked_signals[signal] -= 1


class DelayedCallback(object):
	'''Wrapper for callbacks that need to be delayed after a signal

	This class allows you to add a callback to a signal, but only have
	it called after a certain timeout. If the signal is emitted
	again during this time the callback will be canceled and the
	timeout starts again. (So the callback is not called for each repeat
	of the signal.) This can be used e.g. in case want to update some
	other widget after the user changes a text entry widget, but this
	can be done once the user pauses, while calling the callback for
	every key stroke would make the application non-responsive.

	Objects of this class wrap the actual callback function and can be
	called as a normal function.

	Note that when a repeated callback is canceled, only the arguments
	of the last call are passed on.

	@todo: allow an option to check arguments and pass on all unique
	combinations ?

	@todo: add support for async callbacks, in this case block
	the callback until the async process is finished
	'''

	__slots__ = ('timeout', 'cb_func', 'timer_id')

	def __init__(self, timeout, cb_func):
		'''Constructor

		@param timeout: timeout in milliseconds (e.g. 500)
		@param cb_func: the callback to call
		'''
		self.cb_func = cb_func
		self.timeout = timeout
		self.timer_id = None

	def __call__(self, *arg, **kwarg):
		if self.timer_id:
			gobject.source_remove(self.timer_id)
			self.timer_id = None

		def callback():
			self.timer_id = None
			self.cb_func(*arg, **kwarg)
			return False # destroy timeout

		self.timer_id = gobject.timeout_add(self.timeout, callback)

	def __del__(self):
		if self.timer_id:
			gobject.source_remove(self.timer_id)

	def cancel(self):
		'''Cancel the scheduled callback'''
		self.__del__()



