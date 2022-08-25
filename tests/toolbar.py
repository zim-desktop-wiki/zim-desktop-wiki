
# Copyright 2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.plugins import find_extension, PluginManager
from zim.plugins.toolbar import *

from zim.gui.customtools import CustomToolManager
from zim.config import ConfigManager

from tests.mainwindow import setUpMainWindow

from gi.repository import Gtk


class TestToolbarWithHeaderbar(tests.TestCase):

	def runTest(self):
		preferences = ConfigManager.preferences['GtkInterface']
		preferences.input(show_headerbar=True)
		window = setUpMainWindow(self.setUpNotebook())
		toolbar = window._toolbar
		self.assertFalse(toolbar.get_visible())


class TestToolbarWithoutHeaderbar(tests.TestCase):

	def runTest(self):
		preferences = ConfigManager.preferences['GtkInterface']
		preferences.input(show_headerbar=False)
		window = setUpMainWindow(self.setUpNotebook())
		toolbar = window._toolbar
		self.assertTrue(toolbar.get_visible())


class TestToolBarBase(tests.TestCase):

	# This test tests features that are implemented in the plugin but in the
	# mainwindow base

	def setUp(self):
		self.window = setUpMainWindow(self.setUpNotebook())
		self.window.setup_toolbar(show=True)

	def get_toolbar(self):
		return self.window._toolbar

	def testShowsCustomTools(self):
		toolbar = self.get_toolbar()
		n_children = len(toolbar.get_children())
		tool = {'Name': 'Test', 'X-Zim-ExecTool': 'test', 'X-Zim-ShowInToolBar': True}
		CustomToolManager().create(**tool)
		self.assertEqual(len(toolbar.get_children()), n_children + 2) # tool + separator

	def testDetectsNewExtensions(self):
		toolbar = self.get_toolbar()
		n_children = len(toolbar.get_children())
		PluginManager.load_plugin('arithmetic')
		self.assertEqual(len(toolbar.get_children()), n_children + 1)


class TestToolBarPlugin(tests.TestCase):

	# This test tests the toolbar customization by the plugin

	def setUp(self):
		self.plugin = PluginManager.load_plugin('toolbar')
		self.window = setUpMainWindow(self.setUpNotebook())
		self.extension = find_extension(self.window.pageview, ToolBarMainWindowExtension)

	def get_toolbar(self):
		return self.window._toolbar

	def testShowHide(self):
		toolbar = self.get_toolbar()
		self.assertTrue(toolbar.get_visible())
		self.plugin.preferences['show_toolbar'] = False
		self.assertFalse(toolbar.get_visible())
		self.plugin.preferences['show_toolbar'] = True
		self.assertTrue(toolbar.get_visible())

	def testPositionAndStyle(self):
		from zim.gui.widgets import RIGHT

		toolbar = self.get_toolbar()
		self.assertEqual(toolbar.get_style(), Gtk.ToolbarStyle.ICONS)
		self.assertEqual(toolbar.get_icon_size(), Gtk.IconSize.SMALL_TOOLBAR)
		# TODO: verify bar position

		self.plugin.preferences.update(
			position=RIGHT,
			style='BOTH',
			size='LARGE_TOOLBAR',
		)

		toolbar = self.get_toolbar()
		self.assertEqual(toolbar.get_style(), Gtk.ToolbarStyle.BOTH)
		self.assertEqual(toolbar.get_icon_size(), Gtk.IconSize.LARGE_TOOLBAR)
		# TODO: verify bar position

	def testIncludeFormatting(self):
		toolbar = self.get_toolbar()
		self.plugin.preferences['include_formatting'] = False
		n_children = len(toolbar.get_children())
		self.assertTrue(self.window.pageview.edit_bar.get_property('visible'))
		self.plugin.preferences['include_formatting'] = True
		self.assertGreater(len(toolbar.get_children()), n_children + 5)
		self.assertFalse(self.window.pageview.edit_bar.get_property('visible'))
		self.plugin.preferences['include_formatting'] = False
		self.assertEqual(len(toolbar.get_children()), n_children)
		self.assertTrue(self.window.pageview.edit_bar.get_property('visible'))
