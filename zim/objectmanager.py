# -*- coding: utf-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>


import gobject
import weakref


class _ObjectManager(object):
	'''Manages custom objects.'''

	def __init__(self):
		self.factories = {}
		self.objects = {}

	def register_object(self, type, factory):
		'''Register a factory method or class for a specific object type.
		A 'factory' can be either an object class or a method, as long
		as it it callable and returns objects. It will get the to be
		created object attributes, text and the ui object as arguments.
		Returns previously set factory for 'type' or None.
		'''
		type = type.lower()
		old = self.factories.get(type)
		self.factories[type] = factory
		self.objects[type] = WeakRefSet()
		return old

	def unregister_object(self, type):
		'''Unregister a specific object type.
		Returns True on success, False if given type has not been
		registered yet.
		'''
		type = type.lower()
		if type in self.factories:
			del self.factories[type]
			del self.objects[type]
			return True
		else:
			return False

	def is_registered(self, type):
		'''Returns True if object type has already been registered.'''
		return type.lower() in self.factories

	def get_object(self, type, attrib, text, ui=None):
		'''Returns a new object for given type with given attributes'''
		type = type.lower()
		if type in self.factories:
			factory = self.factories[type]
		else:
			factory = FallbackObject

		obj = factory(attrib, text, ui)
		self.objects[type].add(obj)
		return obj

	def get_active_objects(self, type):
		'''Returns an iterator for active objects for a specific type.
		(Objects are 'active' as long as they are not destroyed.)
		'''
		return iter(self.objects[type])

ObjectManager = _ObjectManager() # Singleton object


class WeakRefSet(object):
	'''Simpel collection of weak references to objects.
	Can be iterated over to list objects that are still active.
	'''

	def __init__(self):
		self._refs = []

	def add(self, obj):
		'''Add an object to the collection'''
		ref = weakref.ref(obj, self._remove)
		self._refs.append(ref)

	def _remove(self, ref):
		self._refs.remove(ref)

	def __iter__(self):
		for ref in self._refs:
			obj = ref()
			if obj:
				yield obj


class CustomObjectClass(gobject.GObject):
	'''
	Base Class for custom objects.

	Signal:
	 * 'modified-changed' -- modification state has been changed

	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'modified-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		#'changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, attrib, data, ui=None):
		gobject.GObject.__init__(self)
		self._attrib = attrib
		self._data = data if data is not None else ''
		self._widget = None
		self.ui = ui
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
		'''Returns GTK widget if GUI is detected, None otherwise.'''
		return self._widget

	def get_attrib(self):
		'''Returns object attributes. The 'type' attribute stores type of object.'''
		return self._attrib

	def get_data(self):
		'''Returns serialized data of object.'''
		return self._data

	def dump(self, format, dumper, linker=None):
		'''Dumps current object. Returns None if format is not supported.'''
		return None

gobject.type_register(CustomObjectClass)


class FallbackObject(CustomObjectClass):
	'''Fallback object displays data as TextView and
	preserves attributes unmodified.
	'''

	def __init__(self, attrib, data, ui=None):
		CustomObjectClass.__init__(self, attrib, data, ui)
		if self.ui and self.ui.ui_type == 'gtk':
			import gtk
			from zim.gui.widgets import CustomObjectBin
			self._widget = CustomObjectBin()
			box = gtk.VBox()
			box.set_border_width(5)
			self.label = gtk.Label(_("Unknown object") + ":")
			box.pack_start(self.label)
			self.view = gtk.TextView()
			self.view.set_size_request(400, 100)
			buffer = self.view.get_buffer();
			buffer.set_text(self._data)
			buffer.connect('modified-changed', self.on_modified_changed)
			buffer.set_modified(False)
			self._data = None
			win = gtk.ScrolledWindow()
			win.add(self.view)
			box.pack_start(win)
			self._widget.add(box)

	def get_data(self):
		if self._widget:
			buffer = self.view.get_buffer()
			bounds = buffer.get_bounds()
			return buffer.get_text(bounds[0], bounds[1])
		return self._data

	def on_modified_changed(self, buffer):
		'''Callback for TextBuffer's modifications.'''
		if buffer.get_modified():
			self.set_modified(True)
			buffer.set_modified(False)

	def set_label(self, label):
		'''Sets label at the top area of widget.'''
		self.label.set_text(label)

	# TODO: undo(), redo() stuff
