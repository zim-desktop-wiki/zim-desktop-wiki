# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains a number of custom gtk widgets
that are used in the zim gui modules.

TODO document dialog base classes
'''

import gobject
import gtk
import pango
import logging
import sys
import os

from zim.fs import *
import zim.errors
import zim.config
from zim.config import value_is_coord
from zim.notebook import Notebook, Path, PageNameError
from zim.parsing import link_type


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


# UI Environment config. Would properly belong in zim.gui.__init__
# but defined here to avoid unnecessary dependencies on zim.gui
ui_environment = {
	'platform': None, # platform name to trigger platform specific optimizations
	'maxscreensize': None, # max screensize _if_ fixed by the platform
	'smallscreen': False, # trigger optimizations for small screens
}


# Check for Maemo environment
try:
	import hildon
	gtkwindowclass = hildon.Window
	ui_environment['platform'] = 'maemo'
	if hasattr(Window,'set_app_menu'):
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
except ImportError:
	gtkwindowclass = gtk.Window


def _encode_xml(text):
	return text.replace('>', '&gt;').replace('<', '&lt;')


def gtk_window_set_default_icon():
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


def scrolled_text_view(text=None, monospace=False):
	'''Initializes a gtk.TextView with sane defaults for displaying a
	piece of multiline text, wraps it in a scrolled window and returns
	both the window and the textview. When 'monospace' is True the font
	will be set to Monospaced and line wrapping disabled, use this to
	display log files etc.
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
	window = gtk.ScrolledWindow()
	window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
	window.set_shadow_type(gtk.SHADOW_IN)
	window.add(textview)
	return window, textview


def gtk_combobox_set_active_text(combobox, text):
	'''Like gtk.ComboBox.set_active() but takes a string instead of an
	index. Will match this string agains the list of options and select
	the correct index. Raises a ValueError when the string is not found
	in the list. Intended as companion of gtk.ComboBox.get_active_text().
	'''
	model = combobox.get_model()
	for i, value in enumerate(model):
		if value[0] == text:
			return combobox.set_active(i)
	else:
		raise ValueError, text


class TextBuffer(gtk.TextBuffer):
	'''Sub-class of gtk.TextBuffer that does utf-8 decoding on get_text
	and get_slice.
	'''

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


def gtk_get_style():
	'''Returns a gtk.Style object for the current theme style.
	This function is a bit of a hack, but works.
	'''
	w = gtk.Window()
	w.realize()
	return w.get_style()


def rotate_pixbuf(pixbuf):
	'''If the pixbuf has asociated data for the image rotation
	(e.g. EXIF for photos) it will rotate the pixbuf to the correct
	orientation. Returns a new version of the pixbuf or the pixbuf itself.
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
	'''Create a label with an info icon in front of it. Intended for
	iformational text in dialogs.
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
	# Hook label or secondairy widget to follow state of e.g. entry widget
	# check_active is only meaningfull if widget is a togglebutton and
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
	'''Takes a list of inputs and returns a table with nice layout
	for those inputs. Inputs in the list given should be either 'None',
	a gtk widget, or a tuple of a string and one or more widgets.
	If a tuple is given and the first item is 'None', the widget
	will be lined out in the 2nd column. A 'None' value in the input
	list represents an empty row in the table.

	Only use this function directly if you want a completely custom
	input form. For standard forms see the InputForm class.
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
	'''This class overloads the constructor of the default gtk.Button
	class. The purpose is to change the behavior in such a way that stock
	icon and label can be specified independently. If only stock or only
	label is given, it falls back to the default behavior of gtk.Button .
	'''

	def __init__(self, label=None, stock=None, use_underline=True):
		if label is None or stock is None:
			gtk.Button.__init__(self, label=label, stock=stock)
		else:
			gtk.Button.__init__(self, label=label)
			icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
			self.set_image(icon)
		self.set_use_underline(use_underline)


class IconButton(gtk.Button):
	'''Button with a stock icon, but no label.'''

	def __init__(self, stock, relief=True):
		gtk.Button.__init__(self)
		icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
		self.add(icon)
		self.set_alignment(0.5, 0.5)
		if not relief:
			self.set_relief(gtk.RELIEF_NONE)


class IconChooserButton(gtk.Button):
	'''Button with a stock icon, but no label.'''

	def __init__(self, stock=gtk.STOCK_MISSING_IMAGE, pixbuf=None):
		'''Constructor with initial image. If a pixbuf is given it is
		used instead of the stock icon.
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
		image = self.get_child()
		size = max(image.size_request()) # HACK to get icon size
		pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.path, size, size)
		image.set_from_pixbuf(pixbuf)
		self.file = file

	def get_file(self):
		return self.file

# Need to register classes defining / overriding gobject signals
gobject.type_register(IconChooserButton)


class SingleClickTreeView(gtk.TreeView):
	'''Treeview subclass for trees that want single-click behavior,
	but do allow multiple items to be selected.
	'''

	mask = gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK

	def do_button_release_event(self, event):
		'''Handler for button-release-event, implements single click navigation'''

		if event.button == 1 and not event.state & self.mask \
		and not self.is_rubber_banding_active():
			x, y = map(int, event.get_coords())
				# map to int to surpress deprecation warning :S
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

	# backwards compatibility
	if gtk.gtk_version < (2, 12, 0):
		def set_rubber_banding(self, enable):
			pass

		def is_rubber_banding_active(self):
			return False

# Need to register classes defining / overriding gobject signals
gobject.type_register(SingleClickTreeView)


class BrowserTreeView(SingleClickTreeView):
	'''TreeView subclass intended for lists that are in "browser" mode.
	Default behavior will be single click navigation for these lists.

	Extra keybindings that are added here:
		<Left>   Collapse sub-items
		<Right>  Expand sub-items
		\        Collapse whole tree
		*        Expand whole tree
	'''

	# TODO some global option to restore to double click navigation ?

	def __init__(self, *arg):
		gtk.TreeView.__init__(self, *arg)
		self.get_selection().set_mode(gtk.SELECTION_BROWSE)

	def do_key_press_event(self, event):
		'''Handler for key-press-event, adds extra key bindings'''
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
			model, iter = self.get_selection().get_selected()
			if not iter is None:
				path = model.get_path(iter)
				self.collapse_row(path)
		elif event.keyval == KEYVAL_RIGHT:
			model, iter = self.get_selection().get_selected()
			if not iter is None:
				path = model.get_path(iter)
				self.expand_row(path, 0)
		else:
			handled = False

		if handled:
			return True
		else:
			return gtk.TreeView.do_key_press_event(self, event)

