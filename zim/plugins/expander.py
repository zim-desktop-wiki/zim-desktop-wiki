# Copyright 2024 Mike Bluett <bluett80@gmail.com>

import logging

logger = logging.getLogger('zim.plugins.textexpander')

import weakref
import functools
import xml.etree.ElementTree as ElementTreeModule

from gi.repository import Gtk, GObject, Gdk

from zim.config import ConfigManager, Boolean, String, Choice
from zim.plugins import PluginClass, InsertedObjectTypeExtension

from zim.gui.pageview import TextBuffer, TextView, PluginInsertedObjectAnchor, PageView
from zim.gui.insertedobjects import InsertedObjectWidget
from zim.gui.widgets import widget_set_css, strip_boolean_result, Dialog, InputEntry
from zim.formats import list_formats, TEXT_FORMAT
from zim.formats.wiki import Parser



# TODO: Update the description
class InsertTextExpanderPlugin(PluginClass):
	plugin_info = {
		'name': _('Text Expander'),  # T: plugin name
		'description': _('''\
This plugin adds a foldable text section as an insert 
in a zim page.

'''),  # T: plugin description
		'author': 'Mike Bluett',
		'help': 'Plugins:Text Expander',
	}

	def __init__(self):
		PluginClass.__init__(self)

class TextExpanderObjectType(InsertedObjectTypeExtension):

	name = 'expander'

	label = _('Text Expander') # T: menu item

	# This is used to distinguish one Expander object from another.
	object_attr = {
		'name': String(None),
	}

	def __init__(self, plugin, objmap):
		self._widgets = weakref.WeakSet()
		super().__init__(plugin, objmap)
		self.plugin = plugin

	# This is where a new buffer is created from the text in a Page file.
	def model_from_data(self, notebook, page, attrib, text):
		self.notebook = notebook
		self.page = page
		return ExpanderBuffer(notebook, page, attrib, text)
		
	# This is where a buffer already exists. This is executed whenever new text is added to the expander object buffer.
	# This data is passed to gui/pageview/__init__.py: class PluginInsertedObjectAnchor: def dump() as a tuple of 'attrib' & 'text'
	def data_from_model(self, buffer):
		# Returns the Expander object_attrib and the text it contains
		return buffer.get_object_data()

	def create_widget(self, buffer):
		widget = ExpanderWidget(self.plugin, self.notebook, self.page, buffer)
		self._widgets.add(widget)
		return widget


class ExpanderBuffer(TextBuffer):

	def __init__(self, notebook, page, attrib, text):
		TextBuffer.__init__(self, notebook, page)
		self.notebook = notebook
		self.page = page

		self.object_attrib = attrib

		# The following is responsible for converting the formatting in the Page file to the formatting used in memory
		# (e.g., converting '**' to 'strong'). 
		if text is not None:
			tree = Parser().parse(text)
			self.set_parsetree(tree)

	# This results in textual additions and formatting changes being saved to the Page file. Essentially, it copies the contents
		# of the ExpanderBuffer into the Tree that represents the whole Zim Page.
	def get_object_data(self):
		tree = self.get_parsetree()
		from zim.formats import get_format
		format = get_format("wiki")
		dumper = format.Dumper()
		list = dumper.dump(tree)
		# Convert list to a string
		text = ''.join(list)
		# Newline character makes certain the end of the Expander object '}}}' characters are 
		# placed on the line after the last line of text. If this is not done the Expander object 
		# will not be rendered properly.
		text += '\n'
		attrib = self.object_attrib.copy()			# self.object_attrib is a Dict
		return attrib, text



CURSOR_TEXT = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'text')
CURSOR_LINK = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'pointer')
CURSOR_WIDGET = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'default')
#BULLET = '*'
COPY_FORMATS = list_formats(TEXT_FORMAT)


