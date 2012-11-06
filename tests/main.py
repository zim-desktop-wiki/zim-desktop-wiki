# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the base zim module.'''

from __future__ import with_statement


import tests


from zim import NotebookInterface
from zim.config import XDG_CONFIG_HOME, ConfigFile, ConfigDictFile, config_file, get_config


class FilterFailedToLoadPlugin(tests.LoggingFilter):

	logger = 'zim'
	message = 'Failed to load plugin'


class TestProfiles(tests.TestCase):

	def setUp(self):
		path = self.get_tmp_name()
		self.nb = tests.new_notebook(fakedir=path)
		self.assertIsNone(self.nb.profile)

		with FilterFailedToLoadPlugin():
			self.ui = NotebookInterface(self.nb)

		configfile = self.ui.preferences.file
		configfile.file.remove() # just in case

	def tearDown(self):
		configfile = self.ui.preferences.file
		configfile.file.remove()

	def profile_file(self, name):
		return XDG_CONFIG_HOME.file('zim/profiles/%s.conf' % name.lower())

	def save_profile(self, name, preferences):
		file = self.profile_file(name)
		file.remove()
		self.assertFalse(file.exists())
		with FilterFailedToLoadPlugin():
			ui = NotebookInterface() # use defaults set in this object
		ui.preferences.change_file(file)
		for section in preferences:
			ui.preferences[section].update(preferences[section])
		ui.preferences.write()
		self.assertTrue(file.exists())

	def testProfilePreferences(self):
		'''Test the profile is used and its preferences applied'''
		# set up a test profile
		self.save_profile('TestProfile', {
			'General': {
				'plugins': ['calendar']
			},
			'CalendarPlugin': {
				'embedded': True,
				'granularity': 'Week',
				'namespace': 'TestProfile',
			}
		})

		# set the profile name in the notebook, open it, and
		# check that the profile was applied
		self.nb.config['Notebook']['profile'] = 'TestProfile' # include some caps
		self.assertEqual(self.nb.profile, 'TestProfile')

		with FilterFailedToLoadPlugin():
			ui = NotebookInterface(self.nb)
		self.assertEqual(ui.preferences.file.basename, 'testprofile.conf')
		self.assertEqual(len(ui.plugins), 1)
		self.assertEqual(
			ui.preferences['General']['plugins'][0], 'calendar')
		self.assertTrue(ui.preferences['CalendarPlugin']['embedded'])
		self.assertEqual(
			ui.preferences['CalendarPlugin']['granularity'], 'Week')
		self.assertEqual(
			ui.preferences['CalendarPlugin']['namespace'], 'TestProfile')

	def testNewProfile(self):
		'''Test that current preferences are used if the profile doesn't exist '''
		# Make sure the profile does not exist
		file = self.profile_file('NewProfile')
		file.remove()
		self.assertFalse(file.exists())

		# Save default
		self.ui.preferences.write()
		default = self.ui.preferences.file
		self.assertTrue(default.file.exists())

		# change the profile name, and reload the profile
		# check that default got copied to new profile
		self.nb.save_properties(profile='NewProfile')
		self.assertEqual(self.nb.profile, 'NewProfile')
		self.assertIsInstance(self.ui.preferences.file, ConfigFile)
		self.assertEqual(self.ui.preferences.file.file, file)
		self.assertNotEqual(self.ui.preferences.file.file, default)
		self.ui.preferences.write() # ensure the preferences are saved

		self.assertEqual(file.read(), default.read())

	def testReloadingPlugins(self):
		'''Test correct plugins are kept when changing profile'''
		# Ensure some plugins are loaded, including a independent one
		n_default_plugins = len(self.ui.plugins)
		self.ui.load_plugin('automount')
		self.ui.preferences.write()

		# create a profile just with some of the same plugins, but also
		# a new one -- so we can test merging
		names = self.ui.preferences['General']['plugins']
		self.assertEqual(len(names), n_default_plugins + 1)
		self.assertNotIn('tableofcontents', names)
		profile_plugins = [names[0], names[2], 'tableofcontents']
		self.assertNotIn('automount', profile_plugins)
		self.save_profile('ReloadingPlugins', {
			'General': {
				'plugins': profile_plugins,
			},
			'AutomountPlugin': {
				'test': 'from_profile',
			},
			'CalendarPlugin': {
				'test': 'from_profile',
			},
		})

		# Touch settings for independent plugin
		automount = self.ui.get_plugin('automount')
		calendar = self.ui.get_plugin('calendar')
		automount.preferences['test'] = 'default'
		calendar.preferences['test'] = 'default'

		# load the new profile and check that all plugins but the one
		# we kept were unloaded
		pre = set(p.plugin_key for p in self.ui.plugins)
		self.assertEqual(pre, set(names))

		self.nb.save_properties(profile='ReloadingPlugins')
		names = self.ui.preferences['General']['plugins']
		post = set(p.plugin_key for p in self.ui.plugins)
		self.assertNotEqual(post, pre)
		self.assertEqual(post, set(names))
		self.assertEqual(post, set(profile_plugins + ['automount']))

		# Check independent plugin settings were copied as well
		# but other settings were not copied
		automount = self.ui.get_plugin('automount')
		calendar = self.ui.get_plugin('calendar')
		self.assertEqual(automount.preferences['test'], 'default')
		self.assertEqual(calendar.preferences['test'], 'from_profile')

		# Now switch back
		self.nb.save_properties(profile='')
		self.assertIsNone(self.nb.profile)
		names = self.ui.preferences['General']['plugins']
		reset = set(p.plugin_key for p in self.ui.plugins)
		self.assertEqual(reset, set(names))
		self.assertEqual(reset, pre)

	def testSyncingIndependentPluginConfig(self):
		# Make sure independent plugin not in default config
		names = self.ui.preferences['General']['plugins']
		self.assertNotIn('automount', names)
		self.assertFalse(self.ui.preferences['AutomountPlugin'])

		# Save default
		calendar = self.ui.get_plugin('calendar')
		calendar.preferences['test'] = 'old'
		self.ui.preferences.write()
		self.assertTrue(self.ui.preferences.file.file.exists())

		# Switch profile
		self.nb.save_properties(profile='TestSyncing')

		# Add independent plugin, touch config and save
		self.ui.load_plugin('automount')
		automount = self.ui.get_plugin('automount')
		calendar = self.ui.get_plugin('calendar')
		automount.preferences['test'] = 'new'
		calendar.preferences['test'] = 'new'
		self.ui.save_preferences()

		# Ensure default config also has new config - but not all
		# is overwritten
		default = get_config('preferences.conf')
		self.assertIn('automount', default['General']['plugins'])
		self.assertEqual(default['AutomountPlugin']['test'], 'new')
		self.assertEqual(default['CalendarPlugin']['test'], 'old')


