# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.async module.'''

from __future__ import with_statement


import tests
from tests.gtk_tests import process_events

import time

from zim.async import *
from zim.fs import File


class TestAsync(tests.TestCase):

	def testAPI(self):
		'''Test API for async operations'''

		def somefunction(text):
			return "foo " + text

		lock = AsyncLock()

		with lock:
			operation = AsyncOperation(somefunction, ('bar',))
			operation.start()
			value = operation.wait()

			self.assertEqual(value, 'foo bar')

	def testFS(self):
		'''Test async FS operations'''

		self.path = tests.create_tmp_dir('async_testFS')+'/file.txt'

		file = File(self.path)

		op1 = file.write_async('foo bar 1\n')
		op2 = file.write_async('foo bar 2\n')

		op1.wait()
		op2.wait()

		self.assertEqual(file.read(), 'foo bar 2\n')


class Counter(object):

	def __init__(self):
		self.i = 0

	def count(self):
		self.i += 1


class TestDelayedCallback(tests.TestCase):

	slowTest = True

	def runTest(self):
		counter = Counter()

		callback = DelayedCallback(500, lambda o: counter.count())
		for i in range(3):
			callback('foo')

		for i in range(10):
			time.sleep(1)
			process_events()
			if callback.timer_id is None:
				break

		self.assertEqual(counter.i, 1)
