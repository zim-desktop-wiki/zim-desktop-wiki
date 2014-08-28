# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
L{ImageView}, L{SingleClickTreeView}, L{BrowserTreeView},
and L{TextBuffer}

@newfield requires: Requires
'''

import gobject
import gtk
import pango
import logging
import sys
import os
import re
import weakref
import unicodedata
import locale

try:
	import gtksourceview2
except ImportError:
	gtksourceview2 = None

import zim

import zim.errors
import zim.config
import zim.fs

from zim.fs import File, Dir
from zim.config import value_is_coord
from zim.notebook import Notebook, Path, PageNameError
from zim.parsing import link_type
from zim.signals import ConnectorMixin

logger = logging.getLogger('zim.gui')


if os.environ.get('ZIM_TEST_RUNNING'):
	TEST_MODE = True
	TEST_MODE_RUN_CB = None
else:
	TEST_MODE = False
	TEST_MODE_RUN_CB = None


# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVAL_LEFT = gtk.gdk.keyval_from_name('Left')
KEYVAL_RIGHT = gtk.gdk.keyval_from_name('Right')
KEYVALS_ASTERISK = (
	gtk.gdk.unicode_to_keyval(ord('*')), gtk.gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	gtk.gdk.unicode_to_keyval(ord('\\')),
	gtk.gdk.unicode_to_keyval(ord('/')), gtk.gdk.keyval_from_name('KP_Divide'))
KEYVAL_ESC = gtk.gdk.keyval_from_name('Escape')


# UI Environment config. Would properly belong in zim.gui.__init__
# but defined here to avoid unnecessary dependencies on zim.gui
ui_environment = {
	'platform': None, # platform name to trigger platform specific optimizations
	'maxscreensize': None, # max screensize _if_ fixed by the platform
	'smallscreen': False, # trigger optimizations for small screens
}


# Check for Maemo environment
if zim.PLATFORM == 'maemo':
	import hildon
	gtkwindowclass = hildon.Window
	ui_environment['platform'] = 'maemo'
	if hasattr(gtkwindowclass,'set_app_menu'):
		ui_environment['maemo_version'] = 'maemo5'
	else:
		ui_environment['maemo_version'] = 'maemo4'
	ui_environment['maxscreensize'] = (800, 480)
	ui_environment['smallscreen'] = True

	# Maemo gtk UI bugfix: expander-size is set to 0 by default
	gtk.rc_parse_string('''\
style "toolkit"
{
	GtkTreeView::expander-size = 12
}

class "GtkTreeView" style "toolkit"
''' )
else:
	gtkwindowclass = gtk.Window


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
				pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
				iconlist.append(pixbuf)
	else:
		sizes = ['16x16', '32x32', '48x48']
		for dir in [XDG_DATA_HOME] + XDG_DATA_DIRS:
			for size in sizes:
				file = dir.file('icons/hicolor/%s/apps/zim.png' % size)
				if file.exists():
					sizes.remove(size)
					pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
					iconlist.append(pixbuf)
			if not sizes:
				break

	if not iconlist:
		# fall back to data/zim.png
		file = zim.config.data_file('zim.png')
		pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
		iconlist.append(pixbuf)

		# also register it as stock since theme apparently is not found
		factory = gtk.IconFactory()
		factory.add_default()
		set = gtk.IconSet(pixbuf=pixbuf)
		factory.add('zim', set)


	if len(iconlist) < 3:
		logger.warn('Could not find all icon sizes for the application icon')
	gtk.window_set_default_icon_list(*iconlist)



def ScrolledWindow(widget, hpolicy=gtk.POLICY_AUTOMATIC, vpolicy=gtk.POLICY_AUTOMATIC, shadow=gtk.SHADOW_IN):
	'''Wrap C{widget} in a C{gtk.ScrolledWindow} and return the resulting
	widget
	@param widget: any Gtk widget
	@param hpolicy: the horizontal scrollbar policy
	@param vpolicy: the vertical scrollbar policy
	@param shadow: the shadow type
	@returns: a C{gtk.ScrolledWindow}
	'''
	window = gtk.ScrolledWindow()
	window.set_policy(hpolicy, vpolicy)
	window.set_shadow_type(shadow)
	window.add(widget)

	if hpolicy == gtk.POLICY_NEVER:
		hsize = -1 # do not set
	else:
		hsize = 24

	if vpolicy == gtk.POLICY_NEVER:
		vsize = -1 # do not set
	else:
		vsize = 24

	window.set_size_request(hsize, vsize)
		# scrolled widgets have at least this size...
		# by setting this minimum widgets can not "disappear" when
		# HPaned or VPaned bar is pulled all the way
	return window


def ScrolledTextView(text=None, monospace=False):
	'''Initializes a C{gtk.TextView} with sane defaults for displaying a
	piece of multiline text and wraps it in a scrolled window

	@param text: initial text to show in the textview
	@param monospace: when C{True} the font will be set to monospaced
	and line wrapping disabled, use this to display log files etc.
	@returns: a 2-tuple of the scrolled window and the textview
	'''
	textview = gtk.TextView(TextBuffer())
	textview.set_editable(False)
	textview.set_left_margin(5)
	textview.set_right_margin(5)
	if monospace:
		font = pango.FontDescription('Monospace')
		textview.modify_font(font)
	else:
		textview.set_wrap_mode(gtk.WRAP_WORD)

	if text:
		textview.get_buffer().set_text(text)
	window = ScrolledWindow(textview)
	return window, textview

def ScrolledSourceView(text=None, syntax=None):
	'''If GTKSourceView was succesfully loaded, this generates a SourceView and
	initializes it. Otherwise ScrolledTextView will be used as a fallback.

	@param text: initial text to show in the view
	@param syntax: this will try to enable syntax highlighting for the given
	language. If None, no syntax highlighting will be enabled.
	@returns: a 2-tuple of a window and a view.
	'''
	if gtksourceview2:
		gsvbuf = gtksourceview2.Buffer()
		if syntax:
			gsvbuf.set_highlight_syntax(True)
			language_manager = gtksourceview2.LanguageManager()
			gsvbuf.set_language(language_manager.get_language(syntax))
		if text:
			gsvbuf.set_text(text)
		textview = gtksourceview2.View(gsvbuf)
		textview.set_property("show-line-numbers", True)
		textview.set_property("auto-indent", True)
		font = pango.FontDescription('Monospace')
		textview.modify_font(font)
		textview.set_property("smart-home-end", True)
		window = ScrolledWindow(textview)
		return (window, textview)
	else:
		return ScrolledTextView(text=text, monospace=True)

def populate_popup_add_separator(menu, prepend=False):
	'''Convenience function that adds a C{gtk.SeparatorMenuItem}
	to a context menu. Checks if the menu already contains items,
	if it is empty does nothing. Also if the menu already has a
	seperator in the required place this function does nothing.
	This helps with building menus more dynamically.
	@param menu: the C{gtk.Menu} object for the popup
	@param prepend: if C{False} append, if C{True} prepend
	'''
	items = menu.get_children()
	if not items:
		pass # Nothing to do
	elif prepend:
		if not isinstance(items[0], gtk.SeparatorMenuItem):
			sep = gtk.SeparatorMenuItem()
			menu.prepend(sep)
	else:
		if not isinstance(items[-1], gtk.SeparatorMenuItem):
			sep = gtk.SeparatorMenuItem()
			menu.append(sep)


def gtk_combobox_set_active_text(combobox, text):
	'''Opposite of C{gtk.ComboBox.get_active_text()}. Sets the
	active item based on a string. Will match this string against the
	list of options and select the correct index.
	@raises ValueError: when the string is not found in the list.
	'''
	model = combobox.get_model()
	for i, value in enumerate(model):
		if value[0] == text:
			return combobox.set_active(i)
	else:
		raise ValueError, text


def gtk_notebook_get_active_tab(nb):
	'''Returns the label of the active tab or C{None}'''
	widget = gtk_notebook_get_active_page(nb)
	if widget:
		return nb.get_tab_label_text(widget)
	else:
		return None


def gtk_notebook_get_active_page(nb):
	'''Returns the active child widget or C{None}'''
	num = nb.get_current_page()
	if num >= 0:
		return nb.get_nth_page(num)
	else:
		return None


def gtk_notebook_set_active_tab(nb, label):
	'''Set active tab by the label of the tab'''
	for child in nb.get_children():
		if nb.get_tab_label_text(child) == label:
			num = nb.page_num(child)
			nb.set_current_page(num)
			break
	else:
		raise ValueError, 'No such tab: %s' % label


class TextBuffer(gtk.TextBuffer):
	'''Sub-class of C{gtk.TextBuffer} that handles utf-8 decoding'''

	def get_text(self, start, end, include_hidden_chars=True):
		text = gtk.TextBuffer.get_text(self, start, end, include_hidden_chars)
		if text:
			text = text.decode('utf-8')
		return text

	def get_slice(self, start, end, include_hidden_chars=True):
		text = gtk.TextBuffer.get_slice(self, start, end, include_hidden_chars)
		if text:
			text = text.decode('utf-8')
		return text


def rotate_pixbuf(pixbuf):
	'''Rotate the pixbuf to match orientation from EXIF info.
	This is intended for e.g. photos that have EXIF information that
	shows how the camera was held.
	@returns: a new version of the pixbuf or the pixbuf itself.
	'''
	# Values for orientation seen in some random snippet in gtkpod
	o = pixbuf.get_option('orientation')
	if o: o = int(o)
	if o == 3: # 180 degrees
		return pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
	elif o == 6: # 270 degrees
		return pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
	elif o == 9: # 90 degrees
		return pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
	else:
		# No rotation info, older gtk version, or advanced transpose
		return pixbuf


def help_text_factory(text):
	'''Create a label with an "info" icon in front of it. Intended for
	informational text in dialogs.
	@param text: the text to display
	@returns: a C{gtk.HBox}
	'''
	hbox = gtk.HBox(spacing=12)

	image = gtk.image_new_from_stock(gtk.STOCK_INFO, gtk.ICON_SIZE_BUTTON)
	image.set_alignment(0.5, 0.0)
	hbox.pack_start(image, False)

	label = gtk.Label(text)
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
	if len(a) == 1: subject = a[0]
	else: subject = a[1]
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

	@param table: options C{gtk.Table}, if given inputs will be appended
	to this table

	@returns: a C{gtk.Table}
	'''
	if table is None:
		table = gtk.Table()
		table.set_border_width(5)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
	i = table.get_property('n-rows')

	for input in inputs:
		if input is None:
			table.attach(gtk.Label(' '), 0,1, i,i+1, xoptions=gtk.FILL)
			# HACK: force empty row to have height of label
		elif isinstance(input, basestring):
			label = gtk.Label()
			label.set_markup(input)
			table.attach(label, 0,4, i,i+1)
				# see column below about col span for single widget case
		elif isinstance(input, tuple):
			text = input[0]
			if text:
				label = gtk.Label(text + ':')
				label.set_alignment(0.0, 0.5)
			else:
				label = gtk.Label(' '*4) # minimum label width

			table.attach(label, 0,1, i,i+1, xoptions=gtk.FILL)
			_sync_widget_state(input[1], label)

			for j, widget in enumerate(input[1:]):
				if isinstance(widget, gtk.Entry):
					table.attach(widget, j+1,j+2, i,i+1, xoptions=gtk.FILL|gtk.EXPAND)
				else:
					table.attach(widget, j+1,j+2, i,i+1, xoptions=gtk.FILL)
				if j > 0:
					_sync_widget_state(input[1], widget)
		else:
			widget = input
			table.attach(widget, 0,4, i,i+1)
				# We span 4 columns here so in case these widgets are
				# the widest in the tables (e.g. checkbox + label)
				# they don't force expanded size on first 3 columns
				# (e.g. label + entry + button).
		i += 1

	return table


