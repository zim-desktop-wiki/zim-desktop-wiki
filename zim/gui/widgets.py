
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains a number of custom gtk widgets
that are used in the zim gui modules.

These include base clases for windows and dialogs like L{Window},
L{Dialog}, L{FileDialog}, L{QuestionDialog}, L{ErrorDialog}, and
L{Assistant}. Especially the Dialog class contains a number of
convenience methods.

An important class is te L{InputForm} which is used extensively in the
zim gui to layout forms of input fields etc. And the related specialized
input widgets like L{InputEntry}, L{FileEntry}, L{FolderEntry},
L{LinkEntry}, L{PageEntry} and L{NamespaceEntry}. These widgets take
care of converting specific object types, proper utf-8 encoding etc.

The remaining classes are various widgets used in the gui:
L{Button}, L{IconButton}, L{IconChooserButton}, L{MenuButton},
L{ImageView}, L{SingleClickTreeView} and L{BrowserTreeView}.

@newfield requires: Requires
'''

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango
from gi.repository import GdkPixbuf
from gi.repository import GLib


import logging
import sys
import os
import re
import weakref
import unicodedata
import locale

try:
	import gi
	gi.require_version('GtkSource', '3.0')
	from gi.repository import GtkSource
except:
	GtkSource = None

import zim

import zim.errors
import zim.config
import zim.fs

from zim.fs import File, Dir
from zim.config import value_is_coord
from zim.notebook import Notebook, Path, PageNotFoundError
from zim.parsing import link_type
from zim.signals import ConnectorMixin
from zim.notebook.index import IndexNotFoundError
from zim.actions import action

logger = logging.getLogger('zim.gui')


if os.environ.get('ZIM_TEST_RUNNING'):
	TEST_MODE = True
	TEST_MODE_RUN_CB = None
else:
	TEST_MODE = False
	TEST_MODE_RUN_CB = None


# Check the (undocumented) list of constants in Gtk.keysyms to see all names
KEYVAL_LEFT = Gdk.keyval_from_name('Left')
KEYVAL_RIGHT = Gdk.keyval_from_name('Right')
KEYVALS_ASTERISK = (
	Gdk.unicode_to_keyval(ord('*')), Gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	Gdk.unicode_to_keyval(ord('\\')),
	Gdk.unicode_to_keyval(ord('/')), Gdk.keyval_from_name('KP_Divide'))
KEYVAL_ESC = Gdk.keyval_from_name('Escape')


CANCEL_STR = _('_Cancel') # T: Button label
OK_STR = _('_OK') # T: Button label

def encode_markup_text(text):
	'''Encode text such that it can be used in a piece of markup text
	without causing errors. Needed for all places where e.g. a label
	depends on user input and is formatted with markup to show
	it as bold text.
	@param text: label text as string
	@returns: encoded text
	'''
	return text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')


def decode_markup_text(text):
	'''Decode text that was encoded with L{encode_markup_text()}
	and remove any markup tags.
	@param text: markup text
	@returns: normal text
	'''
	text = re.sub('<.*?>', '', text)
	return text.replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&')


def strip_boolean_result(ret):
	# Wrapper to remove additional boolean
	# See also gi.overrides strip_boolean_result()
	# This version also double checks whether result was stripped already
	# to be robust for API changes
	if ret.__class__.__name__ == '_ResultTuple':
		if ret[0]:
			if len(ret) == 2:
				return ret[1]
			else:
				return ret[1:]
		else:
			return None
	else:
		return ret


def gtk_window_set_default_icon():
	'''Function to set the zim icon as the default window icon for
	all gtk windows in this process.
	'''
	from zim.config import ZIM_DATA_DIR, XDG_DATA_HOME, XDG_DATA_DIRS
	iconlist = []
	if ZIM_DATA_DIR:
		dir = ZIM_DATA_DIR + '../icons'
		for name in ('zim16.png', 'zim32.png', 'zim48.png'):
			file = dir.file(name)
			if file.exists():
				pixbuf = GdkPixbuf.Pixbuf.new_from_file(file.path)
				iconlist.append(pixbuf)
	else:
		sizes = ['16x16', '32x32', '48x48']
		for dir in [XDG_DATA_HOME] + XDG_DATA_DIRS:
			for size in sizes:
				file = dir.file('icons/hicolor/%s/apps/zim.png' % size)
				if file.exists():
					sizes.remove(size)
					pixbuf = GdkPixbuf.Pixbuf.new_from_file(file.path)
					iconlist.append(pixbuf)
			if not sizes:
				break

	if not iconlist:
		# fall back to data/zim.png
		file = zim.config.data_file('zim.png')
		pixbuf = GdkPixbuf.Pixbuf.new_from_file(file.path)
		iconlist.append(pixbuf)

		# also register it as stock since theme apparently is not found
		factory = Gtk.IconFactory()
		factory.add_default()
		set = Gtk.IconSet(pixbuf=pixbuf)
		factory.add('zim', set)


	if len(iconlist) < 3:
		logger.warn('Could not find all icon sizes for the application icon')
	Gtk.Window.set_default_icon_list(iconlist)


def to_utf8_normalized_casefolded(text):
	'''Convert text to utf8 normalized and casefolded form.
	@param text: text string to convert
	@returns: converted text
	'''
	result = GLib.utf8_normalize(text, -1, GLib.NormalizeMode.ALL)
	result = GLib.utf8_casefold(result, -1)
	return result



def ScrolledWindow(widget, hpolicy=Gtk.PolicyType.AUTOMATIC, vpolicy=Gtk.PolicyType.AUTOMATIC, shadow=Gtk.ShadowType.IN):
	'''Wrap C{widget} in a C{Gtk.ScrolledWindow} and return the resulting
	widget
	@param widget: any Gtk widget
	@param hpolicy: the horizontal scrollbar policy
	@param vpolicy: the vertical scrollbar policy
	@param shadow: the shadow type
	@returns: a C{Gtk.ScrolledWindow}
	'''
	window = Gtk.ScrolledWindow()
	window.set_policy(hpolicy, vpolicy)
	window.set_shadow_type(shadow)

	if isinstance(widget, (Gtk.TextView, Gtk.TreeView, Gtk.Layout)):
		# Known native-scrolling widgets
		window.add(widget)
	else:
		window.add_with_viewport(widget)

	if hpolicy == Gtk.PolicyType.NEVER:
		hsize = -1 # do not set
	else:
		hsize = 24

	if vpolicy == Gtk.PolicyType.NEVER:
		vsize = -1 # do not set
	else:
		vsize = 24

	window.set_size_request(hsize, vsize)
		# scrolled widgets have at least this size...
		# by setting this minimum widgets can not "disappear" when
		# HPaned or VPaned bar is pulled all the way
	return window


def ScrolledTextView(text=None, monospace=False, **kwarg):
	'''Initializes a C{Gtk.TextView} with sane defaults for displaying a
	piece of multiline text and wraps it in a scrolled window

	@param text: initial text to show in the textview
	@param monospace: when C{True} the font will be set to monospaced
	and line wrapping disabled, use this to display log files etc.
	@param kwarg: arguments passed on to L{ScrolledWindow}
	@returns: a 2-tuple of the scrolled window and the textview
	'''
	textview = Gtk.TextView()
	textview.set_editable(False)
	textview.set_left_margin(5)
	textview.set_right_margin(5)
	if monospace:
		font = Pango.FontDescription('Monospace')
		textview.modify_font(font)
	else:
		textview.set_wrap_mode(Gtk.WrapMode.WORD)

	if text:
		textview.get_buffer().set_text(text)
	window = ScrolledWindow(textview, **kwarg)
	return window, textview

def ScrolledSourceView(text=None, syntax=None):
	'''If GTKSourceView was successfullly loaded, this generates a SourceView and
	initializes it. Otherwise ScrolledTextView will be used as a fallback.

	@param text: initial text to show in the view
	@param syntax: this will try to enable syntax highlighting for the given
	language. If None, no syntax highlighting will be enabled.
	@returns: a 2-tuple of a window and a view.
	'''
	if GtkSource:
		gsvbuf = GtkSource.Buffer()
		if syntax:
			gsvbuf.set_highlight_syntax(True)
			language_manager = GtkSource.LanguageManager()
			gsvbuf.set_language(language_manager.get_language(syntax))
		if text:
			gsvbuf.set_text(text)
		textview = GtkSource.View()
		textview.set_buffer(gsvbuf)
		textview.set_property("show-line-numbers", True)
		textview.set_property("auto-indent", True)
		font = Pango.FontDescription('Monospace')
		textview.modify_font(font)
		textview.set_property("smart-home-end", True)
		window = ScrolledWindow(textview)
		return (window, textview)
	else:
		return ScrolledTextView(text=text, monospace=True)

def populate_popup_add_separator(menu, prepend=False):
	'''Convenience function that adds a C{Gtk.SeparatorMenuItem}
	to a context menu. Checks if the menu already contains items,
	if it is empty does nothing. Also if the menu already has a
	seperator in the required place this function does nothing.
	This helps with building menus more dynamically.
	@param menu: the C{Gtk.Menu} object for the popup
	@param prepend: if C{False} append, if C{True} prepend
	'''
	items = menu.get_children()
	if not items:
		pass # Nothing to do
	elif prepend:
		if not isinstance(items[0], Gtk.SeparatorMenuItem):
			sep = Gtk.SeparatorMenuItem()
			menu.prepend(sep)
	else:
		if not isinstance(items[-1], Gtk.SeparatorMenuItem):
			sep = Gtk.SeparatorMenuItem()
			menu.append(sep)


def gtk_combobox_set_active_text(combobox, text):
	'''Opposite of C{Gtk.ComboBox.get_active_text()}. Sets the
	active item based on a string. Will match this string against the
	list of options and select the correct index.
	@raises ValueError: when the string is not found in the list.
	'''
	model = combobox.get_model()
	for i, value in enumerate(model):
		if value[0] == text:
			return combobox.set_active(i)
	else:
		raise ValueError(text)


def gtk_notebook_get_active_page(nb):
	'''Returns the active child widget or C{None}'''
	num = nb.get_current_page()
	if num >= 0:
		return nb.get_nth_page(num)
	else:
		return None


def gtk_popup_at_pointer(menu, event=None, button=3):
	'''Introduced in Gtk 3.22, so wrap our own to be compatible for 3.18 and up'''
	if hasattr(menu, 'popup_at_pointer'):
		menu.popup_at_pointer(event)
	else:
		_gtk_popup_at_pointer_backward(menu, event, button)


_ref_cache = {}

def _gtk_popup_at_pointer_backward(menu, event, button):
	# Testing shows that Gtk 3.18 does not show the menu if we don't keep a
	# ref (!?) - see issue #813
	_ref_cache[id(menu)] = menu
	menu.connect('destroy', lambda m: _ref_cache.pop(id(m)))
	time = event.time if event else 0
	menu.popup(None, None, None, None, button, time)


def rotate_pixbuf(pixbuf):
	'''Rotate the pixbuf to match orientation from EXIF info.
	This is intended for e.g. photos that have EXIF information that
	shows how the camera was held.
	@returns: a new version of the pixbuf or the pixbuf itself.
	'''
	# For newer gtk we could use GdkPixbuf.Pixbuf.apply_embedded_orientation

	# Values for orientation seen in some random snippet in gtkpod
	o = pixbuf.get_option('orientation')
	if o:
		o = int(o)
	if o == 3: # 180 degrees
		return pixbuf.rotate_simple(Gdk.PIXBUF_ROTATE_UPSIDEDOWN)
	elif o == 6: # 270 degrees
		return pixbuf.rotate_simple(Gdk.PIXBUF_ROTATE_CLOCKWISE)
	elif o == 9: # 90 degrees
		return pixbuf.rotate_simple(Gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
	else:
		# No rotation info, older gtk version, or advanced transpose
		return pixbuf


def help_text_factory(text):
	'''Create a label with an "info" icon in front of it. Intended for
	informational text in dialogs.
	@param text: the text to display
	@returns: a C{Gtk.HBox}
	'''
	hbox = Gtk.HBox(spacing=12)

	image = Gtk.Image.new_from_stock(Gtk.STOCK_INFO, Gtk.IconSize.BUTTON)
	image.set_alignment(0.5, 0.0)
	hbox.pack_start(image, False, True, 0)

	label = Gtk.Label(label=text)
	label.set_use_markup(True)
	label.set_alignment(0.0, 0.0)
	hbox.add(label)

	return hbox


def _do_sync_widget_state(widget, a, subject):
	# Signal handler to update state of subject based on state of widget
	subject.set_sensitive(widget.get_property('sensitive'))
	subject.set_no_show_all(widget.get_no_show_all())
	if widget.get_property('visible'):
		subject.show()
	else:
		subject.hide()


def _do_sync_widget_state_check_active(widget, *a):
	if len(a) == 1:
		subject = a[0]
	else:
		subject = a[1]
	_do_sync_widget_state(widget, '', subject)
	subject.set_sensitive(widget.get_active())


def _sync_widget_state(widget, subject, check_active=False):
	# Hook label or secondary widget to follow state of e.g. entry widget
	# check_active is only meaningful if widget is a togglebutton and
	# will also add a dependency on the active state of the widget
	check_active = check_active and hasattr(widget, 'get_active')

	if check_active:
		func = _do_sync_widget_state_check_active
	else:
		func = _do_sync_widget_state

	func(widget, '', subject)
	for property in ('visible', 'no-show-all', 'sensitive'):
		widget.connect_after('notify::%s' % property, func, subject)

	if check_active:
		subject.set_sensitive(widget.get_active())
		widget.connect_after('toggled', func, subject)


def input_table_factory(inputs, table=None):
	'''Function to help with the layout of widgets in tables.

	Only use this function directly if you want a completely custom
	input form. For standard forms see the L{InputForm} class.

	@param inputs: a list of inputs. These inputs should be either
	a tuple of a string and one or more widgets, a single widget, a
	string, or C{None}.

	For a tuple the lable will be lined out in the first column followed
	by all the widgets. If a tuple is given and the first item is
	C{None}, the widget will be lined out in the 2nd column.

	A single widget will be lined out in line with the lables (this is
	meant for e.g. checkboxes that have the label behind the checkbox
	as part of the widget).

	A string will be put as a label on it's own row. Use of markup is
	assumed.

	An input that has a C{None} value will result in an empty row in the
	table, separating field above and below.

	@param table: options C{Gtk.Table}, if given inputs will be appended
	to this table

	@returns: a C{Gtk.Table}
	'''
	if table is None:
		table = Gtk.Table()
		table.set_border_width(5)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
	i = table.get_property('n-rows')

	for input in inputs:
		if input is None:
			table.attach(Gtk.Label(label=' '), 0, 1, i, i + 1, xoptions=Gtk.AttachOptions.FILL)
			# HACK: force empty row to have height of label
		elif isinstance(input, str):
			label = Gtk.Label()
			label.set_markup(input)
			table.attach(label, 0, 4, i, i + 1)
				# see column below about col span for single widget case
		elif isinstance(input, tuple):
			text = input[0]
			if text:
				label = Gtk.Label(label=text + ':')
				label.set_alignment(0.0, 0.5)
			else:
				label = Gtk.Label(label=' ' * 4) # minimum label width

			table.attach(label, 0, 1, i, i + 1, xoptions=Gtk.AttachOptions.FILL)
			_sync_widget_state(input[1], label)

			for j, widget in enumerate(input[1:]):
				if isinstance(widget, Gtk.Entry):
					table.attach(widget, j + 1, j + 2, i, i + 1, xoptions=Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND)
				else:
					table.attach(widget, j + 1, j + 2, i, i + 1, xoptions=Gtk.AttachOptions.FILL)
				if j > 0:
					_sync_widget_state(input[1], widget)
		else:
			widget = input
			table.attach(widget, 0, 4, i, i + 1)
				# We span 4 columns here so in case these widgets are
				# the widest in the tables (e.g. checkbox + label)
				# they don't force expanded size on first 3 columns
				# (e.g. label + entry + button).
		i += 1

	return table


class IconButton(Gtk.Button):
	'''Button with a stock icon, but no label.'''

	def __init__(self, stock, relief=True, size=Gtk.IconSize.BUTTON):
		'''Constructor

		@param stock: constant for the stock item
		@param relief: when C{False} the button has no visible raised
		edge and will be flat against the background
		@param size: the icon size
		'''
		GObject.GObject.__init__(self)
		icon = Gtk.Image.new_from_stock(stock, size)
		self.add(icon)
		self.set_alignment(0.5, 0.5)
		if not relief:
			self.set_relief(Gtk.ReliefStyle.NONE)


class IconChooserButton(Gtk.Button):
	'''Widget to allow the user to choose an icon. Intended e.g. for
	the dialog to configure a custom tool to set an icon for the
	tool. Shows a button with an image of the icon which opens up a
	file dialog when clicked.
	'''

	def __init__(self, stock=Gtk.STOCK_MISSING_IMAGE, pixbuf=None):
		'''Constructor

		@param stock: initial stock icon (until an icon is selected)
		@param pixbuf: initial image as pixbuf (until an icon is selected)
		'''
		GObject.GObject.__init__(self)
		self.file = None
		self.image = Gtk.Image()
		self.add(self.image)
		self.set_alignment(0.5, 0.5)
		if pixbuf:
			self.image.set_from_pixbuf(pixbuf)
		else:
			self.image.set_from_stock(stock, Gtk.IconSize.DIALOG)

	def do_clicked(self):
		dialog = FileDialog(self, _('Select File')) # T: dialog title
		dialog.add_filter_images()
		oldfile = self.get_file()
		if oldfile:
			dialog.set_file(oldfile)

		newfile = dialog.run()
		if newfile:
			self.set_file(newfile)

	def set_file(self, file):
		'''Set the file to display in the chooser button
		@param file: a L{File} object
		'''
		w, h = strip_boolean_result(Gtk.icon_size_lookup(Gtk.IconSize.DIALOG))
		pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(file.path, w, h)
		self.image.set_from_pixbuf(pixbuf)
		self.file = file

	def get_file(self):
		'''Get the selected icon file
		@returns: a L{File} object
		'''
		return self.file


class SingleClickTreeView(Gtk.TreeView):
	'''Sub-class of C{Gtk.TreeView} that implements single-click
	navigation.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'populate-popup': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	mask = Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.META_MASK

	def do_button_press_event(self, event):
		# Implement hook for context menu

		if event.type == Gdk.EventType.BUTTON_PRESS \
		and event.button == 3:
			# Check selection state - item under cursor should be selected
			# see do_button_release_event for comments
			x, y = list(map(int, event.get_coords()))
			info = self.get_path_at_pos(x, y)
			selection = self.get_selection()
			if x > 0 and y > 0 and not info is None:
				path, column, x, y = info
				if not selection.path_is_selected(path):
					selection.unselect_all()
					selection.select_path(path)
				# else the click was on a already selected path
			else:
				# click outside area with items ?
				selection.unselect_all()

			# Pop menu
			menu = self.get_popup()
			gtk_popup_at_pointer(menu, event)
		else:
			return Gtk.TreeView.do_button_press_event(self, event)

	def do_button_release_event(self, event):
		# Implement single click behavior for activating list items
		# this needs to be done on button release to avoid conflict with
		# selections, drag-n-drop, etc.

		if event.type == Gdk.EventType.BUTTON_RELEASE \
		and event.button == 1 and not event.get_state() & self.mask \
		and not self.is_rubber_banding_active():
			x, y = list(map(int, event.get_coords()))
				# map to int to suppress deprecation warning :S
				# note that get_coords() gives back (0, 0) when cursor
				# is outside the treeview window (e.g. drag & drop that
				# was started inside the tree - see bug lp:646987)
			info = self.get_path_at_pos(x, y)
			if x > 0 and y > 0 and not info is None:
				path, column, x, y = info
				if self.get_selection().path_is_selected(path):
					self.row_activated(path, column)
				# This action is conditional on the path being selected
				# because otherwise we can not toggle the folding state
				# of a path without activating it. The assumption being
				# that the path gets selected on button press and then
				# gets activated on button release. Clicking the
				# expander in front of a path should not select the path.
				# This logic is based on particulars of the C implementation
				# and might not be future proof.

		return Gtk.TreeView.do_button_release_event(self, event)

	def get_popup(self):
		'''Get a popup menu (the context menu) for this widget
		@returns: a C{Gtk.Menu} or C{None}
		@emits: populate-popup
		@implementation: do NOT overload this method, implement
		L{do_initialize_popup} instead
		'''
		menu = Gtk.Menu()
		self.do_initialize_popup(menu)
		self.emit('populate-popup', menu)
		if len(menu.get_children()) > 0:
			return menu
		else:
			return None

	def do_initialize_popup(self, menu):
		'''Initialize the context menu.
		This method is called before the C{populate-popup} signal and
		can be used to put any standard items in the menu.
		@param menu: the C{Gtk.Menu} object for the popup
		@implementation: can be implemented by sub-classes. Default
		implementation calls L{populate_popup_expand_collapse()}
		if the model is a C{Gtk.TreeStore}. Otherwise it does nothing.
		'''
		model = self.get_model()
		if isinstance(model, Gtk.TreeStore):
			self.populate_popup_expand_collapse(menu)

	def populate_popup_expand_collapse(self, menu, prepend=False):
		'''Adds "Expand _all" and "Co_llapse all" items to a context
		menu. Called automatically by the default implementation of
		L{do_initialize_popup()}.
		@param menu: the C{Gtk.Menu} object for the popup
		@param prepend: if C{False} append, if C{True} prepend
		'''
		expand = Gtk.MenuItem.new_with_mnemonic(_("Expand _All")) # T: menu item in context menu
		expand.connect_object('activate', self.__class__.expand_all, self)
		collapse = Gtk.MenuItem.new_with_mnemonic(_("_Collapse All")) # T: menu item in context menu
		collapse.connect_object('activate', self.__class__.collapse_all, self)

		populate_popup_add_separator(menu, prepend=prepend)
		if prepend:
			menu.prepend(collapse)
			menu.prepend(expand)
		else:
			menu.append(expand)
			menu.append(collapse)

		menu.show_all()

	def get_cell_renderer_number_of_items(self):
		'''Get a C{Gtk.CellRendererText} that is set up for rendering
		the number of items below a tree item.
		Used to enforce common style between tree views.
		@returns: a C{Gtk.CellRendererText} object
		'''
		cr = Gtk.CellRendererText()
		cr.set_property('xalign', 1.0)
		#~ cr2.set_property('scale', 0.8)
		cr.set_property('foreground', 'darkgrey')
		return cr


