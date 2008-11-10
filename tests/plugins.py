# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from tests import TestCase

import zim.plugins

class testPlugins(TestCase):
	'''FIXME'''

	def testGetPlugin(self):
		'''Test loading a plugin'''
		plugin = zim.plugins.get_plugin('spell')
		self.assertTrue(plugin.info['name'] == 'Spell')

