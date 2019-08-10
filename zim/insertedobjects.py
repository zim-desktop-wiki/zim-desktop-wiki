# -*- coding: UTF-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from zim.signals import SignalEmitter, SIGNAL_RUN_LAST
from zim.config import String, ConfigDict


class InsertedObjectType(object):
	'''Base class for defining "objects" that can be inserted in a wiki page

	This class is called "InsertedObjectType" instead of "InsertedObject"
	because it does *not* represent a single inserted object, but defines a
	type of object of which many instances can occur. The instances themselves
	are represented by a series of tokens for the parser and a model plus a
	widget for the user interface.

	Note: if you are looking for how to define a new object type from a plugin,
	please see L{InsertedObjectTypeExtension} in L{zim.plugins}. Base classes
	for widgets can be found in L{zim.gui.insertedobjects}.
	'''

	# TODO: API to communicate whether this is an inline object or a block
	#       level object. This could change while editing so must be a model
	#       property somehow.

	name = None

	label = None
	verb_icon = None

	object_attr = {}

	def __init__(self):
		assert self.name is not None
		assert self.label is not None
		self.object_attr = self.object_attr.copy()
			# Prevent referencing and modifying class attribute of parent class
		self.object_attr['type'] = String(self.name)

		for name in ('model_from_data', 'data_from_model', 'format'):
			orig = getattr(self, name)
			wrapper = getattr(self, '_' + name + '_wrapper')
			setattr(self, '_inner_' + name, orig)
			setattr(self, name, wrapper)

	def parse_attrib(self, attrib):
		'''Convenience method to enforce the supported attributes and their
		types.
		@returns: a L{ConfigDict} using the C{object_attr} dict as definition
		'''
		if not isinstance(attrib, ConfigDict):
			attrib = ConfigDict(attrib)
			attrib.define(self.object_attr)
		return attrib

	def new_object(self):
		'''Create a new empty object
		@returns: a 2-tuple C{(attrib, data)}
		'''
		attrib = self.parse_attrib({})
		return attrib, ''

	def new_model_interactive(self, parent, notebook, page):
		'''Create a new object model interactively
		Interactive means that we can use e.g. a dialog to prompt for input.
		The default behavior is to use L{new_object()}.

		@param parent: Gtk widget to use as parent widget for dialogs
		@param notebook: a L{Notebook} object
		@param page: a L{Page} object for the page where this object occurs
		@returns: a model object (see L{model_from_data()})
		@raises: ValueError: if user cancelled the action
		'''
		attrib, data = self.new_object()
		return self.model_from_data(notebook, page, attrib, data)

	def _model_from_data_wrapper(self, notebook, page, attrib, data):
		attrib = self.parse_attrib(attrib)
		return self._inner_model_from_data(notebook, page, attrib, data)

	def model_from_data(self, notebook, page, attrib, data):
		'''Returns a model for the object

		The main purpose for the model is that it is shared between widgets that
		show the same object. See e.g. C{Gtk.TextBuffer} or C{Gtk.TreeModel}
		for examples.

		No API is expected of the model object other than that it can be used as
		argument for L{create_widget()} and L{data_from_model()} and a
		"changed" signal that should be emitted when the content has changed, so
		the pageview knows that the page has changed and should be saved before
		closing.

		Since the model is specific for the page where the object occurs, any
		user of the object type should serialize back to data before e.g.
		copying the object to a different page.

		This method should always be robust for missing attributes and body
		contents. The C{attrib} will automatically be checked by L{parse_attrib}
		before being given to this method.

		@param notebook: a L{Notebook} object
		@param page: a L{Page} object for the page where this object occurs
		@param attrib: dict with object attributes
		@param data: string with object content
		@returns: a model object
		'''
		raise NotImplementedError

	def _data_from_model_wrapper(self, model):
		attrib, data = self._inner_data_from_model(model)
		return attrib.copy(), data # Enforce shallow copy

	def data_from_model(self, model):
		'''Returns the object data for a model object
		This method is used to serialize the model object back into a form that
		can be handled when parsing wiki content.
		@param model: an object created with L{model_from_data()}
		@returns: a 2-tuple C{(attrib, data)}
		'''
		raise NotImplementedError

	def create_widget(self, model):
		'''Return a Gtk widget for the given model
		@param model: an object created with L{model_from_data()}
		@returns: a Gtk widget object derived from L{InsertedObjectWidget}
		'''
		raise NotImplementedError

	def _format_wrapper(self, format, dumper, attrib, data):
		attrib = self.parse_attrib(attrib)
		return self._inner_format(format, dumper, attrib, data)

	def format(self, format, dumper, attrib, data):
		'''Format the object using a specific output format
		Intended to improve rendering of the object on exporting.

		This method should always be robust for missing attributes and body
		contents. The C{attrib} will automatically be checked by L{parse_attrib}
		before being given to this method.

		Implementing this method is optional, default checks for a specific
		method per format (e.g. C{format_html()} for the "html" format) and
		raises C{ValueError} if no such method is defined.

		@param format: name of the output format
		@param dumper: L{Dumper} object
		@param attrib: dict with object attributes
		@param data: string with object content
		@returns: a list of strings
		@raises ValueError: if no specific formatting for "format" is available
		'''
		try:
			method = getattr(self, 'format_' + format)
		except AttributeError:
			raise ValueError('No "%s" formatting defined for objecttype "%s"' % (format, self.name))
		else:
			return method(dumper, attrib, data)