class Button(gtk.Button):
	'''Sub-class of C{gtk.Button} which changes the constructor to
	allow specifying a stock icon I{and} a label at the same time.
	'''

	def __init__(self, label=None, stock=None, use_underline=True, status_bar_style=False):
		'''Constructor

		If both C{label} and C{stock} are given the button will have
		a stock icon but a custom label (for the default C{gtk.Button}
		class this is an "either or" choice). If only stock or only
		label is given, it falls back to the default behavior.

		@param label: text for the button
		@param stock: constant for a stock item
		@param use_underline: if C{True} a "_" in the label will
		@param status_bar_style: when C{True} all padding and border
		underline the next character
		'''
		if label is None or stock is None:
			gtk.Button.__init__(self, label=label, stock=stock)
		else:
			gtk.Button.__init__(self, label=label)
			icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
			self.set_image(icon)

		self.set_use_underline(use_underline)

		if status_bar_style:
			button_set_statusbar_style(self)


class IconButton(gtk.Button):
	'''Button with a stock icon, but no label.'''

	def __init__(self, stock, relief=True, size=gtk.ICON_SIZE_BUTTON):
		'''Constructor

		@param stock: constant for the stock item
		@param relief: when C{False} the button has no visible raised
		edge and will be flat against the background
		@param size: the icon size
		'''
		gtk.Button.__init__(self)
		icon = gtk.image_new_from_stock(stock, size)
		self.add(icon)
		self.set_alignment(0.5, 0.5)
		if not relief:
			self.set_relief(gtk.RELIEF_NONE)


def CloseButton():
	'''Constructs a close button for panes and bars'''
	return IconButton(gtk.STOCK_CLOSE, relief=False, size=gtk.ICON_SIZE_MENU)


class IconChooserButton(gtk.Button):
	'''Widget to allow the user to choose an icon. Intended e.g. for
	the dialog to configure a custom tool to set an icon for the
	tool. Shows a button with an image of the icon which opens up a
	file dialog when clicked.
	'''

	def __init__(self, stock=gtk.STOCK_MISSING_IMAGE, pixbuf=None):
		'''Constructor

		@param stock: initial stock icon (until an icon is selected)
		@param pixbuf: initial image as pixbuf (until an icon is selected)
		'''
		gtk.Button.__init__(self)
		self.file = None
		image = gtk.Image()
		self.add(image)
		self.set_alignment(0.5, 0.5)
		if pixbuf:
			image.set_from_pixbuf(pixbuf)
		else:
			image.set_from_stock(stock, gtk.ICON_SIZE_DIALOG)

	def do_clicked(self):
		dialog = FileDialog(self, _('Select File')) # T: dialog title
		dialog.add_filter_images()
		file = dialog.run()
		if file:
			self.set_file(file)

	def set_file(self, file):
		'''Set the file to display in the chooser button
		@param file: a L{File} object
		'''
		image = self.get_child()
		size = max(image.size_request()) # HACK to get icon size
		pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.path, size, size)
		image.set_from_pixbuf(pixbuf)
		self.file = file

	def get_file(self):
		'''Get the selected icon file
		@returns: a L{File} object
		'''
		return self.file

# Need to register classes defining / overriding gobject signals
gobject.type_register(IconChooserButton)


class SingleClickTreeView(gtk.TreeView):
	'''Sub-class of C{gtk.TreeView} that implements single-click
	navigation.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'populate-popup': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	mask = gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK

	# backwards compatibility
	if gtk.gtk_version < (2, 12, 0):
		def set_rubber_banding(self, enable):
			pass

		def is_rubber_banding_active(self):
			return False

	def do_button_press_event(self, event):
		# Implement hook for context menu

		if event.type == gtk.gdk.BUTTON_PRESS \
		and event.button == 3:
			# Check selection state - item under cursor should be selected
			# see do_button_release_event for comments
			x, y = map(int, event.get_coords())
			info = self.get_path_at_pos(x, y)
			selection = self.get_selection()
			if x > 0 and y > 0 and not info is None:
				path, column, x, y = info
				if not selection.path_is_selected(path):
					selection.unselect_all()
					selection.select_path(path)
				# else the clcik was on a already selected path
			else:
				# click outside area with items ?
				selection.unselect_all()

			# Pop menu
			menu = self.get_popup()
			if menu:
				menu.show_all()
				menu.popup(None, None, None, 3, event.get_time())
		else:
			return gtk.TreeView.do_button_press_event(self, event)

	def do_button_release_event(self, event):
		# Implement single click behavior for activating list items
		# this needs to be done on button release to avoid conflict with
		# selections, drag-n-drop, etc.

		if event.type == gtk.gdk.BUTTON_RELEASE \
		and event.button == 1 and not event.state & self.mask \
		and not self.is_rubber_banding_active():
			x, y = map(int, event.get_coords())
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

		return gtk.TreeView.do_button_release_event(self, event)

	def get_popup(self):
		'''Get a popup menu (the context menu) for this widget
		@returns: a C{gtk.Menu} or C{None}
		@emits: populate-popup
		@implementation: do NOT overload this method, implement
		L{do_initialize_popup} instead
		'''
		menu = gtk.Menu()
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
		@param menu: the C{gtk.Menu} object for the popup
		@implementation: can be implemented by sub-classes. Default
		implementation calls L{populate_popup_expand_collapse()}
		if the model is a C{gtk.TreeStore}. Otherwise it does nothing.
		'''
		model = self.get_model()
		if isinstance(model, gtk.TreeStore):
			self.populate_popup_expand_collapse(menu)

	def populate_popup_expand_collapse(self, menu, prepend=False):
		'''Adds "Expand _all" and "Co_llapse all" items to a context
		menu. Called automatically by the default implementation of
		L{do_initialize_popup()}.
		@param menu: the C{gtk.Menu} object for the popup
		@param prepend: if C{False} append, if C{True} prepend
		'''
		expand = gtk.MenuItem(_("Expand _All")) # T: menu item in context menu
		expand.connect_object('activate', self.__class__.expand_all, self)
		collapse = gtk.MenuItem(_("_Collapse All")) # T: menu item in context menu
		collapse.connect_object('activate', self.__class__.collapse_all, self)

		populate_popup_add_separator(menu, prepend=prepend)
		if prepend:
			menu.prepend(collapse)
			menu.prepend(expand)
		else:
			menu.append(expand)
			menu.append(collapse)

	def get_cell_renderer_number_of_items(self):
		'''Get a C{gtk.CellRendererText} that is set up for rendering
		the number of items below a tree item.
		Used to enforce common style between tree views.
		@returns: a C{gtk.CellRendererText} object
		'''
		cr = gtk.CellRendererText()
		cr.set_property('xalign', 1.0)
		#~ cr2.set_property('scale', 0.8)
		cr.set_property('foreground', 'darkgrey')
		return cr

# Need to register classes defining / overriding gobject signals
gobject.type_register(SingleClickTreeView)


class BrowserTreeView(SingleClickTreeView):
	'''Sub-class of C{gtk.TreeView} that is intended for hierarchic
	lists that can be navigated in "browser mode". It inherits the
	single-click behavior of L{SingleClickTreeView} and adds the
	following keybindings:
		- C{<Left>}: Collapse sub-items
		- C{<Right>}: Expand sub-items
		- C{\}: Collapse whole tree
		- C{*}: Expand whole tree
	'''

	# TODO some global option to restore to double click navigation ?

	def __init__(self, *arg):
		'''Constructor, all arguments are passed to C{gtk.TreeView}'''
		gtk.TreeView.__init__(self, *arg)
		self.get_selection().set_mode(gtk.SELECTION_BROWSE)

	def do_key_press_event(self, event):
		# Keybindings for the treeview:
		#  * expand all
		#  / or \ collapse all
		#  Right expand sub items
		#  Left collapse sub items
		handled = True
		#~ print 'KEY %s (%i)' % (gtk.gdk.keyval_name(event.keyval), event.keyval)

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
			return gtk.TreeView.do_key_press_event(self, event)

# Need to register classes defining / overriding gobject signals
gobject.type_register(BrowserTreeView)


def button_set_statusbar_style(button):
	# Set up a style for the statusbar variant to decrease spacing of the button
	gtk.rc_parse_string('''\
style "zim-statusbar-button-style"
{
	GtkWidget::focus-padding = 0
	GtkWidget::focus-line-width = 0
	xthickness = 0
	ythickness = 0
}
widget "*.zim-statusbar-button" style "zim-statusbar-button-style"
''')
	button.set_name('zim-statusbar-button')
	button.set_relief(gtk.RELIEF_NONE)


