# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a number of custom gtk widgets
that are used in the zim gui modules.

TODO document dialog base classes
'''

import gobject
import gtk
import pango
import logging
import sys

from zim.fs import *
import zim.errors
import zim.config
from zim.notebook import Path, PageNameError


logger = logging.getLogger('zim.gui')


# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVAL_LEFT = gtk.gdk.keyval_from_name('Left')
KEYVAL_RIGHT = gtk.gdk.keyval_from_name('Right')
KEYVALS_ASTERISK = (
	gtk.gdk.unicode_to_keyval(ord('*')), gtk.gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	gtk.gdk.unicode_to_keyval(ord('\\')),
	gtk.gdk.unicode_to_keyval(ord('/')), gtk.gdk.keyval_from_name('KP_Divide'))


def _encode_xml(text):
	return text.replace('>', '&gt;').replace('<', '&lt;')


def scrolled_text_view(text=None, monospace=False):
	'''Initializes a gtk.TextView with sane defaults for displaying a
	piece of multiline text, wraps it in a scrolled window and returns
	both the window and the textview.
	'''
	textview = gtk.TextView()
	textview.set_editable(False)
	textview.set_wrap_mode(gtk.WRAP_WORD)
	textview.set_left_margin(5)
	textview.set_right_margin(5)
	if monospace:
		font = pango.FontDescription('Monospace')
		textview.modify_font(font)
	if text:
		textview.get_buffer().set_text(text)
	window = gtk.ScrolledWindow()
	window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
	window.set_shadow_type(gtk.SHADOW_IN)
	window.add(textview)
	return window, textview


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


class SingleClickTreeView(gtk.TreeView):

	mask = gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK

	def do_button_release_event(self, event):
		'''Handler for button-release-event, implements single click navigation'''

		if event.button == 1 and not event.state & self.mask \
		and not self.is_rubber_banding_active():
			x, y = map(int, event.get_coords())
				# map to int to surpress deprecation warning :S
			info = self.get_path_at_pos(x, y)
			if not info is None:
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
			assert isinstance(label, gtk.Widget)
			self.label = label
		self.menu = menu
		self.button = gtk.ToggleButton()
		if status_bar_style:
			self.button.set_name('zim-statusbar-menubutton')
			self.button.set_relief(gtk.RELIEF_NONE)
		self.button.add(self.label)
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


class PageEntry(gtk.Entry):

	allow_select_root = False

	def __init__(self, notebook, path=None, path_context=None):
		'''Contructor. Needs at least a Notebook to resolve paths.
		If a context is given this is the reference Path for resolving
		relative links.
		'''
		gtk.Entry.__init__(self)
		assert notebook, 'Page completion needs a notebook'
		assert path_context is None or isinstance(path_context, Path)
		self.notebook = notebook
		self.path_context = path_context
		self.force_child = False
		self._completing = ''

		self.completion_model = gtk.ListStore(str)
		completion = gtk.EntryCompletion()
		completion.set_model(self.completion_model)
		completion.set_text_column(0)
		completion.set_inline_completion(True)
		self.set_completion(completion)

		if path:
			self.set_path(path)

		self.connect('changed', self.__class__.do_changed)

	def set_path(self, path):
		self.set_text(':'+path.name)

	def get_path(self):
		name = self.get_text().strip()
		if not name:
			return None
		elif self.allow_select_root and name == ':':
			return Path(':')
		else:
			if self.force_child and not name.startswith('+'):
				name = '+' + name
			try:
				return self.notebook.resolve_path(name, source=self.path_context)
			except PageNameError:
				return None

	def clear(self):
		self.set_text('')
		self.emit('activate')

	def do_changed(self):
		text = self.get_text()

		# Figure out some hint about the namespace
		if ':' in text:
			# can still have context and start with '+'
			i = text.rfind(':')
			completing = text[:i+1]
			prefix = completing
		elif self.path_context:
			if text.startswith('+'):
				completing = ':' + self.path_context.name
				prefix = '+'
			else:
				completing = ':' + self.path_context.namespace
				prefix = ''
		else:
			completing = ':'
			prefix = ''

		if self.force_child and not completing.startswith('+'):
			# Needed for new_sub_page - always force child page
			completing = '+' + completing

		# Check if we completed already for this namespace
		if completing == self._completing:
			return
		self._completing = completing

		# Else fill model with pages from namespace
		self.completion_model.clear()

		if completing == ':':
			path = Path(':')
		else:
			try:
				path = self.notebook.resolve_path(completing, source=self.path_context)
			except PageNameError:
				return

		#~ print '!! COMPLETING %s context: %s prefix: %s' % (path, self.path_context, prefix)
		for p in self.notebook.index.list_pages(path):
			self.completion_model.append((prefix+p.basename,))


class NamespaceEntry(PageEntry):

	allow_select_root = True


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

	def __init__(self, ui, title,
			buttons=gtk.BUTTONS_OK_CANCEL, button=None,
			text=None, fields=None, help=None,
			defaultwindowsize=(-1, -1), path_context=None
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

		Options 'text', 'fields' and 'help' will be past on to add_text(),
		add_fields() and set_help() respectively.
		'''
		self.ui = ui
		self.result = None
		self.inputs = {}
		self.destroyed = False
		self.path_context = path_context
		gtk.Dialog.__init__(
			self, parent=get_window(self.ui),
			title=format_title(title),
			flags=gtk.DIALOG_NO_SEPARATOR,
		)
		self.set_border_width(10)
		self.vbox.set_spacing(5)

		if hasattr(ui, 'uistate') and isinstance(ui.uistate, zim.config.ConfigDict):
			assert isinstance(defaultwindowsize, tuple)
			key = self.__class__.__name__
			self.uistate = ui.uistate[key]
			#~ print '>>', self.uistate
			self.uistate.setdefault('windowsize', defaultwindowsize, check=self.uistate.is_coord)
			w, h = self.uistate['windowsize']
			self.set_default_size(w, h)
		else:
			self.uistate = { # used in tests/debug
				'windowsize': (-1, -1)
			}

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

		if text: self.add_text(text)
		if fields: self.add_fields(fields)
		if help: self.set_help(help)

	def set_help(self, pagename):
		'''Set the name of the manual page with help for this dialog.
		Setting this will add a "help" button to the dialog.
		'''
		self.help_page = pagename
		button = gtk.Button(stock=gtk.STOCK_HELP)
		button.connect('clicked', lambda o: self.ui.show_help(self.help_page))
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

	def add_text(self, text):
		'''Adds a label in italics. Intended for informational text at the
		top of the dialog.
		'''
		label = gtk.Label()
		label.set_markup('<i>%s</i>' % _encode_xml(text))
		self.vbox.pack_start(label, False)

	def add_fields(self, fields, table=None, trigger_response=True):
		'''Add a number of fields to the dialog, convenience method to
		construct simple forms. The argument 'fields' should be a list of
		field definitions; each definition is a tupple of:

			* The field name
			* The field type
			* The label to put in front of the input field
			* The initial value of the field

		The following field types are supported: 'bool', 'int', 'list',
		'string', 'password', 'page', 'namespace', 'dir', 'file' and 'image'.

		If 'table' is specified the fields are added to that table, otherwise
		a new table is constructed and added to the dialog. Returns the table
		to allow building a form in multiple calls.

		If 'trigger_response' is True pressing <Enter> in the last Entry widget
		will call response_ok(). Set to False if more forms will follow in the
		same dialog.
		'''
		if table is None:
			table = gtk.Table()
			table.set_border_width(5)
			table.set_row_spacings(5)
			table.set_col_spacings(12)
			self.vbox.add(table)
		i = table.get_property('n-rows')

		for field in fields:
			name, type, label, value = field
			if type == 'bool':
				button = gtk.CheckButton(label=label)
				button.set_active(value or False)
				self.inputs[name] = button
				table.attach(button, 0,2, i,i+1)
			elif type == 'int':
				label = gtk.Label(label+':')
				label.set_alignment(0.0, 0.5)
				table.attach(label, 0,1, i,i+1, xoptions=gtk.FILL)
				button = gtk.SpinButton()
				v, min, max = value
				button.set_value(v)
				button.set_range(min, max)
				self.inputs[name] = button
				table.attach(button, 1,2, i,i+1)
			elif type == 'list':
				label = gtk.Label(label+':')
				label.set_alignment(0.0, 0.5)
				table.attach(label, 0,1, i,i+1, xoptions=gtk.FILL)
				value, options = value
				combobox = gtk.combo_box_new_text()
				for option in options:
					combobox.append_text(str(option))
				try:
					active = list(options).index(value)
						# list() needed for python 2.5 compat
					combobox.set_active(active)
				except ValueError:
					pass
				self.inputs[name] = combobox
				table.attach(combobox, 1,2, i,i+1)
			elif type in ('string', 'password', 'page', 'namespace', 'dir', 'file', 'image'):
				label = gtk.Label(label+': ')
				label.set_alignment(0.0, 0.5)
				table.attach(label, 0,1, i,i+1, xoptions=gtk.FILL)
				if type in ('page', 'namespace'):
					if type == 'page':
						entry = PageEntry(self.ui.notebook, path_context=self.path_context)
					else:
						entry = NamespaceEntry(self.ui.notebook, path_context=self.path_context)
					if value:
						if isinstance(value, basestring):
							value = Path(value)
						entry.set_path(value)
					self.inputs[name] = entry
					table.attach(entry, 1,2, i,i+1)
				else:
					entry = gtk.Entry()
					entry.zim_type = type
					if not value is None:
						entry.set_text(str(value))
					self.inputs[name] = entry
					table.attach(entry, 1,2, i,i+1)

					if type in ('dir', 'file', 'image'):
						# FIXME use inline icon for newer versions of Gtk
						browse = gtk.Button('_Browse')
						browse.connect('clicked', self._select_file, (type, entry))
						table.attach(browse, 2,3, i,i+1, xoptions=gtk.FILL)
					elif type == 'password':
						entry.set_visibility(False)
			else:
				assert False, 'BUG: unknown field type: %s' % type
			i += 1

		def focus_next(o, next):
			next.grab_focus()

		for i in range(len(fields)-1):
			name = fields[i][0]
			next = fields[i+1][0]
			try:
				self.inputs[name].connect('activate', focus_next, self.inputs[next])
			except Exception:
				pass

		if trigger_response:
			last = fields[-1][0]
			self.inputs[last].connect('activate', lambda o: self.response_ok())

		return table

	def _select_file(self, button, data):
		'''Triggered by the 'browse' button for file entries'''
		type, entry = data
		if type == 'dir':
			dialog = SelectFolderDialog(self)
		else:
			dialog = SelectFileDialog(self)
			if type == 'image':
				dialog.add_filter_images()
		file = dialog.run()
		if not file is None:
			entry.set_text(file.path)

	def get_field(self, name):
		'''Returns the value of a single field'''
		return self.get_fields()[name]

	def get_fields(self):
		'''Returns a dict with values of the fields.'''
		values = {}
		for name, widget in self.inputs.items():
			if isinstance(widget, (PageEntry, NamespaceEntry)):
				values[name] = widget.get_path()
			elif isinstance(widget, gtk.Entry):
				values[name] = widget.get_text().strip()
			elif isinstance(widget, gtk.ToggleButton):
				values[name] = widget.get_active()
			elif isinstance(widget, gtk.ComboBox):
				values[name] = widget.get_active_text()
			elif isinstance(widget, gtk.SpinButton):
				values[name] = int(widget.get_value())
			else:
				assert False, 'BUG: unkown widget in inputs'
		return values

	def run(self):
		'''Calls show_all() followed by gtk.Dialog.run().
		Returns the 'result' attribute of the dialog if any.
		'''
		self.show_all()
		assert not self.destroyed, 'BUG: re-using dialog after it was closed'
		while not self.destroyed:
			gtk.Dialog.run(self)
			# will be broken when _close is set from do_response()
		return self.result

	def present(self):
		self.show_all()
		gtk.Dialog.present(self)

	def show(self):
		self.show_all()

	def show_all(self):
		'''Logs debug info and calls gtk.Dialog.show_all()'''
		assert not self.destroyed, 'BUG: re-using dialog after it was closed'
		logger.debug('Opening dialog "%s"', self.title)
		gtk.Dialog.show_all(self)

	def response_ok(self):
		'''Trigger the response signal with an 'Ok' response type.'''
		self.response(gtk.RESPONSE_OK)

	def do_response(self, id):
		'''Handler for the response signal, dispatches to do_response_ok()
		if response was positive and destroys the dialog if that function
		returns True. If response was negative just closes the dialog without
		further action.
		'''
		if id == gtk.RESPONSE_OK and not self._no_ok_action:
			logger.debug('Dialog response OK')
			self.destroyed = self.do_response_ok()
		else:
			self.destroyed = True

		w, h = self.get_size()
		self.uistate['windowsize'] = (w, h)
		self.save_uistate()

		if self.destroyed:
			self.destroy()
			logger.debug('Closed dialog "%s"', self.title[:-6])

	def do_response_ok(self):
		'''Function to be overloaded in child classes. Called when the
		user clicks the 'Ok' button or the equivalent of such a button.

		Should return True to allow the dialog to close. If e.g. input is not
		valid, returning False will keep the dialog open.
		'''
		raise NotImplementedError

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
		if isinstance(error, zim.errors.Error):
			msg = error.msg
			description = error.description
		else:
			# Other exception or string
			msg = unicode(error)
			description = None

		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_CLOSE,
			message_format=msg
		)
		if description:
			self.format_secondary_text(description)

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