class BrowserTreeView(SingleClickTreeView):
	'''Sub-class of C{Gtk.TreeView} that is intended for hierarchic
	lists that can be navigated in "browser mode". It inherits the
	single-click behavior of L{SingleClickTreeView} and adds the
	following keybindings:
		- C{<Left>}: Collapse sub-items
		- C{<Right>}: Expand sub-items
		- C{\}: Collapse whole tree
		- C{*}: Expand whole tree
	'''

	# TODO some global option to restore to double click navigation ?

	def __init__(self, model=None):
		'''Constructor, all arguments are passed to C{Gtk.TreeView}'''
		GObject.GObject.__init__(self)
		self.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
		if model:
			self.set_model(model)

	def do_key_press_event(self, event):
		# Keybindings for the treeview:
		#  * expand all
		#  / or \ collapse all
		#  Right expand sub items
		#  Left collapse sub items
		handled = True
		#~ print('KEY %s (%i)' % (Gdk.keyval_name(event.keyval), event.keyval))

		if event.keyval in KEYVALS_ASTERISK:
			self.expand_all()
		elif event.keyval in KEYVALS_SLASH:
			self.collapse_all()
		elif event.keyval == KEYVAL_LEFT:
			model, paths = self.get_selection().get_selected_rows()
			if len(paths) == 1:
				self.collapse_row(paths[0])
		elif event.keyval == KEYVAL_RIGHT:
			model, paths = self.get_selection().get_selected_rows()
			if len(paths) == 1:
				self.expand_row(paths[0], 0)
		else:
			handled = False

		if handled:
			return True
		else:
			return Gtk.TreeView.do_key_press_event(self, event)


def widget_set_css(widget, name, css):
	text = '#%s {%s}' % (name, css)
	css_provider = Gtk.CssProvider()
	css_provider.load_from_data(text.encode('UTF-8'))
	widget_style = widget.get_style_context()
	widget_style.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
	widget.set_name(name)


def button_set_statusbar_style(button):
	# Set up a style for the statusbar variant to decrease spacing of the button
	widget_set_css(button, 'zim-statusbar-button',	'''
													border: none;
													border-radius: 0px; 
													padding: 0px 8px 0px 8px; 
													''')
	button.set_relief(Gtk.ReliefStyle.NONE)


class MenuButton(Gtk.HBox):
	'''This class implements a button which pops up a menu when clicked.
	It behaves different from a combobox because it is not a selector
	and the button does not show the selected item. So it more like
	a normal menu. Main example where this class is used is the button
	with backlinks in the statusbar of the main window.

	This module is based loosely on gedit-status-combo-box.c from the
	gedit sources.
	'''

	def __init__(self, label, menu, status_bar_style=False):
		'''Constructor

		@param label: the label to show on the button (string or C{Gtk.Label})
		@param menu: the menu to show on button click
		@param status_bar_style: when C{True} all padding and border
		is removed so the button fits in the status bar
		'''
		GObject.GObject.__init__(self)
		if isinstance(label, str):
			self.label = Gtk.Label()
			self.label.set_markup_with_mnemonic(label)
		else:
			assert isinstance(label, Gtk.Label)
			self.label = label

		self.menu = menu
		self.button = Gtk.ToggleButton()
		if status_bar_style:
			button_set_statusbar_style(self.button)

		arrow = Gtk.Arrow(Gtk.ArrowType.UP, Gtk.ShadowType.NONE)
		widget = Gtk.HBox(spacing=3)
		widget.pack_start(self.label, False, True, 0)
		widget.pack_start(arrow, False, True, 0)


		self.button.add(widget)
		# We need to wrap stuff in an eventbox in order to get the Gdk.Window
		# which we need to get coordinates when positioning the menu
		self.eventbox = Gtk.EventBox()
		self.eventbox.add(self.button)
		self.add(self.eventbox)

		self.button.connect_object(
			'button-press-event', self.__class__.popup_menu, self)
		self._clicked_signal = self.button.connect_object(
			'clicked', self.__class__.popup_menu, self)

		# TODO reduce size of toggle-button - see gedit-status-combo for example
		# TODO looks like other statusbar items resize on toggle button

	def popup_menu(self, event=None):
		'''This method actually pops up the menu.
		@param event: the gdk event that triggered this action

		@implementation: can be overloaded, e.g. to populate the menu
		dynamically.
		'''
		if not self.get_property('sensitive'):
			return

		if event: # we came from button-press-event or similar
			button = event.button
			time = event.time
			if self.button.get_active():
				return
		else:
			button = 0
			time = Gtk.get_current_event_time()

		self.button.handler_block(self._clicked_signal)
		self.button.set_active(True)
		self.button.handler_unblock(self._clicked_signal)
		self.menu.connect('deactivate', self._deactivate_menu)
		self.menu.show_all()
		self.menu.set_property('rect_anchor_dx', -1) # This is needed to line up menu with borderless button 
		self.menu.popup_at_widget(self, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, event)

	def _deactivate_menu(self, menu):
		self.button.handler_block(self._clicked_signal)
		self.button.set_active(False)
		self.button.unset_state_flags(Gtk.StateFlags.PRELIGHT)
		self.button.handler_unblock(self._clicked_signal)


class PanedClass(object):
	# We change default packing to shrink=False

	def pack1(self, widget, resize=True, shrink=False):
		Gtk.Paned.pack1(self, widget, resize, shrink)

	def pack2(self, widget, resize=True, shrink=False):
		Gtk.Paned.pack2(self, widget, resize, shrink)

	add1 = pack1
	add2 = pack2

	def add(*a):
		raise NotImplementedError

	def pack(*a):
		raise NotImplementedError

class HPaned(PanedClass, Gtk.HPaned):
	pass

class VPaned(PanedClass, Gtk.VPaned):
	pass