class MenuButton(gtk.HBox):
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

		@param label: the label to show on the button (string or C{gtk.Label})
		@param menu: the menu to show on button click
		@param status_bar_style: when C{True} all padding and border
		is removed so the button fits in the status bar
		'''
		gtk.HBox.__init__(self)
		if isinstance(label, basestring):
			self.label = gtk.Label()
			self.label.set_markup_with_mnemonic(label)
		else:
			assert isinstance(label, gtk.Label)
			self.label = label

		self.menu = menu
		self.button = gtk.ToggleButton()
		if status_bar_style:
			button_set_statusbar_style(self.button)
			widget = self.label
		else:
			arrow = gtk.Arrow(gtk.ARROW_UP, gtk.SHADOW_NONE)
			widget = gtk.HBox(spacing=3)
			widget.pack_start(self.label, False)
			widget.pack_start(arrow, False)


		self.button.add(widget)
		# We need to wrap stuff in an eventbox in order to get the gdk.Window
		# which we need to get coordinates when positioning the menu
		self.eventbox = gtk.EventBox()
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
			time = gtk.get_current_event_time()

		self.button.handler_block(self._clicked_signal)
		self.button.set_active(True)
		self.button.handler_unblock(self._clicked_signal)
		self.menu.connect('deactivate', self._deactivate_menu)
		self.menu.show_all()
		self.menu.popup(None, None, self._position_menu, button, time)

	def _position_menu(self, menu):
		x, y = self.eventbox.window.get_origin()
		w, h = menu.get_toplevel().size_request()
		y -= h # make the menu pop above the button
		return x, y, False

	def _deactivate_menu(self, menu):
		self.button.handler_block(self._clicked_signal)
		self.button.set_active(False)
		self.button.handler_unblock(self._clicked_signal)


# Need to register classes defining / overriding gobject signals
gobject.type_register(MenuButton)


class PanedClass(object):
	# We change default packing to shrink=False

	def pack1(self, widget, resize=True, shrink=False):
		gtk.Paned.pack1(self, widget, resize, shrink)

	def pack2(self, widget, resize=True, shrink=False):
		gtk.Paned.pack2(self, widget, resize, shrink)

	add1 = pack1
	add2 = pack2

	def add(*a):
		raise NotImplementedError

	def pack(*a):
		raise NotImplementedError

class HPaned(PanedClass, gtk.HPaned):
	pass

class VPaned(PanedClass, gtk.VPaned):
	pass


class InputForm(gtk.Table):
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
		'last-activated': (gobject.SIGNAL_RUN_LAST, None, ()),
		'input-valid-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
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
		gtk.Table.__init__(self)
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
			for k, v in depends.items():
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
			elif isinstance(input, basestring):
				widgets.append(input)
				continue

			if len(input) == 4:
				name, type, label, extra = input
			else:
				name, type, label = input
				extra = None

			if type == 'bool':
				widgets.append(gtk.CheckButton(label=label))

			elif type == 'option':
				assert ':' in name, 'BUG: options should have name of the form "group:key"'
				key, _ = name.rsplit(':', 1)
					# using rsplit to assure another ':' in the
					# group name is harmless
				group = self._get_radiogroup(key)
				if not group:
					group = None # we are the first widget
				else:
					group = group[0][1] # link first widget in group
				widgets.append(gtk.RadioButton(group=group, label=label))

			elif type == 'int':
				button = gtk.SpinButton()
				button.set_range(*extra)
				button.set_increments(1, 5)
				widgets.append((label, button))

			elif type == 'choice':
				combobox = gtk.combo_box_new_text()
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
				button = gtk.Button('_Browse')
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
				button = gtk.Button('_Browse')
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
				button = gtk.ColorButton()
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
				group, _ = name.split(':', 1)
				if not group in self._keys:
					self._keys.append(group)
			else:
				self._keys.append(name)

			# Connect activate signal
			if isinstance(widget, gtk.Entry):
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
		#~ print '-'*42
		valid = []
		for name in self._widgets:
			widget = self.widgets[name]
			if isinstance(widget, InputEntry)  \
			and widget.get_property('visible') \
			and widget.get_property('sensitive'):
				valid.append(self.widgets[name].get_input_valid())
				#~ print '>', name, valid[-1]
		#~ print '=', all(valid)

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
		if gtk.gtk_version >=  (2, 14, 0):
			widget = self.get_focus_child()
		else:
			for w in self.widgets.values():
				if w.is_focus:
					widget = w
					break

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
			for k, v in self.widgets.items():
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
				and not isinstance(widget, (gtk.Entry, gtk.ComboBox))
			):
				widget.grab_focus()
				return True
		else:
			return False

	#}

	#{ Dict access methods

	def __getitem__(self, key):
		if not key in self._keys:
			raise KeyError, key
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
			elif isinstance(widget, gtk.CheckButton):
				return widget.get_active()
			elif isinstance(widget, gtk.ComboBox):
				if hasattr(widget, 'zim_key_mapping'):
					label = widget.get_active_text()
					if label:
						label = label.decode('utf-8')
					return widget.zim_key_mapping.get(label) or label
				else:
					return widget.get_active_text()
			elif isinstance(widget, gtk.SpinButton):
				return int(widget.get_value())
			elif isinstance(widget, gtk.ColorButton):
				if gtk.gtk_version > (2, 14, 0):
					# This version supposedly gives compacter values
					return str(widget.get_color())
				else:
					return widget.get_color().to_string()
			else:
				raise TypeError, widget.__class__.name
		else:
			# Group of RadioButtons
			for name, widget in self._get_radiogroup(key):
				if widget.get_active():
					_, name = name.rsplit(':', 1)
						# using rsplit to assure another ':' in the
						# group name is harmless
					return name

	def __setitem__(self, key, value):
		if not key in self._keys:
			raise KeyError, key
		elif key in self.widgets:
			widget = self.widgets[key]
			if isinstance(widget, LinkEntry):
				assert isinstance(value, basestring)
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
			elif isinstance(widget, gtk.CheckButton):
				widget.set_active(value)
			elif isinstance(widget, gtk.ComboBox):
				if hasattr(widget, 'zim_key_mapping'):
					for key, v in widget.zim_key_mapping.items():
						if v == value:
							gtk_combobox_set_active_text(widget, key)
							break
					else:
						gtk_combobox_set_active_text(widget, value)
				else:
					gtk_combobox_set_active_text(widget, value)
			elif isinstance(widget, gtk.SpinButton):
				widget.set_value(value)
			elif isinstance(widget, gtk.ColorButton):
				color = gtk.gdk.color_parse(value)
				widget.set_color(color)
			else:
				raise TypeError, widget.__class__.name
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
		for key, value in map.items():
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

# Need to register classes defining / overriding gobject signals
gobject.type_register(InputForm)


class InputEntry(gtk.Entry):
	'''Sub-class of C{gtk.Entry} with support for highlighting
	mal-formatted inputs and handles UTF-8 decoding. This class must be
	used as a generic replacement for C{gtk.Entry} to avoid UTF-8
	issues. (This is enforced by the zim test suite which will throw an
	error for any module using C{gtk.Entry} directly.)

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
		'input-valid-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
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
		# NOTE: when porting to Gtk3 use gtk.Entry.set_placeholder_text()
		# and remove our own implementation
		gtk.Entry.__init__(self)
		self._normal_color = None
		self.allow_empty = allow_empty
		self.show_empty_invalid = show_empty_invalid
		self.allow_whitespace = allow_whitespace
		self.placeholder_text = placeholder_text
		self._placeholder_text_shown = False
		self.check_func = check_func
		self._input_valid = False
		self.do_changed() # Initialize state
		self.connect('changed', self.__class__.do_changed)

		def _init_base_color(*a):
			# This is handled on expose event, because style does not
			# yet reflect theming on construction
			if self._normal_color is None:
				self._normal_color = self.style.base[gtk.STATE_NORMAL]
				self._set_base_color(self.get_input_valid())

		self.connect('expose-event', _init_base_color)

	def set_check_func(self, check_func):
		'''Set a function to check whether input is valid or not
		@param check_func: the function
		'''
		self.check_func = check_func
		self.do_changed()

	def set_icon(self, icon, cb_func, tooltip=None):
		'''Add an icon in the entry widget behind the text

		@param icon: the icon as stock ID
		@param cb_func: the callback when the icon is clicked; the
		callback will be called without any arguments
		@param tooltip: tooltip text for the icon

		@returns: C{True} if succesful, C{False} if not supported
		by Gtk version

		@requires: Gtk >= 2.16
		@todo: add argument to set tooltip on the icon
		'''
		if gtk.gtk_version < (2, 16, 0):
			return False

		self.set_property('secondary-icon-stock', icon)
		if tooltip:
			self.set_property('secondary-icon-tooltip-text', tooltip)

		def on_icon_press(self, icon_pos, event):
			if icon_pos == gtk.ENTRY_ICON_SECONDARY:
				cb_func()
		self.connect('icon-press', on_icon_press)

		return True

	def set_icon_to_clear(self):
		'''Adds a "clear" icon in the entry widget

		This method calls L{set_icon()} with the right defaults for
		a stock "Clear" icon. In addition it makes the icon insensitive
		when there is no text in the entry. Clicking the icon will
		clear the entry.

		@returns: C{True} if succesful, C{False} if not supported
		by Gtk version

		@requires: Gtk >= 2.16
		'''
		if gtk.gtk_version < (2, 16, 0):
			return False

		self.set_icon(gtk.STOCK_CLEAR, self.clear, _('Clear'))
			# T: tooltip for the inline icon to clear a text entry widget

		def check_icon_sensitive(self):
			text = self.get_text()
			self.set_property('secondary-icon-sensitive', bool(text))

		check_icon_sensitive(self)
		self.connect('changed', check_icon_sensitive)

		return True

	def get_text(self):
		'''Get the text from the widget. Like C{gtk.Entry.get_text()}
		but with UTF-8 decoding and whitespace stripped.
		@returns: string
		'''
		if self._placeholder_text_shown:
			return ''

		text = gtk.Entry.get_text(self)
		if not text:
			return ''
		elif self.allow_whitespace:
			return text.decode('utf-8')
		else:
			return text.decode('utf-8').strip()

	def set_text(self, text):
		'''Wrapper for C{gtk.Entry.set_text()}.
		@param text: string
		'''
		if not text \
		and not self.get_property('has-focus'):
			gtk.Entry.set_text(self, text)
			self._show_placeholder_text()
		else:
			self._hide_placeholder_text()
			gtk.Entry.set_text(self, text)

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

		if self._normal_color:
			self._set_base_color(valid)
		# else: not yet initialized

		self._input_valid = valid
		self.emit('input-valid-changed')

	def _set_base_color(self, valid):
		if valid \
		or (not self.get_text() and not self.show_empty_invalid):
			self.modify_base(gtk.STATE_NORMAL, self._normal_color)
		else:
			self.modify_base(gtk.STATE_NORMAL, gtk.gdk.color_parse(self.ERROR_COLOR))

	def clear(self):
		'''Clear the text in the entry'''
		self.set_text('')

	def do_expose_event(self, event):
		gtk.Entry.do_expose_event(self, event)
		if not self.get_property('has-focus'):
			self._show_placeholder_text()

	def do_focus_in_event(self, event):
		self._hide_placeholder_text()
		gtk.Entry.do_focus_in_event(self, event)

	def do_focus_out_event(self, event):
		gtk.Entry.do_focus_out_event(self, event)
		self._show_placeholder_text()

	def _show_placeholder_text(self):
		if not self.get_text() \
		and self.placeholder_text:
			self._placeholder_text_shown = True
			gtk.Entry.set_text(self, self.placeholder_text)

			layout = self.get_layout()
			attr = pango.AttrList()
			end = len(self.placeholder_text)
			attr.insert(pango.AttrStyle(pango.STYLE_ITALIC, 0, end))
			c = 65535/16*8
			attr.insert(pango.AttrForeground(c,c,c, 0, end))
				# TODO make color configurable, now just solid grey
			layout.set_attributes(attr)
			# The layout is reset when new text is set, so
			# no need to "unset" the style at _hide_placeholder_text()

	def _hide_placeholder_text(self):
		if self._placeholder_text_shown:
			gtk.Entry.set_text(self, '')
			self._placeholder_text_shown = False

	def do_changed(self):
		text = self.get_text() or ''
		if self.check_func:
			self.set_input_valid(self.check_func(text))
		else:
			self.set_input_valid(bool(text) or self.allow_empty)


# Need to register classes defining / overriding gobject signals
gobject.type_register(InputEntry)


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
		if self.action == gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER:
			title = _('Select Folder') # T: dialog title
		elif self.file_type_hint == 'image':
			title = _('Select Image') # T: dialog title
		else:
			title = _('Select File') # T: dialog title

		dialog = FileDialog(window, title, self.action)
		if self.file_type_hint == 'image':
			dialog.add_filter_images()

		path = FSPathEntry.get_path(self) # overloaded in LinkEntry
		if path:
			dialog.set_file(path)

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
		if new: self.action = gtk.FILE_CHOOSER_ACTION_SAVE
		else: self.action = gtk.FILE_CHOOSER_ACTION_OPEN

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
		self.action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER

		if folder:
			self.set_folder(folder)

	set_folder = FSPathEntry.set_path
	get_folder = FSPathEntry.get_path


def gtk_entry_completion_match_func(completion, key, iter, column):
	if key is None:
		return False

	key = key.decode('utf-8').lower()
	key = unicodedata.normalize('NFKD', key)
		# decode utf-8 because we are called by gtk function
		# normalization could be done elsewhere, but keep together

	model = completion.get_model()
	text = model.get_value(iter, column)
	if text is not None:
		text = unicodedata.normalize('NFKD', text.decode('utf-8'))
		return key in text.lower()
	else:
		return False


