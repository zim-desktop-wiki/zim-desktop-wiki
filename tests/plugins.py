
# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import os

from zim.plugins import *
from zim.fs import File

from tests.mainwindow import setUpMainWindow

import zim.plugins
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
			#~ print('>>', name)
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
			ignore = getattr(klass, 'hide_preferences', [])
			for pref in klass.plugin_preferences:
				if pref[0] in ignore:
					continue
				label = pref[2]
				if '\n' in label:
					label, x = label.split('\n', 1)
					label = label.rstrip(',')
				self.assertIn(label, manual, 'Preference "%s" for %s plugin not documented in manual page' % (label, name))

			# test dependencies data
			dep = klass.check_dependencies()
			self.assertTrue(isinstance(dep, tuple))
			check, dep = dep
			self.assertTrue(isinstance(check, bool))
			self.assertTrue(isinstance(dep, list))
			for i in range(len(dep)):
				self.assertTrue(isinstance(dep[i], tuple))
				self.assertTrue(isinstance(dep[i][0], str))
				self.assertTrue(isinstance(dep[i][1], bool))
				self.assertTrue(isinstance(dep[i][2], bool))


class TestPluginManager(tests.TestCase):
	'''Test case for TestManager infrastructure'''

	def testLoadAndRemovePlugin(self):
		manager = PluginManager()
		self.assertEqual(len(manager), 0)
		self.assertEqual(list(manager), [])

		obj = manager.load_plugin('journal')
		self.assertEqual(len(manager), 1)
		self.assertEqual(list(manager), ['journal'])
		self.assertEqual(manager['journal'], obj)

		obj1 = manager.load_plugin('journal') # redundant call
		self.assertEqual(obj1, obj)
		self.assertEqual(len(manager), 1)

		manager.remove_plugin('journal')
		self.assertEqual(len(manager), 0)
		self.assertEqual(list(manager), [])
		self.assertRaises(KeyError, manager.__getitem__, 'journal')

		manager.remove_plugin('journal') # redundant call

	def testLoadNonExistingPlugin(self):
		manager = PluginManager()
		self.assertRaises(ImportError, manager.load_plugin, 'nonexistingplugin')


class TestPlugins(tests.TestCase):
	'''Test case to initiate all (loadable) plugins and load some extensions'''

	def runTest(self):
		preferences = ConfigManager.get_config_dict('preferences.conf')
		manager = PluginManager()
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

		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		self.assertGreaterEqual(len(notebook.__zim_extension_objects__), 2)
			# At least journal and tasklist should load

		mainwindow = setUpMainWindow(notebook, plugins=manager)
		self.assertGreaterEqual(len(mainwindow.pageview.__zim_extension_objects__), 3)
			# enough plugins without dependencies here

		for i, name in enumerate(manager):
			manager[name].preferences.emit('changed')
				# Checking for exceptions and infinite recursion

		for name in manager:
			#~ print("REMOVE:", name)
			self.assertIsInstance(manager[name], PluginClass)
			manager.remove_plugin(name)
			self.assertNotIn(name, manager)

		self.assertTrue(len(manager) == 0)


class TestFunctions(tests.TestCase):

	def test_find_extension(self):

		class Extension(ExtensionBase):
			pass

		@extendable(Extension)
		class Extendable(object):
			pass

		obj = Extendable()
		ext = Extension(None, obj)

		self.assertIs(find_extension(obj, Extension), ext)
		with self.assertRaises(ValueError):
			self.assertIs(find_extension(obj, Extendable), ext)

	def test_find_action(self):
		from zim.actions import action

		class Extension(ExtensionBase):

			@action('Bar')
			def bar(self):
				pass

		@extendable(Extension)
		class Extendable(object):

			@action('Foo')
			def foo(self):
				pass

		obj = Extendable()
		ext = Extension(None, obj)

		self.assertTrue(hasaction(obj, 'foo'))
		self.assertTrue(hasaction(ext, 'bar'))

		self.assertIsNotNone(find_action(obj, 'foo'))
		self.assertIsNotNone(find_action(obj, 'bar'))
		with self.assertRaises(ValueError):
			find_action(obj, 'dus')
