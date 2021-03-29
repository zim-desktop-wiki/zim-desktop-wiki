
# Copyright 2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.plugins import find_extension, PluginManager
from zim.plugins.toolbar import *

from zim.gui.customtools import CustomToolManager

from tests.mainwindow import setUpMainWindow


class TestToolBarPlugin(tests.TestCase):

	def setUp(self):
		self.plugin = PluginManager.load_plugin('toolbar')
		self.window = setUpMainWindow(self.setUpNotebook())
		self.extension = find_extension(self.window.pageview, ToolBarMainWindowExtension)

	def testExtendsMainwindow(self):
		self.assertEqual(self.extension.toolbar.get_toplevel(), self.window)
		self.assertGreater(len(self.extension.toolbar.get_children()), 0)

	def testShowsCustomTools(self):
		n_children = len(self.extension.toolbar.get_children())
		tool = {'Name': 'Test', 'X-Zim-ExecTool': 'test', 'X-Zim-ShowInToolBar': True}
		CustomToolManager().create(**tool)
		self.assertEqual(len(self.extension.toolbar.get_children()), n_children + 2) # tool + separator

	def testDetectsNewExtensions(self):
		n_children = len(self.extension.toolbar.get_children())
		PluginManager.load_plugin('arithmetic')
		self.assertEqual(len(self.extension.toolbar.get_children()), n_children + 1)

	def testClassicMode(self):
		n_children = len(self.extension.toolbar.get_children())
		self.assertTrue(self.window.pageview.edit_bar.get_property('visible'))
		self.plugin.preferences['classic'] = True
		self.assertGreater(len(self.extension.toolbar.get_children()), n_children + 5)
		self.assertFalse(self.window.pageview.edit_bar.get_property('visible'))
		self.plugin.preferences['classic'] = False
		self.assertEqual(len(self.extension.toolbar.get_children()), n_children)
		self.assertTrue(self.window.pageview.edit_bar.get_property('visible'))