def gtk_entry_completion_match_func_startswith(completion, key, iter, column):
	if key is None:
		return False

	key = key.decode('utf-8').lower()
	key = unicodedata.normalize('NFKD', key)
		# decode utf-8 because we are called by gtk function
		# normalization could be done elsewhere, but keep together

	model = completion.get_model()
	text  = model.get_value(iter, column)
	if text is not None:
		text = unicodedata.normalize('NFKD', text.decode('utf-8'))
		return text.lower().startswith(key)
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
		self._current_completion = ()

		if self._allow_select_root:
			placeholder_text = _('<Top>')
			# T: default text for empty page section selection
		else:
			placeholder_text = None
		InputEntry.__init__(self, allow_empty=self._allow_select_root, placeholder_text=placeholder_text)
		assert path is None or isinstance(path, Path)

		completion = gtk.EntryCompletion()
		completion.set_model(gtk.ListStore(str, str)) # visible name, match name
		completion.set_text_column(0)
		completion.set_inline_completion(True)
		self.set_completion(completion)

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
		self.set_text(':'+path.name)

	def get_path(self):
		'''Get the path shown in the widget.
		If C{None} is returned the widget is flagged as invalid. So e.g. in a
		dialog you can get a path and refuse to close a dialog if the path
		is None and the user will automatically be alerted to the missing input.

		@returns: a L{Path} object or C{None} is no valid path was entered
		'''
		name = self.get_text().decode('utf-8').strip()
		if self._allow_select_root and (name == ':' or not name):
			return Path(':')
		elif not name:
			self.set_input_valid(False)
			return None
		else:
			if self.subpaths_only and not name.startswith('+'):
				name = '+' + name
			try:
				if self.notebook:
					path = self.notebook.resolve_path(name, source=self.notebookpath)
				else:
					path = Path(name)
			except PageNameError:
				self.set_input_valid(False)
				return None
			else:
				if self.existing_only:
					page = self.notebook.get_page(path)
					if not (page and page.exists()):
						return None
				return path

	@staticmethod
	def _walk_relative(notebook, path):
		# sort nearest neighbor first using relative paths

		## TODO can be more efficient with a visitor pattern
		## that can stop recursion of some branches or force order

		# first yield children
		index = notebook.index
		for p in index.walk(path):
			yield notebook.relative_link(path, p), p.basename

		# than peers and parents, sort by distance
		if path.namespace:
			parent = Path(path.parts[0])
			peers = []
			for p in index.walk(parent):
				if not p.ischild(path):
					relname = notebook.relative_link(path, p)
					basename = p.basename
					distance = relname.count(':')
					peers.append((distance, relname, basename))
			peers.sort()
			for distance, relname, basename in peers:
				yield relname, basename
		else:
			parent = path

		# than the rest of the tree, excluding direct parent
		for p in index.walk():
			if not p.ischild(parent):
				yield notebook.relative_link(path, p), p.basename

	def do_changed(self):
		text = self.get_text()

		if not text:
			if self.existing_only:
				self.set_input_valid(False)
			else:
				self.set_input_valid(True)
				# FIXME: why should pageentry always allow empty input ?
			return

		# Check for a valid page name and clean up the text for completion
		orig = text
		if text in (':', '+'):
			pass
		else:
			try:
				text = Notebook.cleanup_pathname(text.lstrip('+'))
			except PageNameError:
				self.set_input_valid(False)
				return
			else:
				if self.existing_only:
					path = self.get_path() # get_path() checks existence
					self.set_input_valid(not path is None)
				else:
					self.set_input_valid(True)

			# restore pre- and postfix to cleaned up text
			if orig[0] == ':' and text[0] != ':':
				text = ':' + text
			elif orig[0] == '+' and text[0] != '+':
				text = '+' + text

			if orig[-1] == ':' and text[-1] != ':':
				text = text + ':'

		# Start completion
		#~ print 'COMPLETE page: "%s", raw: "%s", ref: %s' % (text, orig, self.notebookpath)
		if not self.notebook:
			return # no completion without a notebook

		if ':' in text:
			i = text.rfind(':')
			prefix = text[:i+1] # can still start with "+"
		elif text.startswith('+'):
			prefix = '+'
		else:
			prefix = ''

		# Check if we completed already for this case
		if prefix == self._current_completion:
			return
		else:
			self._current_completion = prefix

		# Resolve path
		if prefix == ':':
			path = Path(':')
		elif prefix == '':
			if self.notebookpath:
				path = Path(self.notebookpath.namespace)
			else:
				path = Path(':')
		elif prefix == '+':
			path = self.notebookpath or Path(':')
		else:
			link = prefix
			reference = self.notebookpath or Path(':')
			if self.subpaths_only and not link.startswith('+'):
				link = '+' + link.lstrip(':')

			try:
				path = self.notebook.resolve_path(link, source=reference)
			except PageNameError:
				return

		# Fill model with pages from pathname
		completion = self.get_completion()
		model = completion.get_model()
		model.clear()
		if prefix:
			# Complete a single namespace based on the prefix
			completion.set_match_func(gtk_entry_completion_match_func_startswith, 1)
			for p in self.notebook.index.list_pages(path):
				model.append((prefix+p.basename, prefix+p.basename))
		else:
			# Find any pages that match the text
			completion.set_match_func(gtk_entry_completion_match_func, 1)
			if self.notebookpath:
				for relname, basename in self._walk_relative(self.notebook, self.notebookpath):
					model.append((relname, basename))
			else:
				for p in self.notebook.index.walk():
					model.append((":"+p.name, p.basename))

		completion.complete()


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
		self.action = gtk.FILE_CHOOSER_ACTION_OPEN
		self.file_type_hint = None

	def get_path(self):
		# Check we actually got a valid path
		text = self.get_text().decode('utf-8').strip()
		if text:
			type = link_type(text)
			if type == 'page':
				return PageEntry.get_path(self)
			else:
				return None
		else:
			return None

	def do_changed(self):
		# Switch between path completion and file completion
		text = self.get_text().decode('utf-8').strip()
		if text:
			type = link_type(text)
			if type == 'page':
				PageEntry.do_changed(self)
			#~ elif type == 'file':
				#~ FileEntry.do_changed(self)
			else:
				self.set_input_valid(True)
		else:
			self.set_input_valid(True)


def format_title(title):
	'''Formats a window title (in fact just adds " - Zim" to the end).'''
	assert not title.lower().endswith(' zim')
	return '%s - Zim' % title


def get_window(ui):
	'''Returns a C{gtk.Window} object or C{None}.
	Used to find the parent window for dialogs.
	@param ui: a parent dialog or window, or GtkInterface object
	@returns: a C{gtk.Window} object or C{None}
	'''
	if isinstance(ui, gtk.Window):
		return ui
	elif hasattr(ui, 'mainwindow') \
	and isinstance(ui.mainwindow, gtk.Window):
		return ui.mainwindow
	else:
		return None


def register_window(window):
	'''Register this instance with the zim application, if not done
	so already.
	'''
	if  hasattr(window, 'ui') \
	and hasattr(window.ui, 'register_new_window'):
		window.ui.register_new_window(window)


# Some constants used to position widgets in the window panes
# These are named rather than numbered because they also appear
# in plugin preferences as options and as uistate keys
TOP = 'top' #: Top frame position in window
BOTTOM = 'bottom'#: Bottom frame position in window

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

WIDGET_POSITIONS = (
	((LEFT_PANE, TOP), _('Top Left')), # T: Option for placement of plugin widgets
	((LEFT_PANE, BOTTOM), _('Bottom Left')), # T: Option for placement of plugin widgets
	((RIGHT_PANE, TOP), _('Top Right')), # T: Option for placement of plugin widgets
	((RIGHT_PANE, BOTTOM), _('Bottom Right')), # T: Option for placement of plugin widgets
)


class WindowSidePane(gtk.VBox):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'close': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self):
		gtk.VBox.__init__(self)

		# Add bar with label and close button
		self.topbar = gtk.HBox()
		self.topbar.label = gtk.Label()
		self.topbar.label.set_alignment(0.0, 0.5)
		self.topbar.pack_start(self.topbar.label)
		self.topbar.pack_end(self._close_button(), False)
		self.pack_start(self.topbar, False)

		# Add notebook
		self.notebook = gtk.Notebook()
		self.notebook.set_show_border(False)
		if gtk.gtk_version >= (2, 22, 0):
			button = self._close_button()
			self.notebook.set_action_widget(button, gtk.PACK_END)

		self.add(self.notebook)

		self._update_topbar()

	def _close_button(self):
		button = CloseButton()
		button.connect('clicked', lambda o: self.emit('close'))
		return button

	def _update_topbar(self):
		children = self.get_children()
		assert children[0] == self.topbar
		n_pages = self.notebook.get_n_pages()

		# remove close button if any
		for widget in children:
			if isinstance(widget, WindowSidePaneWidget):
				widget.embed_closebutton(None)
		for widget in self.notebook.get_children():
			if isinstance(widget, WindowSidePaneWidget):
				widget.embed_closebutton(None)

		# Option 1: widget above notebook or no tabs in notebook
		# Show topbar without title, show tabs in notebook
		# (or embed close button in widget)
		if children[1] != self.notebook or n_pages == 0:
			embedded = False
			if children[1] != self.notebook \
			and isinstance(children[1], WindowSidePaneWidget):
				# see if we can embed the close button in the widget
				button = self._close_button()
				embedded = children[1].embed_closebutton(button)

			if not embedded:
				self.topbar.label.set_text('') # no title
				self.topbar.set_no_show_all(False)
				self.topbar.show_all()
			else:
				self.topbar.set_no_show_all(True)
				self.topbar.hide()

			self.notebook.set_show_tabs(True)
			if gtk.gtk_version >= (2, 22, 0):
				button = self.notebook.get_action_widget(gtk.PACK_END)
				button.set_no_show_all(True)
				button.hide()

			# TODO: for widget + single tab case add another title bar ?

		# Option 2: notebook with single tab
		# hide tabs, use topbar to show tab label
		# (or embed close button in notebook tab)
		elif n_pages == 1:
			self.notebook.set_show_tabs(False)
			child = self.notebook.get_nth_page(0)
			title = self.notebook.get_tab_label_text(child)
			self.topbar.label.set_text(title)
			if gtk.gtk_version >= (2, 22, 0):
				button = self.notebook.get_action_widget(gtk.PACK_END)
				button.set_no_show_all(True)
				button.hide()

			embedded = False
			if isinstance(child, WindowSidePaneWidget):
				# see if we can embed the close button in the widget
				button = self._close_button()
				embedded = child.embed_closebutton(button)

			if not embedded:
				self.topbar.set_no_show_all(False)
				self.topbar.show_all()
			else:
				self.topbar.set_no_show_all(True)
				self.topbar.hide()

		# Option 3: notebook with multiple tabs
		# show tabs, no text in topbar
		# If possible put close button next to tabs
		else:
			self.notebook.set_show_tabs(True)
			self.topbar.label.set_text('') # no title
			if gtk.gtk_version >= (2, 22, 0):
				button = self.notebook.get_action_widget(gtk.PACK_END)
				button.set_no_show_all(False)
				button.show_all()
				self.topbar.set_no_show_all(True)
				self.topbar.hide()
			else:
				self.topbar.set_no_show_all(False)
				self.topbar.show_all()

	def add_widget(self, widget, position):
		self.pack_start(widget, False)
		if position == TOP:
			# shuffle above notebook, below close bar
			self.reorder_child(widget, 1)
		self._update_topbar()

	def add_tab(self, title, widget):
		self.notebook.append_page(widget, tab_label=gtk.Label(title))
		self._update_topbar()

	def remove(self, widget):
		# Note: try box.remove() except .. causes GErrors here :(
		if widget in self.get_children():
			gtk.Box.remove(self, widget)
			self._update_topbar()
			return True
		elif widget in self.notebook.get_children():
			self.notebook.remove(widget)
			self._update_topbar()
			return True
		else:
			return False

	def is_empty(self):
		children = self.get_children()
		if len(children) == 2:
			assert children[0] == self.topbar
			assert children[1] == self.notebook
			return children[1].get_n_pages() == 0 # check for tabs
		else:
			return False # some widget in the pane

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
		else:
			for widget in self.get_children():
				if widget != self.topbar and widget != self.notebook:
					widget.grab_focus()
					break

	def do_key_press_event(self, event):
		if event.keyval == KEYVAL_ESC:
			self.emit('close')
			return True
		else:
			return gtk.VBox.do_key_press_event(self, event)

