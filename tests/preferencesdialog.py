# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

from zim.plugins import PluginManager
from zim.config import VirtualConfigManager

from zim.gui.preferencesdialog import PreferencesDialog, PluginConfigureDialog


def MyWindow(config):
	import gtk
	window = gtk.Window()
	window.__pluginmanager__ = PluginManager(config)
	return window


class TestPreferencesDialog(tests.TestCase):

	def testSetSimpleValue(self):
		config = VirtualConfigManager()
		preferences = config.get_config_dict('<profile>/preferences.conf')

		dialog = PreferencesDialog(MyWindow(config), config)
		self.assertEquals(dialog.forms['Interface']['toggle_on_ctrlspace'], False)
		dialog.assert_response_ok()
		self.assertEquals(preferences['GtkInterface']['toggle_on_ctrlspace'], False)

		dialog = PreferencesDialog(MyWindow(config), config)
		dialog.forms['Interface']['toggle_on_ctrlspace'] = True
		dialog.assert_response_ok()
		self.assertEquals(preferences['GtkInterface']['toggle_on_ctrlspace'], True)

	def testChangeFont(self):
		config = VirtualConfigManager()
		preferences = config.get_config_dict('<profile>/preferences.conf')

		text_style = config.get_config_dict('<profile>/style.conf')
		text_style['TextView'].setdefault('font', None, basestring)
		text_style['TextView']['font'] = 'Sans 12'

		dialog = PreferencesDialog(MyWindow(config), config)
		self.assertEquals(dialog.forms['Interface']['use_custom_font'], True)
		dialog.assert_response_ok()
		self.assertEqual(text_style['TextView']['font'], 'Sans 12')
		self.assertFalse(any(['use_custom_font' in d for d in preferences.values()]))

		text_style['TextView']['font'] = 'Sans 12'
		dialog = PreferencesDialog(MyWindow(config), config)
		self.assertEquals(dialog.forms['Interface']['use_custom_font'], True)
		dialog.forms['Interface']['use_custom_font'] = False
		dialog.assert_response_ok()
		self.assertEqual(text_style['TextView']['font'], None)
		self.assertFalse(any(['use_custom_font' in d for d in preferences.values()]))

	def testConfigurePlugin(self):
		config = VirtualConfigManager()

		from zim.plugins.calendar import CalendarPlugin
		plugin = CalendarPlugin()

		window = MyWindow(config)
		pref_dialog = PreferencesDialog(window, config)
		dialog = PluginConfigureDialog(pref_dialog, plugin)
		dialog.assert_response_ok()

		## Try plugins + cancel
		pref_dialog = PreferencesDialog(MyWindow(config), config)
		treeview = pref_dialog.plugins_tab.treeview
		for name in window.__pluginmanager__.list_installed_plugins():
			pref_dialog.plugins_tab.select_plugin(name)
			model, iter = treeview.get_selection().get_selected()
			self.assertEqual(model[iter][0], name)

			path = model.get_path(iter)
			wasactive = model[iter][1]
			model.do_toggle_path(path)
			if wasactive:
				self.assertEqual(model[iter][1], False)
			else:
				self.assertEqual(model[iter][1], model[iter][2]) # active matched activatable

		pref_dialog.do_response_cancel()
