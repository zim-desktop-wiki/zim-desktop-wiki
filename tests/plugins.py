# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

from tests import TestCase

import zim.plugins

class testPlugins(TestCase):
	'''FIXME'''

	def runTest(self):
		'''Test loading plugins and meta data'''
		plugin_path = [i.path for i in zim.plugins.plugin_dirs(_path=['.'])]
		plugins = zim.plugins.list_plugins(_path=plugin_path)
		self.assertTrue(len(plugins) > 0)
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