# Need to register classes defining gobject signals
gobject.type_register(WindowSidePane)


class WindowSidePaneWidget(object):
	'''Base class for widgets that want to integrate nicely in the
	L{WindowSidePane}
	'''

	def embed_closebutton(self, button):
		'''Embed a button in the widget to close the side pane
		@param button: an L{IconButton} or C{None} to un-set
		@returns: C{True} if supported and succesful
		'''
		return False



from zim.config import ConfigDefinition, ConfigDefinitionByClass

class ConfigDefinitionPaneToggle(ConfigDefinition):

	def __init__(self, default, window):
		ConfigDefinition.__init__(self, default)
		self.window = window

	def check(self, value):
		# Must be list of valid pane names
		if isinstance(value, basestring):
			value = self._eval_string(value)

		if isinstance(value, (tuple, list)) \
		and all(e in self.window._zim_window_sidepanes for e in value):
			return value
		else:
			raise ValueError, 'Unknown pane names in: %s' % value


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
		and (value[2] is None or isinstance(value[2], basestring)):
			return value
		else:
			raise ValueError, 'Value is not a valid pane state'


class Window(gtkwindowclass):
	'''Sub-class of C{gtk.Window} that will take care of hooking
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

	When zim is configured to run on a maemo device this class will
	inherit from C{hildon.Window} instead of C{gtk.Window} to make
	sure it plays nicely with the maemo environment.

	All windows in zim must inherit from this class.

	@signal: C{pane-state-changed (pane, visible, active)}: emitted when
	visibility or active tab changed for a specific pane
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'pane-state-changed': (gobject.SIGNAL_RUN_LAST, None, (object, bool, object)),
	}

	def __init__(self):
		gtkwindowclass.__init__(self)
		self._registered = False
		self._last_sidepane_focus = None

		self._zim_window_main = gtk.VBox()
		self._zim_window_left_paned = HPaned()
		self._zim_window_right_paned = HPaned()
		self._zim_window_top_paned = VPaned()
		self._zim_window_bottom_paned = VPaned()

		self._zim_window_left_pane = WindowSidePane()
		self._zim_window_right_pane = WindowSidePane()
		self._zim_window_top_pane = WindowSidePane()
		self._zim_window_bottom_pane = WindowSidePane()

		self._zim_window_top_special = gtk.VBox()

		gtkwindowclass.add(self, self._zim_window_main)
		self._zim_window_main.add(self._zim_window_left_paned)
		self._zim_window_left_paned.pack1(self._zim_window_left_pane, resize=False)
		self._zim_window_left_paned.pack2(self._zim_window_right_paned, resize=True)
		self._zim_window_right_paned.pack1(self._zim_window_top_special, resize=True)
		self._zim_window_right_paned.pack2(self._zim_window_right_pane, resize=False)
		self._zim_window_top_special.add(self._zim_window_top_paned)
		self._zim_window_top_paned.pack1(self._zim_window_top_pane, resize=False)
		self._zim_window_top_paned.pack2(self._zim_window_bottom_paned, resize=True)
		self._zim_window_bottom_paned.pack2(self._zim_window_bottom_pane, resize=True)

		self._zim_window_sidepanes = {
			LEFT_PANE: (
				self._zim_window_left_paned,
				self._zim_window_left_pane),
			RIGHT_PANE: (
				self._zim_window_right_paned,
				self._zim_window_right_pane),
			TOP_PANE: (
				self._zim_window_top_paned,
				self._zim_window_top_pane),
			BOTTOM_PANE: (
				self._zim_window_bottom_paned,
				self._zim_window_bottom_pane),
		}

		def _on_switch_page(notebook, page, pagenum, key):
			visible, size, active = self.get_pane_state(key)
			self.emit('pane-state-changed', key, visible, active)

		for key, value in self._zim_window_sidepanes.items():
			paned, pane = value
			pane.set_no_show_all(True)
			pane.zim_pane_state = (False, 200, None)
			pane.connect('close', lambda o, k: self.set_pane_state(k, False), key)
			pane.notebook.connect_after('switch-page', _on_switch_page, key)

	def add(self, widget):
		'''Add the main widget.
		@param widget: gtk widget to add in the window
		'''
		self._zim_window_bottom_paned.pack1(widget, resize=True)

	def add_bar(self, widget, position):
		'''Add a bar to top or bottom of the window. Used e.g. to add
		menu-, tool- & status-bars.
		@param widget: gtk widget for the bar
		@param position: C{TOP} or C{BOTTOM}
		'''
		self._zim_window_main.pack_start(widget, False)

		if position == TOP:
			# reshuffle widget to go above main widgets but
			# below earlier added bars
			i = self._zim_window_main.child_get_property(
					self._zim_window_left_paned, 'position')
			self._zim_window_main.reorder_child(widget, i)

		self._zim_window_main.set_focus_chain([self._zim_window_left_paned])
			# Force to ignore the bars in keyboard navigation
			# items in the bars are all accesible by accelerators

	def add_tab(self, title, widget, pane):
		'''Add a tab in one of the panes.
		@param title: string with title to put in the tab
		@param widget: the gtk widget to show in the tab
		@param pane: can be one of: C{LEFT_PANE}, C{RIGHT_PANE},
		C{TOP_PANE} or C{BOTTOM_PANE}.
		'''
		key = pane
		paned, pane = self._zim_window_sidepanes[key]
		pane.add_tab(title, widget)
		self.set_pane_state(key, True)

	def add_widget(self, widget, position):
		'''Add a widget in one of the panes outside of the tabs

		@param widget: the gtk widget to show in the tab
		@param position: a 2-tuple of a pane and a position in the pane.
		First element can be either C{LEFT_PANE} or C{RIGHT_PANE}
		(C{TOP_PANE} and C{BOTTOM_PANE} are not supported).
		Second element  can be either C{TOP}, or C{BOTTOM}.

		@note: Placing a widget in C{TOP_PANE}, C{TOP}, is supported as
		a special case, but should not be used by plugins.
		'''
		key, pos = position
		if key in (TOP_PANE, BOTTOM_PANE):
			if key == TOP_PANE and pos == TOP:
				# Special case for top widget outside of pane
				# used especially for PathBar
				self._zim_window_top_special.pack_start(widget, False)
				self._zim_window_top_special.reorder_child(widget, 0)
			else:
				raise NotImplementedError
		elif key in (LEFT_PANE, RIGHT_PANE):
			paned, pane = self._zim_window_sidepanes[key]
			pane.add_widget(widget, pos)
			self.set_pane_state(key, True)
		else:
			raise KeyError

	def remove(self, widget):
		'''Remove widget from any pane
		@param widget: the widget to remove
		'''
		if self._last_sidepane_focus == widget:
			self._last_sidepane_focus = None

		box = self._zim_window_top_special
		if widget in box.get_children():
			box.remove(widget)
			return

		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			paned, pane = self._zim_window_sidepanes[key]
			if pane.remove(widget):
				if pane.is_empty():
					self.set_pane_state(key, False)
				break
		else:
			raise ValueError, 'Widget not found in this window'

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
		assert self.uistate
		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			self.uistate[key] = self.get_pane_state(key)

	def get_pane_state(self, pane):
		'''Returns the state of a side pane.
		@param pane: can be one of: C{LEFT_PANE}, C{RIGHT_PANE},
		C{TOP_PANE} or C{BOTTOM_PANE}.
		@returns: a 3-tuple of visibility (boolean),
		pane size (integer), and active tab (label).
		'''
		# FIXME revert calculate size instead of position for left
		# and bottom widget
		key = pane
		paned, pane = self._zim_window_sidepanes[key]
		if pane.get_property('visible'):
			position = paned.get_position()
			active = gtk_notebook_get_active_tab(pane.notebook)
			return (True, position, active)
		else:
			return pane.zim_pane_state

		return state

	def set_pane_state(self, pane, visible, size=None, activetab=None, grab_focus=False):
		'''Returns the state of a side pane.
		@param pane: can be one of: C{LEFT_PANE}, C{RIGHT_PANE},
		C{TOP_PANE} or C{BOTTOM_PANE}.
		@param visible: C{True} to show the pane, C{False} to hide
		@param size: size of the side pane
		@param activetab: label of the active tab in the notebook or None
		(fails silently if tab is not found)
		@param grab_focus: if C{True} active tab will grab focus
		'''
		# FIXME get parent widget size and subtract to get position
		# for left and botton notebook
		# FIXME enforce size <  parent widget and > 0
		key = pane
		paned, pane = self._zim_window_sidepanes[key]
		if pane.get_property('visible') == visible \
		and size is None and activetab is None:
			if grab_focus:
				pane.grab_focus()
			return # nothing else to do

		oldstate = self.get_pane_state(key)
		if size is None:
			size = oldstate[1]
		if activetab is None:
			activetab = oldstate[2]
		position = size

		if visible:
			if not pane.is_empty():
				pane.set_no_show_all(False)
				pane.show_all()
				paned.set_position(position)
				if activetab is not None:
					try:
						gtk_notebook_set_active_tab(pane.notebook, activetab)
					except ValueError:
						pass

				if grab_focus:
					pane.grab_focus()
			#else:
			#	logger.debug('Trying to show an empty pane...')
		else:
			pane.hide()
			pane.set_no_show_all(True)

		pane.zim_pane_state = (visible, size, activetab)
		self.emit('pane-state-changed', key, visible, activetab)

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
			self.uistate['toggle_panes'] = self.get_visible_panes()
			for pane in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
				self.set_pane_state(pane, False)

	def show_all_panes(self):
		for pane in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			self.set_pane_state(pane, True)

	def get_visible_panes(self):
		'''Returns a list of panes that are visible'''
		panes = []
		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			paned, pane = self._zim_window_sidepanes[key]
			if not pane.is_empty() and pane.get_property('visible'):
				panes.append(key)
		return panes

	def get_used_panes(self):
		'''Returns a list of panes that are in use (i.e. not empty)'''
		panes = []
		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			paned, pane = self._zim_window_sidepanes[key]
			if not pane.is_empty():
				panes.append(key)
		return panes

	def do_set_focus(self, widget):
		# keep track of last sidepane widget that had focus..
		if widget:
			parent = widget.get_parent()
			while parent:
				if isinstance(parent, WindowSidePane):
					self._last_sidepane_focus = widget
					break
				parent = parent.get_parent()

		return gtkwindowclass.do_set_focus(self, widget)

	def focus_last_sidepane(self):
		if self._last_sidepane_focus \
		and self._last_sidepane_focus.get_property('visible'):
			self._last_sidepane_focus.grab_focus()
			return True
		else:
			return False

	def pack_start(self, *a):
		raise NotImplementedError, "Use add() instead"

	def show(self):
		self.show_all()

	def show_all(self):
		# First register, than init uistate - this ensures plugins
		# are enabled before we finalize the presentation of the window.
		# This is important for state of e.g. panes to work correctly
		if not self._registered:
			register_window(self)
			self._registered = True
		if hasattr(self, 'uistate'):
			self.init_uistate()
		gtkwindowclass.show_all(self)

# Need to register classes defining gobject signals
gobject.type_register(Window)


class Dialog(gtk.Dialog, ConnectorMixin):
	'''Sub-class of C{gtk.Dialog} with a number of convenience methods
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

	@ivar ui: parent C{gtk.Window} or C{GtkInterface}
	@ivar vbox: C{gtk.VBox} for main widgets of the dialog
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

			dialog = MyDialog.unique(ui, somearg)
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

	def __init__(self, ui, title,
			buttons=gtk.BUTTONS_OK_CANCEL, button=None,
			help_text=None, help=None,
			defaultwindowsize=(-1, -1)
		):
		'''Constructor.

		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object
		@param title: the dialog title
		@param buttons: a constant controlling what kind of buttons the
		dialog will have. One of:
			- C{None} or C{gtk.BUTTONS_NONE}: for dialogs taking care
			  of constructing the buttons themselves
			- C{gtk.BUTTONS_OK_CANCEL}: Render Ok and Cancel
			- C{gtk.BUTTONS_CLOSE}: Only set a Close button
		@param button: a 2-tuple of a label and a stock item to use
		instead of the default 'Ok' button (either stock or label
		can be None).
		@param help_text: set the help text, see L{add_help_text()}
		@param help: pagename for a manual page, see L{set_help()}
		@param defaultwindowsize: default window size in pixels

		@note: some sub-classes expect C{self.ui} to always be a
		L{GtkInterface}
		'''
		gtk.Dialog.__init__(
			self, parent=get_window(ui),
			title=format_title(title),
			flags=gtk.DIALOG_NO_SEPARATOR|gtk.DIALOG_DESTROY_WITH_PARENT,
		)
		if hasattr(ui, 'ui') and hasattr(ui.ui, 'uistate'):
				ui = ui.ui # HACK - we get other window instead.. - avoid triggering Mock objects in test ...

		self.ui = ui
		self.result = None
		self._registered = False
		if not ui_environment['smallscreen']:
			self.set_border_width(10)
			self.vbox.set_spacing(5)

		if hasattr(self, 'uistate'):
			assert isinstance(self.uistate, zim.config.ConfigDict) # just to be sure
		elif hasattr(ui, 'uistate') \
		and isinstance(ui.uistate, zim.config.SectionedConfigDict):
			key = self.__class__.__name__
			self.uistate = ui.uistate[key]
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
		if not button is None:
			button = Button(*button)

		if buttons is None or buttons == gtk.BUTTONS_NONE:
			self._no_ok_action = True
		elif buttons == gtk.BUTTONS_OK_CANCEL:
			self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
			if button:
				self.add_action_widget(button, gtk.RESPONSE_OK)
			else:
				self.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
		elif buttons == gtk.BUTTONS_CLOSE:
			self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_OK)
			self._no_ok_action = True
		else:
			assert False, 'BUG: unknown button type'
		# TODO set Ok button as default widget
		# see gtk.Window.set_default()

		if help_text: self.add_help_text(help_text)
		if help: self.set_help(help)

	def destroy(self):
		self.disconnect_all()
		gtk.Dialog.destroy(self)

	@property
	def destroyed(self): return not self.has_user_ref_count
		# Returns True when dialog has been destroyed

	#{ Layout methods

	def add_extra_button(self, button, pack_start=True):
		'''Add a button to the action area at the bottom of the dialog.
		Packs the button in the list of primary buttons (by default
		these are in the lower right of the dialog)
		@param button: the C{gtk.Button} (or other widget)
		@param pack_start: if C{True} pack to the left (towards the
		middle of the dialog), if C{False} pack to the right.
		'''
		self.action_area.pack_start(button, False)
		if pack_start:
			self.action_area.reorder_child(button, 0)

	def set_help(self, pagename):
		'''Set the name of the manual page with help for this dialog.
		Setting this will add a "help" button to the dialog.
		@param pagename: the manual page name
		'''
		#~ assert hasattr(self.ui, 'show_help'), 'Need ui object to open help'
		self.help_page = pagename
		button = gtk.Button(stock=gtk.STOCK_HELP)
		button.connect_object('clicked', self.__class__.show_help, self)
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

	def show_help(self, page=None):
		'''Show a help page
		@param page: the manual page, if C{None} the page as set with
		L{set_help()} is used
		'''
		self.ui.show_help(page or self.help_page)
			# recurses until gui.show_help is reached

	def add_help_text(self, text):
		'''Adds a label with an info icon in front of it. Intended for
		informational text in dialogs.
		@param text: help text
		'''
		hbox = help_text_factory(text)
		self.vbox.pack_start(hbox, False)

	def add_text(self, text):
		'''Adds a label to the dialog
		Also see L{add_help_text()} for another style option.
		@param text: dialog text
		'''
		label = gtk.Label(text)
		label.set_use_markup(True)
		label.set_alignment(0.0, 0.0)
		self.vbox.pack_start(label, False)

	def add_form(self, inputs, values=None, depends=None, trigger_response=True):
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
		if hasattr(self.ui, 'notebook'):
			notebook = self.ui.notebook
		else:
			notebook = None
		self.form = InputForm(inputs, values, depends, notebook)
		if trigger_response:
			self.form.connect('last-activated', lambda o: self.response_ok())
		self.vbox.pack_start(self.form, False)
		return self.form

	#}

	#{ Interaction methods

	def run(self):
		'''Wrapper for C{gtk.Dialog.run()}, also calls C{show_all()}
		@returns: C{self.result}
		'''
		self.show_all()
		if TEST_MODE:
			assert TEST_MODE_RUN_CB, 'Dialog run without test callback'
			TEST_MODE_RUN_CB(self)
		else:
			while not self.destroyed:
				gtk.Dialog.run(self)
		return self.result

	def present(self):
		self.show_all()
		if TEST_MODE:
			assert TEST_MODE_RUN_CB, 'Dialog run without test callback'
			TEST_MODE_RUN_CB(self)
		else:
			gtk.Dialog.present(self)

	def show(self):
		self.show_all()

	def show_all(self):
		logger.debug('Opening dialog "%s"', self.title)
		if not self._registered:
			register_window(self)
			self._registered = True
		if not TEST_MODE:
			gtk.Dialog.show_all(self)

	def response_ok(self):
		'''Trigger the response signal with response type 'OK'.'''
		self.response(gtk.RESPONSE_OK)

	def assert_response_ok(self):
		'''Like L{response_ok()}, but raise an error when
		L{do_response_ok} returns C{False}.
		Also it explicitly does not handle errors in L{do_response_ok}.
		Intended for use by the test suite.
		@returns: C{self.result}
		@raises AssertionError: if L{do_response_ok} returns C{False}
		'''
		if not (self._no_ok_action or self.do_response_ok() is True):
			raise AssertionError, '%s.do_response_ok() did not return True' % self.__class__.__name__
		self.save_uistate()
		self.destroy()
		return self.result

	def do_response(self, id):
		# Handler for the response signal, dispatches to do_response_ok()
		# or do_response_cancel() and destroys the dialog if that function
		# returns True.
		# Ensure the dialog always closes on delete event, regardless
		# of any errors or bugs that may occur.
		if id == gtk.RESPONSE_OK and not self._no_ok_action:
			logger.debug('Dialog response OK')
			try:
				destroy = self.do_response_ok()
			except Exception, error:
				ErrorDialog(self.ui, error).run()
				destroy = False
			else:
				if not destroy:
					logger.warning('Dialog input not valid')
		elif id == gtk.RESPONSE_CANCEL:
			logger.debug('Dialog response CANCEL')
			try:
				destroy = self.do_response_cancel()
			except Exception, error:
				ErrorDialog(self.ui, error).run()
				destroy = False
			else:
				if not destroy:
					logger.warning('Could not cancel dialog')
		else:
			destroy = True

		try:
			if ui_environment['platform'] != 'maemo':
				x, y = self.get_position()
				self.uistate['_windowpos'] = (x, y)
				w, h = self.get_size()
				self.uistate['windowsize'] = (w, h)
				self.save_uistate()
		except:
			logger.exception('Exception in do_response()')

		if destroy:
			self.destroy()
			logger.debug('Closed dialog "%s"', self.title[:-6])

	def do_response_ok(self):
		'''Handler called when the user clicks the "OK" button (or
		an equivalent button)

		@returns: C{True} if succesful and the dialog can close. Returns
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

# Need to register classes defining gobject signals
gobject.type_register(Dialog)


class ErrorDialog(gtk.MessageDialog):
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

	def __init__(self, ui, error, exc_info=None, do_logging=True,
				buttons=gtk.BUTTONS_CLOSE
	):
		'''Constructor

		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object

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
			- C{None} or C{gtk.BUTTONS_NONE}: for dialogs taking care
			  of constructing the buttons themselves
			- C{gtk.BUTTONS_OK_CANCEL}: Render Ok and Cancel
			- C{gtk.BUTTONS_CLOSE}: Only set a Close button
		'''
		if not isinstance(error, Exception):
			if isinstance(error, tuple):
				msg, description = error
				error = zim.errors.Error(msg, description)
			else:
				msg = unicode(error)
				error = zim.errors.Error(msg)

		self.error = error
		self.do_logging = do_logging
		msg, show_trace = zim.errors.get_error_msg(error)

		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_ERROR, buttons=buttons,
			message_format=msg
		)

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
			self.vbox.add(window)
			self.vbox.show_all()
			# TODO use an expander here ?
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
			'FS encoding: %s\n' % zim.fs.ENCODING + \
			'Python: %s\n' % str(tuple(sys.version_info)) + \
			'Gtk: %s\n' % str(gtk.gtk_version) + \
			'Pygtk: %s\n' % str(gtk.pygtk_version)


		text += zim.get_zim_revision() + '\n'

		# FIXME: more info here? Like notebook path, page, environment etc. ?

		text += '\n======= Traceback =======\n'
		if tb:
			lines = traceback.format_tb(tb)
			text += ''.join(lines)
		else:
			text += '<Could not extract stack trace>\n'

		text += self.error.__class__.__name__ + ': ' + unicode(self.error)

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
			response = gtk.MessageDialog.run(self)
			if response == gtk.RESPONSE_OK and not self.do_response_ok():
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


class QuestionDialog(gtk.MessageDialog):
	'''Convenience class to prompt the user with Yes/No answer type
	of questions.

	Note that message dialogs do not have a title.
	'''

	def __init__(self, ui, question):
		'''Constructor.

		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object

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

		self.response = None
		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_QUESTION, buttons=gtk.BUTTONS_YES_NO,
			message_format=question
		)
		if text:
			self.format_secondary_text(text)

		self.connect('response', self.__class__.do_response)

	def do_response(self, id):
		self.response = id

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
			gtk.MessageDialog.run(self)
		self.destroy()
		answer = self.response == gtk.RESPONSE_YES
		logger.debug('A: %s', answer)
		return answer


