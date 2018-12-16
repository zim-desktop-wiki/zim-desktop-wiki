
# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

logger = logging.getLogger("zim.objectmanager")

import zim.plugins

from zim.signals import SignalEmitter, SIGNAL_RUN_LAST


class _ObjectManager(SignalEmitter):

	__signals__ = {
		'changed': (SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self):
		self._objects = {}

	def __iter__(self):
		return iter(self._objects[k] for k in sorted(self._objects))

	def register_object(self, objecttype):
		'''Register an object type
		@param objecttype: an object derived from L{InsertedObjectType}
		@raises AssertionError: if another object already uses the same name
		'''
		key = objecttype.name.lower()
		if key in self._objects:
			raise AssertionError('InsertedObjectType "%s" already defined by %s' % (key, self._objects[key]))
		else:
			self._objects[key] = objecttype
			self.emit('changed')

	def unregister_object(self, objecttype):
		'''Unregister a specific object type.
		@param objecttype: an object derived from L{InsertedObjectType}
		'''
		key = objecttype.name.lower()
		if key in self._objects and self._objects[key] is objecttype:
			self._objects.pop(key)
			self.emit('changed')

	def get_object(self, name):
		'''Returns an object for a name
		@param name: the object type as string
		@returns: an instance of an object derived from C{InsertedObject}
		'''
		return self._objects[name.lower()] # raises KeyError if not found

	def find_plugin(self, name):
		'''Find a plugin to handle a specific object type. Intended to
		suggest plugins to the user that can be loaded.
		@param name: object type as string
		@returns: a 5-tuple of the plugin name, a boolean for the
		dependency check, the plugin class, or C{None} and the related plugin window_extension
		'''
		for plugin in zim.plugins.PluginManager.list_installed_plugins():
			try:
				klass = zim.plugins.PluginManager.get_plugin_class(plugin)
				for objtype in klass.discover_classes(zim.plugins.InsertedObjectType):
					if objtype.name == name:
						activatable = klass.check_dependencies_ok()
						return (plugin, klass.plugin_info['name'], activatable, klass)
			except:
				logger.exception('Could not load plugin %s', name)
				continue
		return None


ObjectManager = _ObjectManager() # Singleton object
