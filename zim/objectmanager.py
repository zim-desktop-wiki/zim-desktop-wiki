# -*- coding: utf-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

logger = logging.getLogger("zim.objectmanager")

from zim.signals import SignalEmitter, SIGNAL_AFTER
from zim.utils import WeakSet
from zim.config.dicts import ConfigDict, String

import zim.plugins

## TODO remove singleton contruction, add ref to plugin manager
##      to allow fallback object widget to have toolbar to load plugin

class _ObjectManager(object):
	'''Manages custom objects.'''

	def __init__(self):
		self.factories = {}
		self.objects = {'fallback': WeakSet()}
		self.window_extensions = {}

	def register_object(self, type, factory, window_extension=None):
		'''Register a factory method or class for a specific object type.
		@param type: the object type as string (unique name)
		@param factory: can be either an object class or a method,
		@param window_extension: dictionary - the plugin related window_extension
		should callable and return objects. When constructing objects
		this factory will be called as::

			factory(attrib, text)

		Where:
		  - C{attrib} is a dict with attributes
		  - C{text} is the main text source of the object

		@returns: a previously set factory for C{type} or C{None}
		'''
		logger.debug('Registered object %s', type)
		type = type.lower()
		old = self.factories.get(type)
		self.factories[type] = factory
		self.objects[type] = WeakSet()
		self.window_extensions[type] = window_extension
		return old

	def unregister_object(self, type):
		'''Unregister a specific object type.
		@returns: C{True} on success, C{False} if given type has not
		been registered.
		'''
		type = type.lower()
		if type in self.factories:
			del self.factories[type]
			del self.objects[type]
			return True
		else:
			return False

	def is_registered(self, type):
		'''Returns C{True} if object type has already been registered.'''
		return type.lower() in self.factories

	def get_object(self, type, attrib, text):
		'''Returns a new object for given type with given attributes
		@param type: the object type as string
		@param attrib: dict with attributes
		@param text: main source of the object
		@returns: a new object instance, either created by the factory
		method for C{type}, or an instance of L{FallbackObject}
		'''
		type = type.lower()

		if type in self.factories:
			factory = self.factories[type]
			obj = factory(attrib, text)
			self.objects[type].add(obj)
		else:
			factory = FallbackObject
			obj = factory(attrib, text)
			self.objects['fallback'].add(obj)

		return obj

	def get_active_objects(self, type):
		'''Returns an iterator for active objects for a specific type.
		(Objects are 'active' as long as they are not destroyed.)
		'''
		if type in self.objects:
			return iter(self.objects[type])
		else:
			return []

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
					win_ext = self.window_extensions[type] if type in self.window_extensions else None
					return (name, klass.plugin_info['name'], activatable, klass, win_ext)
			except:
				logger.exception('Could not load plugin %s', name)
				continue
		return None

ObjectManager = _ObjectManager() # Singleton object


class CustomObjectClass(SignalEmitter):
	'''
	Base Class for custom objects.

	Signal:
	 * 'modified-changed' -- modification state has been changed

	'''

	OBJECT_ATTR = {
		'type': String('object')
	}

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'modified-changed': (SIGNAL_AFTER, None, ()),
	}

	def __init__(self, attrib, data):
		self._attrib = ConfigDict(attrib)
		self._attrib.define(self.OBJECT_ATTR)
		self._data = data if data is not None else ''
		self.modified = False

	def get_modified(self):
		'''Returns True if object has been modified.'''
		return self.modified

	def set_modified(self, modified):
		'''Sets modification state of object and emits signal if needed.'''
		if self.modified != modified:
			self.modified = modified
			self.emit("modified-changed")

	def get_widget(self):
		'''Returns a new gtk widget for this object'''
		raise NotImplemented

	def get_attrib(self):
		'''Returns object attributes. The 'type' attribute stores type of object.'''
		return self._attrib.dump()

	def get_data(self):
		'''Returns serialized data of object.'''
		return self._data

	def dump(self, format, dumper, linker=None):
		'''Dumps current object. Returns None if format is not supported.'''
		return None


class FallbackObject(CustomObjectClass):
	'''Fallback object displays data as TextView and
	preserves attributes unmodified.
	'''

	def __init__(self, attrib, data):
		CustomObjectClass.__init__(self, attrib, data)
		self.buffer = None

	def get_widget(self):
		import gtk
		from zim.gui.objectmanager import FallbackObjectWidget

		if not self.buffer:
			self.buffer = gtk.TextBuffer()
			self.buffer.set_text(self._data)
			self.buffer.connect('modified-changed', self.on_modified_changed)
			self.buffer.set_modified(False)
			self._data = None

		type = self._attrib['type']
		return FallbackObjectWidget(type, self.buffer)

	def get_data(self):
		if self.buffer:
			bounds = self.buffer.get_bounds()
			return self.buffer.get_text(bounds[0], bounds[1])
		else:
			return self._data

	def set_data(self, text):
		if self.buffer:
			self.buffer.set_text(text)
		else:
			self._data = text

	def on_modified_changed(self, buffer):
		'''Callback for TextBuffer's modifications.'''
		if buffer.get_modified():
			self.set_modified(True)
			buffer.set_modified(False)

	def set_label(self, label):
		'''Sets label at the top area of widget.'''
		self.label.set_text(label)

