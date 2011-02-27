# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from tests import TestCase

from zim.objectmanager import *


class TestObjectManager(TestCase):

	def runTest(self):
		'''Test object manager for inline objects'''
		manager = ObjectManager

		self.assertFalse(manager.is_registered('classa'))
		self.assertFalse(manager.is_registered('classb'))
		self.assertFalse(manager.is_registered('foo'))

		manager.register_object('classa', classafactory)
		manager.register_object('classb', ClassB)

		self.assertTrue(manager.is_registered('classa'))
		self.assertTrue(manager.is_registered('classb'))
		self.assertFalse(manager.is_registered('foo'))

		self.assertTrue(isinstance(manager.get_object('classa', {}, ''), ClassA))
		self.assertTrue(isinstance(manager.get_object('classb', {}, ''), ClassB))
		self.assertTrue(isinstance(manager.get_object('foo', {}, ''), FallbackObject))


def classafactory(attrib, text, ui):
	return ClassA(attrib, text, ui)


class ClassA(CustomObjectClass):
	pass


class ClassB(CustomObjectClass):
	pass
