# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

# The Error class needed to be put in a separate file to avoid recusive
# imports, signal contexts were added later.


class Error(Exception):
	'''Base class for all errors in zim.

	Subclasses should define two attributes. The first is 'msg', which is
	the short description of the error. Typically this gives the specific
	input / page / ... which caused the error. In there should be an attribute
	'description' (either as class attribute or object attribute) with a verbose
	description. This description can be less specific but should explain
	the error in a user friendly way. The default behavior is to take 'msg' as
	the single argument for the constructor. So a minimal subclass only needs
	to define a class attribute 'description'.

	For a typical error dialog in the Gtk interface the short string from 'msg'
	will be shown as the title in bold letters while the longer 'description'
	is shown below it in normal letters. As a guideline error classes that are
	used in the gui or that can be e.g. be raised on invalid input from the
	user should be translated.
	'''

	description = 'Unspecified error...'

	def __init__(self, msg):
		self.msg = msg

	def __str__(self):
		msg = self.__unicode__()
		return msg.encode('utf-8')

	def __unicode__(self):
		msg = u'' + self.msg.strip()
		if self.description:
			msg += '\n\n' + self.description.strip() + '\n'
		return msg

	def __repr__(self):
		return '<%s>' % self.__class__.__name__


_signal_exception_context_stack = []
silence_signal_exception_context = False # used while testing


class SignalExceptionContext(object):
	'''Context for re-raising exceptions outside a signal handler.

	See SignalRaiseExceptionContext for example usage.
	'''

	def __init__(self, object, signal):
		'''Constructor, needs the emitting object and a signal name.'''
		self.object = object
		self.signal = signal
		self.exc_info = None

	def __enter__(self):
		_signal_exception_context_stack.append(self)
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		assert _signal_exception_context_stack[-1] == self
		_signal_exception_context_stack.pop()

		if exc_type:
			# error emitting - not due to our context
			return False # do not surpress raising this exception
		elif self.exc_info:
			# re-raise the error
			#~ print '>>>', self.exc_info
			raise self.exc_info[1]
		else:
			pass


class SignalRaiseExceptionContext(object):
	'''Context for raising signals inside signal handlers

	This context can be used inside a signal handler to wrap code that
	may raise exceptions. Any SignalExceptionContext wrapping the
	signal emission can than re-raise these exceptions.

	This context will also prevent any other handlers for the same
	signal to be called.

	Typical usage:

		from __future__ import with_statement

		def store_page(self, page):
			# Emits the 'store-page' signal
			with SignalExceptionContext(self, 'store-page'):
				self.emit('store-page', page)

		def do_store_page(self, page):
			# Handler for the 'store-page' signal
			with SignalRaiseExceptionContext(self, 'store-page'):
				....

	NOTE: Do not forget to import "with_statement" from __future__,
	otherwise it will fail for python 2.5.
	'''

	# We now only filter by signal name, in theory

	def __init__(self, object, signal):
		'''Constructor, needs the emitting object and a signal name.'''
		self.object = object
		self.signal = signal

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		if exc_type and _signal_exception_context_stack:
			frame = _signal_exception_context_stack[-1]
			if frame.object == self.object \
			and frame.signal == self.signal:
				frame.exc_info = (exc_type, exc_value, traceback)
				self.object.stop_emission(self.signal)

		return silence_signal_exception_context
			# Do not block error output if False

