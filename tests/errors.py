# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement

import tests

import logging

import zim.errors

from zim.gui.widgets import ErrorDialog


text = '''\
Error 6

Some description
here
'''

class TestErrors(tests.TestCase):

	def runTest(self):
		'''Check base class for errors'''
		self.assertEqual(str(StubError(6)), text)
		self.assertEqual(unicode(StubError(6)), text)


class StubError(zim.errors.Error):
	description = '''\
Some description
here
'''

	def __init__(self, i):
		self.msg = 'Error %i' % i


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

		def first_error_dialog(dialog):
			self.assertIsInstance(dialog, ErrorDialog)
			self.assertTrue(dialog.showing_trace)

		def second_error_dialog(dialog):
			self.assertIsInstance(dialog, ErrorDialog)
			self.assertFalse(dialog.showing_trace)


		zim.errors.set_use_gtk(True)
		try:
			self.assertTrue(zim.errors.use_gtk_errordialog)
			with tests.DialogContext(
				first_error_dialog,
				second_error_dialog
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
		try:
			raise AssertionError, 'My AssertionError' # unexpected error/bug
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

		try:
			raise zim.errors.Error('My normal Error') # "expected" error
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