class FileDialog(Dialog):
	'''File chooser dialog, adds a filechooser widget to Dialog.'''

	def __init__(self, ui, title, action=gtk.FILE_CHOOSER_ACTION_OPEN,
			buttons=gtk.BUTTONS_OK_CANCEL, button=None,
			text=None, fields=None, help=None
		):
		if button is None:
			if action == gtk.FILE_CHOOSER_ACTION_OPEN:
				button = (None, gtk.STOCK_OPEN)
			elif action == gtk.FILE_CHOOSER_ACTION_SAVE:
				button = (None, gtk.STOCK_SAVE)
			# else Ok will do
		Dialog.__init__(self, ui, title,
			buttons=buttons, button=button, text=text, help=help)
		if self.uistate['windowsize'] == (-1, -1):
			self.uistate['windowsize'] = (500, 400)
			self.set_default_size(500, 400)
		self.filechooser = gtk.FileChooserWidget(action=action)
		self.filechooser.set_do_overwrite_confirmation(True)
		self.filechooser.connect('file-activated', lambda o: self.response_ok())
		self.vbox.add(self.filechooser)
		# FIXME hook to expander to resize window
		if fields:
			self.add_fields(fields)

	def set_file(self, file):
		'''Wrapper for filechooser.set_filename()'''
		self.filechooser.set_file(file.path)

	def get_file(self):
		'''Wrapper for filechooser.get_filename().
		Returns a File object or None.
		'''
		path = self.filechooser.get_filename()
		if path is None: return None
		else: return File(path)

	def get_dir(self):
		'''Wrapper for filechooser.get_filename().
		Returns a Dir object or None.
		'''
		path = self.filechooser.get_filename()
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


