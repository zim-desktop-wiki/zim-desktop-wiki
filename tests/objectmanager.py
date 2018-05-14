
# Copyright 2011-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.objectmanager import ObjectManager
from zim.plugins import InsertedObjectType


class TestObjectManager(tests.TestCase):

	def runTest(self):
		'''Test object manager for inline objects'''
		manager = ObjectManager
		obj = MyInsertedObjectType(plugin=None)

		manager.register_object(obj)
		self.assertEqual(manager.get_object('myobject'), obj)

		with self.assertRaises(AssertionError):
			manager.register_object(obj)

		manager.unregister_object(obj)

		with self.assertRaises(KeyError):
			manager.get_object('myobject')

		from zim.plugins.sourceview import SourceViewPlugin
		activatable = SourceViewPlugin.check_dependencies_ok()
		self.assertEqual(
			manager.find_plugin('code'),
			('sourceview', 'Source View', activatable, SourceViewPlugin)
		)


class MyInsertedObjectType(InsertedObjectType):

	name = 'myobject'
	label = 'MyObject'