# Need to register classes defining / overriding gobject signals
gobject.type_register(BrowserTreeView)


class MenuButton(gtk.HBox):
	'''A button which pops up a menu when clicked. It behaves different from
	a combobox because it is not a selector and the label on the button is
	not a selected item from the menu. Main example of this widget type is the
	button with backlinks in the statusbar of the main window.

	This module is based loosely on gedit-status-combo-box.c from the gedit
	sources.
	'''

	# Set up a style for the statusbar variant to decrease spacing of the button
	gtk.rc_parse_string('''\
style "zim-statusbar-menubutton-style"
{
	GtkWidget::focus-padding = 0
	GtkWidget::focus-line-width = 0
	xthickness = 0
	ythickness = 0
}
widget "*.zim-statusbar-menubutton" style "zim-statusbar-menubutton-style"
''')

	def __init__(self, label, menu, status_bar_style=False):
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
			self.button.set_name('zim-statusbar-menubutton')
			self.button.set_relief(gtk.RELIEF_NONE)
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
		Sub-calsses can overload and wrap it to populate the menu
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


class InputForm(gtk.Table):
	'''Class wrapping a table with input widgets. Takes care of
	managing the widgets and presenting a nice layout.

	Instances of this class can accessed as a dict to get and set the
	values of the various input widgets by name.

	To access the widgets directly (e.g. to wire more signals) there
	is an attribute 'widgets' which contains a dict of input widgets
	by name.

	Signals:
	  * last-activated: this signal is emitted when the last widget in
	    the form is activated, can be used to trigger a default response
	    in a dialog.
	  * input-valid-changes: valid state the form changed
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

	# TODO actually add support for radio check boxes
	# specify like "name:option"

	def __init__(self, inputs=None, values=None, depends=None, notebook=None):
		'''Constructor.
		The 'inputs' are passed to add_inputs() and 'values' are passed
		to update(). The option 'depends' can be a dict which key values
		pairs are passed on to depends().
		You need to set 'notebook' to get completion in page inputs.
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

		if inputs:
			self.add_inputs(inputs)

		if depends:
			for k, v in depends.items():
				self.depends(k, v)

		if values:
			self.update(values)

	def add_inputs(self, inputs):
		'''Turns a list of field descriptions into a list of widgets.
		This list can be given to layout_table() to turn it into a form.

		The argument 'inputs' should be a list of
		input definitions; each definition is a tuple of:

			* The input name
			* The input type
			* The label to put in front of the input field

		The following field types are supported:
			* 'bool' - checkbox
			* 'option' - radiocheckbox
			* 'int' - integer spin button
			* 'choice' - a drop downlist for multiple choice
			* 'string' - text entry
			* 'password' - text entry with chars hidden
			* 'page' - PageEntry
			* 'namespace' - NamespaceEntry
			* 'link' - LinkEntry
			* 'dir' - input for existing folder
			* 'file' - input for existing file
			* 'image' - like 'file' but specific for images
			* 'output-file' - input for new or existing file

		The option 'option' can be used to have groups of checkboxes.
		In this case the name should exist of two parts separated by a
		':', first part is the group name and the second part the key for
		this option. This way multiple options of the same group can be
		specified as separate widgets. Only the group name will show up
		as a key in the form, the value will be the option name of the
		selected radio button. So you can have names like "select:all"
		and "select:page" which will result in two radiobuttons. The
		form will have a key "select" which has either a value "all" or
		a value "page".

		The 'int' and 'choice' options need an extra argument to specify
		the allowed inputs. For 'int' this should be a tuple with the
		minimum and maximum values. For 'choice' it should be a list
		with the items to choose from.

		The 'page', 'namespace' and 'link' options have an optional
		extra argument which gives the reference path for resolving
		relative paths. This also requires the notebook to be set.

		A None value in the input list will result in additional row
		spacing in the form.
		'''

		# For options we use rsplit to split group and option name.
		# The reason for this that if there are any other ":" separated
		# parts they belong to the group name, not the option name.
		# (This is used in e.g. the preference dialog to encode sections
		# where an option goes in the config.)

		widgets = []

		for input in inputs:
			if input is None:
				widgets.append(None)
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
				widgets.append((label, entry))

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
			elif isinstance(widget, gtk.ComboBox):
				widget.connect('changed', self.on_activate_widget)
			else:
				pass

			# Connect valid state
			if isinstance(widget, InputEntry):
				widget.connect('input-valid-changed', self._check_input_valid)
				for property in ('visible', 'sensitive'):
					widget.connect_after('notify::%s' % property, self._check_input_valid)

		input_table_factory(widgets, table=self)

		self._check_input_valid() # update our state

	def on_activate_widget(self, widget):
		'''Calls focus_next() or emits last-activated when last widget
		was activated.
		'''
		if not self._focus_next(widget, activatable=True):
			self.emit('last-activated')

	def focus_first(self):
		'''Focusses the first input in the form'''
		return self._focus_next(None)

	def focus_next(self):
		'''Focusses the next input in the form'''
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

	def depends(self, subject, object):
		'''Both argument should be names of widgets in the form. This
		method makes behavior of 'subject' depend on state of 'object'.
		E.g. subject will only be sensitive when object is active and
		subject will be hidden when object is hidden.
		'''
		subject = self.widgets[subject]
		object = self.widgets[object]
		_sync_widget_state(object, subject, check_active=True)

	def get_input_valid(self):
		'''Returns combined state of all active widgets in the form'''
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
				return widget.get_active_text()
			elif isinstance(widget, gtk.SpinButton):
				return int(widget.get_value())
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
				gtk_combobox_set_active_text(widget, value)
			elif isinstance(widget, gtk.SpinButton):
				widget.set_value(value)
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
		'''Similar to dict.update(). Updates any values for existing
		inputs from the mapping while silently ignoring other keys in
		the map.
		'''
		for key, value in map.items():
			if key in self._keys:
				self[key] = value

	def copy(self):
		'''Returns a normal dict with values for all widgets in the form'''
		values = {}
		for key in self._keys:
			values[key] = self[key]
		return values

# Need to register classes defining / overriding gobject signals
gobject.type_register(InputForm)


