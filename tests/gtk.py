# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Helper classes and functions for testing Gtk interaction'''

import types


class TestDialogContext(object):
	'''Context manager to catch dialogs being opened

	Inteded to be used like this::

		def myCustomTest(dialog):
			self.assertTrue(isinstance(dialog, CustomDialogClass))
			# ...
			dialog.assert_response_ok()

		with DialogContext(
			myCustomTest,
			SomeOtherDialogClass
		):
			gui.show_dialogs()

	In this example the first dialog that is run by C{gui.show_dialogs()}
	is checked by the function C{myCustomTest()} while the second dialog
	just needs to be of class C{SomeOtherDialogClass} and will then
	be closed with C{assert_response_ok()} by the context manager.

	This context only works for dialogs derived from zim's Dialog class
	as it uses a special hook in L{zim.gui.widgets}.
	'''

	def __init__(self, *definitions):
		'''Constructor
		@param definitions: list of either classes or methods
		'''
		self.stack = list(definitions)
		self.old_test_mode = None

	def __enter__(self):
		import zim.gui.widgets
		self.old_test_mode = zim.gui.widgets.TEST_MODE
		self.old_callback = zim.gui.widgets.TEST_MODE_RUN_CB
		zim.gui.widgets.TEST_MODE = True
		zim.gui.widgets.TEST_MODE_RUN_CB = self._callback

	def _callback(self, dialog):
		#~ print '>>>', dialog
		if not self.stack:
			raise AssertionError, 'Unexpected dialog run: %s' % dialog

		handler = self.stack.pop(0)

		if isinstance(handler, (type, types.ClassType)): # is a class
			if not isinstance(dialog, handler):
				raise AssertionError, 'Expected dialog of class %s, but got %s instead' % (handler, dialog.__class__)
			dialog.assert_response_ok()
		else: # assume a function
			handler(dialog)

	def __exit__(self, *error):
		#~ print 'ERROR', error
		import zim.gui.widgets
		zim.gui.widgets.TEST_MODE = self.old_test_mode
		zim.gui.widgets.TEST_MODE_RUN_CB = self.old_callback
		return False # Raise any errors again outside context
