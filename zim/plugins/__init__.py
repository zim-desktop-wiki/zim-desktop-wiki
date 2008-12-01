# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import types

def get_plugin(pluginname):
	'''FIXME'''
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


class PluginClass(object):

	info = {}

	def __init__(self, application):
		self.app = application
		# TODO: assert self.info['name'] ['author'] etc.

	def __del__(self):
		'''FIXME'''
		pass

	def add_actions(self, actions):
		'''FIXME'''
		import gtk
		self.actions = gtk.ActionGroup('Foo') # FIXME
		self.actions.add_actions(actions)
		#~ self.actions.add_toggle_actions(toggle_actions)
		#~ self.actions.add_radio_actions(radio_actions)
		self.app.mainwindow.uimanager.insert_action_group(self.actions, 0)

		for action in self.actions.list_actions():
				action.connect('activate', self.app.dispatch_action, self)

	def add_toggle_actions(self, actions):
		assert False

	def add_radio_actions(self, actions):
		assert False

	def add_ui(self, xml):
		'''FIXME'''
		self.app.mainwindow.uimanager.add_ui_from_string(xml)

	def del_actions(self):
		'''FIXME'''

