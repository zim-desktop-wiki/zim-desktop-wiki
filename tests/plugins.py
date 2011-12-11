# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import os

import zim.plugins
import zim
import zim.config

assert len(zim.plugins.__path__) > 1 # test __path__ magic
zim.plugins.__path__ = [os.path.abspath('./zim/plugins')] # set back default search path


class testPlugins(tests.TestCase):

	def testListAll(self):
		'''Test loading plugins and meta data'''
		plugins = zim.plugins.list_plugins()
		self.assertTrue(len(plugins) > 10)
		self.assertTrue('spell' in plugins)
		self.assertTrue('linkmap' in plugins)

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
					if not key in plugin.plugin_info:
						print 'NOTE: plugin %s has no help page' % name
						continue

					value = plugin.plugin_info[key]
					self.assertFalse(
						value in seen[key],
						'Value for \'%s\' in %s seen before - copy-paste error ?' % (key, name)
					)
					seen[key].add(value)

			# test manual page present
			if 'help' in plugin.plugin_info:
				page = plugin.plugin_info['help']
				self.assertTrue(page.startswith('Plugins:'), 'Help page for %s not valid' % name)
				file = 'data/manual/' + page.replace(':', '/').replace(' ', '_') + '.txt'
				self.assertTrue(os.path.isfile(file), 'Missing file: %s' % file)

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
