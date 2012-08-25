# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import weakref
import logging
import gobject


logger = logging.getLogger('zim')


# Constants for signal order
SIGNAL_NORMAL = 1
SIGNAL_AFTER = 2


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

			self.connectto(button, clicked=self.on_button_clicked)

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

			self.connect_group(self.ui (
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
				gobject.GObject.disconnect(obj, i)
				# HACK since e.g. plugin class overrules
				# 'disconnect()' ...
		del self._connected_signals[key]


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
