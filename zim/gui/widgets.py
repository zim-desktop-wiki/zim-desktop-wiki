# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a number of custom gtk widgets
that are used in the zim gui modules.

TODO document dialog base classes
'''

import gobject
import gtk
import logging

from zim.fs import *
import zim.errors
import zim.config


logger = logging.getLogger('zim.gui')


# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVAL_LEFT = gtk.gdk.keyval_from_name('Left')
KEYVAL_RIGHT = gtk.gdk.keyval_from_name('Right')
KEYVALS_ASTERISK = (
	gtk.gdk.unicode_to_keyval(ord('*')), gtk.gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	gtk.gdk.unicode_to_keyval(ord('\\')),
	gtk.gdk.unicode_to_keyval(ord('/')), gtk.gdk.keyval_from_name('KP_Divide'))



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


class BrowserTreeView(gtk.TreeView):
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

	def do_button_release_event(self, event):
		'''Handler for button-release-event, implements single click navigation'''
		if event.button == 1:
			x, y = map(int, event.get_coords())
				# map to int to surpress deprecation warning :S
			path, column, x, y = self.get_path_at_pos(x, y)
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
		elif event.button == 3:
			print 'TODO: context menu for page'

		return gtk.TreeView.do_button_release_event(self, event)

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

	def __init__(self, ui, title,
			buttons=gtk.BUTTONS_OK_CANCEL, button=None,
			text=None, fields=None, help=None
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
		gtk.Dialog.__init__(
			self, parent=get_window(self.ui),
			title=format_title(title),
			flags=gtk.DIALOG_NO_SEPARATOR,
		)
		self.set_border_width(10)
		self.vbox.set_spacing(5)

		if hasattr(ui, 'uistate') and isinstance(ui.uistate, zim.config.ConfigDict):
			key = self.__class__.__name__
			self.uistate = ui.uistate[key]
			#~ print '>>', self.uistate
			self.uistate.setdefault('windowsize', (-1, -1), self.uistate.is_coord)
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
		label.set_markup('<i>%s</i>' % text)
		self.vbox.add(label)

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
					active = options.index(value)
					combobox.set_active(active)
				except ValueError:
					pass
				self.inputs[name] = combobox
				table.attach(combobox, 1,2, i,i+1)
			elif type in ('string', 'password', 'page', 'namespace', 'dir', 'file', 'image'):
				label = gtk.Label(label+': ')
				label.set_alignment(0.0, 0.5)
				table.attach(label, 0,1, i,i+1, xoptions=gtk.FILL)
				entry = gtk.Entry()
				if not value is None:
					entry.set_text(str(value))
				self.inputs[name] = entry
				table.attach(entry, 1,2, i,i+1)
				if type == 'page':
					entry.set_completion(self._get_page_completion())
				elif type == 'namespace':
					entry.set_completion(self._get_namespace_completion())
				elif type in ('dir', 'file', 'image'):
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

	def _get_page_completion(self):
		print 'TODO page completion'
		return gtk.EntryCompletion()

	def _get_namespace_completion(self):
		print 'TODO namespace completion'
		return gtk.EntryCompletion()

	def get_field(self, name):
		'''Returns the value of a single field'''
		return self.get_fields()[name]

	def get_fields(self):
		'''Returns a dict with values of the fields.'''
		values = {}
		for name, widget in self.inputs.items():
			if isinstance(widget, gtk.Entry):
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

	def show_all(self):
		'''Logs debug info and calls gtk.Dialog.show_all()'''
		assert not self.destroyed, 'BUG: re-using dialog after it was closed'
		logger.debug('Opening dialog "%s"', self.title[:-6])
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


# Need to register classes defining gobject signals
gobject.type_register(Dialog)


class ErrorDialog(gtk.MessageDialog):

	def __init__(self, ui, error):
		'''Constructor. 'ui' can either be the main application or some
		other dialog from which the error originates. 'error' is the error
		object.
		'''
		self.error = error
		#~ if isinstance(error, basestring):
		if isinstance(error, zim.errors.Error):
			msg = error.msg
			description = error.description
		else:
			msg = unicode(error)
			description = ''

		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_CLOSE,
			message_format=msg
		)
		self.format_secondary_text(description)

	def run(self):
		'''Runs the dialog and destroys it directly.'''
		logger.debug('Running %s', self.__class__.__name__)
		logger.error(self.error)
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
		label.set_markup('<b>'+text+'</b>')
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
			self.msg_label.set_markup('<i>'+msg+'</i>')

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