class FailingPluginFilter(tests.LoggingFilter):

	logger = 'zim'
	message = 'Failed to load plugin'


class TestLoadingPlugins(tests.TestCase):

	def setUp(self):
		path = self.get_tmp_name()
		self.nb = tests.new_notebook(fakedir=path)
		with FilterFailedToLoadPlugin():
			self.ui = NotebookInterface(self.nb)
		self.plugin_conf = self.ui.preferences['General']['plugins']

	def tearDown(self):
		configfile = self.ui.preferences.file
		configfile.file.remove()

	def testLoadPlugin(self):
		self.assertNotIn('automount', self.plugin_conf)
		plugins = self.plugin_conf[:]
		obj = self.ui.load_plugin('automount')
		self.assertEqual(obj.plugin_key, 'automount')
		self.assertIn(obj, self.ui.plugins)
		self.assertTrue(self.plugin_conf, plugins + ['automount'])

		self.assertEqual(obj, self.ui.get_plugin('automount'))

	def testLoadFailingPlugin(self):
		names = self.plugin_conf[:]
		objs = self.ui.plugins[:]
		with FailingPluginFilter():
			self.assertIsNone( self.ui.load_plugin('nonexistingplugin') )
		self.assertEqual(self.plugin_conf, names)
		self.assertEqual(self.ui.plugins, objs)

		self.assertIsNone(self.ui.get_plugin('nonexistingplugin'))

	def testInitPlugin(self):
		self.plugin_conf.append('automount')
		names = self.plugin_conf[:]

		self.ui.preferences.write()
		
		with FilterFailedToLoadPlugin():
			myui = NotebookInterface()
			# no notebook yet - only independent plugins are loaded
		self.assertEqual(len(myui.plugins), 1)
		self.assertEqual(myui.plugins[0].plugin_key, 'automount')

		myui.open_notebook(self.nb)
		# now the rest is loaded as well
		self.assertEqual(len(myui.plugins), len(names))

	def testInitFailingPlugin(self):
		names = self.plugin_conf[:]
		objs = self.ui.plugins[:]
		self.plugin_conf.append('nonexistingplugin')
		self.ui.preferences.set_modified(False)
		self.assertFalse(self.ui.preferences.modified)
		with FailingPluginFilter():
			self.ui.load_plugins()
		self.assertEqual(self.plugin_conf, names)
		self.assertEqual(self.ui.plugins, objs)
		self.assertTrue(self.ui.preferences.modified)

	def testUnloadPlugin(self):
		plugin = self.ui.plugins[0]
		self.assertIn(plugin, self.ui.plugins)
		self.assertIn(plugin.plugin_key, self.plugin_conf)
		self.ui.unload_plugin(plugin)
		self.assertNotIn(plugin, self.ui.plugins)
		self.assertNotIn(plugin.plugin_key, self.plugin_conf)

	def testUnloadPluginByName(self):
		plugin = self.ui.plugins[0]
		self.assertIn(plugin, self.ui.plugins)
		self.assertIn(plugin.plugin_key, self.plugin_conf)
		self.ui.unload_plugin(plugin.plugin_key)
		self.assertNotIn(plugin, self.ui.plugins)
		self.assertNotIn(plugin.plugin_key, self.plugin_conf)