class MessageDialog(gtk.MessageDialog):
	'''Convenience wrapper for C{gtk.MessageDialog}, should be used for
	informational popups without an action.

	Note that message dialogs do not have a title.
	'''

	def __init__(self, ui, msg):
		'''Constructor.

		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object

		@param msg: the message either as sring or a 2-tuple of the
		actual question and a longer explanation as strings. Using a
		tuple here will give a better looking dialog.
		'''

		if isinstance(msg, tuple):
			msg, text = msg
		else:
			text = None

		self.response = None
		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_QUESTION, buttons=gtk.BUTTONS_OK,
			message_format=msg,
			flags=gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT,
		)
		if text:
			self.format_secondary_text(text)

	def add_extra_button(self, button, pack_start=True):
		'''Add a button to the action area at the bottom of the dialog.
		Packs the button in the list of primary buttons (by default
		these are in the lower right of the dialog)
		@param button: the C{gtk.Button} (or other widget)
		@param pack_start: if C{True} pack to the left (towards the
		middle of the dialog), if C{False} pack to the right.
		'''
		self.action_area.pack_start(button, False)
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
			gtk.MessageDialog.run(self)
		self.destroy()

	def assert_response_ok(self):
		return True # message dialogs are always OK


class FileDialog(Dialog):
	'''File Chooser dialog, that allows to browser the file system and
	select files or folders. Similar to C{gtk.FileChooserDialog} but
	inherits from L{Dialog} instead.

	This dialog will automatically show previews for image files.

	When using C{dialog.run()} it will return the selected file(s) or
	dir(s) based on the arguments given during construction.
	'''

	def __init__(self, ui, title, action=gtk.FILE_CHOOSER_ACTION_OPEN,
			buttons=gtk.BUTTONS_OK_CANCEL, button=None,
			help_text=None, help=None, multiple=False
		):
		'''Constructor.

		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object

		@param title: the dialog title

		@param action: the file chooser action, one of::
			gtk.FILE_CHOOSER_ACTION_OPEN
			gtk.FILE_CHOOSER_ACTION_SAVE
			gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
			gtk.FILE_CHOOSER_ACTION_CREATE_FOLDER

		@param buttons: see L{Dialog.__init__()}
		@param button: see L{Dialog.__init__()}
		@param help_text: see L{Dialog.__init__()}
		@param help: see L{Dialog.__init__()}

		@param multiple: if C{True} the dialog will allow selecting
		multiple files at once.
		'''
		if button is None:
			if action == gtk.FILE_CHOOSER_ACTION_OPEN:
				button = (None, gtk.STOCK_OPEN)
			elif action == gtk.FILE_CHOOSER_ACTION_SAVE:
				button = (None, gtk.STOCK_SAVE)
			# else Ok will do

		if ui_environment['platform'] == 'maemo':
			defaultsize = (800, 480)
		else:
			defaultsize = (500, 400)

		Dialog.__init__(self, ui, title, defaultwindowsize=defaultsize,
			buttons=buttons, button=button, help_text=help_text, help=help)

		self.filechooser = gtk.FileChooserWidget(action=action)
		self.filechooser.set_do_overwrite_confirmation(True)
		self.filechooser.set_select_multiple(multiple)
		self.filechooser.connect('file-activated', lambda o: self.response_ok())
		self.vbox.add(self.filechooser)
		# FIXME hook to expander to resize window for FILE_CHOOSER_ACTION_SAVE

		self.preview_widget = gtk.Image()
		self.filechooser.set_preview_widget(self.preview_widget)
		self.filechooser.connect('update-preview', self.on_update_preview)

	def on_update_preview(self, *a):
		filename = self.filechooser.get_preview_filename()
		try:
			info, w, h = gtk.gdk.pixbuf_get_file_info(filename)
			if w <= 128 and h <= 128:
				# Show icons etc. on real size
				pixbuf = gtk.gdk.pixbuf_new_from_file(filename)
			else:
				# Scale other images to fit the window
				pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(filename, 128, 128)
			self.preview_widget.set_from_pixbuf(pixbuf)
			self.filechooser.set_preview_widget_active(True)
		except:
			self.filechooser.set_preview_widget_active(False)
		return

	def set_file(self, file):
		'''Set the file or dir to pre select in the dialog
		@param file: a L{File} or L{Dir} object
		'''
		ok = self.filechooser.set_filename(file.path)
		if not ok:
			raise Exception, 'Could not set filename: %s' % file.path

	def get_file(self):
		'''Get the current selected file
		@returns: a L{File} object or C{None}.
		'''
		path = self.filechooser.get_filename()
		if path is None: return None
		else: return File(path.decode('utf-8'))

	def get_files(self):
		'''Get list of selected file. Assumes the dialog was created
		with C{multiple=True}.
		@returns: a list of L{File} objects
		'''
		paths = [path.decode('utf-8')
				for path in self.filechooser.get_filenames()]
		return [File(path) for path in paths]

	def get_dir(self):
		'''Get the the current selected dir. Assumes the dialog was
		created with action C{gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER} or
		C{gtk.FILE_CHOOSER_ACTION_CREATE_FOLDER}.
		@returns: a L{Dir} object or C{None}
		'''
		path = self.filechooser.get_filename().decode('utf-8')
		if path is None: return None
		else: return Dir(path)

	def _add_filter_all(self):
		filter = gtk.FileFilter()
		filter.set_name(_('All Files'))
			# T: Filter in open file dialog, shows all files (*)
		filter.add_pattern('*')
		self.filechooser.add_filter(filter)

	def add_filter(self, name, glob):
		'''Add a filter for files with specific extensions in the dialog
		@param name: the label to display in the filter selection
		@param glob: a file pattern (e.g. "*.txt")
		@returns: the C{gtk.FileFilter} object
		'''
		if len(self.filechooser.list_filters()) == 0:
			self._add_filter_all()
		filter = gtk.FileFilter()
		filter.set_name(name)
		filter.add_pattern(glob)
		self.filechooser.add_filter(filter)
		self.filechooser.set_filter(filter)
		return filter

	def add_filter_images(self):
		'''Add a standard file filter for selecting image files.
		@returns: the C{gtk.FileFilter} object
		'''
		if len(self.filechooser.list_filters()) == 0:
			self._add_filter_all()
		filter = gtk.FileFilter()
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
		action = self.filechooser.get_action()
		multiple = self.filechooser.get_select_multiple()
		if action in (
			gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
			gtk.FILE_CHOOSER_ACTION_CREATE_FOLDER
		):
			if multiple:
				self.result = self.get_dirs()
			else:
				self.result = self.get_dir()
		else:
			if multiple:
				self.result = self.get_files()
			else:
				self.result = self.get_file()

		return bool(self.result)


