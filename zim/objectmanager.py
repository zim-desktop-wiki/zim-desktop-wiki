
# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

logger = logging.getLogger("zim.objectmanager")

import zim.plugins

class _ObjectManager(object):
	'''Manages custom objects.'''

	def __init__(self):
		self._objects = {}

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

	def unregister_object(self, objecttype):
		'''Unregister a specific object type.
		@param objecttype: an object derived from L{InsertedObjectType}
		'''
		key = objecttype.name.lower()
		if key in self._objects and self._objects[key] is objecttype:
			self._objects.pop(key)

	def get_object(self, name):
		'''Returns an object for a name
		@param type: the object type as string
		@returns: an instance of an object derived from C{InsertedObject}
		'''
		key = name.lower()
		return self._objects[key] # raises KeyError if not found

	def find_plugin(self, type):
		'''Find a plugin to handle a specific object type. Intended to
		suggest plugins to the user that can be loaded.
		@param type: object type as string
		@returns: a 5-tuple of the plugin name, a boolean for the
		dependency check, the plugin class, or C{None} and the related plugin window_extension
		'''
		for name in zim.plugins.PluginManager.list_installed_plugins(): # XXX
			try:
				klass = zim.plugins.PluginManager.get_plugin_class(name) # XXX
				types = klass.plugin_info.get('object_types')
				if types and type in types:
					activatable = klass.check_dependencies_ok()
					return (name, klass.plugin_info['name'], activatable, klass)
			except:
				logger.exception('Could not load plugin %s', name)
				continue
		return None


ObjectManager = _ObjectManager() # Singleton object
