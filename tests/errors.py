# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement

import tests

import logging

import zim.errors

from zim.gui.widgets import ErrorDialog


class StubError(zim.errors.Error):
	description = '''\
Some description
here
'''

	def __init__(self, i):
		self.msg = 'Error %i' % i


class TestErrors(tests.TestCase):

	def runTest(self):
		'''Check base class for errors'''
		wanted = '''\
Error 6

Some description
here
'''
		self.assertEqual(str(StubError(6)), wanted)
		self.assertEqual(unicode(StubError(6)), wanted)
		self.assertEqual(repr(StubError(6)), '<StubError: Error 6>')


class CatchAllLogging(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self)
		self.records = []

	def filter(self, record):
		self.records.append(record)
		return False


class TestExceptionHandler(tests.TestCase):

	def setUp(self):
		logger = logging.getLogger('zim')
		self.oldlevel = logger.getEffectiveLevel()
		logger.setLevel(logging.DEBUG)

	def tearDown(self):
		logger = logging.getLogger('zim')
		logger.setLevel(self.oldlevel)

	def testExceptionHandlerWithGtk(self):

		def error_dialog_with_trace(dialog):
			self.assertIsInstance(dialog, ErrorDialog)
			self.assertTrue(dialog.showing_trace)

		def error_dialog_without_trace(dialog):
			self.assertIsInstance(dialog, ErrorDialog)
			self.assertFalse(dialog.showing_trace)


		zim.errors.set_use_gtk(True)
		try:
			self.assertTrue(zim.errors.use_gtk_errordialog)
			with tests.DialogContext(
				error_dialog_with_trace,
				error_dialog_with_trace,
				error_dialog_without_trace,
				error_dialog_without_trace,
			):
				with tests.LoggingFilter(
					logger='zim.gui',
					message='Running ErrorDialog'
				):
					self.testExceptionHandler()
		except:
			zim.errors.set_use_gtk(False)
			raise
		else:
			zim.errors.set_use_gtk(False)
			self.assertFalse(zim.errors.use_gtk_errordialog)

	def testExceptionHandler(self):

		## Handle unexpected error or bug
		try:
			raise AssertionError, 'My AssertionError'
		except:
			myfilter = CatchAllLogging()
			with myfilter:
				zim.errors.exception_handler('Test Error')
			records = myfilter.records

			# Should log one error message with traceback
			self.assertEqual(len(records), 1)
			self.assertEqual(records[0].getMessage(), 'Test Error')
			self.assertEqual(records[0].levelno, logging.ERROR)
			self.assertIsNotNone(records[0].exc_info)
		else:
			assert False


		## Show caught bug
		try:
			raise AssertionError, 'My AssertionError'
		except Exception, error:
			myfilter = CatchAllLogging()
			with myfilter:
				zim.errors.show_error(error)
			records = myfilter.records

			# Should log one error message with traceback
			self.assertEqual(len(records), 1)
			self.assertEqual(records[0].getMessage(), 'Looks like you found a bug')
			self.assertEqual(records[0].levelno, logging.ERROR)
			self.assertIsNotNone(records[0].exc_info)
		else:
			assert False


		## Handle normal application error
		try:
			raise zim.errors.Error('My normal Error')
		except:
			myfilter = CatchAllLogging()
			with myfilter:
				zim.errors.exception_handler('Test Error')
			records = myfilter.records

			# Should log a debug message with traceback
			# and user error message without traceback
			self.assertEqual(len(records), 2)

			self.assertEqual(records[0].getMessage(), 'Test Error')
			self.assertEqual(records[0].levelno, logging.DEBUG)
			self.assertIsNotNone(records[0].exc_info)

			self.assertEqual(records[1].getMessage(), 'My normal Error')
			self.assertEqual(records[1].levelno, logging.ERROR)
			self.assertIsNone(records[1].exc_info)
		else:
			assert False


		## Handle normal IOError
		try:
			open('/some/non/existing/file/').read()
		except:
			myfilter = CatchAllLogging()
			with myfilter:
				zim.errors.exception_handler('Test IOError')
			records = myfilter.records

			# Should log a debug message with traceback
			# and user error message without traceback
			self.assertEqual(len(records), 2)

			self.assertEqual(records[0].getMessage(), 'Test IOError')
			self.assertEqual(records[0].levelno, logging.DEBUG)
			self.assertIsNotNone(records[0].exc_info)

			self.assertIn('/some/non/existing/file/', records[1].getMessage())
				# do not test exact message - could be localized
			self.assertEqual(records[1].levelno, logging.ERROR)
			self.assertIsNone(records[1].exc_info)
		else:
			assert False