class ProgressBarDialog(gtk.Dialog):
	'''This class implements a dialog with a progress bar.

	ProgressBarDialogs supposed to run modal, but are not called with
	C{run()} as they are typically driven by a callback of a async
	action. Typical construct would be::

		dialog = ProgressBarDialog(ui, 'My progress bar')

		def cb_func(*arg):
			cancel = dialog.pulse()
			return cancel

		with dialog:
			self.async_foo(callback=cb_func)

	This example assumes that the method C{async_foo()} will cancel as
	soon as the callback returns C{False}.

	The dialog is used as context manager, so the dialog is properly
	destroyed in case of an error.

	The usage of a progress bar dialog I{must} implement a cancel action.

	Note that progress bars dialogs do not have a title. But the given
	title will be shown as a label in the dialog itself.

	If you know how often L{pulse()} will be called and give this total
	number the bar will display a percentage. Otherwise the bar will
	just bounce up and down without indication of remaining time.
	'''

	def __init__(self, ui, text, total=None):
		'''Constructor

		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object

		@param text: text to show above the progress bar. Typically
		should be the action being executed, like "Updating Links".
		This is not a dialog title, so phrasing is slightly different.

		@param total: number of times we expect L{pulse()} to be called,
		if known. Will result in the bar showing progress by percentage.
		Can later be modified by supplying a new total number directly
		to L{pulse()}.
		'''
		self.ui = ui
		self.cancelled = False
		gtk.Dialog.__init__(
			# no title - see HIG about message dialogs
			self, parent=get_window(self.ui),
			title='',
			flags=gtk.DIALOG_NO_SEPARATOR | gtk.DIALOG_MODAL,
			buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
		)
		self.set_border_width(10)
		self.vbox.set_spacing(5)
		self.set_default_size(300, 0)

		label = gtk.Label()
		label.set_markup('<b>'+encode_markup_text(text)+'</b>')
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False)

		self.progressbar = gtk.ProgressBar()
		self.vbox.pack_start(self.progressbar, False)

		self.msg_label = gtk.Label()
		self.msg_label.set_alignment(0.0, 0.5)
		self.msg_label.set_ellipsize(pango.ELLIPSIZE_START)
		self.vbox.pack_start(self.msg_label, False)

		self.set_total(total)

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.destroy()
		return False # re-raises error

	def set_total(self, total):
		'''Set the number of times we expect L{pulse()} to be called,
		calling this method also resets the count
		@param total: number of times we expect L{pulse()} to be called
		'''
		self.total = total
		self.count = 0

	def pulse(self, msg=None, count=None, total=None):
		'''update the dialog and move the progress bar by one step.

		First call to C{pulse()} will also trigger a C{show_all()} if
		the dialog is not shown yet. By not showing the dialog before
		C{pulse()} is called prevents the dialog flashing over the
		screen when the operation was very quick after all and never
		needed to call the callback.

		This method also run other pending gtk events. So the interface
		keeps looking repsonsive is a long operation calls this method
		often enough.

		@param msg: optional message to show below the progress bar,
		e.g. the name of the item being processed
		@param count: count of steps already done, if C{None} the
		number of steps is equal to number of times C{pulse()} has
		been called.
		@param total: total number of steps expected, if C{None} a
		previous set total is used. If no total is known the bar
		will just bounce up and down without indication of remaining
		items.

		@returns: C{True} until the 'Cancel' button has been pressed,
		this should be used to decide if the background job should
		continue or not.
		'''
		if not TEST_MODE and not self.get_property('visible'):
			self.show_all()

		if total and total != self.total:
			self.set_total(total)
			self.count = count or 0
		elif count:
			self.count = count - 1

		if self.total and self.count < self.total:
			self.count += 1
			fraction = float(self.count) / self.total
			self.progressbar.set_fraction(fraction)
			self.progressbar.set_text('%i%%' % int(fraction * 100))
		else:
			self.progressbar.pulse()

		if msg:
			self.msg_label.set_markup('<i>'+encode_markup_text(msg)+'</i>')

		while gtk.events_pending():
			gtk.main_iteration(block=False)

		return not self.cancelled

	def show_all(self):
		logger.debug('Opening ProgressBarDialog')
		if not TEST_MODE:
			gtk.Dialog.show_all(self)

	def do_response(self, id):
		logger.debug('ProgressBarDialog get response %s', id)
		self.cancelled = True

	#def do_destroy(self):
	#	logger.debug('Closed ProgressBarDialog')


# Need to register classes defining gobject signals
gobject.type_register(ProgressBarDialog)


class LogFileDialog(Dialog):
	'''Simple dialog to show a log file'''

	def __init__(self, ui, file):
		Dialog.__init__(self, ui, _('Log file'), buttons=gtk.BUTTONS_CLOSE)
			# T: dialog title for log view dialog - e.g. for Equation Editor
		self.set_default_size(600, 300)
		window, textview = ScrolledTextView(file.read(), monospace=True)
		self.vbox.add(window)