# InsertedObjectWidget is based on a Gtk.EventBox
class ExpanderWidget(InsertedObjectWidget):
	'''Text Expander widget.'''

	def __init__(self, plugin, notebook, page, textbuffer):
		InsertedObjectWidget.__init__(self)
		self.textbuffer = textbuffer
		self.notebook = notebook
		self.page = page
		# These two calls override the settings in the InsertedObjectWidget class
		self.set_border_width(0)
		# _vbox is a Gtk.VBox defined in the InsertedObjectWidget class
		widget_set_css(self._vbox, 'zim-inserted-object', 'border: none')
		self._cursor = CURSOR_TEXT
		self._cursor_link = None


		# Hierarchy:  Gtk.EventBox > Gtk.Overlay > Gtk.Label
		#						   				 > Gtk.Expander > Gtk.Frame > TextView
		self.overlay = Gtk.Overlay()
		self._overlay_label = Gtk.Label()
		self._overlay_label.set_halign(Gtk.Align.START)
		self._overlay_label.set_margin_start(12)
		self._overlay_label.set_valign(Gtk.Align.END)
		self._overlay_label.set_margin_bottom(5)
		widget_set_css(self._overlay_label, 'overlay-label',
			'background: rgba(0, 0, 0, 0.8); '
			'padding: 3px 5px; border-radius: 3px; '
			'color: #fff; '
		)
		self._overlay_label.set_no_show_all(True)
		self.overlay.add_overlay(self._overlay_label)
		self.overlay.set_overlay_pass_through(self._overlay_label, True)
		self.add(self.overlay)

		# When some text is selected and a new Text Exapnder object is inserted via the Zim Insert menu.
		if self.page._textbuffer.get_has_selection():
			start, end = self.page._textbuffer.get_selection_bounds()
			INCLUDE_HIDDEN_CHARS = 'True'
			selected_text = self.page._textbuffer.get_slice(start, end, INCLUDE_HIDDEN_CHARS)
			# Sets the Expander object label to the selected text when the Gtk Expander object is instantiated.
			self.text_expander = Gtk.Expander()
			self.text_expander.set_label(selected_text)
			# Adds the selected_text to the Expander object attrib['name']. 
			# This is used to distinguish one Expander object from another.
			self.textbuffer.object_attrib['name'] = selected_text[:len(selected_text) + 1]
			# Delete the selected text on the Page since it has been copied into the Expander object label.
			self.page._textbuffer.delete_interactive(start, end, True)
		elif self.textbuffer.object_attrib['name'] is None:
			# When no text selection is made previously to inserting a new Text Expander object from the Zim Insert menu.
			parent = self.get_parent()
			ExpanderNameDialog(parent, self.textbuffer).run()
			# TODO: Put this next statement after an else: and then test
			self.text_expander = Gtk.Expander()
			self.text_expander.set_label(self.textbuffer.object_attrib['name'])
		else:
			self.text_expander = Gtk.Expander()
			self.text_expander.set_label(self.textbuffer.object_attrib['name'])

		self.text_expander.set_expanded(False)
		# POINTER_MOTION_MASK is to allow Mouse motion events to be caught
		self.text_expander.set_events(Gdk.EventMask.POINTER_MOTION_MASK)
		# Collects mouse motion events so that the mouse pointer can change it's appearance depending on what it is hovering over.
		self.text_expander.connect("motion-notify-event", self.on_mouse_motion_event)
		self.text_expander.connect('button-press-event', self.change_expander_title)
		frame = Gtk.Frame()
		self.preferences = ConfigManager.preferences['ExpanderWidget']
		self.preferences.define(
			follow_on_enter=Boolean(True),
			show_link_label=Boolean(True),
			read_only_cursor=Boolean(False),
			autolink_camelcase=Boolean(True),
			autolink_page=Boolean(True),
			autolink_anchor=Boolean(True),
			autolink_interwiki=Boolean(True),
			autolink_files=Boolean(True),
			autoselect=Boolean(True),
			unindent_on_backspace=Boolean(True),
			cycle_checkbox_type=Boolean(True),
			recursive_indentlist=Boolean(True),
			recursive_checklist=Boolean(False),
			auto_reformat=Boolean(False),
			copy_format=Choice('Text', COPY_FORMATS),
			file_templates_folder=String('~/Templates'),
		)
		self.text_box = TextView(preferences=self.preferences)
		self.text_box.set_buffer(self.textbuffer)
		self.text_box.set_editable(True)
		frame.set_border_width(0.5)
		self.text_expander.add(frame)
		frame.add(self.text_box)
		# The hierarchy is Gtk.EventBox > Gtk.Overlay > Gtk.Expander > Gtk.Frame > Zim TextView > Zim TextBuffer
		# The reason for Gtk.Expander being added to Gtk.Overlay instead of directly to Gtk.EventBox is so that 
		# hovering over a link displays a popup of what the link can open.
		self.overlay.add(self.text_expander)

	def change_expander_title(self, widget, event):
		if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:	
			parent = self.get_parent()
			ChangeNameDialog(parent, self.textbuffer).run()
			self.text_expander.set_label(self.textbuffer.object_attrib['name'])

	def on_mouse_motion_event(self, widget, event):
		# Update the cursor type when the mouse moves
		x, y = event.get_coords()
		x, y = int(x), int(y) 			# avoid some strange DeprecationWarning
		coords = self.text_box.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
		self.update_cursor(coords)

	def update_cursor(self, coords=None):
		'''Update the mouse cursor type

		Set a "hand" cursor when hovering over the Expander widget.

		@param coords: a tuple with C{(x, y)} position in buffer coords.
		Only give this argument if coords are known from an event,
		otherwise the current cursor position is used.
		'''
		if coords is None:
			iter, coords = self.text_box._get_pointer_location()
		else:
			iter = strip_boolean_result(self.text_box.get_iter_at_location(*coords))

		if iter is None:
			self._set_cursor(CURSOR_WIDGET)

	def _set_cursor(self, cursor, link=None):
		if cursor != self._cursor:
			window = self.text_expander.get_window()
			window.set_cursor(cursor)

	def _get_pointer_location(self):
		'''Get an iter and coordinates for the mouse pointer

		@returns: a 2-tuple of a C{Gtk.TextIter} and a C{(x, y)}
		tupple with coordinates for the mouse pointer.
		'''
		x, y = self.text_box.get_pointer()
		x, y = self.text_box.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
		iter = strip_boolean_result(self.text_box.get_iter_at_location(x, y))
		return iter, (x, y)



