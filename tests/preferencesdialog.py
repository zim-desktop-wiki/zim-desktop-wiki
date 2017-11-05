# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

from zim.plugins import PluginManager
from zim.config import VirtualConfigManager

from zim.gui.preferencesdialog import PreferencesDialog, PluginConfigureDialog


class TestPreferencesDialog(tests.TestCase):

	def testSetSimpleValue(self):
		config = VirtualConfigManager()
		plugins = PluginManager(config=config)
		preferences = config.get_config_dict('<profile>/preferences.conf')

		dialog = PreferencesDialog(None, config, plugins)
		self.assertEquals(dialog.forms['Interface']['toggle_on_ctrlspace'], False)
		dialog.assert_response_ok()
		self.assertEquals(preferences['GtkInterface']['toggle_on_ctrlspace'], False)

		dialog = PreferencesDialog(None, config, plugins)
		dialog.forms['Interface']['toggle_on_ctrlspace'] = True
		dialog.assert_response_ok()
		self.assertEquals(preferences['GtkInterface']['toggle_on_ctrlspace'], True)

	def testChangeFont(self):
		config = VirtualConfigManager()
		plugins = PluginManager(config=config)
		preferences = config.get_config_dict('<profile>/preferences.conf')

		text_style = config.get_config_dict('<profile>/style.conf')
		text_style['TextView'].setdefault('font', None, basestring)
		text_style['TextView']['font'] = 'Sans 12'

		dialog = PreferencesDialog(None, config, plugins)
		self.assertEquals(dialog.forms['Interface']['use_custom_font'], True)
		dialog.assert_response_ok()
		self.assertEqual(text_style['TextView']['font'], 'Sans 12')
		self.assertFalse(any(['use_custom_font' in d for d in preferences.values()]))

		text_style['TextView']['font'] = 'Sans 12'
		dialog = PreferencesDialog(None, config, plugins)
		self.assertEquals(dialog.forms['Interface']['use_custom_font'], True)
		dialog.forms['Interface']['use_custom_font'] = False
		dialog.assert_response_ok()
		self.assertEqual(text_style['TextView']['font'], None)
		self.assertFalse(any(['use_custom_font' in d for d in preferences.values()]))

	def testConfigurePlugin(self):
		config = VirtualConfigManager()
		plugins = PluginManager(config=config)

		from zim.plugins.calendar import CalendarPlugin
		plugin = CalendarPlugin()

		pref_dialog = PreferencesDialog(None, config, plugins)
		dialog = PluginConfigureDialog(pref_dialog, plugin)
		dialog.assert_response_ok()

		## Try plugins + cancel
		pref_dialog = PreferencesDialog(None, config, plugins)
		treeview = pref_dialog.plugins_tab.treeview
		for name in plugins.list_installed_plugins():
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
