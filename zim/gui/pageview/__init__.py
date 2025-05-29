# Copyright 2008-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the main text editor widget.
It includes all classes needed to display and edit a single page as well
as related dialogs like the dialogs to insert images, links etc.

The main widget accessed by the rest of the application is the
L{PageView} class. This wraps a L{TextView} widget which actually
shows the page. The L{TextBuffer} class is the data model used by the
L{TextView}.
'''

# TODO
# - create "load" & "serialize" and refactor that part out of buffer
# - refactor autoformatting end-of-word / end-of-line to helper object
# - check TextBufferList usage - extend or limit ?
# - check other parts of textbuffer to refactor out


import logging

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import Pango
from gi.repository import Gtk

import re
import functools

import zim.formats
import zim.errors

from zim.newfs import FilePath, LocalFolder
from zim.errors import Error
from zim.config import \
	String, Boolean, Choice, ConfigManager, XDG_TEMPLATES_DIR, ConfigDefinitionConstant
from zim.notebook import Path, interwiki_link, HRef
from zim.notebook.operations import NotebookState, ongoing_operation
from zim.parse.links import link_type
from zim.signals import callback

from zim.templates.expression import ExpressionFunction
from zim.actions import get_gtk_actiongroup, action, get_actions, \
	ActionClassMethod, ToggleActionClassMethod, initialize_actiongroup
from zim.plugins import PluginManager, ExtensionBase, extendable

from zim.gui.widgets import \
	ErrorDialog, ScrolledWindow, populate_popup_add_separator, \
	strip_boolean_result, widget_set_css
from zim.gui.actionextension import ActionExtensionBase, os_default_headerbar
from zim.gui.applications import OpenWithMenu, open_url, open_file, open_folder_prompt_create
from zim.gui.clipboard import Clipboard, SelectionClipboard


from .constants import *
from .objectanchors import LineSeparatorAnchor, PluginInsertedObjectAnchor
from .textbuffer import TextBuffer
from .textview import TextView
from .editbar import EditBar
from .find import FindAndReplaceDialog, FindBar
from .dialogs import *


logger = logging.getLogger('zim.gui.pageview')


MAX_PAGES_UNDO_STACK = 10 #: Keep this many pages in a queue to keep ref and thus undostack alive



MENU_ACTIONS = (
	# name, stock id, label
	('insert_new_file_menu', None, _('New _Attachment')), # T: Menu title
)

COPY_FORMATS = zim.formats.list_formats(zim.formats.TEXT_FORMAT)

ui_preferences = (
	# key, type, category, label, default
	('show_edit_bar', 'bool', 'Interface',
		_('Show edit bar along bottom of editor'), os_default_headerbar),
		# T: option in preferences dialog
	('follow_on_enter', 'bool', 'Interface',
		_('Use the <Enter> key to follow links\n(If disabled you can still use <Alt><Enter>)'), True),
		# T: option in preferences dialog
	('show_link_label', 'bool', 'Interface',
		_('Preview link destination in overlay'), True),
		# T: option in preferences dialog
	('read_only_cursor', 'bool', 'Interface',
		_('Show the cursor also for pages that can not be edited'), False),
		# T: option in preferences dialog
	('autolink_camelcase', 'bool', 'Editing',
		_('Automatically turn "CamelCase" words into links'), True),
		# T: option in preferences dialog
	('autolink_page', 'bool', 'Editing',
		_('Automatically turn wiki page names into links'), True),
		# T: option in preferences dialog
	('autolink_anchor', 'bool', 'Editing',
		_('Automatically turn identifiers starting with "#" into links'), True),
		# T: option in preferences dialog
	('autolink_interwiki', 'bool', 'Editing',
		_('Automatically turn interwiki names into links'), True),
		# T: option in preferences dialog
	('autolink_files', 'bool', 'Editing',
		_('Automatically turn file paths into links'), True),
		# T: option in preferences dialog
	('autoselect', 'bool', 'Editing',
		_('Automatically select the current word when you apply formatting'), True),
		# T: option in preferences dialog
	('unindent_on_backspace', 'bool', 'Editing',
		_('Unindent on <BackSpace>\n(If disabled you can still use <Shift><Tab>)'), True),
		# T: option in preferences dialog
	('cycle_checkbox_type', 'bool', 'Editing',
		_('Repeated clicking a checkbox cycles through the checkbox states'), True),
		# T: option in preferences dialog
	('recursive_indentlist', 'bool', 'Editing',
		_('(Un-)indenting a list item also changes any sub-items'), True),
		# T: option in preferences dialog
	('recursive_checklist', 'bool', 'Editing',
		_('Checking a checkbox also changes any sub-items'), False),
		# T: option in preferences dialog
	('auto_reformat', 'bool', 'Editing',
		_('Reformat wiki markup on the fly'), False),
		# T: option in preferences dialog
	('copy_format', 'choice', 'Editing',
		_('Default format for copying text to the clipboard'), 'Text', COPY_FORMATS),
		# T: option in preferences dialog
	('file_templates_folder', 'dir', 'Editing',
		_('Folder with templates for attachment files'), XDG_TEMPLATES_DIR),
		# T: option in preferences dialog
)


class SavePageHandler(object):
	'''Object for handling page saving.

	This class implements auto-saving on a timer and tries writing in
	a background thread to ot block the user interface.
	'''

	def __init__(self, pageview, notebook, get_page_cb, timeout=15, use_thread=True):
		self.pageview = pageview
		self.notebook = notebook
		self.get_page_cb = get_page_cb
		self.timeout = timeout
		self.use_thread = use_thread
		self._autosave_timer = None
		self._error_event = None

	def wait_for_store_page_async(self):
		# FIXME: duplicate of notebook method
		self.notebook.wait_for_store_page_async()

	def queue_autosave(self, timeout=15):
		'''Queue a single autosave action after a given timeout.
		Will not do anything once an autosave is already queued.
		Autosave will keep running until page is no longer modified and
		then stop.
		@param timeout: timeout in seconds
		'''
		if not self._autosave_timer:
			self._autosave_timer = GObject.timeout_add(
				self.timeout * 1000, # s -> ms
				self.do_try_save_page
			)

	def cancel_autosave(self):
		'''Cancel a pending autosave'''
		if self._autosave_timer:
			GObject.source_remove(self._autosave_timer)
			self._autosave_timer = None

	def _assert_can_save_page(self, page):
		if self.pageview.readonly:
			raise AssertionError('BUG: can not save page when UI is read-only')
		elif page.readonly:
			raise AssertionError('BUG: can not save read-only page')

	def save_page_now(self, dialog_timeout=False):
		'''Save the page in the foregound

		Can result in a L{SavePageErrorDialog} when there is an error
		while saving a page. If that dialog is cancelled by the user,
		the page may not be saved after all.

		@param dialog_timeout: passed on to L{SavePageErrorDialog}
		'''
		self.cancel_autosave()

		self._error_event = None

		with NotebookState(self.notebook):
			page = self.get_page_cb()
			if page:
				try:
					self._assert_can_save_page(page)
					logger.debug('Saving page: %s', page)
					buffer = page.get_textbuffer()
					if buffer:
						buffer.showing_template = False # allow save_page to save template content
					#~ assert False, "TEST"
					self.notebook.store_page(page)

				except Exception as error:
					logger.exception('Failed to save page: %s', page.name)
					SavePageErrorDialog(self.pageview, error, page, dialog_timeout).run()

	def try_save_page(self):
		'''Try to save the page

		  * Will not do anything if page is not modified or when an
			autosave is already in progress.
		  * If last autosave resulted in an error, will run in the
			foreground, else it tries to write the page in a background
			thread
		'''
		self.cancel_autosave()
		self.do_try_save_page()

	def do_try_save_page(self, *a):
		page = self.get_page_cb()
		if not (page and page.modified):
			self._autosave_timer = None
			return False # stop timer

		if ongoing_operation(self.notebook):
			logger.debug('Operation in progress, skipping auto-save') # Could be auto-save
			return True # Check back later if on timer


		if not self.use_thread:
			self.save_page_now(dialog_timeout=True)
		elif self._error_event and self._error_event.is_set():
			# Error in previous auto-save, save in foreground to allow error dialog
			logger.debug('Last auto-save resulted in error, re-try in foreground')
			self.save_page_now(dialog_timeout=True)
		else:
			# Save in background async
			# Retrieve tree here and pass on to thread to prevent
			# changing the buffer while extracting it
			parsetree = page.get_parsetree()
			op = self.notebook.store_page_async(page, parsetree)
			self._error_event = op.error_event

		if page.modified:
			return True # if True, timer will keep going
		else:
			self._autosave_timer = None
			return False # stop timer


class SavePageErrorDialog(ErrorDialog):
	'''Error dialog used when we hit an error while trying to save a page.
	Allow to save a copy or to discard changes. Includes a timer which
	delays the action buttons becoming sensitive. Reason for this timer is
	that the dialog may popup from auto-save while the user is typing, and
	we want to prevent an accidental action.
	'''

	def __init__(self, pageview, error, page, timeout=False):
		msg = _('Could not save page: %s') % page.name
			# T: Heading of error dialog
		desc = str(error).strip() \
				+ '\n\n' \
				+ _('''\
