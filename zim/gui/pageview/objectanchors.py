from zim.gui.insertedobjects import InsertedObjectWidget


from gi.repository import GObject
from gi.repository import Gtk

from .constants import LINE, OBJECT


class InsertedObjectAnchor(Gtk.TextChildAnchor):

	is_inline = False # T: whether or not this object can be inline in a paragraph

	def create_widget(self):
		raise NotImplementedError

	def dump(self, builder):
		raise NotImplementedError


class LineSeparatorAnchor(InsertedObjectAnchor):

	def create_widget(self):
		return LineSeparator()

	def dump(self, builder):
		builder.start(LINE, {})
		builder.data('-'*20) # FIXME: get rid of text here
		builder.end(LINE)


class LineSeparator(InsertedObjectWidget):
	'''Class to create a separation line.'''

	def __init__(self):
		InsertedObjectWidget.__init__(self)
		widget = Gtk.Box()
		widget.get_style_context().add_class(Gtk.STYLE_CLASS_BACKGROUND)
		widget.set_size_request(-1, 3)
		self.add(widget)


class TableAnchor(InsertedObjectAnchor):
	# HACK - table support is native in formats, but widget is still in plugin
	#        so we need to "glue" the table tokens to the plugin widget

	def __init__(self, objecttype, objectmodel):
		GObject.GObject.__init__(self)
		self.objecttype = objecttype
		self.objectmodel = objectmodel

	def create_widget(self):
		return self.objecttype.create_widget(self.objectmodel)

	def dump(self, builder):
		self.objecttype.dump(builder, self.objectmodel)


class PluginInsertedObjectAnchor(InsertedObjectAnchor):

	def __init__(self, objecttype, objectmodel):
		GObject.GObject.__init__(self)
		self.objecttype = objecttype
		self.objectmodel = objectmodel
		self.is_inline = objecttype.is_inline

	def create_widget(self):
		return self.objecttype.create_widget(self.objectmodel)

	def dump(self, builder):
		attrib, data = self.objecttype.data_from_model(self.objectmodel)
		builder.start(OBJECT, dict(attrib)) # dict() because ElementTree doesn't like ConfigDict
		if data is not None:
			builder.data(data)
		builder.end(OBJECT)