class ExpanderNameDialog(Gtk.Dialog):

	def __init__(self, parent, buffer):
		Gtk.Dialog.__init__(self, parent) 		# T: dialog title
		name = ''
		self.buffer = buffer
		self.set_title('Expander Object Name')
		self.set_default_size(250, 150)
		
		# grid is just for the window title.
		grid = Gtk.Grid()
		grid.set_column_spacing(5)
		grid.set_row_spacing(5)

		label = Gtk.Label(_('Name') + ':') 				# T: input label for object Name
		grid.attach(label, 0, 1, 1, 1)
		self.entry = InputEntry()
		grid.attach(self.entry, 1, 1, 1, 1)

		self.vbox.add(grid)
		self.add_button('Ok', Gtk.ResponseType.OK)
		self.ok_btn = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
		self.ok_btn.connect("clicked", self.on_ok_clicked)
		self.entry.connect ("key-press-event", self.on_enter)

		self.show_all()

	def on_ok_clicked(self, widget):
		self.set_buffer()

	def on_enter(self, widget, event):
		# Keycode = 36 (Enter)
		if event.type == Gdk.EventType.KEY_PRESS and event.hardware_keycode == 36:
			self.set_buffer()

	def set_buffer(self):
		self.buffer.object_attrib['name'] = self.entry.get_text()
		if self.buffer.object_attrib['name']:
			self.destroy()
			return True
		else:
			return False 			# no name selected


class ChangeNameDialog(Gtk.Dialog):

	def __init__(self, parent, buffer):
		Gtk.Dialog.__init__(self, parent) 		# T: dialog title
		name = ''
		self.buffer = buffer
		self.set_title('Change Expander Name')
		self.set_default_size(250, 150)
		
		# grid is just for the window title.
		grid = Gtk.Grid()
		grid.set_column_spacing(5)
		grid.set_row_spacing(5)

		label = Gtk.Label(_('Name') + ':') 				# T: input label for object Name
		grid.attach(label, 0, 1, 1, 1)
		self.entry = InputEntry()
		grid.attach(self.entry, 1, 1, 1, 1)

		self.vbox.add(grid)
		self.add_button('Ok', Gtk.ResponseType.OK)
		self.ok_btn = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
		self.ok_btn.connect("clicked", self.on_ok_clicked)
		self.entry.connect ("key-press-event", self.on_enter)

		self.show_all()

	def on_ok_clicked(self, widget):
		self.set_buffer()

	def on_enter(self, widget, event):
		# Keycode = 36 (Enter)
		if event.type == Gdk.EventType.KEY_PRESS and event.hardware_keycode == 36:
			self.set_buffer()

	def set_buffer(self):
		self.buffer.object_attrib['name'] = self.entry.get_text()
		if self.buffer.object_attrib['name']:
			self.destroy()


# This re-implementation of the Gtk.Expander adds a get_editable method so that no error occurs as listed above.
class Expander (Gtk.Expander):

	def __init__(self, label):
		Gtk.Expander.__init__(self)
		self.set_label(label)

	def get_editable(self):
		# By returning True here it tells the code in the TextViewWidget to make the TextViewWidget editable.
		return True