class InputForm(Gtk.Table):
	'''This class implements a table with input widgets. It takes care
	of constructing the widgets and lay them out as a well formatted
	input form.

	This class can be accessed as a dict to get and set the values of
	the various input widgets by name. This makes it more or less
	transparent when getting and setting values from the form into
	the config or preferences.

	@ivar notebook: the L{Notebook} object, used e.g. for completion in
	L{PageEntry} inputs
	@ivar widgets: a dict with the input widgets by name. Use this
	to access the widgets directly (e.g. to wire more signals).

	@signal: C{last-activated ()}: this signal is emitted when the last
	widget in the form is activated, can be used to trigger a default
	response in a dialog.
	@signal: C{input-valid-changes ()}: valid state the form changed
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'last-activated': (GObject.SignalFlags.RUN_LAST, None, ()),
		'input-valid-changed': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	# Supported input widgets:
	#	CheckButton
	#	RadioButton
	#	SpinButton
	#	ComboBox (text based)
	#	PageEntry / NamespaceEntry / LinkEntry
	#	InputEntry

	# Because of naming used to map radio buttons into a group
	# we can't use the keys of the widget mapping one-on-one for
	# the value mapping. This is why we keep the attribute '_keys'.

	def __init__(self, inputs=None, values=None, depends=None, notebook=None):
		'''Constructor.

		@param inputs: list with input definitions, see L{add_inputs()}
		for details
		@param values: initial values for the inputs
		@param depends: dict with dependencies between widgets, see
		L{depends()} for details
		@param notebook: a L{Notebook} object, e.g. for completion in
		L{PageEntry} inputs
		'''
		GObject.GObject.__init__(self)
		self.set_border_width(5)
		self.set_row_spacings(5)
		self.set_col_spacings(12)

		self.notebook = notebook
		self._input_valid = True
		self._keys = [] # names of options - radiogroups are represented as a single item
		self.widgets = {} # all widgets - contains individual radiobuttons
		self._widgets = [] # sequence for widgets in self.widgets

		self._default_activate = None

		if inputs:
			self.add_inputs(inputs)

		if depends:
			for k, v in list(depends.items()):
				self.depends(k, v)

		if values:
			self.update(values)

	def set_default_activate(self, name):
		'''Mark a widget as the default activation widget.
		This will cause the "last-activated" signal to be triggered
		for this widget even if it is not the last widget in the form.
		@param name: the name or C{None}
		'''
		if name is None:
			self._default_activate = None
		else:
			self._default_activate = self.widgets[name]

	#{ Form construction methods

	def add_inputs(self, inputs):
		'''Add input widgets to the form.

		Inputs are defined by 3-tuples or 4-tuples of:
			- The input name
			- The input type
			- The label to put in front of the input field
			- optional extra argument

		The following input types are supported:
			- "C{bool}" - C{True} or C{False} (checkbox)
			- "C{int}" - integer (spin button)
			- "C{string}" - text entry (L{InputEntry})
			- "C{password}" - text entry with chars hidden (L{InputEntry})
			- "C{page}" - a page L{Path} (L{PageEntry})
			- "C{namespace}" - a namespace L{Path} (L{NamespaceEntry})
			- "C{link}" - a link as string (L{LinkEntry})
			- "C{dir}" - a L{Dir} object (L{FolderEntry})
			- "C{file}" - a L{File} object for an existing file (L{FileEntry})
			- "C{image}" - like 'file' but specific for images
			- "C{output-file}" - like 'file' but for new or existing file
			- "C{option}" - single option in a group (radio checkboxes)
			- "C{choice}" - list with choices (combo box)
			- "C{color}" - color string

		The "C{int}" and "C{choice}" options need an extra argument to specify
		the allowed inputs. For "C{int}" this should be a 2-tuple with the
		minimum and maximum values. For 'choice' it should be a tuple
		or list with the items to choose from. If the items in the list are
		2-tuples they are considered pairs of a key and a user readable label.

		The input type "C{option}"' can be used to have groups of checkboxes.
		In this case the name should exist of two parts separated by a
		':', first part is the group name and the second part the key for
		this option. This way multiple options of the same group can be
		specified as separate widgets. Only the group name will show up
		as a key in the form, and the value will be the option name of the
		selected radio button. So you can have names like "select:all"
		and "select:page" which will result in two radiobuttons. The
		form will have a key "select" which has either a value "all" or
		a value "page".

		The "C{page}", "C{namespace}" and "C{link}" types support an optional
		extra argument which gives the reference L{Path} for resolving
		relative paths. This also requires the notebook to be set.

		A string in the input list will result in a label in the form,
		using markup.

		A C{None} or C{''} value in the input list will result in
		additional row spacing in the form.
		'''

		# For options we use rsplit to split group and option name.
		# The reason for this that if there are any other ":" separated
		# parts they belong to the group name, not the option name.
		# (This is used in e.g. the preference dialog to encode sections
		# where an option goes in the config.)

		widgets = []

		for input in inputs:
			if not input:
				widgets.append(None)
				continue
			elif isinstance(input, str):
				widgets.append(input)
				continue

			if len(input) == 4:
				name, type, label, extra = input
			else:
				name, type, label = input
				extra = None

			if type == 'bool':
				widgets.append(Gtk.CheckButton.new_with_mnemonic(label))

			elif type == 'option':
				assert ':' in name, 'BUG: options should have name of the form "group:key"'
				key, x = name.rsplit(':', 1)
					# using rsplit to assure another ':' in the
					# group name is harmless
				group = self._get_radiogroup(key)
				if not group:
					group = None # we are the first widget
				else:
					group = group[0][1] # link first widget in group
				widgets.append(Gtk.RadioButton.new_with_mnemonic_from_widget(group, label))

			elif type == 'int':
				button = Gtk.SpinButton()
				button.set_range(*extra)
				button.set_increments(1, 5)
				widgets.append((label, button))

			elif type == 'choice':
				combobox = Gtk.ComboBoxText()
				if all(isinstance(t, tuple) for t in extra):
					mapping = {}
					for key, value in extra:
						combobox.append_text(value)
						mapping[value] = key
					combobox.zim_key_mapping = mapping
				else:
					for option in extra:
						combobox.append_text(option)
				widgets.append((label, combobox))

			elif type == 'link':
				#~ assert self.notebook
				entry = LinkEntry(self.notebook, path=extra)
				# FIXME use inline icon for newer versions of Gtk
				button = Gtk.Button.new_with_mnemonic(_('_Browse')) # T: Button label
				button.connect_object('clicked', entry.__class__.popup_dialog, entry)
				widgets.append((label, entry, button))

			elif type == 'page':
				#~ assert self.notebook
				entry = PageEntry(self.notebook, path=extra)
				widgets.append((label, entry))

			elif type == 'namespace':
				#~ assert self.notebook
				entry = NamespaceEntry(self.notebook, path=extra)
				widgets.append((label, entry))

			elif type in ('dir', 'file', 'image', 'output-file'):
				if type == 'dir':
					entry = FolderEntry()
				else:
					new = (type == 'output-file')
					entry = FileEntry(new=new)

				entry.file_type_hint = type

				# FIXME use inline icon for newer versions of Gtk
				button = Gtk.Button.new_with_mnemonic(_('_Browse')) # T: Button label
				button.connect_object('clicked', entry.__class__.popup_dialog, entry)
				widgets.append((label, entry, button))

			elif type in ('string', 'password'):
				entry = InputEntry()
				entry.zim_type = type
				if type == 'password':
					entry.set_visibility(False)
				if extra:
					entry.set_check_func(extra)
				widgets.append((label, entry))

			elif type == 'color':
				button = Gtk.ColorButton()
				widgets.append((label, button))

			else:
				assert False, 'BUG: unknown field type: %s' % type

			# Register widget
			widget = widgets[-1]
			if isinstance(widget, tuple):
				widget = widget[1]
			self.widgets[name] = widget
			self._widgets.append(name)
			if ':' in name:
				# radio button - only add group once
				group, x = name.split(':', 1)
				if not group in self._keys:
					self._keys.append(group)
			else:
				self._keys.append(name)

			# Connect activate signal
			if isinstance(widget, Gtk.Entry):
				widget.connect('activate', self.on_activate_widget)
			else:
				pass

			# Connect valid state
			if isinstance(widget, InputEntry):
				widget.connect('input-valid-changed', self._check_input_valid)
				for property in ('visible', 'sensitive'):
					widget.connect_after('notify::%s' % property, self._check_input_valid)

		input_table_factory(widgets, table=self)

		self._check_input_valid() # update our state

	def depends(self, subject, object):
		'''Make one of the inputs depend on another widget. This means
		that e.g. the "subject" widget will become insensitive when the
		"object" widget is made insensitive. Also hiding the "object"
		will result in the "subject" being hidden as well.

		If the "object" has an active state (e.g. if it is an checkbox
		or a radio option) the "subject" will only be sensitive when the
		"object" is active. This is useful e.g. when you want a
		text input that is only sensitive when a specific radio box
		is selected.

		@param subject: the name of the subject widget
		@param object: the name of the object widget
		'''
		subject = self.widgets[subject]
		object = self.widgets[object]
		_sync_widget_state(object, subject, check_active=True)

	def get_input_valid(self):
		'''Get combined state of all sensitive widgets in the form
		@returns: C{True} if all sensitive widgets have a valid input
		'''
		return self._input_valid

	def _check_input_valid(self, *a):
		# Called by signals when widget state changes
		#~ print('-'*42)
		valid = []
		for name in self._widgets:
			widget = self.widgets[name]
			if isinstance(widget, InputEntry)  \
			and widget.get_property('visible') \
			and widget.get_property('sensitive'):
				valid.append(self.widgets[name].get_input_valid())
				#~ print('>', name, valid[-1])
		#~ print('=', all(valid))

		valid = all(valid)
		if self._input_valid != valid:
			self._input_valid = valid
			self.emit('input-valid-changed')

	def _get_radiogroup(self, name):
		name += ':'
		group = [k for k in self._widgets if k.startswith(name)]
		return [(k, self.widgets[k]) for k in group]

	def on_activate_widget(self, widget):
		if widget == self._default_activate \
		or not self._focus_next(widget, activatable=True):
			self.emit('last-activated')

	def focus_first(self):
		'''Focus the first widget in the form'''
		return self._focus_next(None)

	def focus_next(self):
		'''Focus the next input in the form'''
		widget = self.get_focus_child()
		if widget:
			return self._focus_next(widget)
		else:
			return False

	def _focus_next(self, widget, activatable=False):
		# If 'activatable' is True we only focus widgets that have
		# an 'activated' signal (mainly just TextEntries). This is used
		# to fine tune the last-activated signal
		if widget is None:
			i = 0
		else:
			for k, v in list(self.widgets.items()):
				if v == widget:
					i = self._widgets.index(k) + 1
					break
			else:
				raise ValueError

		for k in self._widgets[i:]:
			widget = self.widgets[k]
			if widget.get_property('sensitive') \
			and widget.get_property('visible') \
			and not (
				activatable
				and not isinstance(widget, (Gtk.Entry, Gtk.ComboBox))
			):
				widget.grab_focus()
				return True
		else:
			return False

	#}

	#{ Dict access methods

	def __getitem__(self, key):
		if not key in self._keys:
			raise KeyError(key)
		elif key in self.widgets:
			widget = self.widgets[key]
			if isinstance(widget, LinkEntry):
				return widget.get_text() # Could be either page or file
			elif isinstance(widget, (PageEntry, NamespaceEntry)):
				return widget.get_path()
			elif isinstance(widget, FSPathEntry):
				return widget.get_path()
			elif isinstance(widget, InputEntry):
				return widget.get_text()
			elif isinstance(widget, Gtk.CheckButton):
				return widget.get_active()
			elif isinstance(widget, Gtk.ComboBox):
				if hasattr(widget, 'zim_key_mapping'):
					label = widget.get_active_text()
					return widget.zim_key_mapping.get(label) or label
				else:
					return widget.get_active_text()
			elif isinstance(widget, Gtk.SpinButton):
				return int(widget.get_value())
			elif isinstance(widget, Gtk.ColorButton):
				return widget.get_rgba().to_string()
			else:
				raise TypeError(widget.__class__.name)
		else:
			# Group of RadioButtons
			for name, widget in self._get_radiogroup(key):
				if widget.get_active():
					x, name = name.rsplit(':', 1)
						# using rsplit to assure another ':' in the
						# group name is harmless
					return name

	def __setitem__(self, key, value):
		if not key in self._keys:
			raise KeyError(key)
		elif key in self.widgets:
			widget = self.widgets[key]
			if isinstance(widget, LinkEntry):
				assert isinstance(value, str)
				widget.set_text(value)
			elif isinstance(widget, (PageEntry, NamespaceEntry)):
				if isinstance(value, Path):
					widget.set_path(value)
				else:
					widget.set_text(value or '')
			elif isinstance(widget, FSPathEntry):
				if isinstance(value, (File, Dir)):
					widget.set_path(value)
				else:
					widget.set_text(value or '')
			elif isinstance(widget, InputEntry):
				value = value or ''
				widget.set_text(value)
			elif isinstance(widget, Gtk.CheckButton):
				widget.set_active(value)
			elif isinstance(widget, Gtk.ComboBox):
				if hasattr(widget, 'zim_key_mapping'):
					for key, v in list(widget.zim_key_mapping.items()):
						if v == value:
							gtk_combobox_set_active_text(widget, key)
							break
					else:
						gtk_combobox_set_active_text(widget, value)
				else:
					gtk_combobox_set_active_text(widget, value)
			elif isinstance(widget, Gtk.SpinButton):
				widget.set_value(value)
			elif isinstance(widget, Gtk.ColorButton):
				rgba = Gdk.RGBA()
				rgba.parse(value)
				widget.set_rgba(rgba)
			else:
				raise TypeError(widget.__class__.name)
		else:
			# RadioButton
			widget = self.widgets[key + ':' + value]
			widget.set_active(True)

	def __iter__(self):
		return iter(self._keys)

	def __contains__(self, key):
		return key in self._keys

	def keys(self):
		return self._keys

	def items(self):
		return [(k, self[k]) for k in self._keys]

	def update(self, map):
		'''Update the value for any existing widget to the value
		given in C{map}. Unkown keys in C{map} are ignored and
		widgets that do not have a value in C{map} keep their
		original value.
		@param map: a dict with new values for the widgets
		'''
		for key, value in list(map.items()):
			if key in self._keys:
				self[key] = value

	def copy(self):
		'''Copy the values of all widgets in the form into a normal dict
		@returns: a dict with widget values
		'''
		values = {}
		for key in self._keys:
			values[key] = self[key]
		return values

	#}


class InputEntry(Gtk.Entry):
	'''Sub-class of C{Gtk.Entry} with support for highlighting
	mal-formatted inputs and handles UTF-8 decoding. This class must be
	used as a generic replacement for C{Gtk.Entry} to avoid UTF-8
	issues. (This is enforced by the zim test suite which will throw an
	error for any module using C{Gtk.Entry} directly.)

	The widget has a "valid" state which determines if the content is
	well formed or not. When the state is invalid the widget will have
	a red background color. This is used e.g. in dialog response
	handlers to show the user what widget to modify.

	The valid state can be either done manually by calling
	L{set_input_valid()}, or it can be done automatically by providing
	a function to check what content is valid. Using a function is
	recommended because it gives more immediate feedback to the user.

	@signal: C{input-valid-changes ()}: valid state of the widget changed
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'input-valid-changed': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	ERROR_COLOR = '#EF7F7F' # light red (derived from Tango style guide)

	def __init__(self, check_func=None, allow_empty=True, show_empty_invalid=False, placeholder_text=None, allow_whitespace=False):
		'''Constructor

		@param check_func: a function to check input is valid.
		This function will be called with the current text as argument
		and should return C{True} if this text is a valid input.

		@param allow_empty: if C{False} an empty string is considered
		invalid input

		@param show_empty_invalid: if C{True} a red background is also
		shown when the entry is still empty, if C{False} the background
		is kept normal even if the empty input is invalid. Without this
		option a whole input form would start in red color, which looks
		bad.

		@param placeholder_text: text to show in the widget when it is
		empty and does not have focus, text will be shown in a
		color different from normal text and disappear when the user
		selects the widget. Used to set hints on the usage of the
		widget.

		@param allow_whitespace: if C{True} allow trailing whitespace
		or even string containing only whitespace. If C{False} all
		whitespace is stripped.
		'''
		GObject.GObject.__init__(self)
		self._normal_color = None
		self.allow_empty = allow_empty
		self.show_empty_invalid = show_empty_invalid
		self.allow_whitespace = allow_whitespace
		self.set_placeholder_text(placeholder_text)
		self.check_func = check_func
		self._input_valid = False
		self.update_input_valid()
		self.connect('changed', self.__class__.update_input_valid)

		def _init_base_color(*a):
			# This is handled on expose event, because style does not
			# yet reflect theming on construction
			if self._normal_color is None:
				self._normal_color = self.style.base[Gtk.StateType.NORMAL]
				self._set_base_color(self.get_input_valid())

		#self.connect('expose-event', _init_base_color)

	def set_check_func(self, check_func):
		'''Set a function to check whether input is valid or not
		@param check_func: the function
		'''
		self.check_func = check_func
		self.emit('changed')

	def set_icon(self, icon, cb_func, tooltip=None):
		'''Add an icon in the entry widget behind the text

		@param icon: the icon as stock ID
		@param cb_func: the callback when the icon is clicked; the
		callback will be called without any arguments
		@param tooltip: tooltip text for the icon

		@returns: C{True} if successfull, C{False} if not supported
		by Gtk version

		@todo: add argument to set tooltip on the icon
		'''
		self.set_property('secondary-icon-stock', icon)
		if tooltip:
			self.set_property('secondary-icon-tooltip-text', tooltip)

		def on_icon_press(self, icon_pos, event):
			if icon_pos == Gtk.EntryIconPosition.SECONDARY:
				cb_func()
		self.connect('icon-press', on_icon_press)

		return True

	def set_icon_to_clear(self):
		'''Adds a "clear" icon in the entry widget

		This method calls L{set_icon()} with the right defaults for
		a stock "Clear" icon. In addition it makes the icon insensitive
		when there is no text in the entry. Clicking the icon will
		clear the entry.

		@returns: C{True} if successfull, C{False} if not supported
		by Gtk version
		'''
		self.set_icon(Gtk.STOCK_CLEAR, self.clear, _('Clear'))
			# T: tooltip for the inline icon to clear a text entry widget

		def check_icon_sensitive(self):
			text = self.get_text()
			self.set_property('secondary-icon-sensitive', bool(text))

		check_icon_sensitive(self)
		self.connect('changed', check_icon_sensitive)

		return True

	def get_text(self):
		'''Get the text from the widget. Like C{Gtk.Entry.get_text()}
		but with UTF-8 decoding and whitespace stripped.
		@returns: string
		'''
		text = Gtk.Entry.get_text(self)
		if not text:
			return ''
		elif self.allow_whitespace:
			return text
		else:
			return text.strip()

	def get_input_valid(self):
		'''Get the valid state.
		@returns: C{True} if the input is valid
		'''
		return self._input_valid

	def set_input_valid(self, valid, show_empty_invalid=None):
		'''Set input valid or invalid state
		@param valid: C{True} or C{False}
		@param show_empty_invalid: if not C{None} change the
		C{show_empty_invalid} attribute
		'''
		if show_empty_invalid is not None:
			self.show_empty_invalid = show_empty_invalid

		if valid == self._input_valid:
			return

		#if self._normal_color:
		#	self._set_base_color(valid)
		# else: not yet initialized

		self._input_valid = valid
		self.emit('input-valid-changed')

	def _set_base_color(self, valid):
		if valid \
		or (not self.get_text() and not self.show_empty_invalid):
			self.modify_base(Gtk.StateType.NORMAL, self._normal_color)
		else:
			self.modify_base(Gtk.StateType.NORMAL, Gdk.color_parse(self.ERROR_COLOR))

	def clear(self):
		'''Clear the text in the entry'''
		self.set_text('')

	def update_input_valid(self):
		text = self.get_text() or ''
		if self.check_func:
			self.set_input_valid(self.check_func(text))
		else:
			self.set_input_valid(bool(text) or self.allow_empty)


