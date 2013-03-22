# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement

import tests

from zim.signals import *


class TestEmitter(tests.TestCase):

	def runTest(self):

		# Test hook
		emitter = Emitter()
		self.assertIsNone(emitter.emit('foo', 'x'))

		emitter.connect('foo', lambda o, a: a * 3)
		emitter.connect('foo', lambda o, a: a * 5)
		self.assertEqual(emitter.emit('foo', 'x'), 'xxx')
			# pick first result


# TODO test Connector, DelayedCallback

class Emitter(SignalEmitter):

	__hooks__ = ('foo')
