# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import os

import zim.plugins
import zim
import zim.config

from zim.fs import File

assert len(zim.plugins.__path__) > 1 # test __path__ magic
zim.plugins.__path__ = [os.path.abspath('./zim/plugins')] # set back default search path


class testPlugins(tests.TestCase):

	def testListAll(self):
		'''Test loading plugins and meta data'''
		plugins = zim.plugins.list_plugins()
		self.assertTrue(len(plugins) > 10)
		self.assertTrue('spell' in plugins)
		self.assertTrue('linkmap' in plugins)

		# plugins listed here will be tested for is_profile_independent == True
		profile_independent = ['automount',]

		pluginindex = File('data/manual/Plugins.txt').read()

		seen = {
			'name': set(),
			'description': set(),
			'help': set(),
		}
		for name in plugins:
			#~ print '>>', name
			plugin = zim.plugins.get_plugin(name)

			# test plugin info
			for key in ('name', 'description', 'author'):
				self.assertTrue(
					plugin.plugin_info.get(key),
					'Plugin %s misses info field \'%s\'' % (name, key)
				)

			for key in ('name', 'description', 'help'):
				self.assertIn(key, plugin.plugin_info, 'Plugin %s missing "%s"' % (name, key))
				value = plugin.plugin_info[key]
				self.assertFalse(
					value in seen[key],
					'Value for \'%s\' in %s seen before - copy-paste error ?' % (key, name)
				)
				seen[key].add(value)

			# test manual page present and at least documents preferences
			page = plugin.plugin_info['help']
			self.assertTrue(page.startswith('Plugins:'), 'Help page for %s not valid' % name)

			rellink = "+%s" % page[8:]
			self.assertIn(rellink, pluginindex, 'Missing links "%s" in manual/Plugins.txt' % rellink)

			file = File('data/manual/' + page.replace(':', '/').replace(' ', '_') + '.txt')
			self.assertTrue(file.exists(), 'Missing file: %s' % file)

			manual = file.read()
			for pref in plugin.plugin_preferences:
				label = pref[2]
				if '\n' in label:
					label, x = label.split('\n', 1)
					label = label.rstrip(',')
				self.assertIn(label, manual, 'Preference "%s" for %s plugin not documented in manual page' % (label, name))

			# test dependencies data
			dep = plugin.check_dependencies()
			self.assertTrue(isinstance(dep,tuple))
			check, dep = dep
			self.assertTrue(isinstance(check,bool))
			self.assertTrue(isinstance(dep,list))
			for i in range(len(dep)):
				self.assertTrue(isinstance(dep[i],tuple))
				self.assertTrue(isinstance(dep[i][0],str))
				self.assertTrue(isinstance(dep[i][1],bool))
				self.assertTrue(isinstance(dep[i][2],bool))

			# test is_profile_independent
			self.assertTrue(isinstance(plugin.is_profile_independent,bool))
			if name in profile_independent:
				self.assertTrue(plugin.is_profile_independent)
			else:
				self.assertFalse(plugin.is_profile_independent)

	def testDefaulPlugins(self):
		'''Test loading default plugins'''
		# Note that we use parent interface class here, so plugins
		# will not really attach - just testing loading and prereq
		# checks are OK.
		notebook = tests.new_notebook()
		interface = zim.NotebookInterface(notebook)
		interface.uistate = zim.config.ConfigDict()
		interface.load_plugins()
		self.assertTrue(len(interface.plugins) > 3)

	# TODO: create a full GtkUI object and load & unload each plugin in turn
