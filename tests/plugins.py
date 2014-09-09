# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import os

from zim.plugins import *
from zim.fs import File

from zim.gui.propertiesdialog import PropertiesDialog
from tests.gui import setupGtkInterface


assert len(zim.plugins.__path__) > 1 # test __path__ magic
zim.plugins.__path__ = [os.path.abspath('./zim/plugins')] # set back default search path


class TestPluginClasses(tests.TestCase):
	'''Test case to check coding and documentation of plugin classes'''

	def runTest(self):
		plugins = PluginManager.list_installed_plugins()
		self.assertTrue(len(plugins) > 10)
		self.assertTrue('spell' in plugins)
		self.assertTrue('linkmap' in plugins)

		pluginindex = File('data/manual/Plugins.txt').read()

		seen = {
			'name': set(),
			'description': set(),
			'help': set(),
		}
		for name in plugins:
			#~ print '>>', name
			klass = PluginManager.get_plugin_class(name)

			# test plugin info
			for key in ('name', 'description', 'author'):
				self.assertTrue(
					klass.plugin_info.get(key),
					'Plugin %s misses info field \'%s\'' % (name, key)
				)

			for key in ('name', 'description', 'help'):
				self.assertIn(key, klass.plugin_info, 'Plugin %s missing "%s"' % (name, key))
				value = klass.plugin_info[key]
				self.assertFalse(
					value in seen[key],
					'Value for \'%s\' in %s seen before - copy-paste error ?' % (key, name)
				)
				seen[key].add(value)

			# test manual page present and at least documents preferences
			page = klass.plugin_info['help']
			self.assertTrue(page.startswith('Plugins:'), 'Help page for %s not valid' % name)

			rellink = "+%s" % page[8:]
			self.assertIn(rellink, pluginindex, 'Missing links "%s" in manual/Plugins.txt' % rellink)

			file = File('data/manual/' + page.replace(':', '/').replace(' ', '_') + '.txt')
			self.assertTrue(file.exists(), 'Missing file: %s' % file)

			manual = file.read()
			for pref in klass.plugin_preferences:
				label = pref[2]
				if '\n' in label:
					label, x = label.split('\n', 1)
					label = label.rstrip(',')
				self.assertIn(label, manual, 'Preference "%s" for %s plugin not documented in manual page' % (label, name))

			# test dependencies data
			dep = klass.check_dependencies()
			self.assertTrue(isinstance(dep,tuple))
			check, dep = dep
			self.assertTrue(isinstance(check,bool))
			self.assertTrue(isinstance(dep,list))
			for i in range(len(dep)):
				self.assertTrue(isinstance(dep[i],tuple))
				self.assertTrue(isinstance(dep[i][0],str))
				self.assertTrue(isinstance(dep[i][1],bool))
				self.assertTrue(isinstance(dep[i][2],bool))


class TestPluginManager(tests.TestCase):
	'''Test case for TestManager infrastructure'''

	def testLoadAndRemovePlugin(self):
		manager = PluginManager()
		self.assertEqual(len(manager), 0)
		self.assertEqual(list(manager), [])

		obj = manager.load_plugin('calendar')
		self.assertEqual(len(manager), 1)
		self.assertEqual(list(manager), ['calendar'])
		self.assertEqual(manager['calendar'], obj)

		obj1 = manager.load_plugin('calendar') # redundant call
		self.assertEqual(obj1, obj)
		self.assertEqual(len(manager), 1)

		manager.remove_plugin('calendar')
		self.assertEqual(len(manager), 0)
		self.assertEqual(list(manager), [])
		self.assertRaises(KeyError, manager.__getitem__, 'calendar')

		manager.remove_plugin('calendar') # redundant call

	def testLoadNonExistingPlugin(self):
		manager = PluginManager()
		self.assertRaises(ImportError, manager.load_plugin, 'nonexistingplugin')

	def testProfileSwitch(self):
		# Two lists of plugins without dependencies - with some overlap
		list_a = ['attachmentbrowser', 'backlinkpane', 'calendar', 'distractionfree', 'insertsymbol']
		list_b = ['calendar', 'distractionfree', 'insertsymbol', 'printtobrowser', 'quicknote']

		manager = PluginManager()
		for name in list_a:
			manager.load_plugin(name)
		self.assertEqual(manager.general_preferences['plugins'], list_a)

		manager.general_preferences['plugins'] = list_b
		self.assertEqual(sorted(manager._plugins), list_b)


class TestPlugins(tests.TestCase):
	'''Test case to initiate all (loadable) plugins and load some extensions'''

	def runTest(self):
		manager = PluginManager()
		preferences = manager.config.get_config_dict('<profile>/preferences.conf')
		self.assertFalse(preferences.modified)
		for name in PluginManager.list_installed_plugins():
			klass = PluginManager.get_plugin_class(name)
			if klass.check_dependencies_ok():
				manager.load_plugin(name)
				self.assertIn(name, manager)

				self.assertFalse(preferences.modified,
					'Plugin "%s" modified the preferences while loading' % name)

		self.assertTrue(len(manager) > 3)

		for i, name in enumerate(manager):
			manager[name].preferences.emit('changed')
				# Checking for exceptions and infinite recursion

		self.assertTrue(i > 0)
		#~ self.assertTrue(preferences.modified)
			# If "False" the check while loading the plugins is not valid
			# FIXME this detection is broken due to autosave in ConfigManager ...

		notebook = tests.new_notebook(self.get_tmp_name())
		ui = setupGtkInterface(self, notebook=notebook)
		dialog = PropertiesDialog(ui) # random dialog
		for obj in (
			notebook,
			notebook.index,
			ui.mainwindow,
			ui.mainwindow.pageview,
			dialog,
		):
			manager.extend(obj)

		for i, name in enumerate(manager):
			manager[name].preferences.emit('changed')
				# Checking for exceptions and infinite recursion

		for name in manager:
			#~ print "REMOVE:", name
			self.assertIsInstance(manager[name], PluginClass)
			manager.remove_plugin(name)
			self.assertNotIn(name, manager)

		self.assertTrue(len(manager) == 0)


