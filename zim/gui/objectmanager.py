# -*- coding: utf-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import gtk
import gobject

from zim.objectmanager import ObjectManager

from zim.gui.widgets import ScrolledTextView, ScrolledWindow, TableVBox


# Constants for grab-focus-cursor and release-focus-cursor
POSITION_BEGIN = 1
POSITION_END = 2

class CustomObjectWidget(gtk.EventBox):
	'''Base class & contained for custom object widget

	We derive from a C{gtk.EventBox} because we want to re-set the
	default cursor for the area of the object widget. For this the
	widget needs it's own window for drawing.

	Child widgets should be added to the C{vbox} attribute. This attribute
	is a L{TableVBox} which draws 1px borders around it's child elements.

	@signal: C{link-clicked (link)}: To be emitted when the user clicks a link
	@signal: C{link-enter (link)}: To be emitted when the mouse pointer enters a link
	@signal: C{link-leave (link)}: To be emitted when the mouse pointer leaves a link
	@signal: C{grab-cursor (position)}: emitted when embedded widget
	should grab focus, position can be either POSITION_BEGIN or POSITION_END
	@signal:  C{release-cursor (position)}: emitted when the embedded
	widget wants to give back focus to the embedding TextView
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'link-clicked': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-enter': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-leave': (gobject.SIGNAL_RUN_LAST, None, (object,)),

		'grab-cursor': (gobject.SIGNAL_RUN_LAST, None, (int,)),
		'release-cursor': (gobject.SIGNAL_RUN_LAST, None, (int,)),

		'size-request': 'override',
	}

	def __init__(self):
		gtk.EventBox.__init__(self)
		self.set_border_width(5)
		self._has_cursor = False
		self.vbox = TableVBox()
		self.add(self.vbox)
		self._textview_width = -1

	def do_realize(self):
		gtk.EventBox.do_realize(self)
		self.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.ARROW))

	def on_textview_size_changed(self, textview, width, height):
		self._textview_width = width
		self.queue_resize()

	def do_size_request(self, requisition):
		gtk.EventBox.do_size_request(self, requisition)

		#~ print "Widget requests: %i textview: %i" % (requisition.width, self._textview_width)
		if self._textview_width > requisition.width:
			requisition.width = self._textview_width

	def	has_cursor(self):
		'''Returns True if this object has an internal cursor. Will be
		used by the TextView to determine if the cursor should go
		"into" the object or just jump from the position before to the
		position after the object. If True the embedded widget is
		expected to support grab_cursor() and use release_cursor().
		'''
		return self._has_cursor

	def	set_has_cursor(self, has_cursor):
		'''See has_cursor()'''
		self._has_cursor = has_cursor

	def grab_cursor(self, position):
		'''Emits the grab-cursor signal'''
		self.emit('grab-cursor', position)

	def release_cursor(self, position):
		'''Emits the release-cursor signal'''
		self.emit('release-cursor', position)

gobject.type_register(CustomObjectWidget)



class TextViewWidget(CustomObjectWidget):
	# TODO make this the base class for the Sourceview plugin
	# and ensure the same tricks to integrate in the parent textview

	def __init__(self, buffer):
		CustomObjectWidget.__init__(self)
		self.set_has_cursor(True)
		self.buffer = buffer

		win, self.view = ScrolledTextView(monospace=True,
			hpolicy=gtk.POLICY_AUTOMATIC, vpolicy=gtk.POLICY_NEVER, shadow=gtk.SHADOW_NONE)
		self.view.set_buffer(buffer)
		self.view.set_editable(True)
		self.vbox.pack_start(win)

		# Hook up integration with pageview cursor movement
		self.view.connect('move-cursor', self.on_move_cursor)

	def do_grab_cursor(self, position):
		# Emitted when we are requesed to capture the cursor
		begin, end = self.buffer.get_bounds()
		if position == POSITION_BEGIN:
			self.buffer.place_cursor(begin)
		else:
			self.buffer.place_cursor(end)
		self.view.grab_focus()

	def on_move_cursor(self, view, step_size, count, extend_selection):
		# If you try to move the cursor out of the sourceview
		# release the cursor to the parent textview
		buffer = view.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		if (iter.is_start() or iter.is_end()) \
		and not extend_selection:
			if iter.is_start() and count < 0:
				self.release_cursor(POSITION_BEGIN)
				return None
			elif iter.is_end() and count > 0:
				self.release_cursor(POSITION_END)
				return None

		return None # let parent handle this signal


class FallbackObjectWidget(TextViewWidget):

	def __init__(self, type, buffer):
		TextViewWidget.__init__(self, buffer)
		#~ self.view.set_editable(False) # object knows best how to manage content
		# TODO set background grey ?

		plugin = ObjectManager.find_plugin(type) if type else None
		if plugin:
			self._add_load_plugin_bar(plugin)
		else:
			label = gtk.Label(_("No plugin is available to display this object.")) # T: Label for object manager
			self.vbox.pack_start(label)

	def _add_load_plugin_bar(self, plugin):
		key, name, activatable, klass, _winextension = plugin

		hbox = gtk.HBox(False, 5)
		label = gtk.Label(_("Plugin %s is required to display this object.") % name)
			# T: Label for object manager
		hbox.pack_start(label)

		#~ if activatable: # and False:
			# Plugin can be enabled
			#~ button = gtk.Button(_("Enable plugin")) # T: Label for object manager
			#~ def load_plugin(button):
				#~ self.ui.plugins.load_plugin(key)
				#~ self.ui.reload_page()
			#~ button.connect("clicked", load_plugin)
		#~ else:
			# Plugin has some unresolved dependencies
			#~ button = gtk.Button(_("Show plugin details")) # T: Label for object manager
			#~ def plugin_info(button):
				#~ from zim.gui.preferencesdialog import PreferencesDialog
				#~ dialog = PreferencesDialog(self.ui, "Plugins", select_plugin=name)
				#~ dialog.run()
				#~ self.ui.reload_page()
			#~ button.connect("clicked", plugin_info)

		#~ hbox.pack_start(button)
		self.vbox.pack_start(hbox)
		self.vbox.reorder_child(hbox, 0)


# TODO: undo(), redo() stuff
