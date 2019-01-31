
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from zim.plugins import PluginManager
from zim.config import ConfigManager

from zim.gui.preferencesdialog import PreferencesDialog, PluginConfigureDialog


def MyWindow():
	from gi.repository import Gtk
	window = Gtk.Window()
	window.__pluginmanager__ = PluginManager()
	return window


class TestPreferencesDialog(tests.TestCase):

	def setUp(self):
		import zim.config.manager
		zim.config.manager.makeConfigManagerVirtual()

	def testSetSimpleValue(self):
		preferences = ConfigManager.get_config_dict('preferences.conf')
		window = MyWindow()

		dialog = PreferencesDialog(window)
		self.assertEqual(dialog.forms['Interface']['toggle_on_ctrlspace'], False)
		dialog.assert_response_ok()
		self.assertEqual(preferences['GtkInterface']['toggle_on_ctrlspace'], False)

		dialog = PreferencesDialog(window)
		dialog.forms['Interface']['toggle_on_ctrlspace'] = True
		dialog.assert_response_ok()
		self.assertEqual(preferences['GtkInterface']['toggle_on_ctrlspace'], True)

	def testChangeFont(self):
		preferences = ConfigManager.get_config_dict('preferences.conf')
		window = MyWindow()

		text_style = ConfigManager.get_config_dict('style.conf')
		text_style['TextView'].setdefault('font', None, str)
		text_style['TextView']['font'] = 'Sans 12'

		dialog = PreferencesDialog(window)
		self.assertEqual(dialog.forms['Interface']['use_custom_font'], True)
		dialog.assert_response_ok()
		self.assertEqual(text_style['TextView']['font'], 'Sans 12')
		self.assertFalse(any(['use_custom_font' in d for d in list(preferences.values())]))

		text_style['TextView']['font'] = 'Sans 12'
		dialog = PreferencesDialog(window)
		self.assertEqual(dialog.forms['Interface']['use_custom_font'], True)
		dialog.forms['Interface']['use_custom_font'] = False
		dialog.assert_response_ok()
		self.assertEqual(text_style['TextView']['font'], None)
		self.assertFalse(any(['use_custom_font' in d for d in list(preferences.values())]))

	def testSelectPlugins(self):
		window = MyWindow()

		pref_dialog = PreferencesDialog(window)
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

	def testConfigurePlugin(self):
		from zim.plugins.journal import JournalPlugin
		plugin = JournalPlugin()

		window = MyWindow()
		pref_dialog = PreferencesDialog(window)
		dialog = PluginConfigureDialog(pref_dialog, plugin)
		dialog.assert_response_ok()
