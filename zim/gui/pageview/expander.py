from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gio

import logging
import weakref
import copy

logger = logging.getLogger('zim.gui.pageview.expander')

from zim.config import ConfigManager, Boolean, Choice, String
from zim.formats import list_formats, TEXT_FORMAT, get_format
from zim.gui.insertedobjects import InsertedObjectWidget
from zim.gui.widgets import widget_set_css, strip_boolean_result, \
populate_popup_add_separator, InputEntry
from .textview import TextView, CURSOR_TEXT, CURSOR_LINK, CURSOR_WIDGET
from .objectanchors import InsertedObjectAnchor
from .__init__ import PageView, PageViewExtension
from zim.formats.wiki import Parser
from zim.plugins import extendable
from zim.actions import get_gtk_actiongroup
from zim.gui.actionextension import os_default_headerbar

COPY_FORMATS = list_formats(TEXT_FORMAT)

# MGB
class ExpanderAnchor(InsertedObjectAnchor):

	def __init__(self, notebook, page, name, data):
		InsertedObjectAnchor.__init__(self)
		logger.debug('ExpanderAnchor: __init__(): name = %s', name)
		self._widgets = weakref.WeakSet()
		self.page = page
		self.notebook = notebook
		logger.debug('ExpanderAnchor: init(): Notebook = %s', self.notebook)
		self.name = name
		self.attrib = {'name': name, 'type': 'expander'}
		#self.data = data
		self.preferences = ConfigManager.preferences['ExpanderAnchor']
		self.preferences.define(
			follow_on_enter=Boolean(True),
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
		self.textview = TextView(preferences=self.preferences)
		self.buffer = self.textview.get_buffer()
		logger.debug('ExpanderAnchor: init(): Buffer = %s', self.buffer)
		# These next two lines are required so that copy_clipboard & 
		# paste_clipboard work with Expander buffers.
		self.buffer.notebook = self.notebook
		self.buffer.page = self.page
		
	def create_widget(self):
		logger.debug('ExpanderAnchor: create_widget()')
		widget = ExpanderWidget(self.notebook, self.page, self.textview, self.attrib)
		self._widgets.add(widget)
		return widget

	# Data comes in from the Zim file as attrib and data, if any is present, and is passed 
	# into ExpanderAnchor from TextBuffer.insert_object_at_cursor(). This is also responsible 
	# for converting the formatting in the Page file to the formatting used in memory.
	# (e.g., converting '**' to 'strong'). Also, returns the Expander buffer to 
	# TextBuffer.insert_object_at_cursor() so that the 'changed' signal is connected to the 
	# Expander buffer. This 'changed' signal insures that updates to the buffer are saved to
	# the Zim page file.
	def model_from_data(self, notebook, page, attrib, data):
		if data is not None:
			tree = Parser().parse(data)
			logger.debug('ExpanderAnchor: __init__(): tree = %s', tree.tostring())
			self.buffer.set_parsetree(tree)
		return self.buffer
		
	# This constructs a new builder object after new data is added to the Expander buffer.
		# It is called from TextBuffer: get_parsetree() in the 'elif anchor:' section (specifically, anchor.dump()).
	def dump(self, builder):
		logger.debug('ExpanderAnchor: dump()')
		tag = 'object'
		builder.start(tag, self.attrib)
		data = self.get_expander_data()
		if data:
			builder.data(data)
		builder.end(tag)
		return builder

	def get_expander_data(self):
		tree = self.buffer.get_parsetree()
		logger.debug('ExpanderAnchor: get_expander_data(): Before calling Dumper.dump(): tree = %s', tree.tostring())
		format = get_format("wiki")
		dumper = format.Dumper()
		list = dumper.dump(tree)
		# Convert list to a string
		data = ''.join(list)
		# Newline character makes certain the end of the Expander object '}}}' characters are 
		# placed on the line after the last line of buffer text. If this is not done the Expander 
		# object will not be rendered properly. The line_count() only adds a newline after the 
		# first new text is added. This prevents excess newlines, unecessarily, being added to 
		# the end of an Expander buffer.
		#if self.line_count() == 1:
		last_line = self.buffer.get_line_count() - 1
		iter = self.buffer.get_iter_at_line(last_line)
		current_line = iter.get_line()
		last_line_empty = self.buffer.get_line_is_empty(current_line)
		logger.debug('Expander: last_line = %d, current_line = %d', last_line, current_line)
		logger.debug('Expander: last_line_empty = %s', last_line_empty)
		if current_line == last_line and last_line_empty is not True:
			data += '\n'
		logger.debug('ExpanderAnchor: get_expander_data(): buffer = %s', data)
		return data


# MGB
# InsertedObjectWidget is based on Gtk.EventBox
class ExpanderWidget(InsertedObjectWidget):
	'''Text Expander widget.'''

	__signals__ = {
		'key-press-event': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	def __init__(self, notebook, page, textview, attrib):
		InsertedObjectWidget.__init__(self)
		logger.debug('ExpanderWidget: __init__()')
		self.notebook = notebook
		self.page = page
		self.textview = textview
		self.textview.set_focus_on_click(True)
		self.attrib = attrib
		# Previously I was doing only one of these or the other. I discovered it is necessary to do BOTH, 
		# as they are both used in the InsertedObjectWidget class. These two calls override the settings in the 
		# InsertedObjectWidget class.
		self.set_border_width(0)
		# _vbox is a Gtk.VBox defined in the InsertedObjectWidget class
		widget_set_css(self._vbox, 'zim-inserted-object', 'border: none')
		self._cursor = CURSOR_TEXT
		self._cursor_link = None
		self.page_buffer = page.get_textbuffer()
		self.preferences = ConfigManager.preferences['ExpanderAnchor']

		# Hierarchy:  Gtk.EventBox > Gtk.Overlay > Gtk.Label
		#						   > Gtk.Expander > Gtk.Frame > Zim TextView
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

		self.textbuffer = self.textview.get_buffer()
		self.textview.set_editable(True)

		self.expander = Gtk.Expander()
		self.expander.set_label(attrib['name'])
		self.expander.set_expanded(False)
		
		# POINTER_MOTION_MASK is to allow Mouse motion events to be caught
		# KEY_PRESS_MASK is to permit all keyboard keypresses to be caught. It is not necessary to use this. 
			# Simply connecting the key-press-event to the correct widget is all that is required.
		# Both set_events & add_events function but are not documented in the PyGTK documentation: PRETTY BAD!!!
			# Since they are not documented I have no idea what to properly use.
		self.expander.set_events(Gdk.EventMask.POINTER_MOTION_MASK)
		# Collects mouse motion events so that the mouse pointer can change it's appearance depending on what it is hovering over.

		# TODO: Need to fix this. Simplify this code, if possible.
		self.expander.connect("motion-notify-event", self.on_mouse_motion_event)
		self.expander.connect("button-press-event", self.change_expander_title)

		# FIXED:  If I use Gtk.TextView() instead of the Zim TextViewWidget class I will have to find a way to save the textual 
		# contents added to the Gtk.TextView box. Zim's TextView doesn't save the text either. If I use the Zim TextViewWidget class the 
		# text is saved automatically, but an error of get_editable() not being part of the expander object occurs. By, doing my own 
		# implementation of an Expander class I can now use Zim TextViewWidget without getting the get_editable error.

		# When I had this connect() method added as self (i.e., to the ExpanderWidget class), it would 
		# only accept Modifier keys (such as Shift). I could not get regular key press events to be accepted.
		# After adding the connect to the Gtk.TextView, it accepts all key presses,
		# which, in retrospect, makes sense.
		self.textview.connect('key-press-event', self.on_key_press)
		#self.textview.connect('link-enter', PageView.on_link_enter)
		#self.textview.connect('link-leave', PageView.on_link_leave)
		self.textview.connect('button-press-event', self.on_button_press_event)
		# I thought Gdk.KEY_asterisk would limit the key presses received by the textview: It does not. 
			# From what I have read it is supposed to act like a mask. Essentially, it seems to do nothing, obviously, useful.
		self.textview.set_events(Gdk.KEY_asterisk)
		frame = Gtk.Frame()
		frame.set_border_width(0.5)
		frame.add(self.textview)
		self.expander.add(frame)
		# The hierarchy is Gtk.EventBox > Gtk.Overlay > Gtk.Expander > Gtk.Frame > Zim TextView > Zim TextBuffer
		# The reason for Gtk.Expander being added to Gtk.Overlay instead of directly to Gtk.EventBox is so that 
		# hovering over a link displays a popup of what the link can open.
		self.overlay.add(self.expander)
	
	def grab_focus(self):
		logger.debug('ExpanderWidget: grab_focus()')
		self.textview.grab_focus()

	def on_mouse_motion_event(self, widget, event):
		#logger.debug('expander.py: ExpanderWidget: on_mouse_motion_event(event)')
		# Update the cursor type when the mouse moves
		x, y = event.get_coords()
		x, y = int(x), int(y)
		coords = self.textview.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
		self.update_cursor(coords)

	def update_cursor(self, coords=None):
		'''Update the mouse cursor type

		E.g. set a "hand" cursor when hovering over a link.

		@param coords: a tuple with C{(x, y)} position in buffer coords.
		Only give this argument if coords are known from an event,
		otherwise the current cursor position is used.
		
		Actually, these are emitted by def _set_cursor():
		@emits: link-enter
		@emits: link-leave
		'''
		#logger.debug('ExpanderWidget: update_cursor(coords)')
		if coords is None:
			iter, coords = self.textview._get_pointer_location()
		else:
			iter = strip_boolean_result(self.textview.get_iter_at_location(*coords))

		if iter is None:
			self._set_cursor(CURSOR_TEXT)
		else:
			pixbuf = self._get_pixbuf_at_pointer(iter, coords)
			object = self.get_name()
			if pixbuf:
				if pixbuf.zim_type == 'icon' and pixbuf.zim_attrib['stock'] in bullets:
					self._set_cursor(CURSOR_WIDGET)
				elif pixbuf.zim_type == 'anchor':
					self._set_cursor(CURSOR_WIDGET)
				elif 'href' in pixbuf.zim_attrib:
					self._set_cursor(CURSOR_LINK, link={'href': pixbuf.zim_attrib['href']})
				else:
					self._set_cursor(CURSOR_TEXT)
			elif object:
				#logger.debug('ExpanderWidget: update_cursor(coords): object = %s', object)
				self._set_cursor(CURSOR_WIDGET)
			else:
				link = self.textview.get_buffer().get_link_data(iter)
				if link:
					self._set_cursor(CURSOR_LINK, link=link)
				else:
					self._set_cursor(CURSOR_TEXT)

	def _set_cursor(self, cursor, link=None):
		#logger.debug('ExpanderWidget: _set_cursor(cursor, link)')
		if cursor != self._cursor:
			window = self.expander.get_window()
			window.set_cursor(cursor)

		# Check if we need to emit any events for hovering
		if self._cursor == CURSOR_LINK: # was over link before
			if cursor == CURSOR_LINK: # still over link
				if link != self._cursor_link:
					# but other link
					self.emit('link-leave', self._cursor_link)
					self.emit('link-enter', link)
			else:
				self.emit('link-leave', self._cursor_link)
		elif cursor == CURSOR_LINK: # was not over link, but is now
			self.emit('link-enter', link)

		self._cursor = cursor
		self._cursor_link = link

	def _get_pointer_location(self):
		'''Get an iter and coordinates for the mouse pointer

		@returns: a 2-tuple of a C{Gtk.TextIter} and a C{(x, y)}
		tupple with coordinates for the mouse pointer.
		'''
		logger.debug('ExpanderWidget: _get_pointer_location()')
		x, y = self.textview.get_pointer()
		x, y = self.textview.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
		iter = strip_boolean_result(self.textview.get_iter_at_location(x, y))
		return iter, (x, y)

	def _get_pixbuf_at_pointer(self, iter, coords):
		'''Returns the pixbuf that is under the mouse or C{None}. The
		parameters should be the TextIter and the (x, y) coordinates
		from L{_get_pointer_location()}. This method handles the special
		case where the pointer is on an iter next to the image but the
		mouse is visible above the image.
		'''
		#logger.debug('ExpanderWidget: _get_pixbuf_at_pointer(iter, coords)')
		pixbuf = iter.get_pixbuf()
		if not pixbuf:
			# right side of pixbuf will map to next iter
			iter = iter.copy()
			iter.backward_char()
			pixbuf = iter.get_pixbuf()

		if pixbuf and hasattr(pixbuf, 'zim_type'):
			# If we have a pixbuf double check the cursor is really
			# over the image and not actually on the next cursor position
			area = self.textview.get_iter_location(iter)
			if (coords[0] >= area.x and coords[0] <= area.x + area.width
				and coords[1] >= area.y and coords[1] <= area.y + area.height):
				return pixbuf
			else:
				return None
		else:
			return None

	def on_button_press_event(self, widget, event):
		logger.debug('ExpanderWidget: on_button_press_event()')
		# LEFT-Mouse-Click
		if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
			self.grab_focus()
			# Handle clicking a link or checkbox
			# TODO:  Is this necessary?
			cont = Gtk.TextView.do_button_release_event(self, event)
			if self.textview.get_editable():
				if self.preferences['cycle_checkbox_type']:
					# Cycle through all states - more useful for
					# single click input devices
					self.click_link() or self.click_checkbox() or self.click_anchor()
				else:
					self.click_link() or self.click_checkbox(CHECKED_BOX) or self.click_anchor()
		elif event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
			logger.debug('ExpanderWidget: on_button_press_event(): Calling Menu.show_menu()...')
			popup = Menu()
			popup.show_all()
		return True 	# Prevent propagating event past Expander
			
	def change_expander_title(self, widget, event):
		logger.debug('ExpanderWidget: change_expander_title()')
		if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
			logger.debug('ExpanderWidget: change_expander_title(): right mouse button')
			parent = self.get_parent()
			ChangeNameDialog(parent, self).run()
			self.expander.set_label(self.attrib['name'])
			logger.debug('ExpanderWidget: change_expander_title(): label = %s', self.expander.get_label())
			self.page._textbuffer.set_modified(True)
					
	# This 'return True' means that no other key-press-event's will be processed after this event.
	def on_key_press(self, widget, event) -> bool:
		logger.debug('ExpanderWidget: on_key_press(): event keyval = %s', event.keyval)
		# 65367 = End key
		if (event.keyval == 65367 and event.state & Gdk.ModifierType.SHIFT_MASK):
			iter = self.textbuffer.get_insert_iter()
			# Permits a Link to be selected left-to-right. Zim only permits right-to-left
			# with the Remove Link menu item enabled.
			self.textbuffer.select_word()
			# Results in the 'mark-set' signal which permits the Remove Link menu 
			# item being enabled.
			logger.debug('ExpanderWidget: on_key_press(): Calling Expander TextBuffer.place_cursor()...')
			self.textbuffer.place_cursor(iter)
			self.textbuffer.select_word()
			return True
		return False
	
	def click_link(self):
		'''Activate the link under the mouse pointer, if any

		@emits: link-clicked
		@returns: C{True} when there was indeed a link
		'''
		logger.debug('ExpanderWidget: click_link()')
		iter, coords = self.textview._get_pointer_location()
		if iter is None:
			return False

		pixbuf = self.textview._get_pixbuf_at_pointer(iter, coords)
		if pixbuf and pixbuf.zim_attrib.get('href'):
			self.emit('link-clicked', {'href': pixbuf.zim_attrib['href']})
			return True
		elif iter:
			return self.click_link_at_iter(iter)

	def _get_pointer_location(self):
		'''Get an iter and coordinates for the mouse pointer

		@returns: a 2-tuple of a C{Gtk.TextIter} and a C{(x, y)}
		tupple with coordinates for the mouse pointer.
		'''
		logger.debug('gui/pageview/init.py: _get_pointer_location()')
		x, y = self.textview.get_pointer()
		x, y = self.textview.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
		iter = strip_boolean_result(self.textview.get_iter_at_location(x, y))
		return iter, (x, y)

	def click_link_at_iter(self, iter):
		'''Activate the link at C{iter}, if any

		Like L{click_link()} but activates a link at a specific text
		iter location

		@emits: link-clicked
		@param iter: a C{Gtk.TextIter}
		@returns: C{True} when there was indeed a link
		'''
		logger.debug('ExpanderWidget: click_link_at_iter(iter)')
		link = self.textview.get_buffer().get_link_data(iter)
		if link:
			self.emit('link-clicked', link)
			return True
		else:
			return False

	def click_checkbox(self, checkbox_type=None):
		'''Toggle the checkbox under the mouse pointer, if any

		@param checkbox_type: the checkbox type to toggle between, see
		L{TextBuffer.toggle_checkbox()} for details.
		@returns: C{True} for success, C{False} if no checkbox was found.
		'''
		logger.debug('ExpanderWidget: click_checkbox()')
		iter, coords = self.textview._get_pointer_location()
		if iter and iter.get_line_offset() < 2:
			# Only position 0 or 1 can map to a checkbox
			buffer = self.textview.get_buffer()
			recurs = self.textview.preferences['recursive_checklist']
			return buffer.toggle_checkbox(iter.get_line(), checkbox_type, recurs)
		else:
			return False

	def click_anchor(self):
		'''Show popover for anchor under the cursor'''
		logger.debug('ExpanderWidget: click_anchor()')
		iter, coords = self.textview._get_pointer_location()
		if not iter:
			return False

		pixbuf = self.textview._get_pixbuf_at_pointer(iter, coords)
		if not (pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'anchor'):
			return False

		# Show popover with anchor name and option to copy link
		popover = Gtk.Popover()
		popover.set_relative_to(self)
		rect = Gdk.Rectangle()
		rect.x, rect.y = self.textview.get_pointer()
		rect.width, rect.height = 1, 1
		popover.set_pointing_to(rect)

		name =  pixbuf.zim_attrib['name']
		def _copy_link_to_anchor(o):
			buffer = self.textview.get_buffer()
			notebook, page = buffer.notebook, buffer.page
			Clipboard.set_pagelink(notebook, page, name)
			SelectionClipboard.set_pagelink(notebook, page, name)
			popover.popdown()

		hbox = Gtk.Box(Gtk.Orientation.HORIZONTAL, 12)
		hbox.set_border_width(3)
		label = Gtk.Label()
		label.set_markup('#%s' %name)
		hbox.add(label)
		button = Gtk.Button.new_from_icon_name('edit-copy-symbolic', Gtk.IconSize.BUTTON)
		button.set_tooltip_text(_("Copy link to clipboard")) # T: tooltip for button in anchor popover
		button.connect('clicked', _copy_link_to_anchor)
		hbox.add(button)
		popover.add(hbox)
		popover.show_all()
		popover.popup()

		return True

	def click_formatted_text(self):
		logger.debug('ExpanderWidget: click_formatted_text()')
		pass


class ChangeNameDialog(Gtk.Dialog):

	def __init__(self, parent, caller):
		Gtk.Dialog.__init__(self, parent) 		# T: dialog title
		name = ''
		self.caller = caller
		self.set_title('Change Expander Name')
		self.set_default_size(250, 100)
		
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
		self.caller.attrib['name'] = self.entry.get_text()
		if self.caller.attrib['name']:
			self.destroy()
