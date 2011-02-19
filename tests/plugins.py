# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from tests import TestCase, get_test_notebook

import os

import zim.plugins
import zim
import zim.config

assert len(zim.plugins.__path__) > 1 # test __path__ magic
zim.plugins.__path__ = [os.path.abspath('./zim/plugins')] # set back default search path


class testPlugins(TestCase):
	'''FIXME'''

	def testListAll(self):
		'''Test loading plugins and meta data'''
		plugins = zim.plugins.list_plugins()
		self.assertTrue(len(plugins) > 10)
		self.assertTrue('spell' in plugins)
		self.assertTrue('linkmap' in plugins)

		for name in plugins:
			#~ print '>>', name
			plugin = zim.plugins.get_plugin(name)

			# test plugin info
			self.assertTrue(plugin.plugin_info['name'])
			self.assertTrue(plugin.plugin_info['description'])
			self.assertTrue(plugin.plugin_info['author'])

			# test dependencies data
			dep = plugin.check_dependencies()
			self.assertTrue(isinstance(dep,list))
			for i in range(len(dep)):
				self.assertTrue(isinstance(dep[i],tuple))
				self.assertTrue(isinstance(dep[i][0],str))
				self.assertTrue(isinstance(dep[i][1],bool))

	def testDefaulPlugins(self):
		'''Test loading default plugins'''
		# Note that we use parent interface class here, so plugins
		# will not really attach - just testing loading and prereq
		# checks are OK.
		notebook = get_test_notebook()
		interface = zim.NotebookInterface(notebook)
		interface.uistate = zim.config.ConfigDict()
		interface.load_plugins()
		self.assertTrue(len(interface.plugins) > 3)