class FSPathEntry(InputEntry):
	'''Base class for L{FileEntry} and L{FolderEntry}, handles input of
	file system paths.

	File paths can either be absolute paths or relative to the notebook.
	When a notebook and optionally a page path are set,
	L{Notebook.resolve_file()<zim.notebook.Notebook.resolve_file()>} is
	used to make file paths relative.

	This class should not be instantiated directly, use either
	L{FileEntry} or L{FolderEntry}.

	@todo: add completion for file paths - make sure both absolute
	and relative paths are supported + re-use this completion in
	L{LinkEntry}
	'''

	def __init__(self):
		InputEntry.__init__(self, allow_empty=False)
		self.notebook = None
		self.notebookpath = None
		self.action = None
		self.file_type_hint = None

	def set_use_relative_paths(self, notebook, path=None):
		'''Set the notebook and path to be used for relative paths.

		@param notebook: the L{Notebook} object for resolving paths
		or C{None} to disable relative paths.
		@param path: a L{Path} object used for resolving relative links
		'''
		self.notebook = notebook
		self.notebookpath = path

	def set_path(self, path):
		'''Set the file path for this entry
		@param path: a L{File} or L{Dir} object
		'''
		assert isinstance(path, (File, Dir))
		if self.notebook:
			text = self.notebook.relative_filepath(path, self.notebookpath)
			if text is None:
				if self.notebook.document_root:
					text = path.uri
				else:
					text = path.path
			self.set_text(text)
		else:
			self.set_text(path.user_path or path.path)

	def get_path(self):
		'''Get the file path for this entry
		@returns: a L{File} or L{Dir} object (depending on sub-class)
		'''
		text = self.get_text()
		if text:
			if self.notebook:
				path = self.notebook.resolve_file(text, self.notebookpath)
				if path:
					return self._class(path.path)

			return self._class(text)
		else:
			return None

	def popup_dialog(self):
		'''Run a dialog to browse for a file or folder.
		Used by the 'browse' button in input forms.
		'''
		window = self.get_toplevel()
		if self.action == Gtk.FileChooserAction.SELECT_FOLDER:
			title = _('Select Folder') # T: dialog title
		elif self.file_type_hint == 'image':
			title = _('Select Image') # T: dialog title
		else:
			title = _('Select File') # T: dialog title

		dialog = FileDialog(window, title, self.action)
		if self.file_type_hint == 'image':
			dialog.add_filter_images()

		if self.notebook:
			dialog.add_shortcut(self.notebook, self.notebookpath)

		path = FSPathEntry.get_path(self) # overloaded in LinkEntry
		if path:
			dialog.set_file(path)
		elif self.notebook and self.notebookpath:
			page = self.notebook.get_page(self.notebookpath)
			dialog.set_current_dir(page.source.dir)
		elif self.notebook:
			dialog.set_current_dir(self.notebook.folder)


		file = dialog.run()
		if not file is None:
			FSPathEntry.set_path(self, file)


class FileEntry(FSPathEntry):
	'''Widget to select a file'''

	_class = File

	def __init__(self, file=None, new=False):
		'''Constructor.

		@param file: a L{File} object
		@param new: if C{True} the intention is a new file
		(e.g. output file), or to overwrite an existing file.
		If C{False} only existing files can be selected.
		'''
		FSPathEntry.__init__(self)
		self.file_type_hint = 'file'
		if new:
			self.action = Gtk.FileChooserAction.SAVE
		else:
			self.action = Gtk.FileChooserAction.OPEN

		if file:
			self.set_file(file)

	set_file = FSPathEntry.set_path
	get_file = FSPathEntry.get_path


class FolderEntry(FSPathEntry):
	'''Widget to select a folder'''

	_class = Dir

	def __init__(self, folder=None):
		'''Constructor

		@param folder: a L{Dir} object
		'''
		FSPathEntry.__init__(self)
		self.file_type_hint = 'dir'
		self.action = Gtk.FileChooserAction.SELECT_FOLDER

		if folder:
			self.set_folder(folder)

	set_folder = FSPathEntry.set_path
	get_folder = FSPathEntry.get_path


def gtk_entry_completion_match_func(completion, key, iter, column):
	if key is None:
		return False

	model = completion.get_model()
	text = to_utf8_normalized_casefolded(model.get_value(iter, column))
	if text is not None:
		return key in text
	else:
		return False


def gtk_entry_completion_match_func_startswith(completion, key, iter, column):
	if key is None:
		return False

	model = completion.get_model()
	text = to_utf8_normalized_casefolded(model.get_value(iter, column))
	if text is not None:
		return text.startswith(key)
	else:
		return False


class PageEntry(InputEntry):
	'''Widget to select a zim page path

	This widget features completion for existing page names and shows
	whether the entered text is not a valid page name.

	The page paths can be shown eitehr absolute or relative. If a
	reference path is given paths will be shown relative to this reference.
	'''

	_allow_select_root = False
		# This attribute implements logic needed for NamespaceEntry

	def __init__(self, notebook, path=None, subpaths_only=False, existing_only=False):
		'''Constructor

		@param notebook: the L{Notebook} object for resolving paths and
		completing existing pages, but allowed to be C{None} e.g. for testing
		@param path: a L{Path} object used for resolving relative links
		@param subpaths_only: if C{True} the input will always be
		considered a child 'C{path}'
		@param existing_only: if C{True} only allow to select existing pages

		@note: 'C{subpaths_only}' and 'C{existing_only}' can also be set
		using the like named attributes
		'''
		self.notebook = notebook
		self.notebookpath = path
		self.subpaths_only = subpaths_only
		self.existing_only = existing_only

		if self._allow_select_root:
			placeholder_text = _('<Top>')
			# T: default text for empty page section selection
		else:
			placeholder_text = None
		InputEntry.__init__(self, allow_empty=self._allow_select_root, placeholder_text=placeholder_text)
		assert path is None or isinstance(path, Path)

		completion = Gtk.EntryCompletion()
		completion.set_model(Gtk.ListStore(str, str)) # visible name, match name
		completion.set_text_column(0)
		self.set_completion(completion)

		self.connect_after('changed', self.__class__.update_completion)

	def set_use_relative_paths(self, notebook, path=None):
		'''Set the notebook and path to be used for relative paths.

		@param notebook: the L{Notebook} object for resolving paths and
		completing existing pages, or C{None} to disable relative paths.
		@param path: a L{Path} object used for resolving relative links
		'''
		self.notebook = notebook
		self.notebookpath = path

	def set_path(self, path):
		'''Set the path to be shown in the entry.
		If you have the link as a string, use L{set_text()} instead

		@param path: L{Path} object
		'''
		if self.subpaths_only:
			assert path.ischild(self.notebookpath)
		self.set_text(':' + path.name)

	def get_path(self):
		'''Get the path shown in the widget.
		If C{None} is returned the widget is flagged as invalid. So e.g. in a
		dialog you can get a path and refuse to close a dialog if the path
		is None and the user will automatically be alerted to the missing input.

		@returns: a L{Path} object or C{None} is no valid path was entered
		'''
		name = self.get_text().strip()
		if self._allow_select_root and (name == ':' or not name):
			self.set_input_valid(True)
			return Path(':')
		elif not name:
			self.set_input_valid(False)
			return None
		else:
			if self.subpaths_only and name[0] not in ('+', ':'):
				name = '+' + name

			try:
				if self.notebook:
					path = self.notebook.pages.lookup_from_user_input(
						name, reference=self.notebookpath
					)
				else:
					if name.startswith('+') and self.notebookpath:
						name = self.notebookpath.name + ':' + name[1:]
					name = Path.makeValidPageName(name)
					path = Path(name)
			except ValueError:
				logger.warn('Invalid path name: %s', name)
				self.set_input_valid(False)
				return None
			else:
				self.set_input_valid(True)
				if self.existing_only:
					try:
						page = self.notebook.get_page(path)
						if not page.exists():
							return None
					except PageNotFoundError:
						return None
				return path

	def update_input_valid(self):
		# Update valid state
		text = self.get_text()

		if not text:
			if self.existing_only:
				self.set_input_valid(False)
			else:
				self.set_input_valid(True)
				# FIXME: why should pageentry always allow empty input ?
		elif text in (':', '+'):
			pass
		elif text.startswith('+') and not self.notebookpath:
			self.set_input_valid(False)
		else:
			try:
				Path.assertValidPageName(text.lstrip('+').strip(':'))
			except AssertionError:
				self.set_input_valid(False)
			else:
				if self.existing_only:
					path = self.get_path() # get_path() checks existence
					self.set_input_valid(not path is None)
				else:
					self.set_input_valid(True)

	def update_completion(self):
		# Start completion
		if not self.notebook:
			return # no completion without a notebook

		text = self.get_text()
		completion = self.get_completion()
		if completion is None:
			return # during tests in certain cases the completion is not yet initialized
		model = completion.get_model()
		model.clear()

		if not text or not self.get_input_valid():
			return

		if ':' in text:
			i = text.rfind(':')
			prefix = text[:i + 1] # can still start with "+"
			if prefix == ':':
				path = Path(':')
			else: # resolve page
				reference = self.notebookpath or Path(':')
				link = prefix
				if self.subpaths_only and not link.startswith('+'):
					link = '+' + link.lstrip(':')

				try:
					path = self.notebook.pages.lookup_from_user_input(link, reference)
				except ValueError:
					return

			try:
				self._fill_completion_for_anchor(path, prefix, text)
			except IndexNotFoundError:
				pass

		elif text.startswith('+'):
			prefix = '+'
			path = self.notebookpath

			try:
				self._fill_completion_for_anchor(path, prefix, text)
			except IndexNotFoundError:
				pass

		else:
			path = self.notebookpath or Path(':')

			try:
				self._fill_completion_any(path, text)
			except IndexNotFoundError:
				pass

		self.get_completion().complete()

	def _fill_completion_for_anchor(self, path, prefix, text):
		#print "COMPLETE ANCHOR", path, prefix, text
		# Complete a single namespace based on the prefix
		# TODO: allow filter on "text" directly in SQL call
		completion = self.get_completion()
		completion.set_match_func(gtk_entry_completion_match_func_startswith, 1)

		model = completion.get_model()
		assert text.startswith(prefix)
		lowertext = text.lower()
		for p in self.notebook.pages.list_pages(path):
			string = prefix + p.basename
			if string.lower().startswith(lowertext):
				model.append((string, string))


	def _fill_completion_any(self, path, text):
		#print "COMPLETE ANY", path, text
		# Complete all matches of "text"
		# start with children and peers, than peers of parents, than rest of tree
		completion = self.get_completion()
		completion.set_match_func(gtk_entry_completion_match_func, 1)

		# TODO: use SQL to list all at once instead of walking and filter on "text"
		#       do better sorting as well ?

		def relative_link(target):
			href = self.notebook.pages.create_link(path, target)
			return href.to_wiki_link()

		model = completion.get_model()
		searchpath = list(path.parents())
		searchpath.insert(1, path) # children after peers but before parents
		for namespace in searchpath:
			for p in self.notebook.pages.match_pages(namespace, text):
				link = relative_link(p)
				model.append((link, p.basename))

			if len(model) > 10:
				break
		else:
			for p in self.notebook.pages.match_all_pages(text, limit=20):
				if p.parent not in searchpath:
					link = relative_link(p)
					model.append((link, p.basename))


class NamespaceEntry(PageEntry):
	'''Widget to select a zim page path as a namespace

	Use this instead of L{PageEntry} when you want to allow selecting a
	namespace. E.g. this will be allowed to select ":" or empty string
	for the root namespace, which is not allowed in PageEntry.
	'''

	_allow_select_root = True


class LinkEntry(PageEntry, FileEntry):
	'''Widget entering links in zim pages. This widget accepts either
	zim page paths, file paths and URLs.
	'''

	_class = File

	def __init__(self, notebook, path=None):
		'''Constructor

		@param notebook: the L{Notebook} object for resolving paths and
		completing existing pages, but allowed to be C{None} e.g. for testing
		@param path: a L{Path} object used for resolving relative links
		'''
		PageEntry.__init__(self, notebook, path)
		self.action = Gtk.FileChooserAction.OPEN
		self.file_type_hint = None

	def get_path(self):
		# Check we actually got a valid path
		text = self.get_text()
		if text:
			type = link_type(text)
			if type == 'page':
				return PageEntry.get_path(self)
			else:
				return None
		else:
			return None

	def update_input_valid(self):
		# Switch between path completion and file completion
		text = self.get_text()
		if text:
			type = link_type(text)
			if type == 'page':
				PageEntry.update_input_valid(self)
			#~ elif type == 'file':
				#~ FileEntry.update_input_valid(self)
			else:
				self.set_input_valid(True)
		else:
			self.set_input_valid(True)


def format_title(title):
	'''Formats a window title (in fact just adds " - Zim" to the end).'''
	assert not title.lower().endswith(' zim')
	return '%s - Zim' % title


def get_window(widget):
	if widget and hasattr(widget, 'get_toplevel'):
		window = widget.get_toplevel()
		return window if isinstance(window, Gtk.Window) else None
	else:
		return None


class uistate_property(object):
	'''Class for uistate get/set attributes'''

	def __init__(self, key, *default):
		self.key = key
		self.default = default

	def __get__(self, obj, klass):
		if obj:
			if not self.key in obj.uistate:
				obj.uistate.setdefault(self.key, *self.default)
			return obj.uistate[self.key]

	def __set__(self, obj, value):
		obj.uistate[self.key] = value


# Some constants used to position widgets in the window panes
# These are named rather than numbered because they also appear
# in plugin preferences as options and as uistate keys

LEFT_PANE = 'left_pane' #: Left pane position in window
RIGHT_PANE = 'right_pane' #: Right pane position in window
TOP_PANE = 'top_pane' #: Top pane position in window
BOTTOM_PANE = 'bottom_pane' #: Bottom pane position in window

PANE_POSITIONS = (
	(LEFT_PANE, _('Left Side Pane')), # T: Option for placement of plugin widgets
	(RIGHT_PANE, _('Right Side Pane')), # T: Option for placement of plugin widgets
	(BOTTOM_PANE, _('Bottom Pane')), # T: Option for placement of plugin widgets
	(TOP_PANE, _('Top Pane')), # T: Option for placement of plugin widgets
)


def _hide(widget):
	widget.hide()
	widget.set_no_show_all(True)


def _show(widget):
	widget.set_no_show_all(False)
	widget.show_all()


