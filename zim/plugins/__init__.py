# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import types
import os
import sys

from zim.fs import Dir

def get_plugin(pluginname):
	'''Returns the plugin class object for a given name'''
	# __import__ has some quirks, see the reference manual
	pluginname = pluginname.lower()
	mod = __import__('zim.plugins.'+pluginname)
	mod = getattr(mod, 'plugins')
	mod = getattr(mod, pluginname)
	for name in dir(mod):
		obj = getattr(mod, name)
		if ( isinstance(obj, (type, types.ClassType)) # is a class
		and issubclass(obj, PluginClass) # is derived from PluginClass
		and not obj == PluginClass ): # but is not PluginClass itself
			return obj


def list_plugins():
	'''Returns a set of available plugin names'''
	# FIXME how should this work for e.g. for python eggs ??
	plugins = set()
	for dir in sys.path:
		dir = Dir((dir, 'zim', 'plugins'))
		if not dir.exists():
			continue
		for candidate in dir.list():
			if candidate.startswith('_'):
				continue
			elif candidate.endswith('.py'):
				plugins.add(candidate[:-3])
			elif os.path.isdir(dir.path+'/'+candidate) \
			and os.path.exists(dir.path+'/'+candidate+'/__init__.py'):
				plugins.add(candidate)
			else:
				pass

	return plugins


class PluginClass(object):

	info = {}

	def __init__(self, ui):
		self.ui = ui
		assert 'name' in self.info, 'Plugins should provide a name'
		assert 'description' in self.info, 'Plugins should provide a description'
		assert 'author' in self.info, 'Plugins should provide a author'

	def disconnect(self):
		'''FIXME'''
		self.ui.remove_actions(self)