class InputEntry(gtk.Entry):
	'''Sub-class of gtk.Entry with support for highlighting errors.
	Use this class as a  generic replacement for gtk.Entry to avoid
	utf-8 issues.

	The constructor takes a function for checking if the content is
	valid. If not set the state is always set to valid after the user
	modifies the text. The way this can be used is to set state to
	invalid e.g. in a dialog response handler. This will show the user
	what widget to modify. After typing try again. Providing a method
	to give immediate feedback to the user is of course better.

	Signals:
	  * input-valid-changes: valid state the form changed
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'input-valid-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	style = gtk_get_style()
	NORMAL_COLOR = style.base[gtk.STATE_NORMAL]
	ERROR_COLOR = gtk.gdk.color_parse('#EF7F7F') # light red (derived from Tango style guide)

	def __init__(self, check_func=None, allow_empty=True, show_empty_invalid=False):
		'''Constructor takes a validation function 'check'. This
		function is called with the current text as argument and
		should return boolean.

		As an alternative you can set 'allow_empty' to False to do
		validation only on the fact if there is content or not.

		The 'show_empty_invalid' determines if we also show a red
		background when the entry is still empty.
		'''
		gtk.Entry.__init__(self)
		self.allow_empty = allow_empty
		self.show_empty_invalid = show_empty_invalid
		self.check_func = check_func
		self._input_valid = False
		self.do_changed() # Initialize state
		self.connect('changed', self.__class__.do_changed)

	def set_check_func(self, check_func):
		'''Set a function to check whether input is valid or not'''
		self.check_func = check_func
		self.do_changed()

	def get_text(self):
		'''Like gtk.Entry.get_text() but with utf-8 decoding and
		whitespace stripped.
		'''
		text = gtk.Entry.get_text(self)
		if not text: return ''
		else: return text.decode('utf-8').strip()

	def get_input_valid(self):
		return self._input_valid

	def set_input_valid(self, valid):
		'''Set input valid or invalid state'''
		if valid == self._input_valid:
			return

		if valid \
		or (not self.get_text() and not self.show_empty_invalid):
			self.modify_base(gtk.STATE_NORMAL, self.NORMAL_COLOR)
		else:
			self.modify_base(gtk.STATE_NORMAL, self.ERROR_COLOR)

		self._input_valid = valid
		self.emit('input-valid-changed')

	def do_changed(self):
		'''Check if content is valid'''
		text = self.get_text() or ''
		if self.check_func:
			self.set_input_valid(self.check_func(text))
		else:
			self.set_input_valid(bool(text) or self.allow_empty)

# Need to register classes defining / overriding gobject signals
gobject.type_register(InputEntry)


class FSPathEntry(InputEntry):
	'''Base class for FileEntry and FolderEntry, should not be
	used directly.

	A notebook and page can be specified to make the entry show
	paths relative to the notebook (based on notebook.resolve_file()
	and notebook.relative_filepath() ). Otherwise paths will show
	absolute paths. Since relative paths can start with "/" when a
	document dir is set, this can result in absolute paths being shown
	as file uris in the entry.
	'''

	# TODO file / folder completion in the entry (think about rel paths!)
	# wire LinkENtry to use this completion

	def __init__(self):
		'''Constructor, notebook and path are used for relative paths'''
		InputEntry.__init__(self, allow_empty=False)
		self.notebook = None
		self.notebookpath = None
		self.action = None
		self.file_type_hint = None

	def set_use_relative_paths(self, notebook, path=None):
		'''Set the notebook and path to be used for relative paths.
		Set C{notebook=None} to disable relative paths.

		@param notebook: the L{Notebook} object for resolving paths
		@keyword path: a L{Path} object used for resolving relative links
		'''
		self.notebook = notebook
		self.notebookpath = path

	def set_path(self, path):
		if self.notebook:
			text = self.notebook.relative_filepath(path, self.notebookpath)
			if text is None:
				if self.notebook.document_root:
					text = path.uri
				else:
					text = path.path
			self.set_text(text)
		else:
			home = Dir('~')
			if path.ischild(home):
				self.set_text('~/'+path.relpath(home))
			else:
				self.set_text(path.path)

	def get_path(self):
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
		'''Run a dialog to browser for a file or folder.
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

	_class = File

	def __init__(self, file=None, new=False):
		'''Construcor. If 'new' is True the intention is a new
		file (e.g. output file), or to overwrite an existing
		file. If 'new' is False only existing files can be selected.
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

	_class = Dir

	def __init__(self, folder=None):
		FSPathEntry.__init__(self)
		self.file_type_hint = 'dir'
		self.action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER

		if folder:
			self.set_folder(folder)

	set_folder = FSPathEntry.set_path
	get_folder = FSPathEntry.get_path


class PageEntry(InputEntry):
	'''Input widget for zim page names

	This widget features completion for existing page names and will show when the
	entered text is not a valid page name.
	'''

	_allow_select_root = False

	def __init__(self, notebook, path=None, subpaths_only=False, existing_only=False):
		'''Contructor

		Typically this widget uses a Notebook to resolve paths and show completion,
		but can be used with notebook=None if really needed. If a path is given as
		well this is used as the start for resolving relative links.

		@param notebook: the L{Notebook} object for resolving paths and
		completing existing pages
		@keyword path: a L{Path} object used for resolving relative links
		@keyword subpaths_only: if C{True} the input will always be
		considered a sub path of 'path'
		@keyword existing_only: if C{True} only allow to select existing pages

		@note: 'subpaths_only' and 'existing_only' can also be set using
		the like named attributes
		'''
		self.notebook = notebook
		self.notebookpath = path
		self.subpaths_only = subpaths_only
		self.existing_only = existing_only
		self._current_completion = ()

		InputEntry.__init__(self, allow_empty=False)
		assert path is None or isinstance(path, Path)

		completion = gtk.EntryCompletion()
		completion.set_model(gtk.ListStore(str))
		completion.set_text_column(0)
		completion.set_inline_completion(True)
		self.set_completion(completion)

	def set_use_relative_paths(self, notebook, path=None):
		'''Set the notebook and path to be used for relative paths.
		Set C{notebook=None} to disable relative paths.

		@param notebook: the L{Notebook} object for resolving paths and
		completing existing pages
		@keyword path: a L{Path} object used for resolving relative links
		'''
		self.notebook = notebook
		self.notebookpath = path

	def set_path(self, path):
		'''Set the path to be shown in the entry

		@note: If you have the link as a string, use L{set_text()} instead

		@param path: L{Path} object
		'''
		self.set_text(':'+path.name)

	def get_path(self):
		'''Returns the path shown in the widget if it is valid or None.

		If None is returned the widget is flagged as invalid. So e.g. in a
		dialog you can get a path and refuse to close a dialog if the path
		is None and the user will automatically be alerted to the missing input.

		@returns: a L{Path} object or C{None} is no valid path was entered
		'''
		name = self.get_text().decode('utf-8').strip()
		if not name:
			self.set_input_valid(False)
			return None
		elif self._allow_select_root and name == ':':
			return Path(':')
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

	def do_changed(self):
		text = self.get_text()

		if not text:
			if self.existing_only:
				self.set_input_valid(False)
			else:
				self.set_input_valid(True)
				# FIXME: why should pageentry always allow empty input ?
			return

		# Check for a valid page name
		orig = text
		if text != ':' and text != '+':
			try:
				text = Notebook.cleanup_pathname(text.lstrip('+'))
			except PageNameError:
				self.set_input_valid(False)
				return

			# restore pre- and postfix
			if orig[0] == ':' and text[0] != ':':
				text = ':' + text
			elif orig[0] == '+' and text[0] != '+':
				text = '+' + text

			if orig[-1] == ':' and text[-1] != ':':
				text = text + ':'
		else:
			pass

		if self.existing_only:
			path = self.get_path()
			self.set_input_valid(not path is None)
		else:
			self.set_input_valid(True)

		# Start completion
		if not self.notebook:
			return # no completion without a notebook

		# Figure out the namespace to complete
		#~ print 'COMPLETE page: "%s", raw: "%s", ref: %s' % (text, orig, self.notebookpath)
		anchored = False
		if ':' in text:
			# can still have context and start with '+'
			i = text.rfind(':')
			completing = text[:i+1]
			prefix = completing
			anchored = True
		elif self.notebookpath:
			if text.startswith('+'):
				completing = ':' + self.notebookpath.name
				prefix = '+'
				anchored = True
			else:
				completing = ':' + self.notebookpath.namespace
				prefix = ''
		else:
			completing = ':'
			prefix = ''

		if self.subpaths_only and not completing.startswith('+'):
			# Needed for new_sub_page - always force child page
			completing = '+' + completing
			anchored = True

		# Check if we completed already for this case
		if (prefix, completing) == self._current_completion:
			#~ print '\t NO NEW COMPLETION'
			return

		#~ print '\t COMPLETING "%s", namespace: %s' % (prefix, completing)
		self._current_completion = (prefix, completing)

		# Resolve path and fill model with pages from namespace
		completion = self.get_completion()
		model = completion.get_model()
		model.clear()

		if completing == ':':
			path = Path(':')
		else:
			try:
				path = self.notebook.resolve_path(completing, source=self.notebookpath)
			except PageNameError:
				#~ print '\t NOT A VALID NAMESPACE'
				return
			#~ else:
				#~ print '\t NAMESPACE', path

		# TODO also add parent namespaces in case text did not contain any ':' (anchored == False)
		for p in self.notebook.index.list_pages(path):
			model.append((prefix+p.basename,))

		completion.complete()


class NamespaceEntry(PageEntry):
	'''Input widget for zim page names when used as namespace

	Use this instead of PageEntry when you want to allow selecting a namespace.
	Most notably it will be allowed to select ":" or empty string for the root
	namespace, this is not allowed in PageEntry.
	'''

	_allow_select_root = True


class LinkEntry(PageEntry, FileEntry):
	'''Input widget that accepts zim page names, file links and urls'''

	_class = File

	def __init__(self, notebook, path=None):
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
	'''Returns a gtk.Window object or None. Used to find the parent window
	for dialogs.
	'''
	if isinstance(ui, gtk.Window):
		return ui
	elif hasattr(ui, 'mainwindow'):
		return ui.mainwindow
	else:
		return None


def register_window(window):
	'''Register this instance with the zim application, if not done
	so already.
	'''
	if ( not hasattr(window, '_zim_window_registered') \
		or not window._zim_window_registered ) \
	and hasattr(window, 'ui') \
	and hasattr(window.ui, 'register_new_window'):
		window.ui.register_new_window(window)
		window._zim_window_registered = True


# Some constants used to position widgets in the window panes
TOP = 0
BOTTOM = 1

LEFT_PANE = 0
RIGHT_PANE = 1
TOP_PANE = 2
BOTTOM_PANE = 3

class Window(gtkwindowclass):
	'''Wrapper for the gtk.Window class that will take care of hooking
	the window into the application framework and adds entry points
	so plugins can add side panes etc. It will divide the window
	horizontally in 3 panes, and the center pane again verticaly in 3.
	The result is something like this:

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

	Of course any pane that is not used will not been shown. The
	important thing is to create placeholders where plugins *might*
	want to add some widget.
	'''

	# TODO generalized way to set pane position and pane visibility
	#      in the uistate and load again
	# TODO generalized way to have a "show pane" button in the toolbar
	#      - general button when multiple tabs, other name of one tab in button ???

	def __init__(self):
		gtkwindowclass.__init__(self)

		self._zim_window_main = gtk.VBox()
		self._zim_window_left_pane = gtk.HPaned()
		self._zim_window_right_pane = gtk.HPaned()
		self._zim_window_top_pane = gtk.VPaned()
		self._zim_window_bottom_pane = gtk.VPaned()

		self._zim_window_left = gtk.VBox()
		self._zim_window_right = gtk.VBox()
		self._zim_window_top = gtk.VBox()
		self._zim_window_bottom = gtk.VBox()

		self._zim_window_left_notebook = gtk.Notebook()
		self._zim_window_right_notebook = gtk.Notebook()
		self._zim_window_top_notebook = gtk.Notebook()
		self._zim_window_bottom_notebook = gtk.Notebook()

		self._zim_window_left.add(self._zim_window_left_notebook)
		self._zim_window_right.add(self._zim_window_right_notebook)
		self._zim_window_top.add(self._zim_window_top_notebook)
		self._zim_window_bottom.add(self._zim_window_bottom_notebook)

		self._zim_window_top_special = gtk.VBox()

		gtkwindowclass.add(self, self._zim_window_main)
		self._zim_window_main.add(self._zim_window_left_pane)
		self._zim_window_left_pane.add1(self._zim_window_left)
		self._zim_window_left_pane.add2(self._zim_window_right_pane)
		self._zim_window_right_pane.add1(self._zim_window_top_special)
		self._zim_window_right_pane.add2(self._zim_window_right)
		self._zim_window_top_special.add(self._zim_window_top_pane)
		self._zim_window_top_pane.add1(self._zim_window_top)
		self._zim_window_top_pane.add2(self._zim_window_bottom_pane)
		self._zim_window_bottom_pane.add2(self._zim_window_bottom)

		for box in (
			self._zim_window_left,
			self._zim_window_right,
			self._zim_window_top,
			self._zim_window_bottom,
		):
			box.set_no_show_all(True)

		for nb in (
			self._zim_window_left_notebook,
			self._zim_window_right_notebook,
			self._zim_window_top_notebook,
			self._zim_window_bottom_notebook,
		):
			nb.set_no_show_all(True)
			nb.set_show_tabs(False)
			nb.set_show_border(False)

	def add(self, widget):
		'''Add the main widget'''
		self._zim_window_bottom_pane.add1(widget)

	def add_bar(self, widget, position):
		'''Add a bar to top or bottom of the window. Used e.g. to add
		menu-, tool- & status-bars. Position can be either 'TOP' or
		'BOTTOM'.
		'''
		self._zim_window_main.pack_start(widget, False)

		if position == TOP:
			# reshuffle widget to go above main widgets
			i = self._zim_window_main.child_get_property(
					self._zim_window_left_pane, 'position')
			self._zim_window_main.reorder_child(widget, i)

	def add_tab(self, title, widget, pane):
		'''Add a tab in one of the panes, 'pane' can be one of
		'LEFT_PANE', 'RIGHT_PANE', 'TOP_PANE' or 'BOTTOM_PANE'.
		'''
		assert pane in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE)

		if pane == LEFT_PANE: nb = self._zim_window_left_notebook
		elif pane == RIGHT_PANE: nb = self._zim_window_right_notebook
		elif pane == TOP_PANE: nb = self._zim_window_top_notebook
		elif pane == BOTTOM_PANE: nb = self._zim_window_bottom_notebook

		nb.append_page(widget, tab_label=gtk.Label(title))
		if nb.get_n_pages() > 1:
			nb.set_show_tabs(True)

		nb.set_no_show_all(False)
		nb.show()

		parent = nb.get_parent()
		parent.set_no_show_all(False)
		parent.show()

	def add_widget(self, widget, pane, position):
		'''Add a widget in one of the panes without using a tab,
		'pane' can be either 'LEFT_PANE' or 'RIGHT_PANE' (placing
		widgets in 'TOP_PANE' or 'BOTTOM_PANE' is currently not
		supported), 'position' can be either 'TOP' or 'BOTTOM'.

		Placing a widget in TOP_PANE, TOP, is supported as a special
		case, but should not be used by plugins.
		'''
		assert not isinstance(widget, gtk.Notebook), 'Please don\'t do this'
		assert pane in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE)
		assert position in (TOP, BOTTOM)

		if pane in (TOP_PANE, BOTTOM_PANE):
			if pane == TOP_PANE and position == TOP:
				# Special case for top widget outside of pane
				# used especially for PathBar
				self._zim_window_top_special.pack_start(widget, False)
				self._zim_window_top_special.reorder_child(widget, 0)
			else:
				raise NotImplementedError
		elif pane in (LEFT_PANE, RIGHT_PANE):
			if pane == LEFT_PANE:
				vbox = self._zim_window_left
			else:
				vbox = self._zim_window_right

			vbox.pack_start(widget, False)
			if position == TOP:
				vbox.reorder_child(widget, 0) # TODO shuffle above notebook
			vbox.set_no_show_all(False)
			vbox.show()
		else:
			raise AssertionError, "Unsupported argument for 'pane'"

	def remove(self, widget):
		'''Remove widget from any pane'''
		for box in (
			self._zim_window_left,
			self._zim_window_right,
			self._zim_window_top,
			self._zim_window_bottom,
			self._zim_window_top_special,
			self._zim_window_left_notebook,
			self._zim_window_right_notebook,
			self._zim_window_top_notebook,
			self._zim_window_bottom_notebook,
		):
			if not widget in box.get_children():
				continue
				# Note: try .. except .. causes GErrors here :(

			box.remove(widget)

			# Hide containers if they are empty
			if box == self._zim_window_top_special:
				pass # special case
			elif isinstance(box, gtk.VBox):
				children = box.get_children()
				if len(children) == 1:
					assert isinstance(children[0], gtk.Notebook)
					if children[0].get_n_pages() == 0:
						box.set_no_show_all(True)
						box.hide()
			else:
				assert isinstance(box, gtk.Notebook)
				i = box.get_n_pages()
				if i == 0:
					box.set_no_show_all(True)
					box.hide()
					parent = box.get_parent()
					if len(parent.get_children()) == 1:
						parent.set_no_show_all(True)
						parent.hide()
				elif i == 1:
					box.set_show_tabs(False)
			return
		else:
			raise ValueError, 'Widget not found in this window'

	def pack_start(self, *a):
		raise NotImplementedError, "Use add() instead"

	def show(self):
		self.show_all()

	def show_all(self):
		register_window(self)
		gtkwindowclass.show_all(self)


class Dialog(gtk.Dialog):
	'''Wrapper around gtk.Dialog used for most zim dialogs.
	It adds a number of convenience routines to build dialogs.
	The default behavior is modified in such a way that dialogs are
	destroyed on response if the response handler returns True.

	For a simple dialog the subclass only needs to call Dialog.__init__()
	with to define the title and input fields of the dialog, and overload
	do_response_ok() to handle the result.
	'''

	@classmethod
	def unique(klass, handler, *args, **opts):
		'''This method is used to instantiate a dialog of which there should
		be only one visible at a time. It enforces a singleton pattern by
		installing a weak reference in the handler object. If there is an
		dialog active which is not yet destroyed, this dialog is returned,
		otherwise a new dialog is created using 'args' and 'opts' as the
		arguments to the constructor.

		For example on "show_dialog" you could do:

			dialog = MyDialog.unique(ui, somearg)
			dialog.present()

		'''
		import weakref
		attr = '_unique_dialog_%s' % klass.__name__
		dialog = None

		if hasattr(handler, attr):
			ref = getattr(handler, attr)
			dialog = ref()

		if dialog is None or dialog.destroyed:
			dialog = klass(*args, **opts)

		setattr(handler, attr, weakref.ref(dialog))
		return dialog

	@property
	def destroyed(self): return not self.has_user_ref_count
		# Returns True when dialog has been destroyed

	def __init__(self, ui, title,
			buttons=gtk.BUTTONS_OK_CANCEL, button=None,
			help_text=None, help=None,
			defaultwindowsize=(-1, -1)
		):
		'''Constructor. 'ui' can either be the main application or some
		other dialog from which this dialog is spwaned. 'title' is the dialog
		title. 'buttons' is a constant controlling what kind of buttons the
		dialog will have. Currently supported are:

			* None or gtk.BUTTONS_NONE - for dialog taking care of this themselves
			* gtk.BUTTONS_OK_CANCEL - Render Ok and Cancel
			* gtk.BUTTONS_CLOSE - Only set a Close button

		'button' is an optional argument giving a tuple of a label and a stock
		item to use instead of the default 'Ok' button (either stock or label
		can be None).

		Options 'help_text' and 'help' will be past on to
		add_help_text() and set_help() respectively.
		'''
		self.ui = ui
		self.result = None
		self.inputs = {}
		gtk.Dialog.__init__(
			self, parent=get_window(self.ui),
			title=format_title(title),
			flags=gtk.DIALOG_NO_SEPARATOR|gtk.DIALOG_DESTROY_WITH_PARENT,
		)
		if not ui_environment['smallscreen']:
			self.set_border_width(10)
			self.vbox.set_spacing(5)

		if hasattr(self, 'uistate'):
			assert isinstance(self.uistate, zim.config.ListDict) # just to be sure
		elif hasattr(ui, 'uistate') \
		and isinstance(ui.uistate, zim.config.ConfigDict):
			key = self.__class__.__name__
			self.uistate = ui.uistate[key]
		else:
			self.uistate = zim.config.ListDict()

		self.uistate.setdefault('windowsize', defaultwindowsize, check=value_is_coord)
		#~ print '>>', self.uistate
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

	def set_help(self, pagename):
		'''Set the name of the manual page with help for this dialog.
		Setting this will add a "help" button to the dialog.
		'''
		self.help_page = pagename
		button = gtk.Button(stock=gtk.STOCK_HELP)
		button.connect_object('clicked', self.__class__.show_help, self)
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

	def show_help(self, page=None):
		self.ui.show_help(page or self.help_page)
			# recurses until gui.show_help is reached

	def add_help_text(self, text):
		'''Adds a label with an info icon in front of it. Intended for
		iformational text in dialogs.
		'''
		hbox = help_text_factory(text)
		self.vbox.pack_start(hbox, False)

	def add_form(self, inputs, values=None, depends=None, trigger_response=True):
		'''Convenience method to construct simple forms. Inputs are
		speccified with 'inputs', see the InputForm class for details.

		If 'trigger_response' is True pressing <Enter> in the last Entry
		widget will call response_ok(). Set to False if more forms
		will follow in the same dialog.
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

	def run(self):
		'''Calls show_all() followed by gtk.Dialog.run().
		Returns the 'result' attribute of the dialog if any.
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
		gtk.Dialog.present(self)

	def show(self):
		self.show_all()

	def show_all(self):
		'''Logs debug info and calls gtk.Dialog.show_all()'''
		logger.debug('Opening dialog "%s"', self.title)
		register_window(self)
		if not TEST_MODE:
			gtk.Dialog.show_all(self)

	def response_ok(self):
		'''Trigger the response signal with an 'Ok' response type.'''
		self.response(gtk.RESPONSE_OK)

	def assert_response_ok(self):
		'''Like response_ok(), but will force False return value
		to raise an error. Also it explicitly does not handle errors
		with an error dialog but just let them go through.
		Intended for use by the test suite.
		'''
		assert self.do_response_ok() is True
		self.save_uistate()
		self.destroy()
		return self.result

	def do_response(self, id):
		'''Handler for the response signal, dispatches to do_response_ok()
		if response was positive and destroys the dialog if that function
		returns True. If response was negative just closes the dialog without
		further action.
		'''
		if id == gtk.RESPONSE_OK and not self._no_ok_action:
			logger.debug('Dialog response OK')
			try:
				destroy = self.do_response_ok()
			except Exception, error:
				ErrorDialog(self.ui, error).run()
				destroy = False
		elif id == gtk.RESPONSE_CANCEL:
			logger.debug('Dialog response CANCEL')
			try:
				destroy = self.do_response_cancel()
			except Exception, error:
				ErrorDialog(self.ui, error).run()
				destroy = False
		else:
			destroy = True

		if ui_environment['platform'] != 'maemo':
			w, h = self.get_size()
			self.uistate['windowsize'] = (w, h)
			self.save_uistate()

		if destroy:
			self.destroy()
			logger.debug('Closed dialog "%s"', self.title[:-6])

	def do_response_ok(self):
		'''Function to be overloaded in child classes. Called when the
		user clicks the 'Ok' button or the equivalent of such a button.

		Should return True to allow the dialog to close. If e.g. input is not
		valid, returning False will keep the dialog open.
		'''
		raise NotImplementedError

	def do_response_cancel(self):
		''' Function to be overloaded in child classes when an action different
		from the default one is needed. Called when the user clicks
		the 'Cancel' button or an equivalent. Returns True to close the dialog.
		'''
		return True

	def save_uistate(self):
		'''Function to be overloaded in child classes. Called when the
		dialog is about to exit or hide and wants the uistate to be
		saved. Just set whatever values need to be save in
		'self.uistate'. The window size is saved by default already.
		'''
		pass


# Need to register classes defining gobject signals
gobject.type_register(Dialog)


class ErrorDialog(gtk.MessageDialog):

	def __init__(self, ui, error):
		'''Constructor. 'ui' can either be the main application or some
		other dialog from which the error originates. 'error' is the error
		object.
		'''
		self.error = error
		show_trace = False
		if isinstance(error, zim.errors.Error):
			msg = error.msg
			description = error.description
		elif isinstance(error, EnvironmentError): # e.g. OSError or IOError
			msg = error.strerror
			if hasattr(error, 'filename') and error.filename:
				msg += ': ' + error.filename
			description = None
		elif isinstance(error, Exception):
			msg = _('Looks like you found a bug') # T: generic error dialog
			# TODO point to bug tracker
			description = error.__class__.__name__ + ': ' + unicode(error)
			description += '\n\n' + _('When reporting this bug please include\nthe information from the text box below') # T: generic error dialog text
			show_trace = True
		elif isinstance(error, tuple):
			msg, description = error
		else:
			# other object or string
			msg = unicode(error)
			description = None

		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_CLOSE,
			message_format=msg
		)
		if description:
			self.format_secondary_text(description)

		# Add widget with debug info
		if show_trace:
			text = self.get_debug_text()
			window, textview = scrolled_text_view(text, monospace=True)
			window.set_size_request(350, 200)
			self.vbox.add(window)
			self.vbox.show_all()
			# TODO use an expander here ?


	def get_debug_text(self):
		'''Returns text to include in an error dialog to support debugging'''
		import zim
		import traceback
		exc_info = sys.exc_info()
		if exc_info[2]:
			tb = exc_info[2]
		else:
			tb = sys.last_traceback

		text = 'This is zim %s\n' % zim.__version__ + \
			'Python version is %s\n' % str(sys.version_info) + \
			'Gtk version is %s\n' % str(gtk.gtk_version) + \
			'Pygtk version is %s\n' % str(gtk.pygtk_version) + \
			'Platform is %s\n' % os.name

		try:
			from zim._version import version_info
			text += \
				'Zim revision is:\n' \
				'  branch: %(branch_nick)s\n' \
				'  revision: %(revno)d %(revision_id)s\n' \
				'  date: %(date)s\n' \
				% version_info
		except ImportError:
			text += 'No bzr version-info found\n'


		# FIXME: more info here? Like notebook path, page, environment etc. ?

		text += '\n======= Traceback =======\n'
		if tb:
			lines = traceback.format_tb(tb)
			text += ''.join(lines)
		else:
			text += '<Could not extract stack trace>\n'

		text += self.error.__class__.__name__ + ': ' + unicode(self.error)

		return text

	def run(self):
		'''Runs the dialog and destroys it directly.'''
		logger.debug('Running %s', self.__class__.__name__)

		exc_info = sys.exc_info() # Check if we are in an exception handler
		if exc_info[0] is None:
			exc_info = None
		logger.error(self.error, exc_info=exc_info)
		del exc_info # Recommended in pydoc sys
		sys.exc_clear() # Avoid showing same message again later

		while True:
			response = gtk.MessageDialog.run(self)
			if response == gtk.RESPONSE_OK and not self.do_response_ok():
				continue
			else:
				break
		self.destroy()

	def do_response_ok(self):
		return True


class QuestionDialog(gtk.MessageDialog):

	def __init__(self, ui, question):
		'''Constructor. 'ui' can either be the main application or some
		other dialog. Question is a message that can be answered by
		'yes' or 'no'. The question can also be a tuple containing a short
		question and a longer explanation, this is prefered for look&feel.
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
		Returns True if the user clicked 'Yes', False otherwise.
		'''
		logger.debug('Running QuestionDialog')
		logger.debug('Q: %s', self.question)
		gtk.MessageDialog.run(self)
		self.destroy()
		answer = self.response == gtk.RESPONSE_YES
		logger.debug('A: %s', answer)
		return answer


class MessageDialog(gtk.MessageDialog):

	def __init__(self, ui, msg):
		'''Constructor. 'ui' can either be the main application or some
		other dialog. The message can also be a tuple containing a short
		question and a longer explanation, this is prefered for look&feel.
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

	def run(self):
		'''Runs the dialog and destroys it directly.'''
		logger.debug('Running MessageDialog')
		gtk.MessageDialog.run(self)
		self.destroy()