class WindowSidePane(Gtk.VBox):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'close': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	def __init__(self, position):
		GObject.GObject.__init__(self)
		self.set_name('zim-sidepane')
		self.key = position

		# Add bar with label and close button
		self.topbar = Gtk.HBox()
		self.topbar.pack_end(self._close_button(), False, True, 0)
		self.pack_start(self.topbar, False, True, 0)

		# Add notebook
		self.notebook = Gtk.Notebook()
		self.notebook.set_show_border(False)
		button = self._close_button()
		self.notebook.set_action_widget(button, Gtk.PackType.END)

		self.add(self.notebook)

		self._update_topbar()

	_arrow_directions = {
		TOP_PANE: Gtk.ArrowType.UP,
		BOTTOM_PANE: Gtk.ArrowType.DOWN,
		LEFT_PANE: Gtk.ArrowType.LEFT,
		RIGHT_PANE: Gtk.ArrowType.RIGHT,
	}

	def _close_button(self):
		arrow = Gtk.Arrow(self._arrow_directions[self.key], Gtk.ShadowType.NONE)
		button = Gtk.Button()
		button.add(arrow)
		button.set_alignment(0.5, 0.5)
		button.set_relief(Gtk.ReliefStyle.NONE)
		button.connect('clicked', lambda o: self.emit('close'))
		return button

	def _update_topbar(self):
		children = self.get_children()
		n_pages = self.notebook.get_n_pages()

		for child in children + self.notebook.get_children():
			if isinstance(child, WindowSidePaneWidget):
				child.set_embeded_closebutton(None)

		assert children[0] == self.topbar

		if n_pages == 0:
			self._show_empty_topbar()
		elif n_pages == 1:
			self._show_single_tab()
		else:
			self._show_multiple_tabs()

	def _set_topbar_label(self, label):
		assert isinstance(label, Gtk.Label)
		label.set_alignment(0.03, 0.5)
		for child in self.topbar.get_children():
			if isinstance(child, Gtk.Label):
				child.destroy()
		self.topbar.pack_start(label, True, True, 0)

	def _show_empty_topbar(self):
		self.notebook.set_show_tabs(False)
		_hide(self.notebook.get_action_widget(Gtk.PackType.END))

		self._set_topbar_label(Gtk.Label(label=''))
		_show(self.topbar)

	def _show_single_tab(self):
		self.notebook.set_show_tabs(False)
		_hide(self.notebook.get_action_widget(Gtk.PackType.END))

		child = self.notebook.get_nth_page(0)
		self._set_topbar_label(child.get_title_label())
		if isinstance(child, WindowSidePaneWidget) \
			and child.set_embeded_closebutton(self._close_button()):
				_hide(self.topbar)
		else:
			_show(self.topbar)

	def _show_multiple_tabs(self):
		self.notebook.set_show_tabs(True)
		self._set_topbar_label(Gtk.Label(label=''))
		# Show close button next to notebook tabs
		_show(self.notebook.get_action_widget(Gtk.PackType.END))
		_hide(self.topbar)

	def add_tab(self, key, widget):
		assert isinstance(widget, WindowSidePaneWidget)
		assert widget.title is not None
		widget.tab_key = key
		self.notebook.append_page(widget, widget.get_title_label())
		self._update_topbar()

	def remove(self, widget):
		if widget in self.notebook.get_children():
			self.notebook.remove(widget)
			self._update_topbar()
			return True
		else:
			return False

	def is_empty(self):
		return self.notebook.get_n_pages() == 0

	def grab_focus(self):
		if self.is_empty():
			return

		widget = gtk_notebook_get_active_page(self.notebook)
		if widget:
			widget.grab_focus()
		elif self.notebook.get_n_pages() > 0:
			self.notebook.set_current_page(0)
			widget = self.notebook.get_nth_page(0)
			widget.grab_focus()

	def do_key_press_event(self, event):
		if event.keyval == KEYVAL_ESC:
			self.emit('close')
			return True
		else:
			return Gtk.VBox.do_key_press_event(self, event)


class MinimizedTabs(object):

	def __init__(self, sidepane, angle):
		self.status_bar_style = False
		assert angle in (0, 90, 270)
		self._angle = angle
		self._update(sidepane.notebook)
		for signal in ('page-added', 'page-reordered', 'page-removed'):
			sidepane.notebook.connect(signal, self._update)

	def _update(self, notebook, *a):
		for child in self.get_children():
			child.destroy()

		if self._angle in (90, 270): # Hack to introduce some empty space
			label = Gtk.Label(label=' ')
			self.pack_start(label, False, True, 0)

		ipages = list(range(notebook.get_n_pages()))
		if self._angle == 90:
			ipages = reversed(ipages) # keep order the same in reading direction

		for i in ipages:
			child = notebook.get_nth_page(i)
			button = Gtk.Button()
			button.add(child.get_title_label())
			if self.status_bar_style:
				button_set_statusbar_style(button)
			else:
				button.set_relief(Gtk.ReliefStyle.NONE)
			button.connect('clicked', self._on_click, child.tab_key)
			if self._angle != 0:
				button.get_child().set_angle(self._angle)
			else:
				self.pack_start(Gtk.Separator(), False, True, 0)
			self.pack_start(button, False, True, 0)
			button.show_all()

	def _on_click(self, b, text):
		self.emit('clicked', text)


class HMinimizedTabs(Gtk.HBox, MinimizedTabs):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'clicked': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	def __init__(self, sidepane, angle=0):
		GObject.GObject.__init__(self)
		self.set_spacing(0)
		MinimizedTabs.__init__(self, sidepane, angle)


class VMinimizedTabs(Gtk.VBox, MinimizedTabs):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'clicked': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	def __init__(self, sidepane, angle=90):
		GObject.GObject.__init__(self)
		self.set_spacing(12)
		MinimizedTabs.__init__(self, sidepane, angle)


class WindowSidePaneWidget(ConnectorMixin):
	'''Base class for widgets that want to integrate nicely in the
	L{WindowSidePane}
	'''

	def get_title_label(self):
		label = Gtk.Label(label=self.title)
		if not hasattr(self, '_title_labels'):
			self._title_labels = set()
		self._title_labels.add(label)
		label.connect('destroy', self._drop_label)
		return label

	def _drop_label(self, label):
		if hasattr(self, '_title_labels'):
			self._title_labels.remove(label)

	def set_title(self, text):
		self.title = text
		if hasattr(self, '_title_labels'):
			for label in self._title_labels:
				label.set_text(text)

	def set_embeded_closebutton(self, button):
		'''Embed a button in the widget to close the side pane
		@param button: a button widget or C{None} to unset
		@returns: C{True} if supported and successfull
		'''
		return False


from zim.config import ConfigDefinition, ConfigDefinitionByClass

class ConfigDefinitionPaneToggle(ConfigDefinition):

	def __init__(self, default, window):
		ConfigDefinition.__init__(self, default)
		self.window = window

	def check(self, value):
		# Must be list of valid pane names
		if isinstance(value, str):
			value = self._eval_string(value)

		if isinstance(value, (tuple, list)) \
		and all(e in self.window._zim_window_sidepanes for e in value):
			return value
		else:
			raise ValueError('Unknown pane names in: %s' % value)


class ConfigDefinitionPaneState(ConfigDefinitionByClass):
	# Check value is state as used by set_pane_state() and
	# get_pane_state(), so 3 elements: boolean, integer and
	# a label or None

	def __init__(self, default):
		ConfigDefinitionByClass.__init__(self, default, klass=tuple)

	def check(self, value):
		value = ConfigDefinitionByClass.check(self, value)
		if isinstance(value, (tuple, list)) \
		and len(value) == 3 \
		and isinstance(value[0], bool) \
		and isinstance(value[1], int) \
		and (value[2] is None or isinstance(value[2], str)):
			return value
		else:
			raise ValueError('Value is not a valid pane state')