class SelectFileDialog(FileDialog):

	def __init__(self, ui, title=_('Select File')):
		# T: Title of file selection dialog
		FileDialog.__init__(self, ui, title)
		self.file = None

	def do_response_ok(self):
		self.file = self.get_file()
		return not self.file is None

	def run(self):
		FileDialog.run(self)
		return self.file


class SelectFolderDialog(FileDialog):

	def __init__(self, ui, title=_('Select Folder')):
		# T: Title of folder selection dialog
		FileDialog.__init__(self, ui, title,
			action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
		self.dir = None

	def do_response_ok(self):
		self.dir = self.get_dir()
		return not self.dir is None

	def run(self):
		FileDialog.run(self)
		return self.dir


class ProgressBarDialog(gtk.Dialog):
	'''Dialog to display a progress bar. Behaves more like a MessageDialog than
	like a normal Dialog. These dialogs are only supposed to run modal, but are
	not called with run() as there is typically a background action giving them
	callbacks. They _always_ should implement a cancel action to break the
        background process, either be overloadig this class, or by checking the
	return value of pulse().

	TODO: also support percentage mode
	'''

	def __init__(self, ui, text):
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

	def pulse(self, msg=None):
		'''Sets an optional message and moves forward the progress bar. Will also
		handle all pending Gtk events, so interface keeps responsive during a background
		job. This method returns True untill the 'Cancel' button has been pressed, this
		boolean could be used to decide if the ackground job should continue or not.
		'''
		self.progressbar.pulse()
		if not msg is None:
			self.msg_label.set_markup('<i>'+_encode_xml(msg)+'</i>')

		while gtk.events_pending():
			gtk.main_iteration(block=False)

		return not self.cancelled

	def show_all(self):
		'''Logs debug info and calls gtk.Dialog.show_all()'''
		logger.debug('Opening ProgressBarDialog')
		gtk.Dialog.show_all(self)

	def do_response(self, id):
		'''Handles the response signal and calls the 'cancel' callback.'''
		logger.debug('ProgressBarDialog get response %s', id)
		self.cancelled = True

	#def do_destroy(self):
	#	logger.debug('Closed ProgressBarDialog')

# Need to register classes defining gobject signals
gobject.type_register(ProgressBarDialog)


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
							wimg, himg, gtk.gdk.INTERP_HYPER)
		else:
			# Generate checkboard background while scaling
			pixbuf = self._pixbuf.composite_color_simple(
				wimg, himg, gtk.gdk.INTERP_HYPER,
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

