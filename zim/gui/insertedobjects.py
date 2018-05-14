
# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk

import zim.errors

from zim.objectmanager import ObjectManager
from zim.plugins import InsertedObjectType

from zim.gui.widgets import ScrolledTextView, ScrolledWindow, widget_set_css


# Constants for grab-focus-cursor and release-focus-cursor
POSITION_BEGIN = 1
POSITION_END = 2


class InsertedObjectWidget(Gtk.EventBox):
	'''Base class & contained for custom object widget

	We derive from a C{Gtk.EventBox} because we want to re-set the
	default cursor for the area of the object widget. For this the
	widget needs it's own window for drawing.

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
		'link-clicked': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-enter': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-leave': (GObject.SignalFlags.RUN_LAST, None, (object,)),

		'grab-cursor': (GObject.SignalFlags.RUN_LAST, None, (int,)),
		'release-cursor': (GObject.SignalFlags.RUN_LAST, None, (int,)),
	}

	def __init__(self):
		GObject.GObject.__init__(self)
		self.set_border_width(3)
		self._has_cursor = False
		self._vbox = Gtk.VBox()
		Gtk.EventBox.add(self, self._vbox)
		widget_set_css(self._vbox, 'zim-pageview-object', 'border: 1px solid @text_color')

	def add(self, widget):
		'''Add a widget to the object'''
		self._vbox.pack_start(widget, True, True, 0)

	def add_header(self, widget):
		'''Add an header widget on top of the object'''
		widget.get_style_context().add_class(Gtk.STYLE_CLASS_BACKGROUND)
		widget_set_css(widget, 'zim-insertedobject-head', 'border-bottom: 1px solid @fg_color')
		self._vbox.pack_start(widget, True, True, 0)
		self._vbox.reorder_child(widget, 0)

	def remove(self, widget):
		self._vbox.remove(widget)

	def do_realize(self):
		Gtk.EventBox.do_realize(self)
		window = self.get_parent_window()
		window.set_cursor(Gdk.Cursor.new(Gdk.CursorType.ARROW))

	def set_textview_wrap_width(self, width):
		def callback(width):
			minimum, natural = self._vbox.get_preferred_width()
			width = natural if width == -1 else max(width, minimum)
			self.set_size_request(width, -1)
			return False # delete signal
		GObject.idle_add(callback, width)

	def has_cursor(self):
		'''Returns True if this object has an internal cursor. Will be
		used by the TextView to determine if the cursor should go
		"into" the object or just jump from the position before to the
		position after the object. If True the embedded widget is
		expected to support grab_cursor() and use release_cursor().
		'''
		return self._has_cursor

	def set_has_cursor(self, has_cursor):
		'''See has_cursor()'''
		self._has_cursor = has_cursor

	def grab_cursor(self, position):
		'''Emits the grab-cursor signal'''
		self.emit('grab-cursor', position)

	def release_cursor(self, position):
		'''Emits the release-cursor signal'''
		self.emit('release-cursor', position)


class TextViewWidget(InsertedObjectWidget):
	# TODO make this the base class for the Sourceview plugin
	# and ensure the same tricks to integrate in the parent textview

	def __init__(self, buffer):
		InsertedObjectWidget.__init__(self)
		self.set_has_cursor(True)
		self.buffer = buffer

		win, self.view = ScrolledTextView(monospace=True,
			hpolicy=Gtk.PolicyType.AUTOMATIC, vpolicy=Gtk.PolicyType.NEVER, shadow=Gtk.ShadowType.NONE)
		self.view.set_buffer(buffer)
		self.view.set_editable(True)
		self.add(win)

		self._init_signals()

	def _init_signals(self):
		# Hook up integration with pageview cursor movement
		self.view.connect('move-cursor', self.on_move_cursor)
		self.connect('parent-set', self.on_parent_set)
		self.parent_notify_h = None

	def set_editable(self, editable):
		self.view.set_editable(editable)
		self.view.set_cursor_visible(editable)

	def on_parent_set(self, widget, old_parent):
		if old_parent and self.parent_notify_h:
			old_parent.disconnect(self.parent_notify_h)
			self.parent_notify_h = None
		parent = self.get_parent()
		if parent:
			self.set_editable(parent.get_editable())
			self.parent_notify_h = parent.connect('notify::editable', self.on_parent_notify)

	def on_parent_notify(self, widget, prop, *args):
		self.set_editable(self.get_parent().get_editable())

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


class UnkownObjectWidget(TextViewWidget):

	def __init__(self, buffer):
		TextViewWidget.__init__(self, buffer)
		#~ self.view.set_editable(False) # object knows best how to manage content
		# TODO set background grey ?

		type = buffer.object_attrib.get('type')
		plugin = ObjectManager.find_plugin(type) if type else None
		if plugin:
			header = self._add_load_plugin_bar(plugin)
			self.add_header(header)
		else:
			label = Gtk.Label(
				_("No plugin available to display objects of type: %s") % type # T: Label for object manager
			)
			self.add_header(label)

	def _add_load_plugin_bar(self, plugin):
		key, name, activatable, klass = plugin

		hbox = Gtk.HBox(False, 5)
		label = Gtk.Label(label=_("Plugin %s is required to display this object.") % name)
			# T: Label for object manager
		hbox.pack_start(label, True, True, 0)

		#~ if activatable: # and False:
			# Plugin can be enabled
			#~ button = Gtk.Button.new_with_mnemonic(_("Enable plugin")) # T: Label for object manager
			#~ def load_plugin(button):
				#~ xxx.plugins.load_plugin(key)
				#~ xxx.mainwindow.reload_page()
			#~ button.connect("clicked", load_plugin)
		#~ else:
			# Plugin has some unresolved dependencies
			#~ button = Gtk.Button.new_with_mnemonic(_("Show plugin details")) # T: Label for object manager
			#~ def plugin_info(button):
				#~ from zim.gui.preferencesdialog import PreferencesDialog
				#~ dialog = PreferencesDialog(self, "Plugins", select_plugin=name)
				#~ dialog.run()
				#~ xxx.mainwindow.reload_page()
			#~ button.connect("clicked", plugin_info)

		#~ hbox.pack_start(button, True, True, 0)
		return hbox


class UnkownObjectBuffer(Gtk.TextBuffer):

	def __init__(self, attrib, data):
		Gtk.TextBuffer.__init__(self)
		self.object_attrib = attrib
		self.set_text(data)

	def get_object_data(self):
		attrib = self.object_attrib.copy()
		start, end = self.get_bounds()
		data = start.get_text(end)
		return attrib, data


class UnknownInsertedObject(InsertedObjectType):

	name = "unknown"

	label = _('Unkown Object')  # T: label for inserted object

	def __init__(self):
		InsertedObjectType.__init__(self, plugin=None)

	def parse_attrib(self, attrib):
		# Overrule base class checks since we don't know what this object is
		attrib.setdefault('type', self.name)
		return attrib

	def model_from_data(self, attrib, data):
		return UnkownObjectBuffer(attrib, data)

	def data_from_model(self, buffer):
		return buffer.get_object_data()

	def create_widget(self, buffer):
		return UnkownObjectWidget(buffer)


# TODO: undo(), redo() stuff


class InsertedObjectUI(object):

	def __init__(self, uimanager, pageview):
		self.uimanager = uimanager
		self.pageview = pageview
		self._ui_id = None
		self._actiongroup = None
		self.add_ui()
		ObjectManager.connect('changed', self.on_changed)

	def on_changed(self, o):
		self.uimanager.remove_ui(self._ui_id)
		self.uimanager.remove_action_group(self._actiongroup)
		self._ui_id = None
		self._actiongroup = None
		self.add_ui()

	def add_ui(self):
		assert self._ui_id is None
		assert self._actiongroup is None

		self._actiongroup = self.get_actiongroup()
		ui_xml = self.get_ui_xml()

		self.uimanager.insert_action_group(self._actiongroup, 0)
		self._ui_id = self.uimanager.add_ui_from_string(ui_xml)

	def get_actiongroup(self):
		actions = [
			('insert_' + obj.name, obj.verb_icon, obj.label, '', None, self._action_handler)
				for obj in ObjectManager
		]
		group = Gtk.ActionGroup('inserted_objects')
		group.add_actions(actions)
		return group

	def get_ui_xml(self):
		menulines = []
		toollines = []
		for obj in ObjectManager:
			name = 'insert_' + obj.name
			menulines.append("<menuitem action='%s'/>\n" % name)
			if obj.verb_icon is not None:
				toollines.append("<toolitem action='%s'/>\n" % name)
		return """\
		<ui>
			<menubar name='menubar'>
				<menu action='insert_menu'>
					<placeholder name='plugin_items'>
					 %s
					</placeholder>
				</menu>
			</menubar>
			<toolbar name='toolbar'>
				<placeholder name='insert_plugin_items'>
				%s
				</placeholder>
			</toolbar>
		</ui>
		""" % (
			''.join(menulines),
			''.join(toollines),
		)

	def _action_handler(self, action):
		try:
			name = action.get_name()[7:] # len('insert_') = 7
			obj = ObjectManager.get_object(name)
			try:
				attrib, data = obj.new_object_interactive(self.pageview)
			except ValueError:
				return # dialog cancelled
			self.pageview.insert_object(attrib, data)
		except:
			zim.errors.exception_handler(
				'Exception during action: %s' % tool.name)