class Window(Gtk.Window):
	'''Sub-class of C{Gtk.Window} that will take care of hooking
	the window into the application framework and adds entry points
	so plugins can add side panes etc. It will divide the window
	horizontally in 3 panes, and the center pane again vertically in 3.
	The result is something like this::

		+-----------------------------+
		|menu                         |
		+-----+----------------+------+
		|     |  top pane      |      |
		|     |                |      |
		| s   +----------------+  s   |
		| i   | Main widget    |  i   |
		| d   |                |  d   |
		| e   |                |  e   |
		| b   +----------------+  b   |
		| a   |tabs|           |  a   |
		| r   | bottom pane    |  r   |
		|     |                |      |
		+----------------------+------+

	Any pane that is not used will not been shown. The important thing
	is to create placeholders where plugins *might* want to add some
	widget.

	All windows in zim must inherit from this class.

	@signal: C{pane-state-changed (pane, visible, active)}: emitted when
	visibility or active tab changed for a specific pane
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'pane-state-changed': (GObject.SignalFlags.RUN_LAST, None, (object, bool, object)),
	}

	def __init__(self):
		GObject.GObject.__init__(self)
		self._registered = False
		self._last_sidepane_focus = None

		# Construct all the components
		self._zim_window_main = Gtk.VBox() # contains bars & central hbox

		self._zim_window_central_hbox = Gtk.HBox() # contains left paned(right paned(central vbox))
		self._zim_window_left_paned = HPaned()
		self._zim_window_right_paned = HPaned()
		self._zim_window_central_vbox = Gtk.VBox() # contains top pane(bottom pane)
		self._zim_window_top_paned = VPaned()
		self._zim_window_bottom_paned = VPaned()

		self._zim_window_left_pane = WindowSidePane(LEFT_PANE)
		self._zim_window_right_pane = WindowSidePane(RIGHT_PANE)
		self._zim_window_top_pane = WindowSidePane(TOP_PANE)
		self._zim_window_bottom_pane = WindowSidePane(BOTTOM_PANE)

		self._zim_window_left_minimized = VMinimizedTabs(self._zim_window_left_pane)
		self._zim_window_right_minimized = VMinimizedTabs(self._zim_window_right_pane, angle=270)
		self._zim_window_top_minimized = HMinimizedTabs(self._zim_window_top_pane)
		self._zim_window_bottom_minimized = HMinimizedTabs(self._zim_window_bottom_pane)

		# put it all together ...
		Gtk.Window.add(self, self._zim_window_main)
		self._zim_window_main.add(self._zim_window_central_hbox)
		self._zim_window_central_hbox.pack_start(self._zim_window_left_minimized, False, True, 0)
		self._zim_window_central_hbox.add(self._zim_window_left_paned)
		self._zim_window_central_hbox.pack_start(self._zim_window_right_minimized, False, True, 0)
		self._zim_window_left_paned.pack1(self._zim_window_left_pane, resize=False)
		self._zim_window_left_paned.pack2(self._zim_window_right_paned, resize=True)
		self._zim_window_right_paned.pack1(self._zim_window_central_vbox, resize=True)
		self._zim_window_right_paned.pack2(self._zim_window_right_pane, resize=False)
		self._zim_window_central_vbox.pack_start(self._zim_window_top_minimized, False, True, 0)
		self._zim_window_central_vbox.add(self._zim_window_top_paned)
		self._zim_window_central_vbox.pack_start(self._zim_window_bottom_minimized, False, True, 0)
		self._zim_window_top_paned.pack1(self._zim_window_top_pane, resize=False)
		self._zim_window_top_paned.pack2(self._zim_window_bottom_paned, resize=True)
		self._zim_window_bottom_paned.pack2(self._zim_window_bottom_pane, resize=True)

		self._zim_window_sidepanes = {
			LEFT_PANE: (
				self._zim_window_left_paned,
				self._zim_window_left_pane,
				self._zim_window_left_minimized
			),
			RIGHT_PANE: (
				self._zim_window_right_paned,
				self._zim_window_right_pane,
				self._zim_window_right_minimized
			),
			TOP_PANE: (
				self._zim_window_top_paned,
				self._zim_window_top_pane,
				self._zim_window_top_minimized
			),
			BOTTOM_PANE: (
				self._zim_window_bottom_paned,
				self._zim_window_bottom_pane,
				self._zim_window_bottom_minimized
			),
		}

		def _on_switch_page(notebook, page, pagenum, key):
			visible, size, active = self.get_pane_state(key)
			self.emit('pane-state-changed', key, visible, active)

		for key, value in list(self._zim_window_sidepanes.items()):
			paned, pane, minimized = value
			pane.set_no_show_all(True)
			pane.connect('close', lambda o, k: self.set_pane_state(k, False), key)
			pane.zim_pane_state = (False, 200, None)
			minimized.set_no_show_all(True)
			minimized.connect('clicked', lambda o, a, k: self.set_pane_state(k, True, activetab=a), key)

			pane.notebook.connect_after('switch-page', _on_switch_page, key)

	def add(self, widget):
		'''Add the main widget.
		@param widget: gtk widget to add in the window
		'''
		self._zim_window_bottom_paned.pack1(widget, resize=True)

	def add_bar(self, widget, start=True):
		'''Add a bar to top or bottom of the window. Used e.g. to add
		menu-, tool- & status-bars.
		@param widget: gtk widget for the bar
		@param start: if C{True} add to top of window, else to bottom
		'''
		self._zim_window_main.pack_start(widget, False, True, 0)

		if start:
			# reshuffle widget to go above main widgets but
			# below earlier added bars
			i = self._zim_window_main.child_get_property(
					self._zim_window_central_hbox, 'position')
			self._zim_window_main.reorder_child(widget, i)

		#self._zim_window_main.set_focus_chain([self._zim_window_left_paned])
			# Force to ignore the bars in keyboard navigation
			# items in the bars are all accesible by accelerators

	def add_center_bar(self, widget):
		'''Add a widget in the central part of the window above the
		page.
		@param widget: the gtk widget to show in the tab
		'''
		self._zim_window_central_vbox.pack_start(widget, False, True, 0)
		self._zim_window_central_vbox.reorder_child(widget, 0)

	def move_bottom_minimized_tabs_to_statusbar(self, statusbar):
		frame = Gtk.Frame()
		frame.set_shadow_type(Gtk.ShadowType.NONE)
		self._zim_window_bottom_minimized.reparent(frame)
		self._zim_window_bottom_minimized.status_bar_style = True
		statusbar.pack_end(frame, False, True, 0)
		frame.show_all()

	def add_tab(self, key, widget, pane):
		'''Add a tab in one of the panes.
		@param key: string that is used to identify this tab in the window state
		@param widget: the gtk widget to show in the tab
		@param pane: can be one of: C{LEFT_PANE}, C{RIGHT_PANE},
		C{TOP_PANE} or C{BOTTOM_PANE}.
		'''
		pane_key = pane
		paned, pane, mini = self._zim_window_sidepanes[pane_key]
		pane.add_tab(key, widget)
		self.set_pane_state(pane_key, True)

	def remove(self, widget):
		'''Remove widget from any pane
		@param widget: the widget to remove
		'''
		if self._last_sidepane_focus == widget:
			self._last_sidepane_focus = None

		for parent in (self._zim_window_central_vbox, self._zim_window_bottom_paned):
			if widget in parent.get_children():
				parent.remove(widget)
				return

		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			paned, pane, mini = self._zim_window_sidepanes[key]
			if pane.remove(widget):
				if pane.is_empty():
					self.set_pane_state(key, False)
				break
		else:
			raise ValueError('Widget not found in this window')

	def init_uistate(self):
		assert self.uistate
		self.uistate.define((
			('toggle_panes', ConfigDefinitionPaneToggle([], self)),
		))

		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			default = self.get_pane_state(key)
			self.uistate.define((
				(key, ConfigDefinitionPaneState(default)),
			))
			self.set_pane_state(key, *self.uistate[key])

	def save_uistate(self):
		assert self.uistate is not None
		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			if key in self.uistate:
				self.uistate[key] = self.get_pane_state(key)
			# else pass - init_uistate() not yet called (!?)

	def get_pane_state(self, pane):
		'''Returns the state of a side pane.
		@param pane: can be one of: C{LEFT_PANE}, C{RIGHT_PANE},
		C{TOP_PANE} or C{BOTTOM_PANE}.
		@returns: a 3-tuple of visibility (boolean),
		pane size (integer), and active tab (string).
		'''
		# FIXME revert calculate size instead of position for left
		# and bottom widget
		key = pane
		paned, pane, mini = self._zim_window_sidepanes[key]
		if pane.get_property('visible'):
			position = paned.get_position()
			widget = gtk_notebook_get_active_page(pane.notebook)
			active = widget.tab_key if widget else None
			return (True, position, active)
		else:
			return pane.zim_pane_state

		return state

	def set_pane_state(self, pane, visible, size=None, activetab=None, grab_focus=False):
		'''Set the state of a side pane.
		@param pane: can be one of: C{LEFT_PANE}, C{RIGHT_PANE},
		C{TOP_PANE} or C{BOTTOM_PANE}.
		@param visible: C{True} to show the pane, C{False} to hide
		@param size: size of the side pane
		@param activetab: key of the active tab in the notebook or None
		(fails silently if tab is not found)
		@param grab_focus: if C{True} active tab will grab focus
		'''
		# FIXME get parent widget size and subtract to get position
		# for left and bottom notebook
		# FIXME enforce size <  parent widget and > 0
		pane_key = pane
		paned, pane, mini = self._zim_window_sidepanes[pane_key]
		if pane.get_property('visible') == visible \
		and size is None and activetab is None:
			if grab_focus:
				pane.grab_focus()
			return # nothing else to do

		oldstate = self.get_pane_state(pane_key)
		if size is None:
			size = oldstate[1]
		if activetab is None:
			activetab = oldstate[2]
		position = size

		if visible:
			if not pane.is_empty():
				mini.hide()
				mini.set_no_show_all(True)
				pane.set_no_show_all(False)
				pane.show_all()
				paned.set_position(position)
				if activetab is not None:
					nb = pane.notebook
					for child in nb.get_children():
						if child.tab_key == activetab:
							num = nb.page_num(child)
							nb.set_current_page(num)
							break

				if grab_focus:
					pane.grab_focus()
			#else:
			#	logger.debug('Trying to show an empty pane...')
		else:
			pane.hide()
			pane.set_no_show_all(True)
			mini.set_no_show_all(False)
			mini.show_all()

		pane.zim_pane_state = (visible, size, activetab)
		self.emit('pane-state-changed', pane_key, visible, activetab)

	def toggle_panes(self, show=None):
		'''Toggle between showing and not showing panes.
		Will remember the panes that were shown last time
		this method was called but defaults to showing
		all panes.
		@param show: if C{True} show panes, if C{False}
		hide them, if C{None} toggle current state
		'''
		# Note that our uistate['toggle_panes'] does not
		# reflect what panes are visible when e.g. restarting zim
		# - this is saved in the pane state uistate - instead it
		# remembers what panes could be shown when toggling.
		visible = bool(self.get_visible_panes())
		if show is None:
			show = not visible
		elif show == visible:
			return # nothing to do

		if show:
			panes = self.uistate['toggle_panes'] \
				or (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE)
			for pane in panes:
				self.set_pane_state(pane, True)
		else:
			self.uistate['toggle_panes'] = [p.key for p in self.get_visible_panes()]
			for pane in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
				self.set_pane_state(pane, False)

	@action(_('_All Panes'), accelerator='<Primary>F9') # T: Menu item
	def show_all_panes(self):
		for pane in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			self.set_pane_state(pane, True)

	def get_visible_panes(self):
		'''Returns a list of panes that are visible'''
		return [p for p in self._panes() if not p.is_empty() and p.get_property('visible')]

	def get_used_panes(self):
		'''Returns a list of panes that are in use (i.e. not empty)'''
		return [p for p in self._panes() if not p.is_empty()]

	def _panes(self):
		return [self._zim_window_sidepanes[key][1]
				for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE)]

	def do_set_focus(self, widget):
		# keep track of last sidepane widget that had focus..
		if widget:
			parent = widget.get_parent()
			while parent:
				if isinstance(parent, WindowSidePane):
					self._last_sidepane_focus = widget
					break
				parent = parent.get_parent()

		return Gtk.Window.do_set_focus(self, widget)

	def focus_sidepane(self):
		try:
			self.focus_last_focussed_sidepane() \
				or self.get_visible_panes()[0].grab_focus()
		except IndexError:
			pass

	def focus_last_focussed_sidepane(self):
		if self._last_sidepane_focus \
		and self._last_sidepane_focus.get_property('visible'):
			self._last_sidepane_focus.grab_focus()
			return True
		else:
			return False

	def pack_start(self, *a):
		raise NotImplementedError("Use add() instead")

	def show(self):
		self.show_all()

	def show_all(self):
		# First register, than init uistate - this ensures plugins
		# are enabled before we finalize the presentation of the window.
		# This is important for state of e.g. panes to work correctly
		if not self._registered:
			self._registered = True
			if hasattr(self, 'uistate'):
				self.init_uistate()

		if not TEST_MODE:
			Gtk.Window.show_all(self)

	def present(self):
		self.show_all()
		if TEST_MODE:
			assert TEST_MODE_RUN_CB, 'Dialog run without test callback'
			TEST_MODE_RUN_CB(self)
		else:
			Gtk.Window.present(self)


class Dialog(Gtk.Dialog, ConnectorMixin):
	'''Sub-class of C{Gtk.Dialog} with a number of convenience methods
	to create dialogs. Also takes care of registering dialogs with the
	main interface object, so plugins can hook into them. Intended as
	base class for all input dialogs in zim. (See L{ErrorDialog},
	L{QuestionDialog}, L{MessageDialog} and L{FileDialog} for other
	dialog types).

	A minimal sub-class should implement a constructor which calls
	L{Dialog.__init__()} and L{Dialog.add_form()} to defined the dialog,
	and implements C{do_response_ok()} to handle the result.

	The C{Dialog} class takes care of calling
	L{ConnecterMixin.disconnect_all()} when it is destroyed. So
	sub-classes can use the L{ConnectorMixin} methods and all callbacks
	will be cleaned up after the dialog.

	@ivar vbox: C{Gtk.VBox} for main widgets of the dialog
	@ivar form: L{InputForm} added by C{add_form()}
	@ivar uistate: L{ConfigDict} to store state of the dialog, persistent
	per notebook. The size and position of the dialog are stored as
	automatically in this dict already.
	@ivar result: result to be returned by L{run()}
	@ivar destroyed: when C{True} the dialog is already destroyed
	'''

	@classmethod
	def unique(klass, handler, *args, **opts):
		'''Constructor which ensures there is only one instance of this
		dialog at a time. It implements a singleton pattern by installing
		a weak reference in the handler object. If there is an dialog
		active which is not yet destroyed, this dialog is returned,
		otherwise a new dialog is created.

		Typically you can use this as::

			dialog = MyDialog.unique(parent, somearg)
			dialog.present()

		@param handler: the object constructing the dialog
		@param args: arguments to pass to the dialog constructor
		@param opts: arguments to pass to the dialog constructor

		@note: when a dialog already existed the arguments provided to
		this constructor are not used
		'''
		attr = '_unique_dialog_%s' % klass.__name__
		dialog = None

		if hasattr(handler, attr):
			ref = getattr(handler, attr)
			dialog = ref()

		if dialog is None or dialog.destroyed:
			if dialog:
				dialog.destroy() # just to be sure - can be called several times without problem
			dialog = klass(*args, **opts)

		setattr(handler, attr, weakref.ref(dialog))
		return dialog

	def __init__(self, parent, title,
			buttons=Gtk.ButtonsType.OK_CANCEL, button=None,
			help_text=None, help=None,
			defaultwindowsize=(-1, -1)
		):
		'''Constructor.

		@param parent: either a parent gtk widget or C{None}. Only used to
		set the dialog on top of the right parent window
		@param title: the dialog title
		@param buttons: a constant controlling what kind of buttons the
		dialog will have. One of:
			- C{None} or C{Gtk.ButtonsType.NONE}: for dialogs taking care
			  of constructing the buttons themselves
			- C{Gtk.ButtonsType.OK_CANCEL}: Render Ok and Cancel
			- C{Gtk.ButtonsType.CLOSE}: Only set a Close button
		@param button: a label to use instead of the default 'Ok' button
		@param help_text: set the help text, see L{add_help_text()}
		@param help: pagename for a manual page, see L{set_help()}
		@param defaultwindowsize: default window size in pixels
		'''
		window = get_window(parent)
		GObject.GObject.__init__(self)
		self.set_transient_for(window)
		self.set_title(title)

		self.destroyed = False
		self.connect('destroy', self.__class__.on_destroy)

		self.result = None
		self._registered = False
		self.set_border_width(10)
		self.vbox.set_spacing(5)

		if hasattr(self, 'uistate'):
			assert isinstance(self.uistate, zim.config.ConfigDict) # just to be sure
		elif hasattr(window, 'notebook'):
			self.uistate = window.notebook.state[self.__class__.__name__]
		else:
			self.uistate = zim.config.ConfigDict()

		# note: _windowpos is defined with a leading "_" so it is not
		# persistent across instances, this is intentional to avoid
		# e.g. messy placement for seldom used dialogs
		self.uistate.setdefault('_windowpos', None, check=value_is_coord)
		if self.uistate['_windowpos'] is not None:
			x, y = self.uistate['_windowpos']
			self.move(x, y)

		self.uistate.setdefault('windowsize', defaultwindowsize, check=value_is_coord)
		if self.uistate['windowsize'] is not None:
			w, h = self.uistate['windowsize']
			self.set_default_size(w, h)

		self._no_ok_action = False
		if button is not None:
			assert isinstance(button, str), 'Usage of string + stock id deprecated'
			button = Gtk.Button.new_with_mnemonic(button)

		if buttons is None or buttons == Gtk.ButtonsType.NONE:
			self._no_ok_action = True
		elif buttons == Gtk.ButtonsType.OK_CANCEL:
			self.add_button(CANCEL_STR, Gtk.ResponseType.CANCEL) # T: Button label
			if button:
				self.add_action_widget(button, Gtk.ResponseType.OK)
			else:
				self.add_button(OK_STR, Gtk.ResponseType.OK) # T: Button label
		elif buttons == Gtk.ButtonsType.CLOSE:
			self.add_button(_('_Close'), Gtk.ResponseType.OK) # T: Button label
			self._no_ok_action = True
		else:
			assert False, 'BUG: unknown button type'
		# TODO set Ok button as default widget
		# see Gtk.Window.set_default()

		if help_text:
			self.add_help_text(help_text)
		if help:
			self.set_help(help)

	def on_destroy(self):
		self.disconnect_all()
		self.destroyed = True

	#{ Layout methods

	def add_extra_button(self, button, pack_start=True):
		'''Add a button to the action area at the bottom of the dialog.
		Packs the button in the list of primary buttons (by default
		these are in the lower right of the dialog)
		@param button: the C{Gtk.Button} (or other widget)
		@param pack_start: if C{True} pack to the left (towards the
		middle of the dialog), if C{False} pack to the right.
		'''
		self.action_area.pack_start(button, False, True, 0)
		if pack_start:
			self.action_area.reorder_child(button, 0)

	def set_help(self, pagename):
		'''Set the name of the manual page with help for this dialog.
		Setting this will add a "help" button to the dialog.
		@param pagename: the manual page name
		'''
		self.help_page = pagename
		button = Gtk.Button.new_with_mnemonic(_('_Help')) # T: Button label
		button.connect_object('clicked', self.__class__.show_help, self)
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

	def show_help(self, page=None):
		'''Show a help page
		@param page: the manual page, if C{None} the page as set with
		L{set_help()} is used
		'''
		from zim.main import ZIM_APPLICATION
		ZIM_APPLICATION.run('--manual', page or self.help_page)

	def add_help_text(self, text):
		'''Adds a label with an info icon in front of it. Intended for
		informational text in dialogs.
		@param text: help text
		'''
		hbox = help_text_factory(text)
		self.vbox.pack_start(hbox, False, True, 0)

	def add_text(self, text):
		'''Adds a label to the dialog
		Also see L{add_help_text()} for another style option.
		@param text: dialog text
		'''
		label = Gtk.Label(label=text)
		label.set_use_markup(True)
		label.set_alignment(0.0, 0.0)
		self.vbox.pack_start(label, False, True, 0)

	def add_form(self, inputs, values=None, depends=None, trigger_response=True, notebook=None):
		'''Convenience method to construct a form with input widgets and
		add them to the dialog. See L{InputForm.add_inputs()} for
		details.

		@param inputs: list with input definitions
		@param values: initial values for the inputs
		@param depends: dict with dependencies between inputs
		@param trigger_response: if C{True} pressing C{<Enter>} in the
		last entry widget will immediatly call L{response_ok()}. Set to
		C{False} if more forms will follow in the same dialog.
		'''
		if notebook is None and hasattr(self, 'notebook'):
			notebook = self.notebook

		self.form = InputForm(inputs, values, depends, notebook)
		if trigger_response:
			self.form.connect('last-activated', lambda o: self.response_ok())

		self.vbox.pack_start(self.form, False, True, 0)
		return self.form

	#}

	#{ Interaction methods

	def set_input(self, **fields):
		'''Method used in test suite to set "interactive" inputs
		@param fields: key value pairs of inputs to set
		@raises KeyError: if a key is not recognized
		@raises ValueError: if the value is of the wrong type and cannot be
		converted by the widget
		@raises AssertionError: if a key is recognized, but the input is
		not enabled for interactive input - e.g. widget insensitive or hidden
		'''
		if hasattr(self, 'form'):
			for key, value in list(fields.items()):
				if key in self.form:
					assert self.get_input_enabled(key)
					self.form[key] = value
				else:
					raise KeyError('No such input field: %s' % key)
		else:
			raise NotImplementedError

	def get_input(self, key):
		'''Method used in test suite to get "interactive" inputs'''
		if hasattr(self, 'form'):
			if not key in self.form:
				raise KeyError('No such input field: %s' % key)
			else:
				return self.form[key]
		else:
			raise NotImplementedError

	def get_input_enabled(self, key):
		return self.form.widgets[key].get_property('sensitive') \
			and not self.form.widgets[key].get_property('no-show-all')

	def run(self):
		'''Wrapper for C{Gtk.Dialog.run()}, also calls C{show_all()}
		@returns: C{self.result}
		'''
		self.show_all()
		if TEST_MODE:
			assert TEST_MODE_RUN_CB, 'Dialog run without test callback'
			TEST_MODE_RUN_CB(self)
		else:
			while not self.destroyed:
				Gtk.Dialog.run(self)
		return self.result

	def present(self):
		self.show_all()
		if TEST_MODE:
			assert TEST_MODE_RUN_CB, 'Dialog run without test callback'
			TEST_MODE_RUN_CB(self)
		else:
			Gtk.Dialog.present(self)

	def show(self):
		self.show_all()

	def show_all(self):
		logger.debug('Opening dialog "%s"', self.get_title())
		if not self._registered:
			self._registered = True

		if not TEST_MODE:
			Gtk.Dialog.show_all(self)

	def response_ok(self):
		'''Trigger the response signal with response type 'OK'.'''
		self.response(Gtk.ResponseType.OK)

	def assert_response_ok(self):
		'''Like L{response_ok()}, but raise an error when
		L{do_response_ok} returns C{False}.
		Also it explicitly does not handle errors in L{do_response_ok}.
		Intended for use by the test suite.
		@returns: C{self.result}
		@raises AssertionError: if L{do_response_ok} returns C{False}
		'''
		if not (self._no_ok_action or self.do_response_ok() is True):
			raise AssertionError('%s.do_response_ok() did not return True' % self.__class__.__name__)
		self.save_uistate()
		self.destroy()
		return self.result

	def do_response(self, id):
		# Handler for the response signal, dispatches to do_response_ok()
		# or do_response_cancel() and destroys the dialog if that function
		# returns True.
		# Ensure the dialog always closes on delete event, regardless
		# of any errors or bugs that may occur.
		if id == Gtk.ResponseType.OK and not self._no_ok_action:
			logger.debug('Dialog response OK')
			try:
				destroy = self.do_response_ok()
			except Exception as error:
				ErrorDialog(self, error).run()
				destroy = False
			else:
				if not destroy:
					logger.warning('Dialog input not valid')
		elif id == Gtk.ResponseType.CANCEL:
			logger.debug('Dialog response CANCEL')
			try:
				destroy = self.do_response_cancel()
			except Exception as error:
				ErrorDialog(self, error).run()
				destroy = False
			else:
				if not destroy:
					logger.warning('Could not cancel dialog')
		else:
			destroy = True

		try:
			x, y = self.get_position()
			self.uistate['_windowpos'] = (x, y)
			w, h = self.get_size()
			self.uistate['windowsize'] = (w, h)
			self.save_uistate()
		except:
			logger.exception('Exception in do_response()')

		if destroy:
			self.destroy()
			logger.debug('Closed dialog "%s"', self.get_title())

	def do_response_ok(self):
		'''Handler called when the user clicks the "OK" button (or
		an equivalent button)

		@returns: C{True} if successfull and the dialog can close. Returns
		C{False} if e.g. input is not valid, this will keep the dialog open.

		@implementation: must be implemented by sub-classes that have
		an "OK" button
		'''
		raise NotImplementedError

	def do_response_cancel(self):
		'''Handler called when the user clicks the "Cancel" button.

		@note: this method is B{not} called when the dialog is closed
		using e.g. the "[x]" button in the window decoration. It is only
		used when the user explicitly clicks "Cancel".

		@returns: C{True} if the dialog can be destroyed close. Returning
		C{False} will keep the dialog open.

		@implementation: can be implemented by sub-classes that have
		an "Cancel" button
		'''
		return True

	def save_uistate(self):
		'''Method when the dialog is about to exit or hide and wants to
		save the uistate. Sub-classes implementing this method should
		use it to set additional state parameter in C{self.uistate}.

		@implementation: can be implemented by sub-classes that have
		some additional uistate to save
		'''
		pass

	#}


class ErrorDialog(Gtk.MessageDialog):
	'''The is the main class for error dialogs in zim. It not only
	presents the error to the user, but also takes care of logging it.
	So the error dialog can be used as a generic catch all for
	exceptions in the user interface. The way the error is shown
	depends on the class of the exception:

	For exceptions that inherit from L{zim.errors.Error} or
	C{EnvironmentError} (e.g. C{OSError} or C{IOError}) a normal error
	dialog will be shown. This covers errors that can can occur in
	normal usage. As a special case the "filename" attribute of
	Environment errors is used and added to the error message.

	On the other all exceptions that do not inherit from these
	classes (so all standard in exceptions like C{AssertionError},
	C{KeyError} etc.) are considered the result of bugs and the dialog
	will say: "Looks like you found a bug" and show a stack trace.

	@note: in menu action handlers you typically do not need to catch
	exceptions with an error dialog. The standard menu wrapper takes
	care of that.
	'''

	def __init__(self, parent, error, exc_info=None, do_logging=True,
				buttons=Gtk.ButtonsType.CLOSE
	):
		'''Constructor

		@param parent: either a parent window or dialog or C{None}

		@param error: the actual error, either an C{Exception} object
		(including instances of L{zim.errors.Error}), a string with the
		error description, or a 2-tuple of the short message and the
		longer description as strings. Using a tuple here will give a
		better looking dialog over using a simple string.

		@param exc_info: this is an optional argument that takes the
		result of C{sys.exc_info()}. This parameter is not necessary in
		most cases where the dialog is run while the exception is still
		in scope. One reason to pass it on explicitly is the handling
		of errors from an async operation in the main tread.

		@param do_logging: if C{True} also log the error, if C{False}
		assume someone else already did

		@param buttons: a constant controlling what kind of buttons the
		dialog will have. One of:
			- C{None} or C{Gtk.ButtonsType.NONE}: for dialogs taking care
			  of constructing the buttons themselves
			- C{Gtk.ButtonsType.OK_CANCEL}: Render Ok and Cancel
			- C{Gtk.ButtonsType.CLOSE}: Only set a Close button
		'''
		if not isinstance(error, Exception):
			if isinstance(error, tuple):
				msg, description = error
				error = zim.errors.Error(msg, description)
			else:
				msg = str(error)
				error = zim.errors.Error(msg)

		self.error = error
		self.do_logging = do_logging
		msg, show_trace = zim.errors.get_error_msg(error)

		Gtk.MessageDialog.__init__(
			self,
			message_type=Gtk.MessageType.ERROR,
			buttons=buttons,
			text=msg
		)
		self.set_resizable(True)
		self.set_transient_for(get_window(parent))
		self.set_modal(True)

		for child in self.get_message_area().get_children():
			if isinstance(child, Gtk.Label):
				child.set_ellipsize(Pango.EllipsizeMode.END)

		if isinstance(error, zim.errors.Error):
			self.showing_trace = False # used in test
			self.format_secondary_text(error.description)
		elif show_trace:
			self.showing_trace = True # used in test
			self.format_secondary_text(
				_('When reporting this bug please include\n'
				  'the information from the text box below')
				) # T: generic error dialog text
				# TODO add link to bug tracker

			# Add widget with debug info
			text = self.get_debug_text(exc_info)
			window, textview = ScrolledTextView(text, monospace=True)
			window.set_size_request(350, 200)
			window.set_property('expand', True)
			self.vbox.add(window)
			self.vbox.show_all()
			self.set_resizable(True)
		else:
			self.showing_trace = False # used in test
			pass


	def get_debug_text(self, exc_info=None):
		'''Get the text to show in the log of a "You found a bug" dialog.
		Includes zim version info and traceback info.

		@param exc_info: this is an optional argument that takes the
		result of C{sys.exc_info()}
		@returns: debug log as string
		'''
		from gi.repository import GObject
		import zim
		import traceback

		if not exc_info:
			exc_info = sys.exc_info()

		if exc_info[2]:
			tb = exc_info[2]
		else:
			tb = None

		text = 'This is zim %s\n' % zim.__version__ + \
			'Platform: %s\n' % os.name + \
			'Locale: %s %s\n' % locale.getdefaultlocale() + \
			'FS encoding: %s\n' % sys.getfilesystemencoding() + \
			'Python: %s\n' % str(tuple(sys.version_info)) + \
			'PyGObject: %s\n' % str(GObject.pygobject_version)

		text += '\n======= Traceback =======\n'
		if tb:
			lines = traceback.format_tb(tb)
			text += ''.join(lines)
		else:
			text += '<Could not extract stack trace>\n'

		text += self.error.__class__.__name__ + ': ' + str(self.error)

		del exc_info # recommended by manual

		return text

	def run(self):
		'''Runs the dialog and destroys it directly.'''
		logger.debug('Running %s', self.__class__.__name__)

		if self.do_logging:
			zim.errors.log_error(self.error)

		if TEST_MODE and TEST_MODE_RUN_CB:
			TEST_MODE_RUN_CB(self)
		else:
			self._run()

	def _run(self):
		while True:
			response = Gtk.MessageDialog.run(self)
			if response == Gtk.ResponseType.OK and not self.do_response_ok():
				continue
			else:
				break
		self.destroy()

	def do_response_ok(self):
		'''Response handler for the 'OK' button
		@implementation: optional to be implemented by sub-classes that
		want to run some action after presenting the error.
		'''
		return True

	def assert_response_ok(self):
		assert self.do_response_ok()


class QuestionDialog(Gtk.MessageDialog):
	'''Convenience class to prompt the user with Yes/No answer type
	of questions.

	Note that message dialogs do not have a title.
	'''

	def __init__(self, parent, question):
		'''Constructor.

		@param parent: either a parent window or dialog or C{None}

		@param question: a question that can be answered by 'yes' or
		'no', either as sring or a 2-tuple of the actual question and
		a longer explanation as srtings. Using a tuple here will give a
		better looking dialog.
		'''
		if isinstance(question, tuple):
			question, text = question
		else:
			text = None
		self.question = question

		self.answer = None
		GObject.GObject.__init__(
			self,
			message_type=Gtk.MessageType.QUESTION,
			buttons=Gtk.ButtonsType.YES_NO,
			text=question
		)
		self.set_transient_for(get_window(parent))
		if text:
			self.format_secondary_text(text)

		self.connect('response', self.__class__.do_response)

	def do_response(self, id):
		self.answer = id

	def answer_yes(self):
		self.response(Gtk.ResponseType.YES)

	def answer_no(self):
		self.response(Gtk.ResponseType.NO)

	def run(self):
		'''Runs the dialog and destroys it directly.
		@returns: C{True} if the user clicked 'Yes', C{False} otherwise.
		'''
		logger.debug('Running QuestionDialog')
		logger.debug('Q: %s', self.question)
		if TEST_MODE:
			assert TEST_MODE_RUN_CB, 'Dialog run without test callback'
			TEST_MODE_RUN_CB(self)
		else:
			Gtk.MessageDialog.run(self)
		self.destroy()
		answer = self.answer == Gtk.ResponseType.YES
		logger.debug('A: %s', answer)
		return answer


class MessageDialog(Gtk.MessageDialog):
	'''Convenience wrapper for C{Gtk.MessageDialog}, should be used for
	informational popups without an action.

	Note that message dialogs do not have a title.
	'''

	def __init__(self, parent, msg):
		'''Constructor.

		@param parent: either a parent window or dialog or C{None}

		@param msg: the message either as sring or a 2-tuple of the
		actual question and a longer explanation as strings. Using a
		tuple here will give a better looking dialog.
		'''

		if isinstance(msg, tuple):
			msg, text = msg
		else:
			text = None

		Gtk.MessageDialog.__init__(
			self,
			type=Gtk.MessageType.QUESTION,
			text=msg,
		)
		self.set_transient_for(get_window(parent))
		self.set_modal(True)
		self.add_button(OK_STR, Gtk.ButtonsType.OK) # T: Button label
		if text:
			self.format_secondary_text(text)

	def add_extra_button(self, button, pack_start=True):
		'''Add a button to the action area at the bottom of the dialog.
		Packs the button in the list of primary buttons (by default
		these are in the lower right of the dialog)
		@param button: the C{Gtk.Button} (or other widget)
		@param pack_start: if C{True} pack to the left (towards the
		middle of the dialog), if C{False} pack to the right.
		'''
		self.action_area.pack_start(button, False, True, 0)
		if pack_start:
			self.action_area.reorder_child(button, 0)

	def run(self):
		'''Runs the dialog and destroys it directly.'''
		logger.debug('Running MessageDialog')
		if TEST_MODE:
			assert TEST_MODE_RUN_CB, 'Dialog run without test callback'
			TEST_MODE_RUN_CB(self)
		else:
			self.show_all()
			Gtk.MessageDialog.run(self)
		self.destroy()

	def assert_response_ok(self):
		return True # message dialogs are always OK


class FileDialog(Dialog):
	'''File Chooser dialog, that allows to browser the file system and
	select files or folders. Similar to C{Gtk.FileChooserDialog} but
	inherits from L{Dialog} instead.

	This dialog will automatically show previews for image files.

	When using C{dialog.run()} it will return the selected file(s) or
	dir(s) based on the arguments given during construction.
	'''

	def __init__(self, parent, title, action=Gtk.FileChooserAction.OPEN,
			buttons=Gtk.ButtonsType.OK_CANCEL, button=None,
			help_text=None, help=None, multiple=False,
		):
		'''Constructor.

		@param parent: either a parent window or dialog or C{None}

		@param title: the dialog title

		@param action: the file chooser action, one of::
			Gtk.FileChooserAction.OPEN
			Gtk.FileChooserAction.SAVE
			Gtk.FileChooserAction.SELECT_FOLDER
			Gtk.FileChooserAction.CREATE_FOLDER

		@param buttons: see L{Dialog.__init__()}
		@param button: see L{Dialog.__init__()}
		@param help_text: see L{Dialog.__init__()}
		@param help: see L{Dialog.__init__()}

		@param multiple: if C{True} the dialog will allow selecting
		multiple files at once.
		'''
		if button is None:
			if action == Gtk.FileChooserAction.OPEN:
				button = _('_Open') # T: Button label
			elif action == Gtk.FileChooserAction.SAVE:
				button = _('_Save') # T: Button label
			# else Ok will do

		Dialog.__init__(self, parent, title, defaultwindowsize=(500, 400),
			buttons=buttons, button=button, help_text=help_text, help=help)

		self.filechooser = Gtk.FileChooserWidget()
		self.filechooser.set_action(action)
		self.filechooser.set_do_overwrite_confirmation(True)
		self.filechooser.set_select_multiple(multiple)
		self.filechooser.connect('file-activated', lambda o: self.response_ok())
		self.vbox.add(self.filechooser)
		# FIXME hook to expander to resize window for FILE_CHOOSER_ACTION_SAVE

		self.preview_widget = Gtk.Image()
		self.filechooser.set_preview_widget(self.preview_widget)
		self.filechooser.connect('update-preview', self.on_update_preview)

		self._action = action

	def on_update_preview(self, *a):
		try:
			filename = self.filechooser.get_preview_filename()

			info, w, h = GdkPixbuf.Pixbuf.get_file_info(filename)
			if w <= 128 and h <= 128:
				# Show icons etc. on real size
				pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
			else:
				# Scale other images to fit the window
				pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, 128, 128)
			self.preview_widget.set_from_pixbuf(pixbuf)
			self.filechooser.set_preview_widget_active(True)
		except:
			self.filechooser.set_preview_widget_active(False)
		return

	def set_current_dir(self, dir):
		'''Set the current folder for the dialog
		(Only needed if not followed by L{set_file()})
		@param dir: a L{Dir} object
		'''
		ok = self.filechooser.set_current_folder_uri(dir.uri)
		if not ok:
			raise AssertionError('Could not set folder: %s' % dir.uri)

	def load_last_folder(self):
		self.uistate.setdefault('last_folder_uri', None, check=str)
		if self.uistate['last_folder_uri']:
			uri = self.uistate['last_folder_uri']
			ok = self.filechooser.set_current_folder_uri(uri)
			if not ok:
				logger.warning('Could not set current folder to: %s', uri)

	def save_last_folder(self):
		last_folder = self.filechooser.get_current_folder_uri()
		if last_folder:
			# e.g. "Recent Used" view in dialog does not have a current folder
			self.uistate['last_folder_uri'] = last_folder
		else:
			self.uistate['last_folder_uri'] = None

	def add_shortcut(self, notebook, path=None):
		'''Add shortcuts for the notebook folder and page folder'''
		try:
			self.filechooser.add_shortcut_folder(notebook.folder.path)
		except:
			pass # GError on doubles ..

		if path:
			page = notebook.get_page(path)
			if hasattr(page, 'source') and page.source is not None:
				try:
					self.filechooser.add_shortcut_folder(page.source.dir.path)
				except:
					pass # GError on doubles ..

	def set_file(self, file):
		'''Set the file or dir to pre select in the dialog
		@param file: a L{File} or L{Dir} object
		'''
		ok = self.filechooser.set_uri(file.uri)
		if not ok:
			raise AssertionError('Could not set file: %s' % file.uri)

		if TEST_MODE:
			self._file = file
			# HACK - for some reason the filechooser doesn't work in test mode

	def get_file(self):
		'''Get the current selected file
		@returns: a L{File} object or C{None}.
		'''
		if self.filechooser.get_select_multiple():
			raise AssertionError('Multiple files selected, use get_files() instead')

		uri = self.filechooser.get_uri()
		if uri:
			return File(uri)
		elif TEST_MODE and hasattr(self, '_file') and self._file:
			return self._file
		else:
			return None

	def get_files(self):
		'''Get list of selected file. Assumes the dialog was created
		with C{multiple=True}.
		@returns: a list of L{File} objects
		'''
		files = [File(uri) for uri in self.filechooser.get_uris()]
		if files:
			return files
		elif TEST_MODE and hasattr(self, '_file') and self._file:
			return [self._file]
		else:
			return []

	def get_dir(self):
		'''Get the the current selected dir. Assumes the dialog was
		created with action C{Gtk.FileChooserAction.SELECT_FOLDER} or
		C{Gtk.FileChooserAction.CREATE_FOLDER}.
		@returns: a L{Dir} object or C{None}
		'''
		if self.filechooser.get_select_multiple():
			raise AssertionError('Multiple files selected, use get_files() instead')

		uri = self.filechooser.get_uri()
		return Dir(uri) if uri else None

	def _add_filter_all(self):
		filter = Gtk.FileFilter()
		filter.set_name(_('All Files'))
			# T: Filter in open file dialog, shows all files (*)
		filter.add_pattern('*')
		self.filechooser.add_filter(filter)

	def add_filter(self, name, glob):
		'''Add a filter for files with specific extensions in the dialog
		@param name: the label to display in the filter selection
		@param glob: a file pattern (e.g. "*.txt")
		@returns: the C{Gtk.FileFilter} object
		'''
		if len(self.filechooser.list_filters()) == 0:
			self._add_filter_all()
		filter = Gtk.FileFilter()
		filter.set_name(name)
		filter.add_pattern(glob)
		self.filechooser.add_filter(filter)
		self.filechooser.set_filter(filter)
		return filter

	def add_filter_images(self):
		'''Add a standard file filter for selecting image files.
		@returns: the C{Gtk.FileFilter} object
		'''
		if len(self.filechooser.list_filters()) == 0:
			self._add_filter_all()
		filter = Gtk.FileFilter()
		filter.set_name(_('Images'))
			# T: Filter in open file dialog, shows image files only
		filter.add_pixbuf_formats()
		filter.add_mime_type('image/*') # to allow types like .ico
		self.filechooser.add_filter(filter)
		self.filechooser.set_filter(filter)
		return filter

	def do_response_ok(self):
		'''Default response handler. Will check filechooser action and
		whether or not we select multiple files or dirs and set result
		of the dialog accordingly, so the method run() will return the
		selected file(s) or folder(s).
		'''
		action = self._action
		multiple = self.filechooser.get_select_multiple()
		if action in (
			Gtk.FileChooserAction.SELECT_FOLDER,
			Gtk.FileChooserAction.CREATE_FOLDER
		):
			#~ if multiple:
				#~ self.result = self.get_dirs()
			#~ else:
			self.result = self.get_dir()
		else:
			if multiple:
				self.result = self.get_files()
			else:
				self.result = self.get_file()

		return bool(self.result)


class ProgressDialog(Gtk.Dialog):
	'''Dialog to show a progress bar for a operation'''

	def __init__(self, parent, op):
		'''Constructor
		@param parent: either a parent gtk widget or C{None}. Only used to
		set the dialog on top of the right parent window
		@param op: operation that supports a "step" signal, a "finished" signal
		and a "run_on_idle" method - see L{NotebookOperation} for the default
		implementation
		'''
		self.op = op
		self._total = None
		self.cancelled = False
		GObject.GObject.__init__(self)
		self.set_transient_for(get_window(parent))
		self.set_modal(True)
		self.add_button(CANCEL_STR, Gtk.ResponseType.CANCEL) # T: Button label
		self.set_border_width(10)
		self.vbox.set_spacing(5)
		self.set_default_size(300, 0)

		label = Gtk.Label()
		label.set_markup('<b>' + encode_markup_text(op.message) + '</b>')
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False, True, 0)

		self.progressbar = Gtk.ProgressBar()
		self.vbox.pack_start(self.progressbar, False, True, 0)

		self.msg_label = Gtk.Label()
		self.msg_label.set_alignment(0.0, 0.5)
		self.msg_label.set_ellipsize(Pango.EllipsizeMode.START)
		self.vbox.pack_start(self.msg_label, False, True, 0)

		self.op.connect('step', self.on_step)
		self.op.connect('finished', self.on_finished)

	def show_all(self):
		logger.debug('Opening ProgressDialog: %s', self.op.message)
		if not TEST_MODE:
			Gtk.Dialog.show_all(self)

	def run(self):
		if TEST_MODE: # Avoid flashing on screen
			for i in self.op:
				pass
		else:
			if not self.op.is_running():
				self.op.run_on_idle()
			self.show_all()
			Gtk.Dialog.run(self)

	def on_step(self, op, info):
		i, total, msg = info

		try:
			frac = float(i) / total
		except TypeError:
			# Apperently i and/or total is not integer
			self.progressbar.pulse()
		else:
			self.progressbar.set_fraction(frac)
			self.progressbar.set_text(_('{count} of {total}').format(count=i, total=total))
			 	# T: lable in progressbar giving number of items and total

		if msg is None:
			self.msg_label.set_text('')
		else:
			self.msg_label.set_markup('<i>' + encode_markup_text(str(msg)) + '</i>')

	def on_finished(self, op):
		self.cancelled = op.cancelled
		self.destroy()

	def do_response(self, id):
		logger.debug('ProgressDialog %s cancelled', self.op.message)
		self.op.cancel()
		self.cancelled = True


class LogFileDialog(Dialog):
	'''Simple dialog to show a log file'''

	def __init__(self, parent, file):
		Dialog.__init__(self, parent, _('Log file'), buttons=Gtk.ButtonsType.CLOSE)
			# T: dialog title for log view dialog - e.g. for Equation Editor
		self.set_default_size(600, 300)
		window, textview = ScrolledTextView(file.read(), monospace=True)
		self.vbox.pack_start(window, True, True, 0)



class Assistant(Dialog):
	'''Dialog with multi-page input, sometimes also revert to as a
	"wizard". Similar to C{Gtk.Assistent} separate implementation to
	allow more flexibility in the dialog layout.

	Each "page" in the assistant is a step in the work flow. Pages
	should inherit from L{AssistantPage}. Pages share the 'uistate'
	dict with assistant object, and can also use this to
	communicate state to another page. So each step can change its
	look based on state set in the previous step. (This is sometimes
	called a "Whiteboard" design pattern: each page can access the
	same "whiteboard" that is the uistate dict.)

	Sub-classes of this dialog can freely manipulate the flow of pages
	e.g. by overloading the L{previous_page()} and L{next_page()} methods.
	'''

	def __init__(self, parent, title, **options):
		'''Constructor

		@param parent: either a parent window or dialog or C{None}
		@param title: dialog title
		@param options: other dialog options, see L{Dialog.__init__()}
		'''
		Dialog.__init__(self, parent, title, buttons=None, **options)
		self.set_border_width(5)
		self._pages = []
		self._page = -1
		self._uistate = self.uistate
		self.uistate = self._uistate.copy()
		# Use temporary state, so we can cancel the wizard

		self._no_ok_action = False
		self.add_button(CANCEL_STR, Gtk.ResponseType.CANCEL) # T: Button label
		self.ok_button = self.add_button(OK_STR, Gtk.ResponseType.OK) # T: Button label

		self.back_button = Gtk.Button.new_with_mnemonic(_('_Back')) # T: Button label
		self.back_button.connect_object('clicked', self.__class__.previous_page, self)
		self.action_area.add(self.back_button)

		self.forw_button = Gtk.Button.new_with_mnemonic(_('_Forward')) # T: Button label
		self.forw_button.connect_object('clicked', self.__class__.next_page, self)
		self.action_area.add(self.forw_button)

		self.action_area.reorder_child(self.ok_button, -1)

	def append_page(self, page):
		'''Append a page
		@param page: an L{AssistantPage} object
		'''
		assert isinstance(page, AssistantPage)
		page.connect('input-valid-changed', self._update_valid)
		self._pages.append(page)

	def run(self):
		assert self._pages
		self.set_page(0)
		Dialog.run(self)

	def get_pages(self):
		'''Get all pages
		@returns: a list of L{AssistantPage} objects
		'''
		return self._pages

	def get_page(self):
		'''Get the current page
		@returns: a L{AssistantPage} object
		'''
		if self._page > -1:
			return self._pages[self._page]
		else:
			return None

	def set_page(self, i):
		'''Set the current page, based on sequence number
		@param i: the index of the page to be shown
		'''
		if i < 0 or i >= len(self._pages):
			return False

		# Wrap up previous page
		if self._page > -1:
			self._pages[self._page].save_uistate()

		# Remove previous page
		for child in self.vbox.get_children():
			if isinstance(child, (AssistantPage, Gtk.EventBox)):
				self.vbox.remove(child)

		self._page = i
		page = self._pages[self._page]

		# Add page title - use same color as used by gtkassistent.c
		# This is handled on expose event, because style does not
		# yet reflect theming on construction
		# However also need to disconnect the signal after first use,
		# because otherwise this keeps firing, which hangs the loop
		# for handling events in ProgressBar.pulse() - LP #929247
		ebox = Gtk.EventBox()
		def _set_heading_color(*a):
			ebox.modify_fg(Gtk.StateType.NORMAL, self.style.fg[Gtk.StateType.SELECTED])
			ebox.modify_bg(Gtk.StateType.NORMAL, self.style.bg[Gtk.StateType.SELECTED])
			self.disconnect(self._expose_event_id)
			#return False # propagate

		#_set_heading_color()
		#self._expose_event_id = \
		#	self.connect_after('expose-event', _set_heading_color)

		hbox = Gtk.HBox()
		hbox.set_border_width(5)
		ebox.add(hbox)
		self.vbox.pack_start(ebox, False, True, 0)

		label = Gtk.Label()
		label.set_markup('<b>' + page.title + '</b>')
		hbox.pack_start(label, False, True, 0)
		label = Gtk.Label()
		label.set_markup('<b>(%i/%i)</b>' % (self._page + 1, len(self._pages)))
		hbox.pack_end(label, False, True, 0)

		# Add actual page
		self.vbox.add(page)
		self.vbox.show_all()
		page.init_uistate()

		self.back_button.set_sensitive(self._page > 0)
		if self._page < len(self._pages) - 1:
			_hide(self.ok_button)
			_show(self.forw_button)
		else:
			_hide(self.forw_button)
			_show(self.ok_button)

		self._update_valid()

		return True

	def _update_valid(self, *a):
		page = self._pages[self._page]
		ok = page.get_input_valid()
		self.forw_button.set_sensitive(ok)
		self.ok_button.set_sensitive(ok)

	def next_page(self):
		'''Go forward to the next page'''
		return self.set_page(self._page + 1)

	def previous_page(self):
		'''Go back to the previous page'''
		return self.set_page(self._page - 1)

	def do_response(self, id):
		if id == Gtk.ResponseType.OK:
			# Wrap up previous page
			if self._page > -1:
				self._pages[self._page].save_uistate()

			self._uistate.update(self.uistate)

		Dialog.do_response(self, id)

	def assert_response_ok(self):
		# Wrap up previous page
		if self._page > -1:
			self._pages[self._page].save_uistate()

		self._uistate.update(self.uistate)

		if not self.do_response_ok() is True:
			raise AssertionError('%s.do_response_ok() did not return True' % self.__class__.__name__)
		self.save_uistate()
		self.destroy()
		return self.result


class AssistantPage(Gtk.VBox):
	'''Base class for pages in an L{Assistant} dialog.

	Typically each page will contain a number of input widgets that
	are logically grouped. After filling them in the user presses
	"Forward" to go to the next page. In order for the "Forward" button
	to becomes sensitive all widgets must have valid input.

	@cvar title: title to show above this page

	@ivar uistate: dict shared between all pages in the same dialog,
	use this to set values giving the interface state.
	@ivar assistant: the dialog this page belongs to
	@ivar form: an L{InputForm} when L{add_form()} was used

	@signal: C{input-valid-changed ()}: emitted when the valid state
	of the page changed
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'input-valid-changed': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	title = ''

	def __init__(self, assistant):
		'''Constructor
		@param assistant: the L{Assistant} dialog
		'''
		GObject.GObject.__init__(self)
		self.set_border_width(5)
		self.uistate = assistant.uistate
		self.assistant = assistant
		self._input_valid = True
		self.form = None

	def init_uistate(self):
		'''This method is called when this page is shown in the dialog.
		Should be used to update uistate according to input of other
		pages. Keep in mind that uistate can have changed since the
		constructor was called - even when this is the first page, the
		dialog has a "Back" button.

		@implementation: must be implementated by all subclasseses
		'''
		pass

	def save_uistate(self):
		'''This method is called before leaving the page. It should
		be used to update uitstate based on in put widgets.

		@implementation: must be implementated by all subclasseses that
		do not update uistate in real time
		'''
		pass

	def add_form(self, inputs, values=None, depends=None):
		'''Convenience method to construct a form with input widgets and
		add them to the dialog. See L{InputForm.add_inputs()} for
		details.

		@param inputs: list with input definitions
		@param values: initial values for the inputs
		@param depends: dict with dependencies between inputs
		'''
		self.form = InputForm(inputs, values, depends, notebook=self.assistant.notebook)
		self.form.connect('input-valid-changed', lambda o: self.check_input_valid())
		self.pack_start(self.form, False, True, 0)
		self.check_input_valid()
		return self.form

	def get_input_valid(self):
		'''Get valid state for the page
		@returns: C{True} if all input is valid
		'''
		return self._input_valid

	def check_input_valid(self):
		'''Check overall valid stat of the page. Called if the valid
		state if the form is changed. And should be called for any
		other custom widgets in the page.

		@implementation: should be implemented by sub-classes that
		add widgets outside of the form

		@emits: input-valid
		'''
		if self.form:
			valid = self.form.get_input_valid()
		else:
			valid = True

		if self._input_valid != valid:
			self._input_valid = valid
			self.emit('input-valid-changed')