class FileDialog(Dialog):
	'''File chooser dialog, adds a filechooser widget to Dialog.
	Tries to show preview for image files.
	'''

	def __init__(self, ui, title, action=gtk.FILE_CHOOSER_ACTION_OPEN,
			buttons=gtk.BUTTONS_OK_CANCEL, button=None,
			help_text=None, help=None, multiple=False
		):
		'''Constructor
		If 'multiple' is True the dialog will allow selecting multiple
		files at once.
		Other arguments are passed on to Dialog.__init__().
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
		'''Wrapper for filechooser.set_filename()'''
		ok = self.filechooser.set_filename(file.path)
		if not ok:
			raise Exception, 'Could not set filename: %s' % file.path

	def get_file(self):
		'''Wrapper for filechooser.get_filename().
		Returns a File object or None.
		'''
		path = self.filechooser.get_filename()
		if path is None: return None
		else: return File(path.decode('utf-8'))

	def get_files(self):
		'''Like get_file() but returns a list of File objects.
		Useful in combination with the option "multiple".
		'''
		paths = [path.decode('utf-8')
				for path in self.filechooser.get_filenames()]
		return [File(path) for path in paths]

	def get_dir(self):
		'''Wrapper for filechooser.get_filename().
		Returns a Dir object or None.
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
		'''Wrapper for filechooser.add_filter()
		using gtk.FileFilter.add_pattern(). Returns the filter object.
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
		'''Wrapper for filechooser.add_filter()
		using gtk.FileFilter.add_pixbuf_formats(). Returns the filter object.
		'''
		if len(self.filechooser.list_filters()) == 0:
			self._add_filter_all()
		filter = gtk.FileFilter()
		filter.set_name(_('Images'))
			# T: Filter in open file dialog, shows image files only
		filter.add_pixbuf_formats()
		self.filechooser.add_filter(filter)
		self.filechooser.set_filter(filter)
		return filter

	def do_response_ok(self):
		'''Default responce handler. Will check filechooser action and
		whether or not we select multiple files or dirs and set result
		of the dialog accordingly, so the method run() wil return the
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
	'''Dialog to display a progress bar. Behaves more like a MessageDialog than
	like a normal Dialog. These dialogs are only supposed to run modal, but are
	not called with run() as there is typically a background action giving them
	callbacks. They _always_ should implement a cancel action to break the
        background process, either be overloadig this class, or by checking the
	return value of pulse().

	If you know up front how often pulse() will be called supply this
	number to the constructor in order to get the bar to display a percentage.
	Otherwise the bar will just bounce up and down without indication of remaining
	time.
	'''

	def __init__(self, ui, text, total=None):
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
		label.set_markup('<b>'+_encode_xml(text)+'</b>')
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False)

		self.progressbar = gtk.ProgressBar()
		self.vbox.pack_start(self.progressbar, False)

		self.msg_label = gtk.Label()
		self.msg_label.set_alignment(0.0, 0.5)
		self.msg_label.set_ellipsize(pango.ELLIPSIZE_START)
		self.vbox.pack_start(self.msg_label, False)

		self.set_total(total)

	def set_total(self, total):
		self.total = total
		self.count = 0

	def pulse(self, msg=None, count=None, total=None):
		'''Sets an optional message and moves forward the progress bar. Will also
		handle all pending Gtk events, so interface keeps responsive during a background
		job. This method returns True until the 'Cancel' button has been pressed, this
		boolean could be used to decide if the ackground job should continue or not.

		First call to pulse() will also trigger a show_all() if the
		dialog is not shown yet. This is done so you don't flash a
		progress dialog that is never used.
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
			self.msg_label.set_markup('<i>'+_encode_xml(msg)+'</i>')

		while gtk.events_pending():
			gtk.main_iteration(block=False)

		return not self.cancelled

	def show_all(self):
		'''Logs debug info and calls gtk.Dialog.show_all()'''
		logger.debug('Opening ProgressBarDialog')
		if not TEST_MODE:
			gtk.Dialog.show_all(self)

	def do_response(self, id):
		'''Handles the response signal and calls the 'cancel' callback.'''
		logger.debug('ProgressBarDialog get response %s', id)
		self.cancelled = True

	#def do_destroy(self):
	#	logger.debug('Closed ProgressBarDialog')


# Need to register classes defining gobject signals
gobject.type_register(ProgressBarDialog)


class Assistant(Dialog):
	'''Dialog with multi-page input, sometimes also revert to as a
	"wizard". Similar to gtk.Assistent but does not derive from that
	class for lack of flexibility in setting the dialog layout.

	Each "page" in the assistant is a step in the work flow. Pages
	should inherit from the AssistantPage class. Pages share the
	'uistate' dict with assistant object, and can also use this to
	communicate state to another page. So each step can change it's
	look based on state set in the previous step. (This is sometimes
	called a "Whiteboard" design pattern: each page can access the
	same "whiteboard" that is the uistate dict.)

	Sub-classes can freely manipulate the flow of pages e.g. by
	overloading the previous_page() and next_page() methods.
	'''

	def __init__(self, ui, title, **options):
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
		'''Append a page'''
		assert isinstance(page, AssistantPage)
		page.connect('input-valid-changed', self._update_valid)
		self._pages.append(page)

	def run(self):
		assert self._pages
		self.set_page(0)
		Dialog.run(self)

	def get_pages(self):
		'''Returns a list with AssistantPage objects'''
		return self._pages

	def get_page(self):
		'''Returns the current page object'''
		if self._page > -1:
			return self._pages[self._page]
		else:
			return None

	def set_page(self, i):
		'''Go to page i in the assistant'''
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
		ebox = gtk.EventBox()
		style = gtk_get_style()
		ebox.modify_fg(gtk.STATE_NORMAL, style.fg[gtk.STATE_SELECTED])
		ebox.modify_bg(gtk.STATE_NORMAL, style.bg[gtk.STATE_SELECTED])

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
		'''Like response_ok(), but will force False return value
		to raise an error. Also it explicitly does not handle errors
		with an error dialog but just let them go through.
		Intended for use by the test suite.
		'''
		# Wrap up previous page
		if self._page > -1:
			self._pages[self._page].save_uistate()

		self._uistate.update(self.uistate)

		assert self.do_response_ok() is True
		self.save_uistate()
		self.destroy()
		return self.result


class AssistantPage(gtk.VBox):
	'''Base class for pages in an Assistant dialog. Should have an
	attribute 'title'. Also will have an attribute 'uistate' which
	is set by the constructor to link to the dialog. This uistate is
	shared between all pages in the same dialog.

	The input needs to be valid before the user is allowed to continue.
	You can set valid state directly or use the convenience functions
	to hook widgets that need to be valid.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'input-valid-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	title = ''

	def __init__(self, assistant):
		gtk.VBox.__init__(self)
		self.set_border_width(5)
		self.uistate = assistant.uistate
		self.assistant = assistant
		self._input_valid = True
		self.form = None

	def init_uistate(self):
		'''Hook called when a new page is shown in the dialog. Should
		be used to update uistate according to input of other pages.
		'''
		pass

	def save_uistate(self):
		'''Hook called when leaving the current page. Should set uistate
		to reflect user input. Should not fail on validation.
		'''
		pass

	def add_form(self, inputs, values=None, depends=None):
		'''Convenience method to construct simple forms. Inputs are
		speccified with 'inputs', see the InputForm class for details.
		'''
		self.form = InputForm(inputs, values, depends, notebook=self.assistant.ui.notebook)
		self.form.connect('input-valid-changed', lambda o: self.check_input_valid())
		self.pack_start(self.form, False)
		self.check_input_valid()
		return self.form

	def get_input_valid(self):
		'''Returns current valid state'''
		return self._input_valid

	def check_input_valid(self):
		'''Called when valid state of some widget is changed and emits
		the input-valid-signal when this affects the total valid state.
		By default only checks state of the main form, if any, but
		can be overloaded in subclasses.
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

	SCALE_FIT = 1 # scale image with the window (if it is bigger)
	SCALE_STATIC = 2 # use scaling factore

	__gsignals__ = {
		'size-allocate': 'override',
	}

	def __init__(self, bgcolor='#FFF', checkboard=True):
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
		self.checkboard = checkboard

	def set_bgcolor(self, bgcolor):
		'''Set background color, bgcolor must be in hex, e.g. "#FFF"'''
		assert bgcolor.startswith('#'), 'BUG: Should specify colors in hex'
		color = gtk.gdk.color_parse(bgcolor)
			# gtk.gdk.Color(spec) only for gtk+ >= 2.14
		self.modify_bg(gtk.STATE_NORMAL, color)

	def set_checkboard(self, checkboard):
		'''If checkboard is True we draw a checkboard behind transparent image,
		if it is False we just show the background color.
		'''
		self.checkboard = checkboard

	def set_scaling(self, scaling, factor=1):
		'''Set the scaling to either one of SCALE_FIT or SCALE_STATIC.
		The factor is only used by SCALE_STATIC as fixed scaling factor.
		'''
		assert scaling in (SCALE_FIT, SCALE_STATIC)
		self.scaling = scaling
		self.factor = factor
		self._render()

	def set_file(self, file):
		'''Convenience method to load a pixbuf from file and load it'''
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
		'''Set the image to display. Set image to 'None' to display a broken
		image icon.
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
		if not self.checkboard or not self._pixbuf.get_has_alpha():
			if (wimg, himg) == (wsrc, hsrc):
				pixbuf = self._pixbuf
			else:
				pixbuf = self._pixbuf.scale_simple(
							wimg, himg, gtk.gdk.INTERP_NEAREST)
		else:
			# Generate checkboard background while scaling
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

	For this dialog 'run()' will return either the original file
	(for overwrite), a new file, or None when the dialog was cancelled.
	'''

	def __init__(self, ui, file):
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