class Assistant(Dialog):
	'''Dialog with multi-page input, sometimes also revert to as a
	"wizard". Similar to C{gtk.Assistent} separate implementation to
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

	def __init__(self, ui, title, **options):
		'''Constructor

		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object
		@param title: dialog title
		@param options: other dialog options, see L{Dialog.__init__()}
		'''
		Dialog.__init__(self, ui, title, **options)
		self.set_border_width(5)
		self._pages = []
		self._page = -1
		self._uistate = self.uistate
		self.uistate = self._uistate.copy()
		# Use temporary state, so we can cancel the wizard

		buttons = [b for b in self.action_area.get_children()
			if not self.action_area.child_get_property(b, 'secondary')]
		#~ print [b.get_label() for b in buttons]
		self.ok_button = buttons[0] # HACK: not sure this order fixed
		self.ok_button.set_no_show_all(True)

		self.back_button = gtk.Button(stock=gtk.STOCK_GO_BACK)
		self.back_button.connect_object('clicked', self.__class__.previous_page, self)
		self.action_area.add(self.back_button)

		self.forw_button = gtk.Button(stock=gtk.STOCK_GO_FORWARD)
		self.forw_button.set_no_show_all(True)
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
			if not isinstance(child, gtk.ButtonBox):
				self.vbox.remove(child)

		self._page = i
		page = self._pages[self._page]

		# Add page title - use same color as used by gtkassistent.c
		# This is handled on expose event, because style does not
		# yet reflect theming on construction
		# However also need to disconnect the signal after first use,
		# because otherwise this keeps firing, which hangs the loop
		# for handling events in ProgressBarDialog.pulse() - LP #929247
		ebox = gtk.EventBox()
		def _set_heading_color(*a):
			ebox.modify_fg(gtk.STATE_NORMAL, self.style.fg[gtk.STATE_SELECTED])
			ebox.modify_bg(gtk.STATE_NORMAL, self.style.bg[gtk.STATE_SELECTED])
			self.disconnect(self._expose_event_id)

		self._expose_event_id = \
			self.connect('expose-event', _set_heading_color)

		hbox = gtk.HBox()
		hbox.set_border_width(5)
		ebox.add(hbox)
		self.vbox.pack_start(ebox, False)

		label = gtk.Label()
		label.set_markup('<b>' + page.title + '</b>')
		hbox.pack_start(label, False)
		label = gtk.Label()
		label.set_markup('<b>(%i/%i)</b>' % (self._page+1, len(self._pages)))
		hbox.pack_end(label, False)

		# Add actual page
		self.vbox.add(page)
		self.vbox.show_all()
		page.init_uistate()

		self.back_button.set_sensitive(self._page > 0)
		if self._page < len(self._pages) - 1:
			self.forw_button.show()
			self.ok_button.hide()
		else:
			self.forw_button.hide()
			self.ok_button.show()

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
		if id == gtk.RESPONSE_OK:
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
			raise AssertionError, '%s.do_response_ok() did not return True' % self.__class__.__name__
		self.save_uistate()
		self.destroy()
		return self.result


class AssistantPage(gtk.VBox):
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
		'input-valid-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	title = ''

	def __init__(self, assistant):
		'''Constructor
		@param assistant: the L{Assistant} dialog
		'''
		gtk.VBox.__init__(self)
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
		self.form = InputForm(inputs, values, depends, notebook=self.assistant.ui.notebook)
		self.form.connect('input-valid-changed', lambda o: self.check_input_valid())
		self.pack_start(self.form, False)
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

# Need to register classes defining gobject signals
gobject.type_register(AssistantPage)


class ImageView(gtk.Layout):
	'''Widget to show an image, scales the image and sets proper
	background.
	'''

	SCALE_FIT = 1 #: scale image with the window (if the image is bigger)
	SCALE_STATIC = 2 #: use scaling factor

	__gsignals__ = {
		'size-allocate': 'override',
	}

	def __init__(self, bgcolor='#FFF', checkerboard=True):
		'''Constructor
		@param bgcolor: background color as color hex code, (e.g. "#FFF")
		@param checkerboard: if C{True} a checkerboard is drawn behind
		transparent images, if C{False} it is just the background color.
		'''
		gtk.Layout.__init__(self)
		self.set_flags(gtk.CAN_FOCUS)
		self.scaling = self.SCALE_FIT
		self.factor = 1

		self._pixbuf = None
		self._render_size = None # allocation w, h for which we have rendered
		self._render_timeout = None # timer before updating rendering
		self._image = gtk.Image() # pixbuf is set for the image in _render()
		self.add(self._image)

		colormap = self._image.get_colormap()
		self._lightgrey = colormap.alloc_color('#666')
		self._darkgrey = colormap.alloc_color('#999')

		if bgcolor:
			self.set_bgcolor(bgcolor)
		self.checkerboard = checkerboard

	def set_bgcolor(self, bgcolor):
		'''Set background color
		@param bgcolor: background color as color hex code, (e.g. "#FFF")
		'''
		assert bgcolor.startswith('#'), 'BUG: Should specify colors in hex'
		color = gtk.gdk.color_parse(bgcolor)
			# gtk.gdk.Color(spec) only for gtk+ >= 2.14
		self.modify_bg(gtk.STATE_NORMAL, color)

	def set_checkerboard(self, checkerboard):
		'''Set checkerboard for transparent images
		@param checkerboard: if C{True} a checkerboard is drawn behind
		transparent images, if C{False} it is just the background color.
		'''
		self.checkerboard = checkerboard

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

		if file:
			try:
				pixbuf = gtk.gdk.pixbuf_new_from_file(str(file))
			except:
				logger.exception('Could not load image "%s"', file)
		else:
			pass

		self.set_pixbuf(pixbuf)

	def set_pixbuf(self, pixbuf):
		'''Set the image to display from a pixbuf
		@param pixbuf: a C{gtk.gdk.Pixbuf} or C{None} to display a
		broken image icon.
		'''
		if pixbuf is None:
			pixbuf = self.render_icon(
				gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_DIALOG).copy()
		self._pixbuf = pixbuf
		self._render()

	def do_size_allocate(self, allocation):
		gtk.Layout.do_size_allocate(self, allocation)

		# remove timer if any
		if self._render_timeout:
			gobject.source_remove(self._render_timeout)

		if not self._pixbuf \
		or (allocation.width, allocation.height) == self._render_size:
			pass # no update of rendering needed
		else:
			# set new timer for 100ms
			self._render_timeout = gobject.timeout_add(100, self._render)

	def _render(self):
		# remove timer if any
		if self._render_timeout:
			gobject.source_remove(self._render_timeout)

		# Determine what size we want to render the image
		allocation = self.allocation
		wwin, hwin = allocation.width, allocation.height
		wsrc, hsrc = self._pixbuf.get_width(), self._pixbuf.get_height()
		self._render_size = (wwin, hwin)
		#~ print 'Allocated', (wwin, hwin),
		#~ print 'Source', (wsrc, hsrc)

		if self.scaling == self.SCALE_STATIC:
			wimg = self.factor * wsrc
			himg = self.factor * hsrc
		elif self.scaling == self.SCALE_FIT:
			if hsrc <= wwin and hsrc <= hwin:
				# image fits in the screen - no scaling
				wimg, himg = wsrc, hsrc
			elif (float(wwin)/wsrc) < (float(hwin)/hsrc):
				# Fit by width
				wimg = wwin
				himg = int(hsrc * float(wwin)/wsrc)
			else:
				# Fit by height
				wimg = int(wsrc * float(hwin)/hsrc)
				himg = hwin
		else:
			assert False, 'BUG: unknown scaling type'
		#~ print 'Image', (wimg, himg)

		# Scale pixbuf to new size
		wimg = max(wimg, 1)
		himg = max(himg, 1)
		if not self.checkerboard or not self._pixbuf.get_has_alpha():
			if (wimg, himg) == (wsrc, hsrc):
				pixbuf = self._pixbuf
			else:
				pixbuf = self._pixbuf.scale_simple(
							wimg, himg, gtk.gdk.INTERP_NEAREST)
		else:
			# Generate checkerboard background while scaling
			pixbuf = self._pixbuf.composite_color_simple(
				wimg, himg, gtk.gdk.INTERP_NEAREST,
				255, 16, self._lightgrey.pixel, self._darkgrey.pixel )

		# And align the image in the layout
		wvirt = max((wwin, wimg))
		hvirt = max((hwin, himg))
		#~ print 'Virtual', (wvirt, hvirt)
		self._image.set_from_pixbuf(pixbuf)
		self.set_size(wvirt, hvirt)
		self.move(self._image, (wvirt-wimg)/2, (hvirt-himg)/2)

		return False # We could be called by a timeout event

# Need to register classes defining gobject signals
gobject.type_register(ImageView)


class PromptExistingFileDialog(Dialog):
	'''Dialog that is used e.g. when a file should be attached to zim,
	but a file with the same name already exists in the attachment
	directory. This Dialog allows to suggest a new name or overwrite
	the existing one.

	For this dialog C{run()} will return either the original file
	(for overwrite), a new file, or None when the dialog was canceled.
	'''

	def __init__(self, ui, file):
		'''Constructor
		@param ui: either a parent window or dialog or the main
		C{GtkInterface} object
		@param file: a L{File} object for an existing file
		'''
		Dialog.__init__(self, ui, _('File Exists'), buttons=None) # T: Dialog title
		self.add_help_text( _('''\
A file with the name <b>"%s"</b> already exists.
You can use another name or overwrite the existing file.''' % file.basename),
		) # T: Dialog text in 'new filename' dialog
		self.old_file = file
		self.dir = file.dir

		suggested_filename = file.dir.new_file(file.basename).basename
		self.add_form((
				('name', 'string', _('Filename')), # T: Input label
			), {
				'name': suggested_filename
			}
		)
		self.form.widgets['name'].set_check_func(self._check_valid)

		# all buttons are defined in this class, to get the ordering right
		# [show folder]      [overwrite] [cancel] [ok]
		button = gtk.Button(_('_Browse')) # T: Button label
		button.connect('clicked', self.do_show_folder)
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

		button = gtk.Button(_('Overwrite')) # T: Button label
		button.connect('clicked', self.do_response_overwrite)
		self.add_action_widget(button, gtk.RESPONSE_NONE)

		self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
		self.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
		self._no_ok_action = False

		self.form.widgets['name'].connect('focus-in-event',	self._on_focus)

	def _on_focus(self, widget, event):
		# filename length without suffix
		length = len(os.path.splitext(widget.get_text())[0])
		widget.select_region(0, length)

	def _check_valid(self, filename):
		# Only valid when same dir and does not yet exist
		file = self.dir.file(filename)
		return file.dir == self.dir and not file.exists()

	def do_show_folder(self, *a):
		self.ui.open_file(self.dir)

	def do_response_overwrite(self, *a):
		logger.info('Overwriting %s', self.old_file.path)
		self.result = self.old_file

	def do_response_ok(self):
		if not self.form.widgets['name'].get_input_valid():
			return False

		newfile = self.dir.file(self.form['name'])
		logger.info('Selected %s', newfile.path)
		assert newfile.dir == self.dir # just to be real sure
		assert not newfile.exists() # just to be real sure
		self.result = newfile
		return True