To continue you can save a copy of this page or discard
any changes. If you save a copy changes will be also
discarded, but you can restore the copy later.''')
			# T: text in error dialog when saving page failed
		ErrorDialog.__init__(self, pageview, (msg, desc), buttons=Gtk.ButtonsType.NONE)

		self.timeout = timeout

		self.pageview = pageview
		self.page = page
		self.error = error

		self.timer_label = Gtk.Label()
		self.timer_label.set_alignment(0.9, 0.5)
		self.timer_label.set_sensitive(False)
		self.timer_label.show()
		self.vbox.add(self.timer_label)

		cancel_button = Gtk.Button.new_with_mnemonic(_('_Cancel')) # T: Button label
		self.add_action_widget(cancel_button, Gtk.ResponseType.CANCEL)

		self._done = False

		discard_button = Gtk.Button.new_with_mnemonic(_('_Discard Changes'))
			# T: Button in error dialog
		discard_button.connect('clicked', lambda o: self.discard())
		self.add_action_widget(discard_button, Gtk.ResponseType.OK)

		save_button = Gtk.Button.new_with_mnemonic(_('_Save Copy'))
			# T: Button in error dialog
		save_button.connect('clicked', lambda o: self.save_copy())
		self.add_action_widget(save_button, Gtk.ResponseType.OK)

		for button in (cancel_button, discard_button, save_button):
			button.set_sensitive(False)
			button.show()

	def discard(self):
		self.page.reload_textbuffer()
		self._done = True

	def save_copy(self):
		from zim.gui.uiactions import SaveCopyDialog
		if SaveCopyDialog(self, self.pageview.notebook, self.page).run():
			self.discard()

	def do_response_ok(self):
		return self._done

	def run(self):
		if self.timeout:
			self.timer = 5
			self.timer_label.set_text('%i sec.' % self.timer)
			def timer(self):
				self.timer -= 1
				if self.timer > 0:
					self.timer_label.set_text('%i sec.' % self.timer)
					return True # keep timer going
				else:
					for button in self.action_area.get_children():
						button.set_sensitive(True)
					self.timer_label.set_text('')
					return False # remove timer

			# older gobject version doesn't know about seconds
			id = GObject.timeout_add(1000, timer, self)
			ErrorDialog.run(self)
			GObject.source_remove(id)
		else:
			for button in self.action_area.get_children():
				button.set_sensitive(True)
			ErrorDialog.run(self)


class PageViewExtensionBase(ActionExtensionBase):
	'''Base class for extensions that want to interact with the "page view",
	which is the primary editor view of the application.

	This extension class will collect actions defined with the C{@action},
	C{@toggle_action} or C{@radio_action} decorators and add them to the window.

	This extension class also supports showing side panes that are visible as
	part of the "decoration" of the editor view.

	@ivar pageview: the L{PageView} object
	@ivar navigation: a L{NavigationModel} model
	@ivar uistate: a L{ConfigDict} to store the extensions ui state or

	The "uistate" is the per notebook state of the interface, it is
	intended for stuff like the last folder opened by the user or the
	size of a dialog after resizing. It is stored in the X{state.conf}
	file in the notebook cache folder. It differs from the preferences,
	which are stored globally and dictate the behavior of the application.
	(To access the preference use C{plugin.preferences}.)
	'''

	def __init__(self, plugin, pageview):
		ExtensionBase.__init__(self, plugin, pageview)
		self.pageview = pageview
		self._window = self.pageview.get_toplevel()
		assert hasattr(self._window, 'add_sidepane_widget'), 'expect mainwindow, got %s' % self._window

		self.navigation = self._window.navigation
		self.uistate = pageview.notebook.state[self.plugin.config_key]

		self._sidepane_widgets = {}
		self._add_actions(self._window.uimanager)

		actiongroup = self.pageview.get_action_group('pageview')
		for name, action in get_actions(self):
			gaction = action.get_gaction()
			actiongroup.add_action(gaction)

	def add_sidepane_widget(self, widget, preferences_key):
		key = widget.__class__.__name__
		position = self.plugin.preferences[preferences_key]
		self._window.add_sidepane_widget(key, widget, position)

		def on_preferences_changed(preferences):
			position = self.plugin.preferences[preferences_key]
			self._window.remove(widget)
			self._window.add_sidepane_widget(key, widget, position)

		sid = self.connectto(self.plugin.preferences, 'changed', on_preferences_changed)
		self._sidepane_widgets[widget] = sid
		widget.show_all()

	def remove_sidepane_widget(self, widget):
		try:
			self._window.remove(widget)
		except ValueError:
			pass

		try:
			sid = self._sidepane_widgets.pop(widget)
			self.plugin.preferences.disconnect(sid)
		except KeyError:
			pass

	def teardown(self):
		for widget in list(self._sidepane_widgets):
			self.remove_sidepane_widget(widget)
			widget.disconnect_all()

		actiongroup = self.pageview.get_action_group('pageview')
		for name, action in get_actions(self):
			actiongroup.remove_action(action.name)


class PageViewExtension(PageViewExtensionBase):
	'''Base class for extensions of the L{PageView},
	see L{PageViewExtensionBase} for API documentation.
	'''
	pass


class InsertedObjectPageviewManager(object):
	'''"Glue" object to manage "insert object" actions for the L{PageView}
	Creates an action object for each object type and inserts UI elements
	for the action in the pageview.
	'''

	_class_actions = set()

	def __init__(self, pageview):
		self.pageview = pageview
		self._actions = set()
		self.on_changed(None)
		PluginManager.insertedobjects.connect('changed', self.on_changed)

	@staticmethod
	def _action_name(key):
		return 'insert_' + re.sub(r'\W', '_', key)

	def on_changed(self, o):
		insertedobjects = PluginManager.insertedobjects
		keys = set(insertedobjects.keys())

		actiongroup = self.pageview.get_action_group('pageview')
		for key in self._actions - keys:
			action = getattr(self, self._action_name(key))
			actiongroup.remove_action(action.name)
			self._actions.remove(key)

		self._update_class_actions() # Modifies class

		for key in keys - self._actions:
			action = getattr(self, self._action_name(key))
			gaction = action.get_gaction()
			actiongroup.add_action(gaction)
			self._actions.add(key)

		assert self._actions == keys

	@classmethod
	def _update_class_actions(cls):
		# Triggered by instance, could be run multiple times for same change
		# but redundant runs should do nothing because of no change compared
		# to "_class_actions"
		insertedobjects = PluginManager.insertedobjects
		keys = set(insertedobjects.keys())
		for key in cls._class_actions - keys:
			name = cls._action_name(key)
			if hasattr(cls, name):
				delattr(cls, name)
			cls._class_actions.remove(key)

		for key in keys - cls._class_actions:
			name = cls._action_name(key)
			obj = insertedobjects[key]
			func = functools.partial(cls._action_handler, key)
			action = ActionClassMethod(
				name, func, obj.label,
				verb_icon=obj.verb_icon,
				menuhints='insert',
			)
			setattr(cls, name, action)
			cls._class_actions.add(key)

		assert cls._class_actions == keys

	def _action_handler(key, self): # reverse arg spec due to partial
		try:
			otype = PluginManager.insertedobjects[key]
			notebook, page = self.pageview.notebook, self.pageview.page
			try:
				model = otype.new_model_interactive(self.pageview, notebook, page)
			except ValueError:
				return # dialog cancelled
			self.pageview.insert_object_model(otype, model)
		except:
			zim.errors.exception_handler(
				'Exception during action: insert_%s' % key)


def _install_format_actions(klass):
	for name, label, accelerator in (
		('apply_format_h1', _('Heading _1'), '<Primary>1'), # T: Menu item
		('apply_format_h2', _('Heading _2'), '<Primary>2'), # T: Menu item
		('apply_format_h3', _('Heading _3'), '<Primary>3'), # T: Menu item
		('apply_format_h4', _('Heading _4'), '<Primary>4'), # T: Menu item
		('apply_format_h5', _('Heading _5'), '<Primary>5'), # T: Menu item
		('apply_format_strong', _('_Strong'), '<Primary>B'), # T: Menu item
		('apply_format_emphasis', _('_Emphasis'), '<Primary>I'), # T: Menu item
		('apply_format_mark', _('_Mark'), '<Primary>U'), # T: Menu item
		('apply_format_strike', _('_Strike'), '<Primary>K'), # T: Menu item
		('apply_format_sub', _('_Subscript'), '<Primary><Shift>b'), # T: Menu item
		('apply_format_sup', _('_Superscript'), '<Primary><Shift>p'), # T: Menu item
		('apply_format_code', _('_Verbatim'), '<Primary>T'), # T: Menu item
	):
		func = functools.partial(klass.do_toggle_format_action, action=name)
		setattr(klass, name,
			ActionClassMethod(name, func, label, accelerator=accelerator, menuhints='edit')
		)

	klass._format_toggle_actions = []
	for name, label, icon in (
		('toggle_format_strong', _('_Strong'), 'format-text-bold-symbolic'), # T: menu item for formatting
		('toggle_format_emphasis', _('_Emphasis'), 'format-text-italic-symbolic'), # T: menu item for formatting
		('toggle_format_mark', _('_Mark'), 'format-text-underline-symbolic'), # T: menu item for formatting
		('toggle_format_strike', _('_Strike'), 'format-text-strikethrough-symbolic'), # T: menu item for formatting
		('toggle_format_code', _('_Verbatim'), 'format-text-code-symbolic'), # T: menu item for formatting
		('toggle_format_sup', _('Su_perscript'), 'format-text-superscript-symbolic'), # T: menu item for formatting
		('toggle_format_sub', _('Su_bscript'), 'format-text-subscript-symbolic'), # T: menu item for formatting
	):
		func = functools.partial(klass.do_toggle_format_action_alt, action=name)
		setattr(klass, name,
			ToggleActionClassMethod(name, func, label, icon=icon, menuhints='edit')
		)
		klass._format_toggle_actions.append(name)

	return klass


from zim.signals import GSignalEmitterMixin

@_install_format_actions
@extendable(PageViewExtension, register_after_init=False)
class PageView(GSignalEmitterMixin, Gtk.VBox):
	'''Widget to display a single page, consists of a L{TextView} and
	a L{FindBar}. Also adds menu items and in general integrates
	the TextView with the rest of the application.

	@ivar text_style: a L{ConfigSectionsDict} with style properties. Although this
	is a class attribute loading the data from the config file is
	delayed till the first object is constructed

	@ivar page: L{Page} object for the current page displayed in the widget
	@ivar readonly: C{True} when the widget is read-only, see
	L{set_readonly()} for details
	@ivar view: the L{TextView} child object
	@ivar find_bar: the L{FindBar} child widget
	@ivar preferences: a L{ConfigDict} with preferences

	@signal: C{modified-changed ()}: emitted when the page is edited
	@signal: C{textstyle-changed (style)}: emitted when textstyle at the cursor changes, gets the list of text styles or None.
	@signal: C{activate-link (link, hints)}: emitted when a link is opened, stops emission after the first handler returns C{True}
	@signal: C{textbuffer-changed (TextBuffer, TextBuffer}: emitted when during page change the L{TextBuffer} is changed,
	Arguments provided are old and new TextBuffer. Main use is to disconnect and connect signals.
	@signal: C{page-changed (Page)}: emitted when page is changed
	@signal: C{link-caret-enter (link)}: emitted when cursor enters a link region
	@signal: C{link-caret-leave (link)}: emitted when cursor leaves a link region
	@signal: C{readonly-changed (bool)}: readonly property change

	@todo: document preferences supported by PageView
	@todo: document extra keybindings implemented in this widget
	@todo: document style properties supported by this widget
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'modified-changed': (GObject.SignalFlags.RUN_LAST, None, ()),
		'textstyle-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'textbuffer-changed': (GObject.SignalFlags.RUN_LAST, None, (object, object)),
		'page-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-caret-enter': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-caret-leave': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'readonly-changed': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
	}

	__signals__ = {
		'activate-link': (GObject.SignalFlags.RUN_LAST, bool, (object, object))
	}

	def __init__(self, notebook, navigation):
		'''Constructor
		@param notebook: the L{Notebook} object
		@param navigation: L{NavigationModel} object
		'''
		GObject.GObject.__init__(self)
		GSignalEmitterMixin.__init__(self)

		self._buffer_signals = ()
		self.notebook = notebook
		self.page = None
		self.navigation = navigation
		self.readonly = True
		self._readonly_set = False
		self._readonly_set_error = False
		self.ui_is_initialized = False
		self._caret_link = None
		self._undo_history_queue = [] # we never lookup in this list, only keep refs - notebook does the caching

		self.preferences = ConfigManager.preferences['PageView']
		self.preferences.define(
			show_edit_bar=Boolean(os_default_headerbar),
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

		self.textview = TextView(preferences=self.preferences)
		self.swindow = ScrolledWindow(self.textview)
		self._hack_hbox = Gtk.HBox()
		self._hack_hbox.add(self.swindow)
		self._hack_label = Gtk.Label() # any widget would do I guess
		self._hack_hbox.pack_end(self._hack_label, False, True, 1)

		self.overlay = Gtk.Overlay()
		self.overlay.add(self._hack_hbox)
		self._overlay_label = Gtk.Label()
		self._overlay_label.set_halign(Gtk.Align.START)
		self._overlay_label.set_margin_start(12)
		self._overlay_label.set_valign(Gtk.Align.END)
		self._overlay_label.set_margin_bottom(5)
		widget_set_css(self._overlay_label, 'overlay-label',
			'background: rgba(0, 0, 0, 0.8); '
			'padding: 3px 5px; border-radius: 3px; '
			'color: #fff; '
		) # Tried to make it look like tooltip - based on Adwaita css
		self._overlay_label.set_no_show_all(True)
		self.overlay.add_overlay(self._overlay_label)
		self.overlay.set_overlay_pass_through(self._overlay_label, True)
		self.add(self.overlay)

		self.textview.connect_object('link-clicked', PageView.activate_link, self)
		self.textview.connect_object('populate-popup', PageView.do_populate_popup, self)
		self._overlay_handlers = ()  # holds signal handler ids

		## Create search box
		self.find_bar = FindBar(textview=self.textview)
		self.pack_end(self.find_bar, False, True, 0)
		self.find_bar.hide()

		## setup GUI actions
		group = get_gtk_actiongroup(self)
		group.add_actions(MENU_ACTIONS, self)

		# setup hooks for new file submenu
		action = self.actiongroup.get_action('insert_new_file_menu')
		action.zim_readonly = False
		action.connect('activate', self._update_new_file_submenu)

		# ...
		self.edit_bar = EditBar(self)
		self._edit_bar_visible = True
		self.pack_start(self.edit_bar, False, True, 0)
		#self.reorder_child(self.edit_bar, 0)

		self.edit_bar.show_all()
		self.edit_bar.set_no_show_all(True)

		def _show_edit_bar_on_hide_find(*a):
			if self._edit_bar_visible and not self.readonly:
				self.edit_bar.show()

		self.find_bar.connect('show', lambda o: self.edit_bar.hide())
		self.find_bar.connect_after('hide', _show_edit_bar_on_hide_find)

		# ...
		self.preferences.connect('changed', self.on_preferences_changed)
		self.on_preferences_changed()

		self.text_style = ConfigManager.get_config_dict('style.conf')
		self.text_style.connect('changed', lambda o: self.on_text_style_changed())
		self.on_text_style_changed()

		def assert_not_modified(page, *a):
			if page == self.page \
			and self.textview.get_buffer().get_modified():
				raise AssertionError('BUG: page changed while buffer changed as well')
				# not using assert here because it could be optimized away

		for s in ('store-page', 'delete-page', 'move-page'):
			self.notebook.connect(s, assert_not_modified)

		# Setup saving
		if_preferences = ConfigManager.preferences['GtkInterface']
		if_preferences.setdefault('autosave_timeout', 15)
		if_preferences.setdefault('autosave_use_thread', True)
		logger.debug('Autosave interval: %r - use threads: %r',
			if_preferences['autosave_timeout'],
			if_preferences['autosave_use_thread']
		)
		self._save_page_handler = SavePageHandler(
			self, notebook,
			lambda: self.page,
			timeout=if_preferences['autosave_timeout'],
			use_thread=if_preferences['autosave_use_thread']
		)

		def on_focus_out_event(*a):
			self._save_page_handler.try_save_page()
			return False # don't block the event
		self.textview.connect('focus-out-event', on_focus_out_event)

		PluginManager.insertedobjects.connect(
			'changed',
			self.on_insertedobjecttypemap_changed
		)

		initialize_actiongroup(self, 'pageview')
		self._insertedobject_manager = InsertedObjectPageviewManager(self)
		self.__zim_extension_objects__.append(self._insertedobject_manager) # HACK to make actions discoverable

	def do_key_press_event(self, event: Gdk.EventKey) -> bool:
		keyval = strip_boolean_result(event.get_keyval())
		if keyval == KEYVAL_ESC:
			# hide the find_bar if it is currently visible
			if self.find_bar.get_visible():
				self.hide_find()
				return True
		return Gtk.VBox.do_key_press_event(self, event)

	def grab_focus(self):
		self.textview.grab_focus()

	def on_preferences_changed(self, *a):
		self.textview.set_cursor_visible(
			self.preferences['read_only_cursor'] or not self.readonly)
		self._set_edit_bar_visible(self.preferences['show_edit_bar'])
		self._set_overlay_visibility(self.preferences['show_link_label'])

	def _set_edit_bar_visible(self, visible):
		self._edit_bar_visible = visible
		if not visible:
			self.edit_bar.hide()
		elif self.find_bar.get_property('visible') or self.readonly:
			self.edit_bar.hide()
		else:
			self.edit_bar.show()

	def on_text_style_changed(self, *a):
		'''(Re-)intializes properties for TextView, TextBuffer and
		TextTags based on the properties in the style config.
		'''

		# TODO: reload buffer on style changed to make change visible
		#       now it is only visible on next page load

		self.text_style['TextView'].define(
			bullet_icon_size=ConfigDefinitionConstant(
				'GTK_ICON_SIZE_MENU',
				Gtk.IconSize,
				'GTK_ICON_SIZE'
			)
		)

		self.text_style['TextView'].setdefault('indent', TextBuffer.pixels_indent)
		self.text_style['TextView'].setdefault('tabs', None, int)
			# Don't set a default for 'tabs' as not to break pages that
			# were created before this setting was introduced.
		self.text_style['TextView'].setdefault('linespacing', 3)
		self.text_style['TextView'].setdefault('wrapped-lines-linespacing', 0)
		self.text_style['TextView'].setdefault('font', None, str)
		self.text_style['TextView'].setdefault('justify', None, str)
		#~ print self.text_style['TextView']

		# Set properties for TextVIew
		if self.text_style['TextView']['tabs']:
			tabarray = Pango.TabArray(1, True) # Initial size, position in pixels
			tabarray.set_tab(0, Pango.TabAlign.LEFT, self.text_style['TextView']['tabs'])
				# We just set the size for one tab, apparently this gets
				# copied automaticlly when a new tab is created by the textbuffer
			self.textview.set_tabs(tabarray)

		if self.text_style['TextView']['linespacing']:
			self.textview.set_pixels_below_lines(self.text_style['TextView']['linespacing'])

		if self.text_style['TextView']['wrapped-lines-linespacing']:
			self.textview.set_pixels_inside_wrap(self.text_style['TextView']['wrapped-lines-linespacing'])

		if self.text_style['TextView']['font']:
			font = Pango.FontDescription(self.text_style['TextView']['font'])
			self.textview.modify_font(font)
		else:
			self.textview.modify_font(None)

		if self.text_style['TextView']['justify']:
			try:
				const = self.text_style['TextView']['justify']
				assert hasattr(Gtk.Justification, const), 'No such constant: Gtk.%s' % const
				self.textview.set_justification(getattr(Gtk.Justification, const))
			except:
				logger.exception('Exception while setting justification:')

		# Set properties for TextBuffer
		TextBuffer.pixels_indent = self.text_style['TextView']['indent']
		TextBuffer.bullet_icon_size = self.text_style['TextView']['bullet_icon_size']

		# Load TextTags
		testbuffer = Gtk.TextBuffer()
		for key in [k for k in list(self.text_style.keys()) if k.startswith('Tag ')]:
			section = self.text_style[key]
			defs = [(k, TextBuffer.tag_attributes[k])
				for k in section._input if k in TextBuffer.tag_attributes]
			section.define(defs)
			tag = key[4:]
			tag = tag.replace('-checkbox', '-box') # backward compatibility after renaming constants

			try:
				if not tag in TextBuffer.tag_styles:
					raise AssertionError('No such tag: %s' % tag)

				attrib = dict(i for i in list(section.items_by_selectors()) if i[1] is not None)
				if 'linespacing' in attrib:
					attrib['pixels-below-lines'] = attrib.pop('linespacing')

				#~ print('TAG', tag, attrib)
				testtag = testbuffer.create_tag('style-' + tag, **attrib)
				if not testtag:
					raise AssertionError('Could not create tag: %s' % tag)
			except:
				logger.exception('Exception while parsing tag: %s:', tag)
			else:
				TextBuffer.tag_styles[tag].update(attrib)

	def _connect_focus_event(self):
		# Connect to parent window here in a HACK to ensure
		# we do not hijack keybindings like ^C and ^V while we are not
		# focus (e.g. paste in find bar) Put it here to ensure
		# mainwindow is initialized.
		def set_actiongroup_sensitive(window, widget):
			#~ print('!! FOCUS SET:', widget)
			sensitive = widget is self.textview

			# Enable keybindings and buttons for find functionality if find bar is in focus
			force_sensitive = ()
			if widget and widget.is_ancestor(self.find_bar):
				force_sensitive = ("show_find", "find_next", "find_previous",
					"show_find_alt1", "find_next_alt1", "find_previous_alt1")

			self._set_menuitems_sensitive(sensitive, force_sensitive)

		window = self.get_toplevel()
		if window and window != self:
			window.connect('set-focus', set_actiongroup_sensitive)

	def _set_overlay_visibility(self, show_overlay):
		# Determines whether link overlay shows up on mouseover/caret
		# according to user preference; doesn't toggle it
		if show_overlay and not self._overlay_handlers:
			self._overlay_handlers = (
					self.textview.connect('link-enter', self.on_link_enter),
					self.textview.connect('link-leave', self.on_link_leave),
					self.connect('link-caret-enter', self.on_link_enter),
					self.connect('link-caret-leave', self.on_link_leave)
					)
		elif not show_overlay and self._overlay_handlers:
			self.textview.disconnect(self._overlay_handlers[0])
			self.textview.disconnect(self._overlay_handlers[1])
			self.disconnect(self._overlay_handlers[2])
			self.disconnect(self._overlay_handlers[3])
			self._overlay_handlers = ()
			self._overlay_label.hide()  # in case one is shown while toggling preferences

	def on_link_enter(self, view, link):
		if link_type(link['href']) == 'page':
			href = HRef.new_from_wiki_link(link['href'])
			path = self.notebook.pages.resolve_link(self.page, href)
			name = path.name + '#' + href.anchor if href.anchor else path.name
			self._overlay_label.set_text('Go to "%s"' % name)# T: tooltip text for links to pages
		else:
			self._overlay_label.set_text('Open "%s"' % link['href']) # T: tooltip text for links to files/URLs etc.

		self._overlay_label.show()

	def on_link_leave(self, view, link):
		self._overlay_label.hide()

	def set_page(self, page, cursor=None):
		'''Set the current page to be displayed in the pageview

		When the page does not yet exist a template is loaded for a
		new page which is obtained from
		L{Notebook.get_template()<zim.notebook.Notebook.get_template>}.

		Exceptions while loading the page are handled gracefully with
		an error dialog and will result in the widget to be read-only
		and insensitive until the next page is loaded.

		@param page: a L{Page} object
		@keyword cursor: optional cursor position (integer)

		When the cursor is set to C{-1} the cursor will be placed at
		the end of the buffer.

		If cursor is C{None} the cursor is set at the start of the page
		for existing pages or to the end of the template when the page
		does not yet exist.

		@emits: textbuffer-changed
		'''
		if self.page is None:
			# first run - bootstrap HACK
			self._connect_focus_event()

		# Teardown connection with current page buffer
		prev_buffer = self.textview.get_buffer()
		for id in self._buffer_signals:
			prev_buffer.disconnect(id)
		self._buffer_signals = ()

		# now create the new buffer
		self._readonly_set_error = False
		try:
			self.page = page
			buffer = page.get_textbuffer(self._create_textbuffer)
			self._buffer_signals = (
				buffer.connect('end-insert-tree', self._hack_on_inserted_tree),
			)
			# TODO: also connect after insert widget ?

			self.textview.set_buffer(buffer)
			self._hack_on_inserted_tree()
		except Exception as error:
			# Maybe corrupted parse tree - prevent page to be edited or saved back
			self._readonly_set_error = True
			self._update_readonly()
			self.set_sensitive(False)
			ErrorDialog(self, error).run()
		else:

			# Finish hooking up the new page
			if cursor is not None:
				self.set_cursor_pos(cursor)
			elif not buffer.showing_template:
				self.set_cursor_pos(0)
			# else the template might already have placed it, or leave it at the end

			self._buffer_signals += (
				buffer.connect('textstyle-changed', lambda o, *a: self.emit('textstyle-changed', *a)),
				buffer.connect('modified-changed', lambda o: self.on_modified_changed(o)),
				buffer.connect_after('mark-set', self.do_mark_set),
			)

			self.set_sensitive(True)
			self._update_readonly()

			self.emit('textbuffer-changed', prev_buffer, buffer)
			self.emit('page-changed', self.page)

	def _create_textbuffer(self, parsetree=None):
		# Callback for page.get_textbuffer
		buffer = TextBuffer(self.notebook, self.page, parsetree=parsetree)

		readonly = self._readonly_set or self.notebook.readonly or self.page.readonly
			# Do not use "self.readonly" here, may not yet be intialized
		if parsetree is None and not readonly:
			# HACK: using None value instead of "hascontent" to distinguish
			# between a page without source and an existing empty page
			CURSOR_CHAR = '\ufffe' # unicode "non-character"
			parsetree = self.notebook.get_template(self.page,
				{'place_cursor': ExpressionFunction(lambda: CURSOR_CHAR)}
			)
			buffer.set_parsetree(parsetree, showing_template=True)
			start, end = buffer.get_bounds()
			start.forward_find_char(lambda c,x: c == CURSOR_CHAR)
			if not start.equal(end):
				buffer.place_cursor(start)
				bound = start.copy()
				bound.forward_char()
				buffer.delete(start, bound)
			buffer.set_modified(False)
			# By setting this instead of providing to the TextBuffer constructor
			# this template can be undone

		return buffer

	def on_modified_changed(self, buffer):
		if buffer.get_modified():
			if self.readonly:
				logger.warning('Buffer edited while textview read-only - potential bug')
			else:
				if not (self._undo_history_queue and self._undo_history_queue[-1] is self.page):
					if self.page in self._undo_history_queue:
						self._undo_history_queue.remove(self.page)
					elif len(self._undo_history_queue) > MAX_PAGES_UNDO_STACK:
						self._undo_history_queue.pop(0)
					self._undo_history_queue.append(self.page)

				buffer.showing_template = False
				self.emit('modified-changed')
				self._save_page_handler.queue_autosave()

	def save_changes(self, write_if_not_modified=False):
		'''Save contents of the widget back to the page object and
		synchronize it with the notebook.

		@param write_if_not_modified: If C{True} page will be written
		even if it is not changed. (This allows e.g. to force saving template
		content to disk without editing.)
		'''
		if write_if_not_modified or self.page.modified:
			self._save_page_handler.save_page_now()
		self._save_page_handler.wait_for_store_page_async()

	def _hack_on_inserted_tree(self, *a):
		if self.textview._object_widgets:
			# Force resize of the scroll window, forcing a redraw to fix
			# glitch in allocation of embedded obejcts, see isse #642
			# Will add another timeout to rendering the page, increasing the
			# priority breaks the hack though. Which shows the glitch is
			# probably also happening in a drawing or resizing idle event
			#
			# Additional hook is needed for scrolling because re-rendering the
			# objects changes the textview size and thus looses the scrolled
			# position. Here idle didn't work so used a time-out with the
			# potential risk that in some cases the timeout is to fast or to slow.

			self._hack_label.show_all()
			def scroll():
				self.scroll_cursor_on_screen()
				return False

			def hide_hack():
				self._hack_label.hide()
				GLib.timeout_add(100, scroll)
				return False

			GLib.idle_add(hide_hack)
		else:
			self._hack_label.hide()

	def on_insertedobjecttypemap_changed(self, *a):
		self.save_changes()
		self.page.reload_textbuffer() # HACK - should not need to reload whole page just to load objects

	def set_readonly(self, readonly):
		'''Set the widget read-only or not

		Sets the read-only state but also update menu items etc. to
		reflect the new state.

		@param readonly: C{True} or C{False} to set the read-only state

		Effective read-only state seen in the C{self.readonly} attribute
		is in fact C{True} (so read-only) when either the widget itself
		OR the current page is read-only. So setting read-only to
		C{False} here may not immediately change C{self.readonly} if
		a read-only page is loaded.
		'''
		self._readonly_set = readonly
		self._update_readonly()
		self.emit('readonly-changed', readonly)

	def _update_readonly(self):
		self.readonly = self._readonly_set \
			or self._readonly_set_error \
			or self.page is None \
			or self.notebook.readonly \
			or self.page.readonly
		self.textview.set_editable(not self.readonly)
		self.textview.set_cursor_visible(
			self.preferences['read_only_cursor'] or not self.readonly)
		self._set_menuitems_sensitive(True) # XXX not sure why this is here

		if not self._edit_bar_visible:
			pass
		elif self.find_bar.get_property('visible') or self.readonly:
			self.edit_bar.hide()
		else:
			self.edit_bar.show()

	def _set_menuitems_sensitive(self, sensitive, force_sensitive=()):
		'''Batch update global menu sensitivity while respecting
		sensitivities set due to cursor position, readonly state etc.
		'''

		if sensitive:
			# partly overrule logic in window.toggle_editable()
			for action in self.actiongroup.list_actions():
				action.set_sensitive(
					action.zim_readonly or not self.readonly)

			# update state for menu items for checkboxes and links
			buffer = self.textview.get_buffer()
			iter = buffer.get_insert_iter()
			mark = buffer.get_insert()
			self.do_mark_set(buffer, iter, mark)
		else:
			for action in self.actiongroup.list_actions():
				if action.get_name() not in force_sensitive:
					action.set_sensitive(False)
				else:
					action.set_sensitive(True)

	def set_cursor_pos(self, pos):
		'''Set the cursor position in the buffer and scroll the TextView
		to show it

		@param pos: the cursor position as an integer offset from the
		start of the buffer

		As a special case when the cursor position is C{-1} the cursor
		is set at the end of the buffer.
		'''
		buffer = self.textview.get_buffer()
		if pos < 0:
			start, end = buffer.get_bounds()
			iter = end
		else:
			iter = buffer.get_iter_at_offset(pos)

		buffer.place_cursor(iter)
		self.scroll_cursor_on_screen()

	def get_cursor_pos(self):
		'''Get the cursor position in the buffer

		@returns: the cursor position as an integer offset from the
		start of the buffer
		'''
		buffer = self.textview.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		return iter.get_offset()

	def scroll_cursor_on_screen(self):
		buffer = self.textview.get_buffer()
		self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	def set_scroll_pos(self, pos):
		pass # FIXME set scroll position

	def get_scroll_pos(self):
		pass # FIXME get scroll position

	def get_selection(self, format=None):
		'''Convenience method to get the text of the current selection.

		@param format: format to use for the formatting of the returned
		text (e.g. 'wiki' or 'html'). If the format is C{None} only the
		text will be returned without any formatting.

		@returns: text selection or C{None}
		'''
		buffer = self.textview.get_buffer()
		bounds = buffer.get_selection_bounds()
		if bounds:
			if format:
				tree = buffer.get_parsetree(bounds)
				dumper = zim.formats.get_format(format).Dumper()
				lines = dumper.dump(tree)
				return ''.join(lines)
			else:
				return bounds[0].get_text(bounds[1])
		else:
			return None

	def get_word(self, format=None):
		'''Convenience method to get the word that is under the cursor

		@param format: format to use for the formatting of the returned
		text (e.g. 'wiki' or 'html'). If the format is C{None} only the
		text will be returned without any formatting.

		@returns: current word or C{None}
		'''
		buffer = self.textview.get_buffer()
		buffer.select_word()
		return self.get_selection(format)

	def replace_selection(self, text, autoselect=None):
		assert autoselect in (None, 'word')
		buffer = self.textview.get_buffer()
		if not buffer.get_has_selection():
			if autoselect == 'word':
				buffer.select_word()
			else:
				raise AssertionError

		bounds = buffer.get_selection_bounds()
		if bounds:
			start, end = bounds
			with buffer.user_action:
				buffer.delete(start, end)
				buffer.insert_at_cursor(''.join(text))
		else:
			buffer.insert_at_cursor(''.join(text))

	def do_mark_set(self, buffer, iter, mark):
		'''Update state after cursor position changes
		@emits link-caret-enter
		@emits link-caret-leave
		'''
		if mark.get_name() != 'insert':
			return

		# Set sensitivity of various menu options
		if not self.readonly:
			line = iter.get_line()
			bullet = buffer.get_bullet(line)

			if bullet and bullet in CHECKBOXES:
				self.actiongroup.get_action('uncheck_checkbox').set_sensitive(True)
				self.actiongroup.get_action('toggle_checkbox').set_sensitive(True)
				self.actiongroup.get_action('xtoggle_checkbox').set_sensitive(True)
				self.actiongroup.get_action('migrate_checkbox').set_sensitive(True)
				self.actiongroup.get_action('transmigrate_checkbox').set_sensitive(True)
			else:
				self.actiongroup.get_action('uncheck_checkbox').set_sensitive(False)
				self.actiongroup.get_action('toggle_checkbox').set_sensitive(False)
				self.actiongroup.get_action('xtoggle_checkbox').set_sensitive(False)
				self.actiongroup.get_action('migrate_checkbox').set_sensitive(False)
				self.actiongroup.get_action('transmigrate_checkbox').set_sensitive(False)

			if buffer.get_link_tag(iter):
				self.actiongroup.get_action('remove_link').set_sensitive(True)
				self.actiongroup.get_action('edit_object').set_sensitive(True)
			elif buffer.get_image_data(iter):
				self.actiongroup.get_action('remove_link').set_sensitive(False)
				self.actiongroup.get_action('edit_object').set_sensitive(True)
			else:
				self.actiongroup.get_action('edit_object').set_sensitive(False)
				self.actiongroup.get_action('remove_link').set_sensitive(False)

			self.actiongroup.get_action('move_text').set_sensitive(buffer.get_has_selection())

		# Emit signal if passing through a link
		link = buffer.get_link_data(iter)
		if link:
			if not self._caret_link:  # we enter link for the first time
				self.emit("link-caret-enter", link)
			elif self._caret_link != link:  # we changed the link
				self.emit("link-caret-leave", self._caret_link)
				self.emit("link-caret-enter", link)
		elif self._caret_link:  # we left the link
			self.emit("link-caret-leave", self._caret_link)
		self._caret_link = link

	def do_textstyle_changed(self, styles):
		if not styles:  # styles can be None or a list
			styles = []

		for name in self._format_toggle_actions:
			getattr(self, name).set_active(name[14:] in styles) # len("toggle_format_") = 14

	def activate_link(self, link, new_window=False):
		if not isinstance(link, str):
			link = link['href']

		logger.debug('Activate link: %s', link)

		if link_type(link) == 'interwiki':
			target = interwiki_link(link)
			if target is not None:
				link = target
			else:
				name = link.split('?')[0]
				error = Error(_('No such wiki defined: %s') % name)
					# T: error when unknown interwiki link is clicked
				return ErrorDialog(self, error).run()

		hints = {'new_window': new_window}
		self.emit_return_first('activate-link', link, hints)

	def do_activate_link(self, link, hints):
		try:
			self._do_activate_link(link, hints)
		except:
			zim.errors.exception_handler(
				'Exception during activate-link(%r)' % ((link, hints),))

	def _do_activate_link(self, link, hints):
		type = link_type(link)

		if type == 'page':
			href = HRef.new_from_wiki_link(link)
			path = self.notebook.pages.resolve_link(self.page, href)
			self.navigation.open_page(path, anchor=href.anchor, new_window=hints.get('new_window', False))
		elif type == 'file':
			path = self.notebook.resolve_file(link, self.page)
			open_file(self, path)
		elif type == 'notebook':
			if link.startswith('zim+'):
				uri, pagelink = link[4:], None
				if '?' in uri:
					uri, pagelink = uri.split('?', 1) # pagelink part can include # anchor

				self.navigation.open_notebook(uri, pagelink)

			else:
				self.navigation.open_notebook(FilePath(link).uri)

		else:
			if type == 'mailto' and not link.startswith('mailto:'):
				link = 'mailto:' + link  # Enforce proper URI form
			open_url(self, link)

		return True # handled

	def navigate_to_anchor(self, name, select_line=False, fail_silent=False):
		"""Navigate to an anchor on the current page.
		@param name: The name of the anchor to navigate to
		@param select_line: Select the whole line after
		"""
		logger.debug("navigating to anchor '%s'", name)
		textview = self.textview
		buffer = textview.get_buffer()
		iter = buffer.find_anchor(name)
		if not iter:
			if not fail_silent:
				ErrorDialog(self, _('Id "%s" not found on the current page') % name).run() # T: error when anchor location in page not found
			return
		elif not iter.starts_line():
			iter.forward_char() # Place iter after inline object

		buffer.place_cursor(iter)
		if select_line:
			buffer.select_line()
		textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	def do_populate_popup(self, menu):
		buffer = self.textview.get_buffer()
		if not buffer.get_has_selection():
			iter = self.textview._get_popup_menu_mark()
			if iter is None:
				self._default_do_populate_popup(menu)
			else:
				if iter.get_line_offset() == 1:
					iter.backward_char() # if clicked on right half of image, iter is after the image
				bullet = buffer.get_bullet_at_iter(iter)
				if bullet and bullet in CHECKBOXES:
					self._checkbox_do_populate_popup(menu, buffer, iter)
				else:
					self._default_do_populate_popup(menu)
		else:
			self._default_do_populate_popup(menu)
		menu.show_all()

	def _default_do_populate_popup(self, menu):
		# Add custom tool
		# FIXME need way to (deep)copy widgets in the menu
		#~ toolmenu = uimanager.get_widget('/text_popup')
		#~ tools = [tool for tool in toolmenu.get_children()
					#~ if not isinstance(tool, Gtk.SeparatorMenuItem)]
		#~ print('>>> TOOLS', tools)
		#~ if tools:
			#~ menu.prepend(Gtk.SeparatorMenuItem())
			#~ for tool in tools:
				#~ tool.reparent(menu)

		buffer = self.textview.get_buffer()

		### Copy As option ###
		default = self.preferences['copy_format'].lower()
		copy_as_menu = Gtk.Menu()
		for label in COPY_FORMATS:
			if label.lower() == default:
				continue # Covered by default Copy action

			format = zim.formats.canonical_name(label)
			item = Gtk.MenuItem.new_with_mnemonic(label)
			if buffer.get_has_selection():
				item.connect('activate',
					lambda o, f: self.textview.do_copy_clipboard(format=f),
					format)
			else:
				item.set_sensitive(False)
			copy_as_menu.append(item)

		item = Gtk.MenuItem.new_with_mnemonic(_('Copy _As...')) # T: menu item for context menu of editor
		item.set_submenu(copy_as_menu)
		menu.insert(item, 2) # position after Copy in the standard menu - may not be robust...
			# FIXME get code from test to seek stock item

		### Paste As
		item = Gtk.MenuItem.new_with_mnemonic(_('Paste As _Verbatim')) # T: menu item for context menu of editor
		item.set_sensitive(Clipboard.clipboard.wait_is_text_available())
		item.connect('activate', lambda o: self.textview.do_paste_clipboard(format='verbatim'))
		item.show_all()
		menu.insert(item, 4) # position after Paste in the standard menu - may not be robust...
			# FIXME get code from test to seek stock item

		### Move text to new page ###
		item = Gtk.MenuItem.new_with_mnemonic(_('Move Selected Text...'))
			# T: Context menu item for pageview to move selected text to new/other page
		menu.insert(item, 7) # position after Copy in the standard menu - may not be robust...
			# FIXME get code from test to seek stock item

		if buffer.get_has_selection():
			item.connect('activate', lambda o: self.move_text())
		else:
			item.set_sensitive(False)
		###

		iter = self.textview._get_popup_menu_mark()
			# This iter can be either cursor position or pointer
			# position, depending on how the menu was called
		if iter is None:
			return

		def _copy_link_to_anchor(o, anchor, text):
			path = self.page
			Clipboard.set_pagelink(self.notebook, path, anchor, text)
			SelectionClipboard.set_pagelink(self.notebook, path, anchor, text)

		# copy link to anchor or heading
		item = Gtk.MenuItem.new_with_mnemonic(_('Copy _link to this location')) # T: menu item to copy link to achor location in page
		anchor = buffer.get_anchor_for_location(iter)
		if anchor:
			lvl, heading_text = buffer.get_heading(iter.get_line()) # can be None if not a heading
			item.connect('activate', _copy_link_to_anchor, anchor, heading_text)
		else:
			item.set_sensitive(False)
		menu.insert(item, 3)

		# link
		link = buffer.get_link_data(iter)
		if link:
			type = link_type(link['href'])
			if type == 'file':
				file = link['href']
			else:
				file = None
		else:
			image = buffer.get_image_data(iter)
			if image is None:
				# Maybe we clicked right side of an image
				iter.backward_char()
				image = buffer.get_image_data(iter)

			if image:
				type = 'image'
				file = image['src']
			else:
				return # No link or image

		if file:
			try:
				file = self.notebook.resolve_file(file, self.page)
			except:
				logger.exception('Could not resolve file link: %s', file)
				file = None

		menu.prepend(Gtk.SeparatorMenuItem())

		# remove link
		if link:
			item = Gtk.MenuItem.new_with_mnemonic(_('_Remove Link'))
			item.connect('activate', lambda o: self.remove_link(iter=iter))
			item.set_sensitive(not self.readonly)
			menu.prepend(item)

		# edit
		if type == 'image':
			item = Gtk.MenuItem.new_with_mnemonic(_('_Edit Properties')) # T: menu item in context menu for image
		else:
			item = Gtk.MenuItem.new_with_mnemonic(_('_Edit Link')) # T: menu item in context menu
		item.connect('activate', lambda o: self.edit_object(iter=iter))
		item.set_sensitive(not self.readonly)
		menu.prepend(item)

		# copy & cut
		def set_pagelink(o, path, anchor):
			Clipboard.set_pagelink(self.notebook, path, anchor)
			SelectionClipboard.set_pagelink(self.notebook, path, anchor)

		def set_interwikilink(o, data):
			href, url = data
			Clipboard.set_interwikilink(href, url)
			SelectionClipboard.set_interwikilink(href, url)

		def set_uri(o, uri):
			Clipboard.set_uri(uri)
			SelectionClipboard.set_uri(uri)

		def cut(o, setter, *args):
			# setter: one of the above three set_* functions
			setter(o, *args)
			self.remove_link(iter=iter)

		item = [
				Gtk.MenuItem.new_with_mnemonic(_('Copy _Link')), # T: context menu item
				Gtk.MenuItem.new_with_mnemonic(_('Cut Lin_k')), # T: context menu item
				]

		if type == 'page':
			href = HRef.new_from_wiki_link(link['href'])
			path = self.notebook.pages.resolve_link(self.page, href)
			item[0].connect('activate', set_pagelink, path, href.anchor)
			item[1].connect('activate', cut, set_pagelink, path, href.anchor)
		elif type == 'interwiki':
			url = interwiki_link(link['href'])
			item[0].connect('activate', set_interwikilink, (link['href'], url))
			item[1].connect('activate', cut, set_interwikilink, (link['href'], url))
		elif type == 'mailto':
			item[0] = Gtk.MenuItem.new_with_mnemonic(_('Copy Email Address')) # T: context menu item
			item[0].connect('activate', set_uri, file or link['href'])
			item[1].connect('activate', cut, set_uri, file or link['href'])
		else:
			item[0].connect('activate', set_uri, file or link['href'])
			item[1].connect('activate', cut, set_uri, file or link['href'])

		item[1].set_sensitive(not self.readonly)
		menu.prepend(item[0])
		menu.prepend(item[1])

		menu.prepend(Gtk.SeparatorMenuItem())

		# open with & open folder
		if type in ('file', 'image') and file:
			item = Gtk.MenuItem.new_with_mnemonic(_('Open Folder'))
				# T: menu item to open containing folder of files
			menu.prepend(item)
			dir = file.parent()
			if dir.exists():
				item.connect('activate', lambda o: open_file(self, dir))
			else:
				item.set_sensitive(False)

			item = Gtk.MenuItem.new_with_mnemonic(_('Open With...'))
				# T: menu item for sub menu with applications
			menu.prepend(item)
			if file.exists():
				submenu = OpenWithMenu(self, file)
				item.set_submenu(submenu)
			else:
				item.set_sensitive(False)
		elif type not in ('page', 'notebook', 'interwiki', 'file', 'image'): # urls etc.
			# FIXME: for interwiki inspect final link and base
			# open with menu based on that url type
			item = Gtk.MenuItem.new_with_mnemonic(_('Open With...'))
			menu.prepend(item)
			submenu = OpenWithMenu(self, link['href'])
			if submenu.get_children():
				item.set_submenu(submenu)
			else:
				item.set_sensitive(False)

		# open in new window
		if type == 'page':
			item = Gtk.MenuItem.new_with_mnemonic(_('Open in New _Window'))
				# T: menu item to open a link
			item.connect(
				'activate', lambda o: self.activate_link(link, new_window=True))
			menu.prepend(item)

		# open
		if type == 'image':
			link = {'href': file.uri}

		item = Gtk.MenuItem.new_with_mnemonic(_('_Open'))
			# T: menu item to open a link or file
		if file and not file.exists():
			item.set_sensitive(False)
		else:
			item.connect_object(
				'activate', PageView.activate_link, self, link)
		menu.prepend(item)

	def _checkbox_do_populate_popup(self, menu, buffer, iter):
		line = iter.get_line()

		menu.prepend(Gtk.SeparatorMenuItem())

		for bullet, label in (
			(TRANSMIGRATED_BOX, _('Check Checkbox \'<\'')), # T: popup menu menuitem
			(MIGRATED_BOX, _('Check Checkbox \'>\'')), # T: popup menu menuitem
			(XCHECKED_BOX, _('Check Checkbox \'X\'')), # T: popup menu menuitem
			(CHECKED_BOX, _('Check Checkbox \'V\'')), # T: popup menu menuitem
			(UNCHECKED_BOX, _('Un-check Checkbox')), # T: popup menu menuitem
		):
			item = Gtk.ImageMenuItem(BULLET_TYPES[bullet])
			item.set_label(label)
			item.connect('activate', callback(buffer.set_bullet, line, bullet))
			menu.prepend(item)

		menu.show_all()

	@action(_('_Save'), '<Primary>S', menuhints='edit') # T: Menu item
	def save_page(self):
		'''Menu action to save the current page.

		Can result in a L{SavePageErrorDialog} when there is an error
		while saving a page. If that dialog is cancelled by the user,
		the page may not be saved after all.
		'''
		self.save_changes(write_if_not_modified=True)

	@action(_('_Reload'), '<Primary>R') # T: Menu item
	def reload_page(self):
		'''Menu action to reload the current page. Will first try
		to save any unsaved changes, then reload the page from disk.
		'''
		cursor = self.get_cursor_pos()
		self.save_changes()
		self.page.reload_textbuffer()
		self.set_cursor_pos(cursor)

	@action(_('_Undo'), '<Primary>Z', menuhints='edit') # T: Menu item
	def undo(self):
		'''Menu action to undo a single step'''
		buffer = self.textview.get_buffer()
		buffer.undostack.undo()
		self.scroll_cursor_on_screen()

	@action(_('_Redo'), '<Primary><shift>Z', alt_accelerator='<Primary>Y', menuhints='edit') # T: Menu item
	def redo(self):
		'''Menu action to redo a single step'''
		buffer = self.textview.get_buffer()
		buffer.undostack.redo()
		self.scroll_cursor_on_screen()

	@action(_('Cu_t'), '<Primary>X', menuhints='edit') # T: Menu item
	def cut(self):
		'''Menu action for cut to clipboard'''
		self.textview.emit('cut-clipboard')

	@action(_('_Copy'), '<Primary>C', menuhints='edit') # T: Menu item
	def copy(self):
		'''Menu action for copy to clipboard'''
		self.textview.emit('copy-clipboard')

	@action(_('_Paste'), '<Primary>V', menuhints='edit') # T: Menu item
	def paste(self):
		'''Menu action for paste from clipboard'''
		self.textview.emit('paste-clipboard')

	@action(_('_Delete'), menuhints='edit') # T: Menu item
	def delete(self):
		'''Menu action for delete'''
		self.textview.emit('delete-from-cursor', Gtk.DeleteType.CHARS, 1)

	@action(_('Un-check Checkbox'), verb_icon=STOCK_UNCHECKED_BOX, menuhints='edit') # T: Menu item
	def uncheck_checkbox(self):
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(UNCHECKED_BOX, recurs)

	@action(_('Toggle Checkbox \'V\''), 'F12', verb_icon=STOCK_CHECKED_BOX, menuhints='edit') # T: Menu item
	def toggle_checkbox(self):
		'''Menu action to toggle checkbox at the cursor or in current
		selected text
		'''
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(CHECKED_BOX, recurs)

	@action(_('Toggle Checkbox \'X\''), '<shift>F12', verb_icon=STOCK_XCHECKED_BOX, menuhints='edit') # T: Menu item
	def xtoggle_checkbox(self):
		'''Menu action to toggle checkbox at the cursor or in current
		selected text
		'''
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(XCHECKED_BOX, recurs)

	@action(_('Toggle Checkbox \'>\''), verb_icon=STOCK_MIGRATED_BOX, menuhints='edit') # T: Menu item
	def migrate_checkbox(self):
		'''Menu action to toggle checkbox at the cursor or in current
		selected text
		'''
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(MIGRATED_BOX, recurs)

	@action(_('Toggle Checkbox \'<\''), verb_icon=STOCK_TRANSMIGRATED_BOX, menuhints='edit') # T: Menu item
	def transmigrate_checkbox(self):
		'''Menu action to toggle checkbox at the cursor or in current
		selected text
		'''
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(TRANSMIGRATED_BOX, recurs)

	@action(_('_Edit Link or Object...'), '<Primary>E', menuhints='edit') # T: Menu item
	def edit_object(self, iter=None):
		'''Menu action to trigger proper edit dialog for the current
		object at the cursor

		Can show e.g. L{InsertLinkDialog} for a link, C{EditImageDialog}
		for the a image, or a plugin dialog for e.g. an equation.

		@param iter: C{TextIter} for an alternative cursor position
		'''
		buffer = self.textview.get_buffer()
		if iter:
			buffer.place_cursor(iter)

		iter = buffer.get_iter_at_mark(buffer.get_insert())
		if buffer.get_link_tag(iter):
			return InsertLinkDialog(self, self).run()

		image = buffer.get_image_data(iter)
		anchor = buffer.get_objectanchor(iter)
		if not (image or (anchor and isinstance(anchor, PluginInsertedObjectAnchor))):
			iter.backward_char() # maybe we clicked right side of an image
			image = buffer.get_image_data(iter)
			anchor = buffer.get_objectanchor(iter)

		if image:
			EditImageDialog(self, buffer, self.notebook, self.page).run()
		elif anchor and isinstance(anchor, PluginInsertedObjectAnchor):
			widget = anchor.get_widgets()[0]
			try:
				widget.edit_object()
			except NotImplementedError:
				return False
			else:
				return True
		else:
			return False

	@action(_('_Remove Link'), menuhints='edit') # T: Menu item
	def remove_link(self, iter=None):
		'''Menu action to remove link object at the current cursor position

		@param iter: C{TextIter} for an alternative cursor position
		'''
		buffer = self.textview.get_buffer()

		if not buffer.get_has_selection() \
		or (iter and not buffer.iter_in_selection(iter)):
			if iter:
				buffer.place_cursor(iter)
			buffer.select_link()

		bounds = buffer.get_selection_bounds()
		if bounds:
			buffer.remove_link(*bounds)

	@action(_('Copy Line'), accelerator='<Primary><Shift>C', menuhints='edit') # T: menu item to copy current line to clipboard
	def copy_current_line(self):
		'''Menu action to copy the current line to the clipboard'''
		buffer = self.textview.get_buffer()
		mark = buffer.create_mark(None, buffer.get_insert_iter())
		buffer.select_line()

		if buffer.get_has_selection():
			bounds = buffer.get_selection_bounds()
			tree = buffer.get_parsetree(bounds)
			Clipboard.set_parsetree(self.notebook, self.page, tree)
			buffer.unset_selection()
			buffer.place_cursor(buffer.get_iter_at_mark(mark))

		buffer.delete_mark(mark)

	@action(_('Cut Line'), accelerator='<Primary><Shift>X', menuhints='edit') # T: menu item to cut current line to clipboard
	def cut_current_line(self):
		'''Menu action to cut the current line to the clipboard'''
		buffer = self.textview.get_buffer()
		buffer.select_lines_for_selection()
		bounds = buffer.get_selection_bounds()
		tree = buffer.get_parsetree(bounds)
		Clipboard.set_parsetree(self.notebook, self.page, tree)
		start, end = bounds
		buffer.delete(start, end)
		buffer.set_modified(True)
		buffer.update_editmode()

	@action(_('Date and Time...'), accelerator='<Primary>D', menuhints='insert') # T: Menu item
	def insert_date(self):
		'''Menu action to insert a date, shows the L{InsertDateDialog}'''
		InsertDateDialog(self, self.textview.get_buffer(), self.notebook, self.page).run()

	def insert_object(self, attrib, data):
		buffer = self.textview.get_buffer()
		with buffer.user_action:
			buffer.insert_object_at_cursor(attrib, data)

	def insert_object_model(self, otype, model):
		buffer = self.textview.get_buffer()
		with buffer.user_action:
			buffer.insert_object_model_at_cursor(otype, model)

	@action(_('Horizontal _Line'), menuhints='insert') # T: Menu item for Insert menu
	def insert_line(self):
		'''Menu action to insert a line at the cursor position'''
		buffer = self.textview.get_buffer()
		with buffer.user_action:
			buffer.insert_objectanchor_at_cursor(LineSeparatorAnchor())
			# Add newline after line separator widget.
			buffer.insert_at_cursor('\n')

	@action(_('_Image...'), menuhints='insert') # T: Menu item
	def show_insert_image(self, file=None):
		'''Menu action to insert an image, shows the L{InsertImageDialog}
		@param file: optional file to suggest in the dialog
		'''
		InsertImageDialog(self, self.textview.get_buffer(), self.notebook, self.page, file).run()

	@action(_('_Attachment...'), verb_icon='zim-attachment', menuhints='insert') # T: Menu item
	def attach_file(self, file=None):
		'''Menu action to show the L{AttachFileDialog}
		@param file: optional file to suggest in the dialog
		'''
		AttachFileDialog(self, self.textview.get_buffer(), self.notebook, self.page, file).run()

	def insert_image(self, file):
		'''Insert a image
		@param file: the image file to insert. If C{file} does not exist or
		isn't an image, a "broken image" icon will be shown
		'''
		src = self.notebook.relative_filepath(file, self.page) or file.uri
		self.textview.get_buffer().insert_image_at_cursor(file, src)

	@action(_('Bulle_t List'), menuhints='insert') # T: Menu item
	def insert_bullet_list(self):
		'''Menu action insert a bullet item at the cursor'''
		self._start_bullet(BULLET)

	@action(_('_Numbered List'), menuhints='insert') # T: Menu item
	def insert_numbered_list(self):
		'''Menu action insert a numbered list item at the cursor'''
		self._start_bullet(NUMBER_BULLET)

	@action(_('Checkbo_x List'), menuhints='insert') # T: Menu item
	def insert_checkbox_list(self):
		'''Menu action insert an open checkbox at the cursor'''
		self._start_bullet(UNCHECKED_BOX)

	def _start_bullet(self, bullet_type):
		buffer = self.textview.get_buffer()
		line = buffer.get_insert_iter().get_line()

		with buffer.user_action:
			iter = buffer.get_iter_at_line(line)
			buffer.insert(iter, '\n')
			buffer.set_bullet(line, bullet_type)
			iter = buffer.get_iter_at_line(line)
			iter.forward_to_line_end()
			buffer.place_cursor(iter)

	@action(_('Bulle_t List'), menuhints='edit') # T: Menu item,
	def apply_format_bullet_list(self):
		'''Menu action to format selection as bullet list'''
		self._apply_bullet(BULLET)

	@action(_('_Numbered List'), menuhints='edit') # T: Menu item,
	def apply_format_numbered_list(self):
		'''Menu action to format selection as numbered list'''
		self._apply_bullet(NUMBER_BULLET)

	@action(_('Checkbo_x List'), menuhints='edit') # T: Menu item,
	def apply_format_checkbox_list(self):
		'''Menu action to format selection as checkbox list'''
		self._apply_bullet(UNCHECKED_BOX)

	@action(_('_Remove List'), menuhints='edit') # T: Menu item,
	def clear_list_format(self):
		'''Menu action to remove list formatting'''
		self._apply_bullet(None)

	def _apply_bullet(self, bullet_type):
		buffer = self.textview.get_buffer()
		bounds = buffer.get_selection_bounds()
		if bounds:
			# set for selected lines & restore selection
			start_mark = buffer.create_mark(None, bounds[0], left_gravity=True)
			end_mark = buffer.create_mark(None, bounds[1], left_gravity=False)
			try:
				buffer.foreach_line_in_selection(buffer.set_bullet, bullet_type, skip_empty_lines=True)
			except:
				raise
			else:
				start = buffer.get_iter_at_mark(start_mark)
				end = buffer.get_iter_at_mark(end_mark)
				buffer.select_range(start, end)
			finally:
				buffer.delete_mark(start_mark)
				buffer.delete_mark(end_mark)
		else:
			# set for current line
			line = buffer.get_insert_iter().get_line()
			buffer.set_bullet(line, bullet_type)

	@action(_('Text From _File...'), menuhints='insert') # T: Menu item
	def insert_text_from_file(self):
		'''Menu action to show a L{InsertTextFromFileDialog}'''
		InsertTextFromFileDialog(self, self.textview.get_buffer(), self.notebook, self.page).run()

	def insert_links(self, links):
		'''Non-interactive method to insert one or more links

		Inserts the links separated by newlines. Intended e.g. for
		drag-and-drop or copy-paste actions of e.g. files from a
		file browser.

		@param links: list of links, either as string, L{Path} objects,
		or L{File} objects
		'''
		links = list(links)
		for i in range(len(links)):
			if isinstance(links[i], Path):
				links[i] = links[i].name
				continue
			elif isinstance(links[i], FilePath):
				file = links[i]
			else:
				type = link_type(links[i])
				if type == 'file':
					try:
						file = FilePath(links[i])
					except:
						continue # mal-formed path
				else:
					continue # not a file
			links[i] = self.notebook.relative_filepath(file, self.page) or file.uri

		if len(links) == 1:
			sep = ' '
		else:
			sep = '\n'

		buffer = self.textview.get_buffer()
		with buffer.user_action:
			if buffer.get_has_selection():
				start, end = buffer.get_selection_bounds()
				buffer.delete(start, end)
			for link in links:
				buffer.insert_link_at_cursor(link, link)
				buffer.insert_at_cursor(sep)

	@action(_('_Link...'), '<Primary>L', verb_icon='zim-link', menuhints='insert') # T: Menu item
	def insert_link(self):
		'''Menu item to show the L{InsertLinkDialog}'''
		InsertLinkDialog(self, self).run()

	def _update_new_file_submenu(self, action):
		folder = self.preferences['file_templates_folder']
		if isinstance(folder, str):
			folder = LocalFolder(folder)

		items = []
		if folder.exists():
			def handler(menuitem, file):
				self.insert_new_file(file)

			for file in folder.list_files():
				name = file.basename
				if '.' in name:
					name, x = name.rsplit('.', 1)
				name = name.replace('_', ' ')
				item = Gtk.MenuItem.new_with_mnemonic(name)
					# TODO mimetype icon would be nice to have
				item.connect('activate', handler, file)
				item.zim_new_file_action = True
				items.append(item)

		if not items:
			item = Gtk.MenuItem.new_with_mnemonic(_('No templates installed'))
				# T: message when no file templates are found in ~/Templates
			item.set_sensitive(False)
			item.zim_new_file_action = True
			items.append(item)


		for widget in action.get_proxies():
			if hasattr(widget, 'get_submenu'):
				menu = widget.get_submenu()
				if not menu:
					continue

				# clear old items
				for item in menu.get_children():
					if hasattr(item, 'zim_new_file_action'):
						menu.remove(item)

				# add new ones
				populate_popup_add_separator(menu, prepend=True)
				for item in reversed(items):
					menu.prepend(item)

				# and finish up
				menu.show_all()

	def insert_new_file(self, template, basename=None):
		dir = self.notebook.get_attachments_dir(self.page)

		if not basename:
			basename = NewFileDialog(self, template.basename).run()
			if basename is None:
				return # cancelled

		file = dir.new_file(basename)
		template.copyto(file)

		# Same logic as in AttachFileDialog
		# TODO - incorporate in the insert_links function ?
		if file.isimage():
			ok = self.insert_image(file)
			if not ok: # image type not supported?
				logger.info('Could not insert image: %s', file)
				self.insert_links([file])
		else:
			self.insert_links([file])

		#~ open_file(self, file) # FIXME should this be optional ?

	@action(_('File _Templates...')) # T: Menu item in "Insert > New File Attachment" submenu
	def open_file_templates_folder(self):
		'''Menu action to open the templates folder'''
		folder = self.preferences['file_templates_folder']
		if isinstance(folder, str):
			folder = LocalFolder(folder)
		open_folder_prompt_create(self, folder)

	@action(_('_Clear Formatting'), accelerator='<Primary>9', menuhints='edit', verb_icon='edit-clear-all-symbolic') # T: Menu item
	def clear_formatting(self):
		'''Menu item to remove formatting from current (auto-)selection'''
		buffer = self.textview.get_buffer()
		buffer.clear_formatting_interactive(autoselect=self.preferences['autoselect'])

	@action(_('_Remove Heading'), '<Primary>7', menuhints='edit') # T: Menu item
	def clear_heading_format(self):
		'''Menu item to remove heading'''
		buffer = self.textview.get_buffer()
		buffer.clear_heading_format_interactive()

	def do_toggle_format_action_alt(self, active, action):
		self.do_toggle_format_action(action)

	def do_toggle_format_action(self, action):
		'''Handler that catches all actions to apply and/or toggle formats'''
		if isinstance(action, str):
			name = action
		else:
			name = action.get_name()
		logger.debug('Action: %s (toggle_format action)', name)
		if name.startswith('apply_format_'):
			style = name[13:]
		elif name.startswith('toggle_format_'):
			style = name[14:]
		else:
			assert False, "BUG: don't known this action"
		self.toggle_format(style)

	def toggle_format(self, name):
		'''Toggle the format for the current (auto-)selection or new
		insertions at the current cursor position

		When the cursor is at the begin or in the middle of a word and there is
		no selection, the word is selected automatically to toggle the format.
		For headings and other line based formats auto-selects the whole line.

		This is the handler for all the format actions.

		@param name: the format style name (e.g. "h1", "strong" etc.)
		'''
		buffer = self.textview.get_buffer()
		buffer.toggle_format_tag_by_name_interactive(name, autoselect=self.preferences['autoselect'])
		
	@action(_('Move Selected Text...')) # T: Menu item
	def move_text(self):
		buffer = self.textview.get_buffer()
		MoveTextDialog(self, self.notebook, self.page, buffer, self.navigation).run()

	@action(_('_Find...'), '<Primary>F', alt_accelerator='<Primary>F3') # T: Menu item
	def show_find(self, string=None, flags=0, highlight=False):
		'''Show the L{FindBar} widget

		@param string: the text to find
		@param flags: options for find behavior, see L{TextFinder.find()}
		@param highlight: if C{True} highlight the results
		'''
		self.find_bar.show()
		if string:
			self.find_bar.find(string, flags, highlight)
		self.find_bar.grab_focus()

	def hide_find(self):
		'''Hide the L{FindBar} widget'''
		self.find_bar.hide()
		self.textview.grab_focus()

	@action(_('Find Ne_xt'), accelerator='<Primary>G', alt_accelerator='F3') # T: Menu item
	def find_next(self):
		'''Menu action to skip to next match'''
		if not self.find_bar.get_visible():
			self.find_bar.show() # Show will already trigger find on next occurence
		else:
			self.find_bar.find_next()

	@action(_('Find Pre_vious'), accelerator='<Primary><shift>G', alt_accelerator='<shift>F3') # T: Menu item
	def find_previous(self):
		'''Menu action to go back to previous match'''
		self.find_bar.show()
		self.find_bar.find_previous()

	@action(_('_Replace...'), '<Primary>H', menuhints='edit') # T: Menu item
	def show_find_and_replace(self):
		'''Menu action to show the L{FindAndReplaceDialog}'''
		dialog = FindAndReplaceDialog.unique(self, self, self.textview)
		# TODO copy settings from find bar if "pop-out" action ?
		dialog.present()

	@action(_('Word Count...')) # T: Menu item
	def show_word_count(self):
		'''Menu action to show the L{WordCountDialog}'''
		WordCountDialog(self).run()

	@action(_('_Zoom In'), '<Primary>plus', alt_accelerator='<Primary>equal') # T: Menu item
	def zoom_in(self):
		'''Menu action to increase the font size'''
		self._zoom_increase_decrease_font_size(+1)

	@action(_('Zoom _Out'), '<Primary>minus') # T: Menu item
	def zoom_out(self):
		'''Menu action to decrease the font size'''
		self._zoom_increase_decrease_font_size(-1)

	def _zoom_increase_decrease_font_size(self, plus_or_minus):
		style = self.text_style
		if self.text_style['TextView']['font']:
			font = Pango.FontDescription(self.text_style['TextView']['font'])
		else:
			logger.debug('Switching to custom font implicitly because of zoom action')
			style = self.textview.get_style_context()
			font = style.get_property(Gtk.STYLE_PROPERTY_FONT, Gtk.StateFlags.NORMAL)

		font_size = font.get_size()
		if font_size <= 1 * 1024 and plus_or_minus < 0:
			return
		else:
			font_size_new = font_size + plus_or_minus * 1024
			font.set_size(font_size_new)
		try:
			self.text_style['TextView']['font'] = font.to_string()
		except UnicodeDecodeError:
			logger.exception('FIXME')
		self.textview.modify_font(font)

		self.text_style.write()

	@action(_('_Normal Size'), '<Primary>0') # T: Menu item to reset zoom
	def zoom_reset(self):
		'''Menu action to reset the font size'''
		if not self.text_style['TextView']['font']:
			return

		widget = TextView({}) # Get new widget
		style = widget.get_style_context()
		default_font = style.get_property(Gtk.STYLE_PROPERTY_FONT, Gtk.StateFlags.NORMAL)

		font = Pango.FontDescription(self.text_style['TextView']['font'])
		font.set_size(default_font.get_size())

		if font.equal(default_font):
			self.text_style['TextView']['font'] = None
			self.textview.modify_font(None)
		else:
			self.text_style['TextView']['font'] = font.to_string()
			self.textview.modify_font(font)

		self.text_style.write()

