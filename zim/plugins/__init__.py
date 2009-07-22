# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import types
import os
import sys

from zim.fs import Dir
from zim.config import ListDict

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
	'''Base class for plugins. Every module containing a plugin should
	have exactly one class derived from this base class. That class
	will be initialized when the plugin is loaded.

	Plugins should define two class attributes. The first is a dict
	called 'plugin_info'. It can contain the following keys:

		* name - short name
		* description - one paragraph description
		* author - name of the author
		* manualpage - page name in the manual (optional)

	This info will be used e.g. in the plugin tab of the preferences
	dialog.

	Secondly a tuple can be defined called 'plugin_preferences'.
	Each item in this list should in turn be tuple containing four items:

		* the key in the config file
		* an option type (see Dialog.add_fields() for more details)
		* a label to show in the dialog
		* a default value

	These preferences will be initialized if not set and the actual values
	can be found in the 'preferences' attribute. The type and label will
	be used to render a default configure dialog when triggered from
	the preferences dialog.
	'''

	plugin_info = {}

	plugin_preferences = ()

	def __init__(self, ui):
		self.ui = ui
		assert 'name' in self.plugin_info, 'Plugins should provide a name in the info dict'
		assert 'description' in self.plugin_info, 'Plugins should provide a description in the info dict'
		assert 'author' in self.plugin_info, 'Plugins should provide a author in the info dict'
		section = self.__class__.__name__
		self.preferences = self.ui.preferences[section]
		for key, type, label, default in self.plugin_preferences:
				self.preferences.setdefault(key, default)
		self.uistate = ListDict()
		self.ui.connect_after('open-notebook', self._merge_uistate)

	def _merge_uistate(self, *a):
		# As a convenience we provide a uistate dict directly after
		# initialization of the plugin. However, in reality this
		# config file is only available after the notebook is openend.
		# Therefore we need to link the actual file and merge back
		# any defaults that were set during plugin intialization etc.
		if self.ui.uistate:
			section = self.__class__.__name__
			defaults = self.uistate
			self.uistate = self.ui.uistate[section]
			for key, value in defaults.items():
				self.uistate.setdefault(key, value)

	def disconnect(self):
		'''Disconnect the plugin object from the ui, should revert
		any changes it made to the application. Default handler removes
		any GUI actions and menu items that were defined.
		'''
		if self.ui.ui_type == 'gtk':
			self.ui.remove_ui(self)
			self.ui.remove_actiongroup(self)

	def add_actions(self, actions):
		'''Define menu actions in the Gtk GUI

		TODO document how an action tuple looks
		'''
		assert self.ui.ui_type == 'gtk'
		self.ui.add_actions(actions, handler=self)

	def add_toggle_actions(self, actions):
		'''Define menu toggle actions in the Gtk GUI

		TODO document how an action tuple looks
		'''
		assert self.ui.ui_type == 'gtk'
		self.ui.add_toggle_actions(actions, handler=self)

	def add_radio_actions(self, actions, methodname):
		'''Define menu actions in the Gtk GUI

		TODO document how an action tuple looks
		'''
		assert self.ui.ui_type == 'gtk'
		self.ui.add_radio_actions(actions, handler=self, methodname=methodname)