class ImageView(Gtk.Layout):
	'''Widget to show an image, scales the image and sets proper
	background.
	'''

	SCALE_FIT = 1 #: scale image with the window (if the image is bigger)
	SCALE_STATIC = 2 #: use scaling factor

	def __init__(self, bgcolor='#FFF'):
		'''Constructor
		@param bgcolor: background color as color hex code, (e.g. "#FFF")
		'''
		GObject.GObject.__init__(self)
		self.set_can_focus(True)
		self.scaling = self.SCALE_FIT
		self.factor = 1

		self._pixbuf = None
		self._render_size = None # allocation w, h for which we have rendered
		self._render_timeout = None # timer before updating rendering
		self._image = Gtk.Image() # pixbuf is set for the image in _render()
		self.add(self._image)

		self.set_bgcolor(bgcolor)
		self.connect('size-allocate', self.__class__.on_size_allocate)

	def set_bgcolor(self, bgcolor):
		'''Set background color
		@param bgcolor: background color as color hex code, (e.g. "#FFF")
		'''
		assert bgcolor.startswith('#'), 'BUG: Should specify colors in hex'
		color = Gdk.color_parse(bgcolor)
			# Gdk.Color(spec) only for gtk+ >= 2.14
		self.modify_bg(Gtk.StateType.NORMAL, color)

	def set_scaling(self, scaling, factor=1):
		'''Set the scaling
		@param scaling: C{SCALE_FIT} to make the image scale down
		to the size of the view, or C{SCALE_STATIC} to set scaling to
		a fixed factor.
		@param factor: static scaling factor (in combination with C{SCALE_STATIC})
		'''
		assert scaling in (SCALE_FIT, SCALE_STATIC)
		self.scaling = scaling
		self.factor = factor
		self._render()

	def set_file(self, file):
		'''Set the image to display from a file
		@param file: a L{File} object
		'''
		pixbuf = None

		if file and file.exists():
			try:
				pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(file))
			except:
				logger.exception('Could not load image "%s"', file)
		else:
			pass

		self.set_pixbuf(pixbuf)

	def set_pixbuf(self, pixbuf):
		'''Set the image to display from a pixbuf
		@param pixbuf: a C{GdkPixbuf.Pixbuf} or C{None} to display a
		broken image icon.
		'''
		if pixbuf is None:
			pixbuf = self.render_icon(
				Gtk.STOCK_MISSING_IMAGE, Gtk.IconSize.DIALOG).copy()
		self._pixbuf = pixbuf
		self._render()

	def on_size_allocate(self, allocation):
		# remove timer if any
		if self._render_timeout:
			GObject.source_remove(self._render_timeout)
			self._render_timeout = None

		size = (allocation.width, allocation.height)
		if size == self._render_size or not self._pixbuf:
			pass # no update of rendering needed
		else:
			def render_on_timeout(size):
				self._render_size = size
				try:
					self._render()
				except:
					logger.exception('Exception while rendering image')

				return False

			self._render_timeout = GObject.timeout_add(100, render_on_timeout, size)

	def _render(self):
		# remove timer if any
		if self._render_timeout:
			GObject.source_remove(self._render_timeout)
			self._render_timeout = None

		# Determine what size we want to render the image
		allocation = self.get_allocation()
		wwin, hwin = allocation.width, allocation.height
		wsrc, hsrc = self._pixbuf.get_width(), self._pixbuf.get_height()
		#~ print('Allocated', (wwin, hwin),)
		#~ print('Source', (wsrc, hsrc))

		if self.scaling == self.SCALE_STATIC:
			wimg = self.factor * wsrc
			himg = self.factor * hsrc
		elif self.scaling == self.SCALE_FIT:
			if hsrc <= wwin and hsrc <= hwin:
				# image fits in the screen - no scaling
				wimg, himg = wsrc, hsrc
			elif (float(wwin) / wsrc) < (float(hwin) / hsrc):
				# Fit by width
				wimg = wwin
				himg = int(hsrc * float(wwin) / wsrc)
			else:
				# Fit by height
				wimg = int(wsrc * float(hwin) / hsrc)
				himg = hwin
		else:
			assert False, 'BUG: unknown scaling type'
		#~ print('Image', (wimg, himg))

		# Scale pixbuf to new size
		wimg = max(wimg, 1)
		himg = max(himg, 1)
		if (wimg, himg) == (wsrc, hsrc):
			pixbuf = self._pixbuf
		else:
			pixbuf = self._pixbuf.scale_simple(wimg, himg, GdkPixbuf.InterpType.NEAREST)

		# And align the image in the layout
		wvirt = max((wwin, wimg))
		hvirt = max((hwin, himg))
		#~ print('Virtual', (wvirt, hvirt))
		self._image.set_from_pixbuf(pixbuf)
		self.set_size(wvirt, hvirt)
		self.move(self._image, (wvirt - wimg) / 2, (hvirt - himg) / 2)
