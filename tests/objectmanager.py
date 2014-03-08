# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.objectmanager import *


class TestObjectManager(tests.TestCase):

	def runTest(self):
		'''Test object manager for inline objects'''
		manager = ObjectManager

		# registering
		self.assertFalse(manager.is_registered('classa'))
		self.assertFalse(manager.is_registered('classb'))
		self.assertFalse(manager.is_registered('foo'))

		manager.register_object('classa', classafactory)
		manager.register_object('classb', ClassB)

		self.assertTrue(manager.is_registered('classa'))
		self.assertTrue(manager.is_registered('classb'))
		self.assertFalse(manager.is_registered('foo'))

		# get objects
		self.assertEqual(list(manager.get_active_objects('classa')), [])
		self.assertEqual(list(manager.get_active_objects('classb')), [])

		obj = manager.get_object('classa', {}, '')
		self.assertTrue(isinstance(obj, ClassA))

		self.assertEqual(list(manager.get_active_objects('classa')), [obj])
		self.assertEqual(list(manager.get_active_objects('classb')), [])

		self.assertTrue(isinstance(manager.get_object('classb', {}, ''), ClassB))
		self.assertTrue(isinstance(manager.get_object('foo', {}, ''), FallbackObject))

		# unregister
		self.assertTrue(manager.is_registered('classa'))
		self.assertTrue(manager.unregister_object('classa'))
		self.assertFalse(manager.is_registered('classa'))
		self.assertFalse(manager.unregister_object('classa'))

		# find plugin
		from zim.plugins.sourceview import SourceViewPlugin
		self.assertEqual(
			manager.find_plugin('code'),
			('sourceview', 'Source View', True, SourceViewPlugin)
		)


def classafactory(attrib, text, ui):
	return ClassA(attrib, text, ui)


class ClassA(CustomObjectClass):
	pass


class ClassB(CustomObjectClass):
	pass


class TestFallbackObject(tests.TestCase):

	def runTest(self):
		attrib = {'lang': 'text/html'}
		text = '''<b>test 123</b>\n'''
		obj = FallbackObject(attrib, text)

		self.assertEqual(obj.get_data(), text)
