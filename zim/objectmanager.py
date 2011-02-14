# -*- coding: utf-8 -*-
# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>


import gobject
import logging
logger = logging.getLogger(__name__)

class ObjectManager(object):
	_objects = {}
	
	@classmethod
	def register_object(cls, type, klass):
		'''
		Registers ObjectManagerClass for type of object.
		Returns previously set ObjectManager or None.
		'''
		type = type.lower()
		if type in cls._objects:
			old = cls._objects[type]
		else:
			old = None
		cls._objects[type] = klass
		return old
	
	@classmethod
	def unregister_object(cls, type):
		'''
		Unregister ObjectManager for given type of object.
		Returns True on success, False if given type has not been
		registered yet.
		'''
		type = type.lower()
		if type in cls._objects:
			del cls._objects[type]
			return True
		else:
			return False
	
	@classmethod
	def get_object(cls, obj, ui=None):
		'''Returns ObjectManager instance for given object.'''
		klass = UnknownObject # fallback
		if 'type' in obj.attrib:
			type = obj.attrib['type'].lower()
			if type in cls._objects:
				klass = cls._objects[type]
		
		return klass(obj.attrib, obj.text, ui)

class CustomObjectClass(gobject.GObject):
	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'modified-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		#'changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}
	def __init__(self, attrib, data, ui=None):
		gobject.GObject.__init__(self)
		self._attrib = attrib
		self._data = data
		self._widget = None
		self.ui = ui
		self.modified = False
	
	def get_modified(self):
		return self.modified
	
	def set_modified(self, modified):
		if self.modified != modified:
			self.modified = modified
			self.emit("modified-changed")
	
	def get_widget(self):
		return self._widget

	def get_attrib(self):
		return self._attrib

	def get_data(self):
		return self._data
	
	def dump(self, format, linker=None):
		'''Dumps current object. Returns None on failure.''' 
		return None
gobject.type_register(CustomObjectClass)		

class UnknownObject(CustomObjectClass):
	def __init__(self, attrib, data, ui=None):
		CustomObjectClass.__init__(self, attrib, data, ui)
		if self.ui.ui_type == 'gtk':
			import gtk
			from zim.gui.widgets import CustomObjectBin
			self._widget = CustomObjectBin()
			box = gtk.VBox()
			box.set_border_width(5)
			label = gtk.Label(_("Unknown object")+":")
			box.pack_start(label)
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
		if buffer.get_modified():
			self.set_modified(True)
			buffer.set_modified(False)
