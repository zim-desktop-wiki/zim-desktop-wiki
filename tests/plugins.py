# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from tests import TestCase

import zim.plugins

class testPlugins(TestCase):
	'''FIXME'''

	def testGetPlugin(self):
		'''Test loading a plugin'''
		plugin = zim.plugins.get_plugin('spell')
		self.assertTrue(plugin.plugin_info['name'])

	def testListPlugins(self):
		plugins = zim.plugins.list_plugins()
		self.assertTrue(len(plugins) > 0)
		self.assertTrue('spell' in plugins)
		self.assertTrue('linkmap' in plugins)

	def testDependencies(self):
		'''test if all plugins provide correct dependency infos'''
		plugins = zim.plugins.list_plugins()
		for name in plugins:
			plugin = zim.plugins.get_plugin(name)
			dep = plugin.check_dependencies()
			assert isinstance(dep,list)
			for i in range(len(dep)):
				assert isinstance(dep[i],tuple)
				assert isinstance(dep[i][0],str)
				assert isinstance(dep[i][1],bool)

