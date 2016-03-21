# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement

import tests

import time

from zim.signals import *


# TODO test Connector


class TestEmitter(tests.TestCase):

	def testSignal(self):
		emitter = Emitter()
		self.assertIsNone(emitter.state)

		emitter.emit('bar', 'test1')
		self.assertEqual(emitter.state, 'DO bar test1')

		data = []
		def check(o, a):
			self.assertIs(o, emitter)
			data.append(a)

		i = emitter.connect('bar', check)
		emitter.emit('bar', 'test2')
		self.assertEqual(emitter.state, 'DO bar test2')
		self.assertEqual(data, ['test2'])
		emitter.disconnect(i)

		emitter.emit('bar', 'test3')
		self.assertEqual(emitter.state, 'DO bar test3')
		self.assertEqual(data, ['test2']) # check stopped listening after disconnect


	def testHook(self):
		emitter = Emitter()
		self.assertIsNone(emitter.emit('foo', 'x'))

		emitter.connect('foo', lambda o, a: a * 3)
		emitter.connect('foo', lambda o, a: a * 5)
		self.assertEqual(emitter.emit('foo', 'x'), 'xxx')
			# pick first result

	def testSignalSetup(self):
		emitter = FancyEmitter()
		self.assertIsNone(emitter.state)

		emitter.connect('foo', lambda o,a: None)
		self.assertEqual(emitter.state, 'SETUP foo')


	# TODO
	# Test inheritance
	# Test validation signal signature
	# Test before / after sequence


class Emitter(SignalEmitter):

	__signals__ = {
		'foo': (),
		'bar': (),
	}

	__hooks__ = ('foo')

	def __init__(self):
		self.state = None

	def do_bar(self, arg):
		self.state = 'DO bar %s' % arg


class FancyEmitter(SignalEmitter):

	__signals__ = {
		'foo': (),
	}

	def __init__(self):
		self.state = None

	def _setup_signal(self, signal):
		self.state = 'SETUP %s' % signal

	def _teardown_signal(self, signal):
		self.state = 'TEARDOWN %s' % signal



class TestSignalHandler(tests.TestCase):

	def runTest(self):
		obj = ClassWithHandler()
		self.assertEqual(obj.count, 0)
		self.assertEqual(id(obj.add_one), id(obj.add_one)) # unique instance object

		obj.add_one()
		self.assertEqual(obj.count, 1)

		with obj.add_one.blocked():
			obj.add_one()
			obj.add_one()
			obj.add_one()
		self.assertEqual(obj.count, 1)

		obj.add_one()
		obj.add_one()
		obj.add_one()
		self.assertEqual(obj.count, 4)


class ClassWithHandler(object):

	def __init__(self):
		self.count = 0

	@SignalHandler
	def add_one(self):
		self.count += 1




@tests.slowTest
class TestDelayedCallback(tests.TestCase):

	def runTest(self):
		counter = tests.Counter()

		callback = DelayedCallback(500, lambda o: counter())
		for i in range(3):
			callback('foo')

		for i in range(10):
			time.sleep(1)
			tests.gtk_process_events()
			if callback.timer_id is None:
				break

		self.assertEqual(counter.count, 1)
