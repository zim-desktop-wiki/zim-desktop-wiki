# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the Gtk user interface for zim.
The main widgets and dialogs are separated out in sub-modules.
Included here are the main class for the zim GUI L{GtkInterface}, which
contains most action handlers and the main window class L{MainWindow},
as well as a number of dialogs.

If you want to extend the user interface, also see L{zim.gui.widgets}
for common base classes for widgets and dialogs.
'''

from __future__ import with_statement

import os
import signal
import re
import logging
import gobject
import gtk
import threading
import webbrowser


from zim.main import get_zim_application
from zim.fs import File, Dir, normalize_win32_share
from zim.errors import Error, TrashNotSupportedError, TrashCancelledError
from zim.environ import environ
from zim.signals import DelayedCallback, SignalHandler
from zim.notebook import Notebook, NotebookInfo, Path, Page, build_notebook
from zim.stores import encode_filename
from zim.index import LINK_DIR_BACKWARD
from zim.config import data_file, data_dirs, ConfigDict, value_is_coord, ConfigManager
from zim.plugins import PluginManager
from zim.parsing import url_encode, url_decode, URL_ENCODE_DATA, is_win32_share_re, is_url_re, is_uri_re
from zim.history import History, HistoryPath
from zim.templates import list_templates, get_template
from zim.gui.pathbar import NamespacePathBar, RecentPathBar, RecentChangesPathBar, HistoryPathBar
from zim.gui.pageindex import PageIndex
from zim.gui.pageview import PageView
from zim.gui.widgets import ui_environment, gtk_window_set_default_icon, \
	Button, MenuButton, \
	Window, Dialog, \
	ErrorDialog, QuestionDialog, FileDialog, ProgressBarDialog, MessageDialog, \
	PromptExistingFileDialog, \
	ScrolledTextView
from zim.gui.clipboard import Clipboard
from zim.gui.applications import ApplicationManager, CustomToolManager, AddApplicationDialog


logger = logging.getLogger('zim.gui')


if gtk.gtk_version >= (2, 10):
	gtk.link_button_set_uri_hook(lambda o, url: webbrowser.open(url))


#: Menu actions
ui_actions = (
	('file_menu', None, _('_File')), # T: Menu title
	('edit_menu', None, _('_Edit')), # T: Menu title
	('view_menu', None, _('_View')), # T: Menu title
	('insert_menu', None, _('_Insert')), # T: Menu title
	('search_menu', None, _('_Search')), # T: Menu title
	('format_menu', None, _('For_mat')), # T: Menu title
	('tools_menu', None, _('_Tools')), # T: Menu title
	('go_menu', None, _('_Go')), # T: Menu title
	('help_menu', None, _('_Help')), # T: Menu title
	('pathbar_menu', None, _('P_athbar')), # T: Menu title
	('toolbar_menu', None, _('_Toolbar')), # T: Menu title

	# name, stock id, label, accelerator, tooltip, readonly
	('new_page',  'gtk-new', _('_New Page...'), '<ctrl>N', '', False), # T: Menu item
	('new_sub_page',  'gtk-new', _('New S_ub Page...'), '<shift><ctrl>N', '', False), # T: Menu item
	('open_notebook', 'gtk-open', _('_Open Another Notebook...'), '<ctrl>O', '', True), # T: Menu item
	('open_new_window', None, _('Open in New _Window'), '', '', True), # T: Menu item
	('import_page', None, _('_Import Page...'), '', '', False), # T: Menu item
	('save_page', 'gtk-save', _('_Save'), '<ctrl>S', '', False), # T: Menu item
	('save_copy', None, _('Save A _Copy...'), '', '', True), # T: Menu item
	('show_export',  None, _('E_xport...'), '', '', True), # T: Menu item
	('email_page', None, _('_Send To...'), '', '', True), # T: Menu item
	('move_page', None, _('_Move Page...'), '', '', False), # T: Menu item
	('rename_page', None, _('_Rename Page...'), 'F2', '', False), # T: Menu item
	('delete_page', None, _('_Delete Page'), '', '', False), # T: Menu item
	('show_properties',  'gtk-properties', _('Proper_ties'), '', '', True), # T: Menu item
	('close',  'gtk-close', _('_Close'), '<ctrl>W', '', True), # T: Menu item
	('quit',  'gtk-quit', _('_Quit'), '<ctrl>Q', '', True), # T: Menu item
	('show_search',  'gtk-find', _('_Search...'), '<shift><ctrl>F', '', True), # T: Menu item
	('show_search_backlinks', None, _('Search _Backlinks...'), '', '', True), # T: Menu item
	('show_recent_changes', None, _('Recent Changes...'), '', '', True), # T: Menu item
	('copy_location', None, _('Copy _Location'), '<shift><ctrl>L', '', True), # T: Menu item
	('show_templateeditor',  None, _('_Templates'), '', '', True), # T: Menu item
	('show_preferences',  'gtk-preferences', _('Pr_eferences'), '', '', True), # T: Menu item
	('reload_page',  'gtk-refresh', _('_Reload'), '<ctrl>R', '', True), # T: Menu item
	('open_attachments_folder', 'gtk-open', _('Open Attachments _Folder'), '', '', True), # T: Menu item
	('open_notebook_folder', 'gtk-open', _('Open _Notebook Folder'), '', '', True), # T: Menu item
	('open_document_root', 'gtk-open', _('Open _Document Root'), '', '', True), # T: Menu item
	('open_document_folder', 'gtk-open', _('Open _Document Folder'), '', '', True), # T: Menu item
	('attach_file', 'zim-attachment', _('Attach _File'), '', _('Attach external file'), False), # T: Menu item
	('edit_page_source', 'gtk-edit', _('Edit _Source'), '', '', False), # T: Menu item
	('show_server_gui', None, _('Start _Web Server'), '', '', True), # T: Menu item
	('reload_index', None, _('Update Index'), '', '', False), # T: Menu item
	('manage_custom_tools', 'gtk-preferences', _('Custom _Tools'), '', '', True), # T: Menu item
	('open_page_back', 'gtk-go-back', _('_Back'), '<alt>Left', _('Go page back'), True), # T: Menu item
	('open_page_forward', 'gtk-go-forward', _('_Forward'), '<alt>Right', _('Go page forward'), True), # T: Menu item
	('open_page_parent', 'gtk-go-up', _('_Parent'), '<alt>Up', _('Go to parent page'), True), # T: Menu item
	('open_page_child', 'gtk-go-down', _('_Child'), '<alt>Down', _('Go to child page'), True), # T: Menu item
	('open_page_previous', None, _('_Previous in index'), '<alt>Page_Up', _('Go to previous page'), True), # T: Menu item
	('open_page_next', None, _('_Next in index'), '<alt>Page_Down', _('Go to next page'), True), # T: Menu item
	('open_page_home', 'gtk-home', _('_Home'), '<alt>Home', _('Go home'), True), # T: Menu item
	('open_page', 'gtk-jump-to', _('_Jump To...'), '<ctrl>J', '', True), # T: Menu item
	('show_help', 'gtk-help', _('_Contents'), 'F1', '', True), # T: Menu item
	('show_help_faq', None, _('_FAQ'), '', '', True), # T: Menu item
	('show_help_keys', None, _('_Keybindings'), '', '', True), # T: Menu item
	('show_help_bugs', None, _('_Bugs'), '', '', True), # T: Menu item
	('show_about', 'gtk-about', _('_About'), '', '', True), # T: Menu item
)

if os.name == 'nt':
	# THe XF86 keys are mapped wrongly on windows, see bug lp:1277929
	ui_actions = ui_actions + (
		('open_page_back_alt1', None, '', '', '', True),
		('open_page_forward_alt1', None, '', '', '', True),
	)
else:
	ui_actions = ui_actions + (
		('open_page_back_alt1', None, '', 'XF86Back', '', True),
		('open_page_forward_alt1', None, '', 'XF86Forward', '', True),
	)

#: More menu actions
ui_actions_window = (
	# name, stock id, label, accelerator, tooltip, readonly
	('show_all_panes', None, _('_All Panes'), '<ctrl>F9', _('Show All Panes'), True), # T: Menu item
)

#: Menu actions that toggle between two states
ui_toggle_actions_window = (
	# name, stock id, label, accelerator, tooltip, initial state, readonly
	('toggle_toolbar', None, _('_Toolbar'),  '', '', True, True), # T: Menu item
	('toggle_statusbar', None, _('_Statusbar'), None, '', True, True), # T: Menu item
	('toggle_panes',  'gtk-index', _('_Side Panes'), 'F9', _('Show Side Panes'), True, True), # T: Menu item # FIXME review text
	('toggle_fullscreen',  'gtk-fullscreen', _('_Fullscreen'), 'F11', '', False, True), # T: Menu item
	('toggle_readonly', 'gtk-edit', _('Notebook _Editable'), '', _('Toggle notebook editable'), True, True), # T: menu item
)

if ui_environment['platform'] == 'maemo':
	ui_toggle_actions_window = (
		# name, stock id, label, accelerator, tooltip, initial state, readonly
		('toggle_toolbar', None, _('_Toolbar'),  '<ctrl>M', '', True, True), # T: Menu item
		('toggle_statusbar', None, _('_Statusbar'), None, '', True, True), # T: Menu item
		('toggle_panes',  'gtk-index', _('_Side Panes'), 'F9', _('Show Side Panes'), True, True), # T: Menu item # FIXME review text
		('toggle_fullscreen',  'gtk-fullscreen', _('_Fullscreen'), 'F11', '', False, True), # T: Menu item
		('toggle_readonly', 'gtk-edit', _('Notebook _Editable'), '', _('Toggle notebook editable'), True, True), # T: menu item
	)

#: Menu items with a radio checkbox
ui_pathbar_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_pathbar_none', None, _('_None'),  None, None, 0), # T: Menu item
	('set_pathbar_recent', None, _('_Recent pages'), None, None, 1), # T: Menu item
	('set_pathbar_recent_changed', None, _('Recently _Changed pages'), None, None, 1), # T: Menu item
	('set_pathbar_history', None, _('_History'),  None, None, 2), # T: Menu item
	('set_pathbar_path', None, _('_Page Hierarchy'), None, None, 3), # T: Menu item
)

PATHBAR_NONE = 'none' #: Constant for no pathbar
PATHBAR_RECENT = 'recent' #: Constant for the recent pages pathbar
PATHBAR_RECENT_CHANGED = 'recent_changed' #: Constant for the recent pages pathbar
PATHBAR_HISTORY = 'history' #: Constant for the history pathbar
PATHBAR_PATH = 'path' #: Constant for the namespace pathbar
PATHBAR_TYPES = (PATHBAR_NONE, PATHBAR_RECENT, PATHBAR_RECENT_CHANGED, PATHBAR_HISTORY, PATHBAR_PATH)

#: Menu items for the context menu of the toolbar
ui_toolbar_style_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_toolbar_icons_and_text', None, _('Icons _And Text'), None, None, 0), # T: Menu item
	('set_toolbar_icons_only', None, _('_Icons Only'), None, None, 1), # T: Menu item
	('set_toolbar_text_only', None, _('_Text Only'), None, None, 2), # T: Menu item
)

#: Menu items for the context menu of the toolbar
ui_toolbar_size_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_toolbar_icons_large', None, _('_Large Icons'), None, None, 0), # T: Menu item
	('set_toolbar_icons_small', None, _('_Small Icons'), None, None, 1), # T: Menu item
	('set_toolbar_icons_tiny', None, _('_Tiny Icons'), None, None, 2), # T: Menu item
)

TOOLBAR_ICONS_AND_TEXT = 'icons_and_text'
TOOLBAR_ICONS_ONLY = 'icons_only'
TOOLBAR_TEXT_ONLY = 'text_only'

TOOLBAR_ICONS_LARGE = 'large'
TOOLBAR_ICONS_SMALL = 'small'
TOOLBAR_ICONS_TINY = 'tiny'

#: Preferences for the user interface
ui_preferences = (
	# key, type, category, label, default
	('tearoff_menus', 'bool', 'Interface', _('Add \'tearoff\' strips to the menus'), False),
		# T: Option in the preferences dialog
	('toggle_on_ctrlspace', 'bool', 'Interface', _('Use <Ctrl><Space> to switch to the side pane'), False),
		# T: Option in the preferences dialog
		# default value is False because this is mapped to switch between
		# char sets in certain international key mappings
	('remove_links_on_delete', 'bool', 'Interface', _('Remove links when deleting pages'), True),
		# T: Option in the preferences dialog
	('always_use_last_cursor_pos', 'bool', 'Interface', _('Always use last cursor position when opening a page'), True),
		# T: Option in the preferences dialog
)

if ui_environment['platform'] == 'maemo':
	# Maemo specific settings
	ui_preferences = (
		# key, type, category, label, default
		('tearoff_menus', 'bool', None, None, False),
			# Maemo can't have tearoff_menus
		('toggle_on_ctrlspace', 'bool', None, None, True),
			# There is no ALT key on maemo devices
	)



# Load custom application icons as stock
def load_zim_stock_icons():
	'''Function to load zim custom stock icons for Gtk. Will load all
	icons found in the "pixmaps" folder with a stock name prefixed
	with "zim-", so "data/pixmaps/link.png" becomes the "zim-link"
	stock icon. Called directly when this module is loaded.
	'''
	factory = gtk.IconFactory()
	factory.add_default()
	for dir in data_dirs(('pixmaps')):
		for file in dir.list('*.png'):
			# not all installs have svg support, so only check png for now..
			name = 'zim-'+file[:-4] # e.g. checked-box.png -> zim-checked-box
			icon_theme = gtk.icon_theme_get_default()
			try:
			    pixbuf = icon_theme.load_icon(name, 24, 0)
			except:
			    pixbuf = gtk.gdk.pixbuf_new_from_file(str(dir+file))

			try:
			    set = gtk.IconSet(pixbuf)
			    factory.add(name, set)
			except Exception:
				logger.exception('Got exception while loading application icons')

load_zim_stock_icons()


def schedule_on_idle(function, args=()):
	'''Helper function to schedule stuff that can be done later, it will
	be triggered on the gtk "idle" signal.

	@param function: function to call
	@param args: positional arguments
	'''
	def callback():
		function(*args)
		return False # delete signal
	gobject.idle_add(callback)


class NoSuchFileError(Error):
	'''Exception for when a file or folder is not found that should
	exist.
	'''

	description = _('The file or folder you specified does not exist.\nPlease check if you the path is correct.')
		# T: Error description for "no such file or folder"

	def __init__(self, path):
		'''Constructor
		@param path: the L{File} or L{Dir} object
		'''
		self.msg = _('No such file or folder: %s') % path.path
			# T: Error message, %s will be the file path


class ApplicationLookupError(Error):
	'''Exception raised when an application was not found'''
	pass


class PageHasUnSavedChangesError(Error):
	'''Exception raised when page could not be saved'''

	msg = _('Page has un-saved changes')
		# T: Error description


class WindowManager(object):

	def __iter__(self):
		for window in gtk.window_list_toplevels():
			if isinstance(window, Window): # implies a zim object
				yield Window

	def present(self):
		assert False, 'TODO pick window to present'



class GtkInterface(gobject.GObject):
	'''Main class for the zim Gtk interface. This object wraps a single
	notebook and provides actions to manipulate and access this notebook.

	This class has quite some methods that are described as "menu
	actions". This means these methods directly implement the action
	that is triggered by a specific menu action. However they are also
	available for other classes to call them directly and are part of
	the public API.

	The GUI uses a few mechanisms for other classes to dynamically add
	elements. One is the use of the C{gtk.UIManager} class to populate
	the menubar and toolbar. This allows other parts of the application
	to define additional actions. See the methods L{add_actions()} and
	L{add_ui()} for wrappers around this functionality.
	A second mechanism is that for simple options other classes can
	register a preference to be shown in the PreferencesDialog. See
	the L{register_preferences()} method.

	B{NOTE:} the L{plugin<zim.plugins>} base class has it's own wrappers
	for these things. Plugin writers should look there first.

	@ivar preferences: L{ConfigSectionsDict} for global preferences, maps to
	the X{preferences.conf} config file.
	@ivar uistate: L{ConfigSectionsDict} for current state of the user interface,
	maps to the X{state.conf} config file per notebook.
	@ivar notebook: The L{Notebook} object
	@ivar page: The L{Page} object for the current page in the
	main window
	@ivar readonly: When C{True} the whole interface is read-only
	@ivar hideonclose: When C{True} the application will hide itself
	instead of closing when the main window is closed, typically used
	in combination with the background server process and the
	L{tray icon plugin<zim.plugins.trayicon>}
	@ivar mainwindow: the L{MainWindow} object
	@ivar history: the L{History} object
	@ivar uimanager: the C{gtk.UIManager} (see the methods
	L{add_actions()} and L{add_ui()} for wrappers)
	@ivar preferences_register: a L{ConfigDict} with preferences to show
	in the preferences dialog, see L{register_preferences()} to add
	to more preferences

	@signal: C{open-page (L{Page}, L{Path})}: Emitted when opening
	a page, the Path is given as the 2nd argument so the source of the
	path can be checked - in particular when a path is opened through a
	history function this will be a L{HistoryPath}
	@signal: C{close-page (L{Page}, final)}: Emitted before closing a
	page, typically just before a new page is opened and before closing
	the application. If 'C{final}' is C{True} we expect this to be the
	final page closure before quiting the application. This it is only
	a hint, so do not destroy any ui components when 'C{final}' is set,
	but it can be used to decide to do some actions async or not.
	@signal: C{read-only-changed ()}: Emitted when the ui changed from
	read-write to read-only or back
	@signal: C{quit ()}: Emitted when the application is about to quit
	@signal: C{start-index-update ()}: Emitted before running a index
	update
	@signal: C{end-index-update ()}: Emitted when an index update is
	finished
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-page': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
		'close-page': (gobject.SIGNAL_RUN_LAST, None, (object, bool)),
		'readonly-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		'quit': (gobject.SIGNAL_RUN_LAST, None, ()),
		'start-index-update': (gobject.SIGNAL_RUN_LAST, None, ()),
		'end-index-update': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, notebook, page=None, config=None,
		fullscreen=False, geometry=None):
		'''Constructor

		@param config: a C{ConfigManager} object
		@param notebook: a L{Notebook} object
		@param page: a L{Path} object
		@param fullscreen: if C{True} open fullscreen
		@param geometry: window geometry as string in format "C{WxH+X+Y}"
		'''
		gobject.GObject.__init__(self)

		if isinstance(notebook, basestring): # deal with IPC call
			info = NotebookInfo(notebook)
			notebook, x = build_notebook(info)
		elif not isinstance(notebook, Notebook):
			notebook, x = build_notebook(notebook)

		logger.debug('Opening notebook: %s', notebook)
		self.notebook = notebook

		self.config = config or ConfigManager(profile=notebook.profile)
		self.preferences = self.config.get_config_dict('<profile>/preferences.conf') ### preferences attrib should just be one section
		self.preferences['General'].setdefault('plugins',
			['calendar', 'insertsymbol', 'printtobrowser', 'versioncontrol'])

		self.plugins = PluginManager(self.config)
		self.plugins.extend(notebook.index)
		self.plugins.extend(notebook)

		self.preferences_register = ConfigDict()
		self.page = None
		self._path_context = None
		self.history = None
		self.readonly = False
		self.hideonclose = False
		self.url_handlers = {}

		self._autosave_thread = None

		logger.debug('Gtk version is %s' % str(gtk.gtk_version))
		logger.debug('Pygtk version is %s' % str(gtk.pygtk_version))

		gtk_window_set_default_icon()

		self.uimanager = gtk.UIManager()
		self.uimanager.add_ui_from_string('''
		<ui>
			<menubar name="menubar">
			</menubar>
			<toolbar name="toolbar">
			</toolbar>
		</ui>
		''')

		self.register_preferences('GtkInterface', ui_preferences)

		# Hidden setting to force the gtk bell off. Otherwise it
		# can bell every time you reach the begin or end of the text
		# buffer. Especially specific gtk version on windows.
		# See bug lp:546920
		self.preferences['GtkInterface'].setdefault('gtk_bell', False)
		if not self.preferences['GtkInterface']['gtk_bell']:
			gtk.rc_parse_string('gtk-error-bell = 0')

		# Init UI
		self.mainwindow = MainWindow(self, self.preferences, fullscreen, geometry)

		self.add_actions(ui_actions, self)
		self.add_actions(ui_actions_window, self.mainwindow)
		self.add_toggle_actions(ui_toggle_actions_window, self.mainwindow)
		self.add_radio_actions(ui_pathbar_radio_actions,
								self.mainwindow, 'do_set_pathbar')
		self.add_radio_actions(ui_toolbar_style_radio_actions,
								self.mainwindow, 'do_set_toolbar_style')
		self.add_radio_actions(ui_toolbar_size_radio_actions,
								self.mainwindow, 'do_set_toolbar_size')

		if ui_environment['platform'] == 'maemo':
			# Customized menubar for maemo, specific for maemo version
			fname = 'menubar-' + ui_environment['maemo_version'] + '.xml'
		else:
			fname = 'menubar.xml'
		self.add_ui(data_file(fname).read(), self)

		if ui_environment['platform'] == 'maemo':
			# Hardware fullscreen key is F6 in N8xx devices
			self.mainwindow.connect('key-press-event',
				lambda o, event: event.keyval == gtk.keysyms.F6
					and self.mainwindow.toggle_fullscreen())

		self._custom_tool_ui_id = None
		self._custom_tool_actiongroup = None
		self._custom_tool_iconfactory = None
		self.load_custom_tools()

		self.preferences.connect('changed', self.do_preferences_changed)
		self.do_preferences_changed()

		self._init_notebook(self.notebook)
		if page and isinstance(page, basestring): # IPC call
			page = self.notebook.resolve_path(page)

		self._first_page = page # XXX HACK - if we call open_page here, plugins are not yet initialized

	def _init_notebook(self, notebook):
		if notebook.cache_dir:
			# may not exist during tests
			from zim.config import INIConfigFile
			self.uistate = INIConfigFile(
				notebook.cache_dir.file('state.conf') )
		else:
			from zim.config import SectionedConfigDict
			self.uistate = SectionedConfigDict()

		def move_away(o, path):
			if path == self.page or self.page.ischild(path):
				self.open_page_back() \
				or self.open_page_parent \
				or self.open_page_home

		def follow(o, path, newpath, update_links):
			if self.page == path:
				self.open_page(newpath)
			elif self.page.ischild(path):
				newpath = newpath + self.page.relname(path)
				newpath = Path(newpath.name) # IndexPath -> Path
				self.open_page(newpath)

		def save_page(o, p, *a):
			page = self.mainwindow.pageview.get_page()
			if p == page and page.modified:
				self.save_page(page)

		self.history = History(notebook, self.uistate)
		self.on_notebook_properties_changed(notebook)
		notebook.connect('properties-changed', self.on_notebook_properties_changed)
		notebook.connect('delete-page', save_page) # before action
		notebook.connect('deleted-page', move_away) # after action
		notebook.connect('move-page', save_page) # before action
		notebook.connect('moved-page', follow) # after action

		def new_child(index, indexpath):
			if self.page and indexpath.ischild(self.page):
				child = self.actiongroup.get_action('open_page_child')
				child.set_sensitive(True)

		def child_deleted(index, indexpath):
			if self.page and indexpath.ischild(self.page):
				ourpath = index.lookup_path(self.page)
				child = self.actiongroup.get_action('open_page_child')
				child.set_sensitive(ourpath.haschildren)

		notebook.index.connect('page-inserted', new_child)
		notebook.index.connect('page-deleted', child_deleted)

		# Start a lightweight background check of the index
		self.notebook.index.update_async()

		self.set_readonly(notebook.readonly)

	def on_notebook_properties_changed(self, notebook):
		self.config.set_profile(notebook.profile)

		has_doc_root = not notebook.document_root is None
		for action in ('open_document_root', 'open_document_folder'):
			action = self.actiongroup.get_action(action)
			action.set_sensitive(has_doc_root)

	def main(self):
		'''Wrapper for C{gtk.main()}, runs main loop of the application.
		Does not return until program has ended. Also takes care of
		a number of initialization actions, like prompting the
		L{NotebookDialog} if needed and will show the main window.
		'''
		assert self.notebook is not None

		if self.notebook.dir:
			os.chdir(self.notebook.dir.path)
			environ['PWD'] = self.notebook.dir.path

		if self._first_page is None:
			self._first_page = self.history.get_current()

		# We schedule the autosave on idle to try to make it impact
		# the performance of the application less. Of course using the
		# async interface also helps, but we need to account for cases
		# where asynchronous actions are not supported.

		def schedule_autosave():
			schedule_on_idle(self.do_autosave)
			return True # keep ticking

		# older gobject version doesn't know about seconds
		self.preferences['GtkInterface'].setdefault('autosave_timeout', 10)
		timeout = self.preferences['GtkInterface']['autosave_timeout'] * 1000 # s -> ms
		self._autosave_timer = gobject.timeout_add(timeout, schedule_autosave)


		# Check notebook
		self.check_notebook_needs_upgrade()

		# Update menus etc.
		self.uimanager.ensure_update()
			# Prevent flashing when the toolbar is after showing the window
			# and do this before connecting signal below for accelmap.
			# For maemo ensure all items are initialized before moving
			# them to the hildon menu

		## HACK - should be in MainWindow, but needs to go after ensure_update()
		space = gtk.SeparatorToolItem()
		space.set_draw(False)
		space.set_expand(True)
		self.mainwindow.toolbar.insert(space, -1)

		from zim.gui.widgets import InputEntry
		entry = InputEntry(placeholder_text=_('Search'))
		if gtk.gtk_version >= (2, 16):
			entry.set_icon_from_stock(gtk.ENTRY_ICON_SECONDARY, gtk.STOCK_FIND)
			entry.set_icon_activatable(gtk.ENTRY_ICON_SECONDARY, True)
			entry.set_icon_tooltip_text(gtk.ENTRY_ICON_SECONDARY, _('Search Pages...'))
				# T: label in search entry
		inline_search = lambda e, *a: self.show_search(query=e.get_text() or None)
		entry.connect('activate', inline_search)
		entry.connect('icon-release', inline_search)
		entry.show()
		item = gtk.ToolItem()
		item.add(entry)
		self.mainwindow.toolbar.insert(item, -1)
		##

		if ui_environment['platform'] == 'maemo':
			# Move the menu to the hildon menu
			# This is save for later updates of the menus (e.g. by plugins)
			# as long as the toplevel menus are not changed
			menu = gtk.Menu()
			for child in self.mainwindow.menubar.get_children():
				child.reparent(menu)
			self.mainwindow.set_menu(menu)
			self.mainwindow.menubar.hide()

			# Localize the fullscreen button in the toolbar
			for i in range(self.mainwindow.toolbar.get_n_items()):
				self.fsbutton = None
				toolitem = self.mainwindow.toolbar.get_nth_item(i)
				if isinstance(toolitem, gtk.ToolButton):
					if toolitem.get_stock_id() == 'gtk-fullscreen':
						self.fsbutton = toolitem
						self.fsbutton.tap_and_hold_setup(menu) # attach app menu to fullscreen button for N900
						break

		accelmap = self.config.get_config_file('accelmap').file
		logger.debug('Accelmap: %s', accelmap.path)
		if accelmap.exists():
			gtk.accel_map_load(accelmap.path)

		def on_accel_map_changed(o, path, key, mod):
			logger.info('Accelerator changed for %s', path)
			gtk.accel_map_save(accelmap.path)

		gtk.accel_map_get().connect('changed', on_accel_map_changed)


		def handle_sigterm(signal, frame):
			logger.info('Got SIGTERM, quit')
			self.close_page()
			self._quit()

		signal.signal(signal.SIGTERM, handle_sigterm)

		# And here we go!
		self.mainwindow.show_all()

		# HACK: Delay opening first page till after show_all() -- else plugins are not initialized
		#       FIXME need to do extension & initialization of uistate earlier
		if self._first_page:
			self.open_page(self._first_page)
			del self._first_page
		else:
			self.open_page_home()

		self.mainwindow.pageview.grab_focus()
		gtk.main()

	def check_notebook_needs_upgrade(self):
		'''Check whether the notebook needs to be upgraded and prompt
		the user to do so if this is the case.

		Interactive wrapper for
		L{Notebook.upgrade_notebook()<zim.notebook.Notebook.upgrade_notebook()>}.
		'''
		if not self.notebook.needs_upgrade:
			return

		ok = QuestionDialog(None, (
			_('Upgrade Notebook?'), # T: Short question for question prompt
			_('This notebook was created by an older of version of zim.\n'
			  'Do you want to upgrade it to the latest version now?\n\n'
			  'Upgrading will take some time and may make various changes\n'
			  'to the notebook. In general it is a good idea to make a\n'
			  'backup before doing this.\n\n'
			  'If you choose not to upgrade now, some features\n'
			  'may not work as expected') # T: Explanation for question to upgrade notebook
		) ).run()

		if not ok:
			return

		with ProgressBarDialog(self, _('Upgrading notebook')) as dialog: # T: Title of progressbar dialog
			self.notebook.index.ensure_update(callback=lambda p: dialog.pulse(p.name))
			dialog.set_total(self.notebook.index.n_list_all_pages())
			self.notebook.upgrade_notebook(callback=lambda p: dialog.pulse(p.name))

	def present(self, page=None, fullscreen=None, geometry=None):
		'''Present the mainwindow. Typically used to bring back a
		the application after it was hidden. Also used for remote
		calls.

		@param page: a L{Path} object or page path as string
		@param fullscreen: if C{True} the window is shown fullscreen,
		if C{None} the previous state is restored
		@param geometry: the window geometry as string in format
		"C{WxH+X+Y}", if C{None} the previous state is restored
		'''
		self.mainwindow.present()
		if page:
			if isinstance(page, basestring):
				page = Path(page)
			self.open_page(page)

		if geometry:
			self.mainwindow.parse_geometry(geometry)
		elif fullscreen:
			self.mainwindow.toggle_fullscreen(show=True)

	def toggle_present(self):
		'''Present main window if it is not on top, but hide if it is.
		Used by the L{trayicon plugin<zim.plugins.trayicon>} to toggle
		visibility of the window.
		'''
		if self.mainwindow.is_active():
			self.mainwindow.hide()
		else:
			self.mainwindow.present()

	def hide(self):
		'''Hide the main window. Note that this is not the same as
		minimize, when minimized there is still an icon in the task
		bar, if hidden there is no visible trace of the application and
		it can not be accessed by the user anymore until L{present()}
		has been called.
		'''
		self.mainwindow.hide()

	def close(self):
		'''Menu action for close. Will hide when L{hideonclose} is set,
		calls L{quit()} otherwise.
		'''
		if self.hideonclose:
			self.hide()
		else:
			self.quit()

	def quit(self):
		'''Menu action for quit.
		@emits: quit
		'''
		if not self.close_page(self.page, final=True):
			# Do not quit if page not saved
			return False

		self.notebook.index.stop_updating() # XXX - avoid long wait
		self.mainwindow.hide() # look more responsive
		while gtk.events_pending():
			gtk.main_iteration(block=False)

		self._quit()

	def _quit(self):
		self.emit('quit')

		if gtk.main_level() > 0:
			gtk.main_quit()

		return True

	def add_actions(self, actions, handler, methodname=None):
		'''Add extra menu actions to the interface which can be used
		in the menubar and toolbar.

		Wrapper for C{gtk.ActionGroup.add_actions()}. Adding actions
		will not show them in the interface immediately. To achieve
		that you first need to load some layout definition using
		L{add_ui()}.

		This method assumes the actions are implemented by a "handler"
		object. The actions are store in the C{gtk.ActionGroup} in
		the "actiongroup" attribute of this object. This attribute
		is created and attached to the uimanager if it does not yet
		exist.

		@param actions: a list of action definitions. Actions are
		defined as a 6-tuple of :
		  - the name of the action
		  - a gtk stock id for the icon, or C{None}
		  - the label
		  - the accelerator key binding
		  - a tooltip message
		  - a boolean, if C{True} this action is can be used in a
		    read-only interface

		Actions that define (sub-)menus are a special case, they are
		defined as a 3-tuple of the name, stock id and a lable. In this
		case the name must end with "_menu"

		See C{gtk.ActionGroup} documentation for more details.

		@param handler: object that implements these actions. Each
		action is mapped to an object method of the same name.
		@param methodname: name for a method on the handler object which
		will handle all actions. This overrules the default mapping of
		actions by action name. Used to implement groups of actions
		with a single handler method.
		'''
		assert isinstance(actions[0], tuple), 'BUG: actions should be list of tupels'
		group = self.init_actiongroup(handler)
		group.add_actions([a[0:5] for a in actions])
		self._connect_actions(actions, group, handler)

	def add_toggle_actions(self, actions, handler):
		'''Add extra menu actions to the interface which can be used
		in the menubar and toolbar.

		Wrapper for C{gtk.ActionGroup.add_toggle_actions()}.

		Differs from L{add_actions()} in the way actions are mapped to
		object methods, the name is prefixed with "do_". The reason for
		this is that we need some code to keep the state of toolbar
		and menubar widgets in sync with the internal state, while at
		the same time we want to be able to call the standard method
		name from other interface. So e.g. an action "foo" will trigger
		a method "C{do_foo()}" which should implement the logic. This
		allows also to have a public method "C{foo()}" which calls
		"C{action.activate()}" whic in turn triggers "C{do_foo()}"
		again. See L{zim.plugins.PluginClass.toggle_action()} for a
		convenience method to help implementing this.

		@param actions: list of action definitions. Actions are defined
		defined as a 7-tuple of :
		  - the name of the action
		  - a gtk stock id for the icon, or C{None}
		  - the label
		  - the accelerator key binding
		  - a tooltip message
		  - initial state C{True} or C{False}
		  - a boolean, if C{True} this action is can be used in a
		    read-only interface

		See C{gtk.ActionGroup} documentation for more details.

		@param handler: object that implements these actions.
		'''
		assert isinstance(actions[0], tuple), 'BUG: actions should be list of tupels'
		group = self.init_actiongroup(handler)
		group.add_toggle_actions([a[0:5]+(None,)+(a[5],) for a in actions])
			# insert 'None' for callback
		self._connect_actions(actions, group, handler, is_toggle=True)

	def add_radio_actions(self, actions, handler, methodname):
		'''Add extra menu actions to the interface which can be used
		in the menubar and toolbar.

		Wrapper for C{gtk.ActionGroup.add_radio_actions()}, defining
		a single group of radio actions. Of this group only one item
		can be active at the time.

		@param actions: a list of action definitions. Actions are
		defined as a 6-tuple of :
		  - the name of the action
		  - a gtk stock id for the icon, or C{None}
		  - the label
		  - the accelerator key binding
		  - a tooltip message
		  - the value to set on the radio

		See C{gtk.ActionGroup} documentation for more details.

		@param handler: object that implements these actions
		@param methodname: name for a method on the handler object which
		will handle all actions, this is mandatory for radio actions,
		they always have a single handler for the whole group. The
		handler gets the name of the selected radio as the first
		argument.
		'''
		# A bit different from the other two methods since radioactions
		# come in mutual exclusive groups. Only need to connect to one
		# action to get signals from whole group. But need to pass on
		# the name of the active action
		assert isinstance(actions[0], tuple), 'BUG: actions should be list of tuples'
		assert hasattr(handler, methodname), 'No such method %s' % methodname
		group = self.init_actiongroup(handler)
		group.add_radio_actions(actions)
		method = getattr(handler, methodname)
		action = group.get_action(actions[0][0])
		action.connect('changed', self._radio_action_handler, method)

	def init_actiongroup(self, handler):
		'''Initializes the actiongroup for a handler object if it does
		not already exist. The actiongroup is set in the "actiongroup"
		attribute of the object and inserted in the ui manager.
		@param handler: the handler object
		@returns: the actiongroup object
		'''
		if not hasattr(handler, 'actiongroup') or handler.actiongroup is None:
			name = handler.__class__.__name__
			handler.actiongroup = gtk.ActionGroup(name)
			self.uimanager.insert_action_group(handler.actiongroup, 0)
		return handler.actiongroup

	def remove_actiongroup(self, handler):
		'''Remove the actiongroup for a handler object and remove all
		actions from the ui manager.
		@param handler: the handler object
		'''
		if hasattr(handler, 'actiongroup') and handler.actiongroup:
			self.uimanager.remove_action_group(handler.actiongroup)
			handler.actiongroup = None

	def _action_handler(self, action, method, *arg):
		name = action.get_name()
		logger.debug('Action: %s', name)
		try:
			method(*arg)
		except Exception, error:
			ErrorDialog(self.mainwindow, error).run()
			# error dialog also does logging automatically

	def _radio_action_handler(self, object, action, method):
		# radio action object is not active radio action
		self._action_handler(action, method, action.get_name())

	def _connect_actions(self, actions, group, handler, is_toggle=False):
		for name, readonly in [(a[0], a[-1]) for a in actions if not a[0].endswith('_menu')]:
			action = group.get_action(name)
			action.zim_readonly = readonly
			if re.search('_alt\d$', name): # alternative key bindings
				name, _ = name.rsplit('_', 1)

			if is_toggle:
				name = 'do_' + name

			assert hasattr(handler, name), 'No method defined for action %s' % name
			method = getattr(handler, name)
			action.connect('activate', self._action_handler, method)
			if self.readonly and not action.zim_readonly:
				action.set_sensitive(False)

	def add_ui(self, xml, handler):
		'''Add a definition of the layout of the menubar and/or toolbar
		adding new menu items.

		Wrapper for C{gtk.UIManager.add_ui_from_string()}, see
		documentation there for more details on XML spec.

		@param xml: layout definition as string in XML format
		@param handler: handler object, this object is used to keep
		track of ui ID's so L{remove_ui()} can remove all ui elements
		of this handler at once
		@returns: the ui ID
		'''
		id = self.uimanager.add_ui_from_string(xml)
		if hasattr(handler, '_ui_merge_ids') and handler._ui_merge_ids:
			handler._ui_merge_ids += (id,)
		else:
			handler._ui_merge_ids = (id,)
		return id

	def remove_ui(self, handler, id=None):
		'''Remove the ui definition(s) for a specific handler.

		@param handler: handler object
		@param id: if a ui ID is given, only that part is removed, else
		all ui definitions for this handler object are removed
		'''
		if id:
			self.uimanager.remove_ui(id)
			if hasattr(handler, '_ui_merge_ids'):
				handler._ui_merge_ids = \
					filter(lambda i: i != id, handler._ui_merge_ids)
		else:
			if hasattr(handler, '_ui_merge_ids'):
				for id in handler._ui_merge_ids:
					self.uimanager.remove_ui(id)
				handler._ui_merge_ids = None

	def populate_popup(self, name, menu, path_context=None):
		'''Populate a popup menu from a popup defined in the uimanager

		This effectively duplicated the menu items from a given popup
		as defined in the uimanager to a given menu. The reason to do
		this is to include a menu that is extendable for plugins etc.
		into an existing popup menu. (Note that changes to the menu
		as returned by uimanager.get_widget() are global.)

		@param name: the uimanager popup name, e.g. "toolbar_popup" or
		"page_popup"
		@param menu: a gtk.Menu to be populated with the menu items
		@param path_context: a L{Path} object in case this menu is about a page,
		will be used as the context for the various actions

		@raises ValueError: when 'name' does not exist
		'''
		# ... so we have to do our own XML parsing here :(
		# but take advantage of nicely formatted line-based output ...
		xml = self.uimanager.get_ui()
		xml = [l.strip() for l in xml.splitlines()]

		# Get slice of XML
		start, end = None, None
		for i, line in enumerate(xml):
			if start is None:
				if line.startswith('<popup name="%s">' % name):
					start = i
			else:
				if line.startswith('</popup>'):
					end = i
					break

		if start is None or end is None:
			raise ValueError, 'No such popup in uimanager: %s' % name

		# Wrapper to set path context
		def wrapper(menuitem, action):
			self._path_context = path_context
			try:
				action.activate()
			except:
				self._path_context = None
				raise
			else:
				self._path_context = None

		# Parse items and add to menu
		seen_item = False # use to track empty parts
		for line in xml[start+1:end]:
			if line.startswith('<separator'):
				if seen_item:
					item = gtk.SeparatorMenuItem()
					menu.append(item)
				seen_item = False
			elif line.startswith('<menuitem'):
				pre, post = line.split('action="', 1)
				actionname, post = post.split('"', 1)
				for group in self.uimanager.get_action_groups():
					action = group.get_action(actionname)
					if action:
						item = action.create_menu_item()

						# Insert our wrapper to set context path in
						# between the menu item and the action
						# bit of a hack...
						action.disconnect_proxy(item)
						item.connect('activate', wrapper, action)

						# don't show accels in popups (based on gtk/gtkuimanager.c)
						child = item.get_child()
						if isinstance(child, gtk.AccelLabel):
							child.set_property('accel-closure', None)

						break
				else:
					raise AssertionError, 'BUG: could not find action for "%s"' % actionname

				menu.append(item)
				seen_item = True
			elif line.startswith('<placeholder') \
			or line.startswith('</placeholder'):
				pass
			else:
				raise AssertionError, 'BUG: Could not parse: ' + line

	def set_readonly(self, readonly):
		'''Set the read-only state of the interface

		@emits: readonly-changed
		'''
		if not self.readonly and self.page:
			# Save any modification now - will not be allowed after switch
			self.assert_save_page_if_modified()

		for group in self.uimanager.get_action_groups():
			for action in group.list_actions():
				if hasattr(action, 'zim_readonly') \
				and not action.zim_readonly:
					action.set_sensitive(not readonly)

		self.readonly = readonly
		self.emit('readonly-changed')

	def register_preferences(self, section, preferences):
		'''Registers user preferences for the preferences dialog

		The section together with the name specifies where to find this
		preference in L{preferences}. E.g. a section "GtkInterface" and
		a name "foo" will result in a value to be stored in
		C{ui.preferences['GtkInterface']['foo']}. All preferences are
		initialized after being registered here, so you do not need
		to check their existing afterwards.

		@param section: the section of the config file to locate these
		plugins, e.g. "GtkInterface" (most classes use their class name
		here)

		@param preferences: a list of preferences definitions. Each
		preference is defined by a 5-tuple or 6-tuple consisting of:
		  - the name of the preference
		  - an option type (e.g. "bool", "int", "string" etc.)
		  - the tab in the dialog where the option will be shown
		    (e.g. "Interface", "Editing")
		  - a label to show in the dialog
		  - a default value
		  - optional a check value

		See L{zim.gui.widgets.InputForm.add_inputs()} for valid values of
		the option type.

 		See L{zim.config.ConfigDict.setdefault())} for usage of the
 		optional check value.

		@todo: unify the check for setdefault() and the option type to
		check the value has the proper type
		'''
		register = self.preferences_register
		for p in preferences:
			if len(p) == 5:
				key, type, category, label, default = p
				self.preferences[section].setdefault(key, default)
				r = (section, key, type, label)
			else:
				key, type, category, label, default, check = p
				self.preferences[section].setdefault(key, default, check=check)
				r = (section, key, type, label, check)

			# Preferences with None category won't be shown in the preferences dialog
			if category:
				register.setdefault(category, [])
				register[category].append(r)


	def register_new_window(self, window):
		'''Register a new window for the application.
		Called by windows and dialogs to register themselves. Used e.g.
		by plugins that want to add some widget to specific windows.
		'''
		#~ print 'WINDOW:', window
		self.plugins.extend(window)

		# HACK
		if hasattr(window, 'pageview'):
			self.plugins.extend(window.pageview)

	def register_url_handler(self, scheme, function):
		'''Register a handler for a particular URL scheme
		Intended for plugins that want to add a handler for a specific
		URL scheme, or introduce a new URL scheme.

		Typically this should B{not} be used for integrating external
		applications that could be added as a preference.

		@param scheme: the url scheme as string
		@param function: a function to call for opening URLs for this
		scheme. The function should return boolean for succes.
		'''
		self.url_handlers[scheme] = function

	def unregister_url_handler(self, function):
		'''Un-register a handler for a particular URL scheme.
		@param function: a function registered with
		L{register_url_handler()}
		'''
		keys = [k for k in self.url_handlers if self.url_handlers[k] == function]
		for k in keys:
			self.url_handlers.pop(k)

	def _get_path_context(self):
		'''Get the current page path. Used to get the default page to
		act upon for actions. Either returns the current page or a page
		selected in the index pane, etc.
		@returns: a L{Path} object
		'''
		return self._path_context or self.page

	def open_notebook(self, notebook=None):
		'''Open a new notebook. If this is the first notebook the
		notebook is opened in this application instance. Otherwise we
		let another instance handle it.
		@param notebook: notebook location, if C{None} we will prompt
		the user with the L{NotebookDialog}
		@emits: open-notebook
		'''
		if notebook is None:
			# Handle menu item for 'open another notebook'
			# FIXME - this should be a "show_open_notebook" action or similar
			from zim.gui.notebookdialog import NotebookDialog
			NotebookDialog.unique(self, self, callback=self.open_notebook).show() # implicit recurs
		else:
			import zim.ipc

			# XXX notebook can be either object or string - fix this to always be an object
			pagename = None
			if isinstance(notebook, basestring):
				if notebook.startswith('zim+'):
					if '?' in notebook:
						uri, pagename = notebook.split('?', 1)
						uri = uri[4:]
					else:
						uri = notebook[4:]
				else:
					uri = File(notebook).uri
			elif hasattr(notebook, 'uri'):
				uri = notebook.uri
			else:
				raise AssertionError, 'Can not handle: %s' % notebook

			if self.notebook and self.notebook.uri == uri:
				self.present(page=pagename)
			elif zim.ipc.in_child_process():
				notebook = zim.ipc.ServerProxy().get_notebook(uri)
				notebook.present(page=pagename)
			else:
				if pagename:
					get_zim_application('--gui', uri, pagename).spawn()
				else:
					get_zim_application('--gui', uri).spawn()

	def open_page(self, path=None):
		'''Method to open a page in the mainwindow, and menu action for
		the "jump to" menu item.

		@param path: a L{path} for the page to open, if C{None} we
		prompt the user with the L{OpenPageDialog}. If C{path} is a
		L{HistoryPath} we assume that this call is the result of a
		history action and the page is not again added to the history.

		@emits: open-page
		'''
		assert self.notebook
		if path is None:
			# the dialog will call us in turn with an argument
			return OpenPageDialog(self).run()

		assert isinstance(path, Path)
		if isinstance(path, Page) and path.valid:
			page = path
		else:
			page = self.notebook.get_page(path)

		if self.page and id(self.page) == id(page):
			# Check ID to enable reload_page but catch all other
			# redundant calls.
			return
		elif self.page:
			if not self.close_page(self.page):
				raise AssertionError, 'Could not close page'
				# assert statement could be optimized away

		logger.info('Open page: %s (%s)', page, path)
		self.emit('open-page', page, path)

	def do_open_page(self, page, path):
		is_first_page = self.page is None
		self.page = page

		back = self.actiongroup.get_action('open_page_back')
		forward = self.actiongroup.get_action('open_page_forward')
		parent = self.actiongroup.get_action('open_page_parent')
		child = self.actiongroup.get_action('open_page_child')

		if isinstance(path, HistoryPath):
			historyrecord = path
			self.history.set_current(path)
			back.set_sensitive(not path.is_first)
			forward.set_sensitive(not path.is_last)
		else:
			self.history.append(path)
			historyrecord = self.history.get_current()
			back.set_sensitive(not is_first_page)
			forward.set_sensitive(False)

		parent.set_sensitive(len(page.namespace) > 0)

		indexpath = self.notebook.index.lookup_path(page)
		child.set_sensitive(indexpath.haschildren)
			# FIXME: Need index path here, page.haschildren is also True
			#        when the page just has a attachment folder

	def close_page(self, page=None, final=False):
		'''Close the page and try to save any changes in the page.

		@param page: the page to close, defaults to current page in
		main window
		@param final: hint if we believe this to be the last page
		before quitting the page

		@returns: C{True} if succesful, C{False} if page still has
		un-saved changes.

		@emits: close-page
		'''
		if page is None:
			page = self.page
		self.emit('close-page', page, final)
		page._parsetree = None
			# XXX HACK to avoid caching parsetree - can be removed
			# once the pageview takes care of saving the page
		return not page.modified

	def do_close_page(self, page, final):
		self.assert_save_page_if_modified()

		current = self.history.get_current()
		if current == page:
			current.cursor = self.mainwindow.pageview.get_cursor_pos()
			current.scroll = self.mainwindow.pageview.get_scroll_pos()

		def save_uistate_cb():
			if self.uistate.modified:
				self.uistate.write_async()
			# else ignore silently

		if self.uistate.modified and hasattr(self.uistate, 'write'):
			# during tests we may have a config dict without config file
			if final:
				self.uistate.write()
			else:
				# Delayed signal avoid queueing many of these in a
				# short time when going back and forward in the history
				if not hasattr(self.uistate, '_delayed_async_write'):
					self.uistate._delayed_async_write = \
						DelayedCallback(2000, save_uistate_cb) # 2 sec
				self.uistate._delayed_async_write()

	def open_page_back(self):
		'''Menu action to open the previous page from the history
		@returns: C{True} if succesful
		'''
		record = self.history.get_previous()
		if not record is None:
			self.open_page(record)
			return True
		else:
			return False

	def open_page_forward(self):
		'''Menu action to open the next page from the history
		@returns: C{True} if succesful
		'''
		record = self.history.get_next()
		if not record is None:
			self.open_page(record)
			return True
		else:
			return False

	def open_page_parent(self):
		'''Menu action to open the parent page
		@returns: C{True} if succesful
		'''
		namespace = self.page.namespace
		if namespace:
			self.open_page(Path(namespace))
			return True
		else:
			return False

	def open_page_child(self):
		'''Menu action to open a child page. Either takes the last child
		from the history, or the first child.
		@returns: C{True} if succesful
		'''
		path = self.notebook.index.lookup_path(self.page)
			# Force refresh "haschildren" ...
		if not path.haschildren:
			print 'HASCHILDREN still False'
			return False

		record = self.history.get_child(path)
		if not record is None:
			self.open_page(record)
		else:
			pages = list(self.notebook.index.list_pages(path))
			if pages:
				self.open_page(pages[0])
		return True

	def open_page_previous(self):
		'''Menu action to open the previous page from the index
		@returns: C{True} if succesful
		'''
		path = self.notebook.index.get_previous(self.page)
		if not path is None:
			self.open_page(path)
			return True
		else:
			return False

	def open_page_next(self):
		'''Menu action to open the next page from the index
		@returns: C{True} if succesful
		'''
		path = self.notebook.index.get_next(self.page)
		if not path is None:
			self.open_page(path)
			return True
		else:
			return False

	def open_page_home(self):
		'''Menu action to open the home page'''
		self.open_page(self.notebook.get_home_page())

	def new_page(self):
		'''Menu action to create a new page, shows the L{NewPageDialog},

		Difference with L{open_page()} is that the page is saved
		directly, so it exists and is stays visible if the user
		navigates away without first adding content. Though subtle this
		is expected behavior for users.
		'''
		NewPageDialog(self, path=self._get_path_context()).run()

	def new_sub_page(self):
		'''Menu action to create a new page, shows the L{NewPageDialog}.
		Like L{new_page()} but forces a child page of the current
		page.
		'''
		NewPageDialog(self, path=self._get_path_context(), subpage=True).run()

	def new_page_from_text(self, text, name=None, use_template=False, attachments=None, open_page=False):
		'''Create a new page with content. This method is intended
		mainly for remote calls. It is used for
		example by the L{quicknote plugin<zim.plugins.quicknote>}.

		@param text: the content of the page (wiki format)
		@param name: the page name as string, if C{None} the first line
		of the text is used as the basename. If the page
		already exists a number is added to force a unique page name.
		@param open_page: if C{True} navigate to this page directly
		@param use_template: if C{True} the "new page" template is used
		@param attachments: a folder as C{Dir} object or C{string}
		(for remote calls). All files in this folder are imported as
		attachments for the new page. In the text these can be referred
		relatively.
		@returns: a L{Path} object for the new page
		'''
		# The 'open_page' and 'attachments' arguments are a bit of a
		# hack for remote calls. They are needed because the remote
		# function doesn't know the exact page name we creates...
		# TODO: with new zim.ipc we can now return the page name and
		# get rid of this hack
		if not name:
			name = text.strip()[:30]
			if '\n' in name:
				name, _ = name.split('\n', 1)
			name = self.notebook.cleanup_pathname(name.replace(':', ''), purge=True)
		elif isinstance(name, Path):
			name = name.name
			name = self.notebook.cleanup_pathname(name, purge=True)
		else:
			name = self.notebook.cleanup_pathname(name, purge=True)

		path = self.notebook.resolve_path(name)
		page = self.notebook.get_new_page(path)
		if use_template:
			parsetree = self.notebook.get_template(page)
			page.set_parsetree(parsetree)
			page.parse('wiki', text, append=True) # FIXME format hard coded
		else:
			page.parse('wiki', text) # FIXME format hard coded

		self.notebook.store_page(page)

		if attachments:
			if isinstance(attachments, basestring):
				attachments = Dir(attachments)
			self.import_attachments(page, attachments)

		if open_page:
			self.present(page)

		return Path(page.name)

	def import_attachments(self, path, dir):
		'''Import a set of files as attachments.
		All files in C{folder} will be imported in the attachment dir.
		Any existing files will be overwritten.
		@param path: a L{Path} object (or C{string} for remote call)
		@param dir: a L{Dir} object (or C{string} for remote call)
		'''
		if isinstance(path, basestring):
			path = Path(path)

		if isinstance(dir, basestring):
			dir = Dir(dir)

		attachments = self.notebook.get_attachments_dir(path)
		for name in dir.list():
			# FIXME could use list objects, or list_files()
			file = dir.file(name)
			if not file.isdir():
				file.copyto(attachments)

	def append_text_to_page(self, name, text):
		'''Append text to an (existing) page. This method is intended
		mainly for remote calls. It is used for
		example by the L{quicknote plugin<zim.plugins.quicknote>}.

		@param name: the page name
		@param text: the content of the page (wiki format)
		'''
		if isinstance(name, Path):
			name = name.name
		path = self.notebook.resolve_path(name)
		page = self.notebook.get_page(path)
		page.parse('wiki', text, append=True) # FIXME format hard coded
		self.notebook.store_page(page)

	def open_new_window(self, page=None):
		'''Menu action to open a page in a secondary L{PageWindow}
		@param page: the page L{Path}, deafults to current selected
		'''
		if page is None:
			page = self._get_path_context()
		PageWindow(self, page).show_all()

	@SignalHandler
	def do_autosave(self):
		if self._check_autosave_done():
			page = self.mainwindow.pageview.get_page()
			if page.modified \
			and self._save_page_check_page(page):
				try:
					self._autosave_thread = self.notebook.store_page_async(page)
				except:
					# probably means backend does not support async store
					# AND failed storing - re-try immediatly
					logger.exception('Error during autosave - re-try')
					self.save_page()
			else:
				self._autosave_thread = None
		else:
			pass # still busy

	def _check_autosave_done(self):
		## Returning True here does not mean previous save was OK, just that it finished!
		if not self._autosave_thread:
			return True
		elif not self._autosave_thread.done:
			return False
		elif self._autosave_thread.error:
			# FIXME - should we force page.modified = True here ?
			logger.error('Error during autosave - re-try',
					exc_info=self._autosave_thread.exc_info)
			self._save_page(self.mainwindow.pageview.get_page()) # force normal save
			return True
		else:
			return True # Done and no error ..

	def assert_save_page_if_modified(self):
		'''Like C{save_page()} but only saves when needed.
		@raises PageHasUnSavedChangesError: when page was not saved
		'''
		page = self.mainwindow.pageview.get_page()
		if page is None:
			return

		if self._autosave_thread \
		and not self._autosave_thread.done:
			self._autosave_thread.join() # wait to finish

		self._check_autosave_done() # handle errors if any

		if page.modified:
			return self._save_page(page)
		else:
			return True

	def save_page(self):
		'''Menu action to save the current page.

		Can result in a L{SavePageErrorDialog} when there is an error
		while saving a page.

		@returns: C{True} when successful, C{False} when the page still
		has unsaved changes
		'''
		page = self.mainwindow.pageview.get_page()
		assert page is not None

		if self._autosave_thread \
		and not self._autosave_thread.done:
			self._autosave_thread.join() # wait to finish

		# No error handling here for autosave, we save anyway

		return self._save_page(page)

	def _save_page(self, page):
		if not self._save_page_check_page(page):
			return

		## HACK - otherwise we get a bug when saving a new page immediatly
		# hasattr assertions used to detect when the hack breaks
		assert hasattr(page, '_ui_object')
		if page._ui_object:
			assert hasattr(page._ui_object, '_showing_template')
			page._ui_object._showing_template = False
		##

		logger.debug('Saving page: %s', page)
		try:
			self.notebook.store_page(page)
		except Exception, error:
			logger.exception('Failed to save page: %s', page.name)
			with self.do_autosave.blocked():
				# Avoid new autosave (on idle) while dialog is seen
				SavePageErrorDialog(self, error, page).run()

		return not page.modified

	def _save_page_check_page(self, page):
		# Ensure that the page can be saved in the first place
		try:
			if self.readonly:
				raise AssertionError, 'BUG: can not save page when read-only'
			elif page.readonly:
				raise AssertionError, 'BUG: can not save read-only page'
		except Exception, error:
			with self.do_autosave.blocked():
				# Avoid new autosave (on idle) while dialog is seen
				SavePageErrorDialog(self, error, page).run()
			return False
		else:
			return True

	def save_copy(self):
		'''Menu action to show a L{SaveCopyDialog}'''
		SaveCopyDialog(self).run()

	def show_export(self):
		'''Menu action to show an L{ExportDialog}'''
		from zim.gui.exportdialog import ExportDialog
		ExportDialog(self).run()

	def email_page(self):
		'''Menu action to open an email containing the current page.
		Encodes the current page as "mailto:" URI and calls L{open_url()}
		to start the preferred email client.
		'''
		text = ''.join(self.page.dump(format='plain'))
		url = 'mailto:?subject=%s&body=%s' % (
			url_encode(self.page.name, mode=URL_ENCODE_DATA),
			url_encode(text, mode=URL_ENCODE_DATA),
		)
		self.open_url(url)

	def import_page(self):
		'''Menu action to show an L{ImportPageDialog}'''
		ImportPageDialog(self).run()

	def move_page(self, path=None):
		'''Menu action to show the L{MovePageDialog}
		@param path: a L{Path} object, or C{None} to move to current
		selected page
		'''
		if path is None:
			path = self._get_path_context()
		MovePageDialog(self, path).run()

	def do_move_page(self, path, newpath, update_links):
		'''Callback for MovePageDialog and PageIndex for executing
		notebook.move_page but wrapping with all the proper exception
		dialogs. Returns boolean for success.
		'''
		self.assert_save_page_if_modified()

		return self._wrap_move_page(
			lambda update_links, callback: self.notebook.move_page(
				path, newpath, update_links, callback),
			update_links
		)

	def rename_page(self, path=None):
		'''Menu action to show the L{RenamePageDialog}
		@param path: a L{Path} object, or C{None} for the current
		selected page
		'''
		if path is None:
			path = self._get_path_context()
		RenamePageDialog(self, path).run()

	def do_rename_page(self, path, newbasename, update_heading=True, update_links=True):
		'''Callback for RenamePageDialog for executing
		notebook.rename_page but wrapping with all the proper exception
		dialogs. Returns boolean for success.
		'''
		self.assert_save_page_if_modified()

		return self._wrap_move_page(
			lambda update_links, callback: self.notebook.rename_page(
				path, newbasename, update_heading, update_links, callback),
			update_links
		)

	def _wrap_move_page(self, func, update_links):
		if self.notebook.index.updating:
			# Ask regardless of update_links because it might very
			# well be that the dialog thinks there are no links
			# but they are simply not indexed yet
			cont = QuestionDialog(self,
				_('The index is still busy updating. Until this '
				  'is finished links can not be updated correctly. '
				  'Performing this action now could break links, '
				  'do you want to continue anyway?'
				) # T: question dialog text
			).run()
			if cont:
				update_links = False
			else:
				return False

		dialog = ProgressBarDialog(self, _('Updating Links'))
			# T: Title of progressbar dialog
		callback = lambda p, **kwarg: dialog.pulse(p.name, **kwarg)

		try:
			with dialog:
				func(update_links, callback)
		except Exception, error:
			ErrorDialog(self, error).run()
			return False
		else:
			return True

	def delete_page(self, path=None):
		'''Delete a page by either trashing it, or permanent deletion
		after confirmation of a L{DeletePageDialog}. When trashing the
		update behavior depends on the "remove_links_on_delete"
		preference.

		@param path: a L{Path} object, or C{None} for the current
		selected page
		'''
		if path is None:
			path = self._get_path_context()
			if not path: return

		update_links = self.preferences['GtkInterface']['remove_links_on_delete']
		dialog = ProgressBarDialog(self, _('Removing Links'))
			# T: Title of progressbar dialog
		callback = lambda p, **kwarg: dialog.pulse(p.name, **kwarg)
		try:
			with dialog:
				self.notebook.trash_page(path, update_links, callback)
		except TrashNotSupportedError, error:
			logger.info('Trash not supported: %s', error.msg)
			DeletePageDialog(self, path).run()
		except TrashCancelledError, error:
			pass

	def show_properties(self):
		'''Menu action to show the L{PropertiesDialog}'''
		from zim.gui.propertiesdialog import PropertiesDialog
		PropertiesDialog(self).run()

	def show_search(self, query=None):
		'''Menu action to show the L{SearchDialog}
		@param query: the search query to show
		'''
		from zim.gui.searchdialog import SearchDialog
		if query is None:
			query = self.mainwindow.pageview.get_selection()

		dialog = SearchDialog(self)
		dialog.show_all()

		if query is not None:
			dialog.search(query)

	def show_search_backlinks(self):
		'''Menu action to show the L{SearchDialog} with a query for
		backlinks
		'''
		query = 'LinksTo: "%s"' % self.page.name
		self.show_search(query)

	def show_recent_changes(self):
		'''Menu action to show the L{RecentChangesDialog}'''
		from .recentchangesdialog import RecentChangesDialog
		dialog = RecentChangesDialog.unique(self, self)
		dialog.present()

	def copy_location(self):
		'''Menu action to copy the current page name to the clipboard'''
		Clipboard.set_pagelink(self.notebook, self.page)

	def show_templateeditor(self):
		'''Menu action to show the L{TemplateEditorDialog}'''
		from zim.gui.templateeditordialog import TemplateEditorDialog
		TemplateEditorDialog(self).run()

	def show_preferences(self):
		'''Menu action to show the L{PreferencesDialog}'''
		from zim.gui.preferencesdialog import PreferencesDialog
		PreferencesDialog(self).run()

	def do_preferences_changed(self, *a):
		self.uimanager.set_add_tearoffs(
			self.preferences['GtkInterface']['tearoff_menus'] )

	def reload_page(self):
		'''Menu action to reload the current page. Will first try
		to save any unsaved changes, then reload the page from disk.
		'''
		self.assert_save_page_if_modified()
		self.notebook.flush_page_cache(self.page)
		self.open_page(self.notebook.get_page(self.page))

	def attach_file(self, path=None):
		'''Menu action to show the L{AttachFileDialog}
		@param path: a L{Path} object, or C{None} for the current
		selected page
		'''
		if path is None:
			path = self._get_path_context()
		AttachFileDialog(self, path).run()

	def do_attach_file(self, path, file, force_overwrite=False):
		'''Callback for AttachFileDialog and InsertImageDialog
		When 'force_overwrite' is False the user will be prompted in
		case the new file has the same name as an existing attachment.
		Returns the (new) filename or None when the action was canceled.
		'''
		dir = self.notebook.get_attachments_dir(path)
		if dir is None:
			raise Error, '%s does not have an attachments dir' % path

		dest = dir.file(file.basename)
		if dest.exists() and not force_overwrite:
			dialog = PromptExistingFileDialog(self, dest)
			dest = dialog.run()
			if dest is None:
				return None	# dialog was cancelled

		file.copyto(dest)
		return dest

	def open_dir(self, dir):
		'''Open a L{Dir} object and prompt to create it if it doesn't
		exist yet.
		@param dir: a L{Dir} object
		'''
		if dir.exists():
			self.open_file(dir)
		else:
			question = (
				_('Create folder?'),
					# T: Heading in a question dialog for creating a folder
				_('The folder "%s" does not yet exist.\nDo you want to create it now?') % dir.basename)
					# T: Text in a question dialog for creating a folder, %s will be the folder base name
			create = QuestionDialog(self, question).run()
			if create:
				dir.touch()
				self.open_file(dir)

	def open_file(self, file, mimetype=None, callback=None):
		'''Open a L{File} or L{Dir} in the system file browser.

		@param file: a L{File} or L{Dir} object
		@param mimetype: optionally specify the mimetype to force a
		specific application to open this file
		@param callback: callback function to be passed on to
		L{Application.spawn()} (if the application supports a
		callback, otherwise it is ignored silently)

		@raises NoSuchFileError: if C{file} does not exist
		@raises ApplicationLookupError: if a specific mimetype was
		given, but no default application is known for this mimetype
		(will not use fallback in this case - fallback would
		ignore the specified mimetype)
		'''
		logger.debug('open_file(%s, %s)', file, mimetype)
		assert isinstance(file, (File, Dir))
		if isinstance(file, (File)) and file.isdir():
			file = Dir(file.path)

		if not file.exists():
			raise NoSuchFileError, file

		if isinstance(file, File): # File
			manager = ApplicationManager()
			if mimetype is None:
				entry = manager.get_default_application(file.get_mimetype())
			else:
				entry = manager.get_default_application(mimetype)
				if entry is None:
					raise ApplicationLookupError, 'No Application found for: %s' % mimetype
					# Do not go to fallback, we can not force
					# mimetype for fallback

			if entry:
				self._open_with(entry, file, callback)
			else:
				self._open_with_filebrowser(file, callback)
		else: # Dir
			self._open_with_filebrowser(file, callback)

	def open_url(self, url):
		'''Open an URL (or URI) in the web browser or other relevant
		program. The application is determined based on the URL / URI
		scheme. Unkown schemes and "file://" URIs are opened with the
		webbrowser.

		@param url: the URL to open, e.g. "http://zim-wiki.org" or
		"mailto:someone@somewhere.org"
		'''
		logger.debug('open_url(%s)', url)
		assert isinstance(url, basestring)

		if is_url_re.match(url):
			# Try custom handlers
			if is_url_re[1] in self.url_handlers:
				handled = self.url_handlers[is_url_re[1]](url)
				if handled:
					return
			else:
				pass # handled below
		elif is_win32_share_re.match(url):
			url = normalize_win32_share(url)
			if os.name == 'nt':
				return self._open_with_filebrowser(url)
			# else consider as a x-scheme-handler/smb type URI
		elif not is_uri_re.match(url):
			raise AssertionError, 'Not an URL: %s' % url

		# Default handlers
		if url.startswith('zim+'):
			# Notebook URL, these we handle ourselves
			self.open_notebook(url)
		elif url.startswith('file:/'):
			# Special case, force to browser (and not to open_file ...
			# even though the result may be the same if the browser is
			# dispatched through xdg-open, gnome-open, ...)
			self._open_with_webbrowser(url)
		elif url.startswith('outlook:') and hasattr(os, 'startfile'):
			# Special case for outlook folder paths on windows
			os.startfile(url)
		else:
			from zim.gui.applications import get_mimetype
			manager = ApplicationManager()
			type = get_mimetype(url)
			logger.debug('Got type "%s" for "%s"', type, url)
			entry = manager.get_default_application(type)
			if entry:
				self._open_with(entry, url)
			elif url.startswith('mailto:'):
				self._open_with_emailclient(url)
			else:
				self._open_with_webbrowser(url)

	def _open_with_filebrowser(self, file, callback=None):
		# Fallback for files and folders, used by open_file()
		entry = ApplicationManager.get_fallback_filebrowser()
		self._open_with(entry, file, callback)

	def _open_with_emailclient(self, uri):
		# Fallback for "mailto:" URIs, used by open_url()
		entry = ApplicationManager.get_fallback_emailclient()
		self._open_with(entry, uri)

	def _open_with_webbrowser(self, url):
		# Fallback for other URLs and URIs, used by open_url()
		entry = ApplicationManager.get_fallback_webbrowser()
		self._open_with(entry, url)

	def _open_with(self, entry, uri, callback=None):
		def check_error(status):
			if status != 0:
					ErrorDialog(self, _('Could not open: %s') % uri).run()
					# T: error when external application fails

		if callback is None:
			callback = check_error

		try:
			entry.spawn((uri,), callback=callback)
		except NotImplementedError:
			entry.spawn((uri,)) # E.g. webbrowser module

	def open_attachments_folder(self):
		'''Menu action to open the attachment folder for the current page'''
		dir = self.notebook.get_attachments_dir(self.page)
		if dir is None:
			error = _('This page does not have an attachments folder')
				# T: Error message
			ErrorDialog(self, error).run()
		else:
			self.open_dir(dir)

	def open_notebook_folder(self):
		'''Menu action to open the notebook folder'''
		if self.notebook.dir:
			self.open_file(self.notebook.dir)
		elif self.notebook.file:
			self.open_file(self.notebook.file.dir)
		else:
			assert False, 'BUG: notebook has neither dir or file'

	def open_document_root(self):
		'''Menu action to open the document root folder'''
		dir = self.notebook.document_root
		if dir:
			self.open_dir(dir)

	def open_document_folder(self):
		'''Menu action to open a sub-foldel of the document root folder
		for the current page
		'''
		dir = self.notebook.document_root
		if dir is None:
			return

		dirpath = encode_filename(self.page.name)
		dir = Dir([dir, dirpath])
		self.open_dir(dir)

	def edit_page_source(self, page=None):
		'''Menu action to edit the page source in an external editor.
		See L{edit_file} for details.

		@param page: the L{Page} object, or C{None} for te current page
		'''
		# This could also be defined as a custom tool, but defined here
		# because we want to determine the editor dynamically
		# We assume that the default app for a text file is a editor
		# and not e.g. a viewer or a browser. Of course users can still
		# define a custom tool for other editors.
		if not page:
			page = self.page

		if not hasattr(self.page, 'source'):
			ErrorDialog(self, 'This page does not have a source file').run()
			return

		self.assert_save_page_if_modified()

		self.edit_file(self.page.source, istextfile=True)
		if page == self.page:
			self.reload_page()

	def edit_config_file(self, configfile):
		'''Edit a config file in an external editor.
		See L{edit_file()} for details.
		@param configfile: a L{ConfigFile} object
		'''
		configfile.touch()
		self.edit_file(configfile.file, istextfile=True)

	def edit_file(self, file, istextfile=None, dialog=None):
		'''Edit a file with and external application.

		This method will show a dialog to block the interface while the
		external application is running. The dialog is closed
		automatically when the application exits _after_ modifying the
		file. If the file is unmodified the user needs to click the
		"Done" button in the dialog because we can not know if the
		application was really done or just forked to another process.

		@param file: a L{File} object
		@param istextfile: if C{True} the text editor is used, otherwise
		we ask the file browser for the correct application. When
		C{None} we check the mimetype of the file to determine if it
		is text or not.
		@param dialog: the dialog that is spawning this action
		'''
		## FIXME force using real text editor, even when file has not
		## text mimetype. This now goes wrong when editing e.g. a html
		## template when the editor is "xdg-open" on linux or default
		## os.startfile() on windows...

		if not file.exists():
			raise NoSuchFileError, file

		oldmtime = file.mtime()

		window = dialog or self
		dialog = MessageDialog(window, (
			_('Editing file: %s') % file.basename,
				# T: main text for dialog for editing external files
			_('You are editing a file in an external application. You can close this dialog when you are done')
				# T: description for dialog for editing external files
		) )

		def check_close_dialog(status):
			if status != 0:
				dialog.destroy()
				ErrorDialog(window, _('Could not open: %s') % file.basename).run()
					# T: error when external application fails
			else:
				newmtime = file.mtime()
				if newmtime != oldmtime:
					dialog.destroy()

		if istextfile:
			try:
				self.open_file(file, mimetype='text/plain', callback=check_close_dialog)
			except ApplicationLookupError:
				app = AddApplicationDialog(window, 'text/plain').run()
				if app:
					# Try again
					self.open_file(file, mimetype='text/plain', callback=check_close_dialog)
				else:
					return # Dialog was cancelled, no default set, ...
		else:
			self.open_file(file, callback=check_close_dialog)

		dialog.run()

	def show_server_gui(self):
		'''Menu action to show the server interface from
		L{zim.gui.server}. Spawns a new zim instance for the server.
		'''
		# TODO instead of spawn, include in this process
		get_zim_application('--server', '--gui', self.notebook.uri).spawn()

	def reload_index(self, flush=False):
		'''Check the notebook for changes and update the index.
		Shows an progressbar while updateing.
		@param flush: if C{True} the index is flushed and rebuild from
		scratch
		@returns: C{True} unless the user cancelled the update
		'''
		self.emit('start-index-update')

		index = self.notebook.index
		index.stop_updating()
		if flush:
			index.flush()

		dialog = ProgressBarDialog(self, _('Updating index'))
			# T: Title of progressbar dialog
		with dialog:
			index.update(callback=lambda p: dialog.pulse(p.name))

		self.emit('end-index-update')
		return not dialog.cancelled

	def manage_custom_tools(self):
		'''Menu action to show the L{CustomToolManagerDialog}'''
		from zim.gui.customtools import CustomToolManagerDialog
		CustomToolManagerDialog(self).run()
		self.load_custom_tools()

	def load_custom_tools(self):
		'''Load the custom tools of the L{CustomToolManager} in the
		menu bar.
		'''
		manager = CustomToolManager()

		# Remove old actions
		if self._custom_tool_ui_id:
			self.uimanager.remove_ui(self._custom_tool_ui_id)

		if self._custom_tool_actiongroup:
			self.uimanager.remove_action_group(self._custom_tool_actiongroup)

		if self._custom_tool_iconfactory:
			self._custom_tool_iconfactory.remove_default()

		# Load new actions
		actions = []
		factory = gtk.IconFactory()
		factory.add_default()
		for tool in manager:
			icon = tool.icon
			if '/' in icon or '\\' in icon:
				# Assume icon is a file path - add it to IconFactory
				icon = 'zim-custom-tool' + tool.key
				try:
					pixbuf = tool.get_pixbuf(gtk.ICON_SIZE_LARGE_TOOLBAR)
					set = gtk.IconSet(pixbuf=pixbuf)
					factory.add(icon, set)
				except Exception:
					logger.exception('Got exception while loading application icons')
					icon = None

			action = (tool.key, icon, tool.name, '', tool.comment, self._exec_custom_tool)
			actions.append(action)

		self._custom_tool_iconfactory = factory
		self._custom_tool_actiongroup = gtk.ActionGroup('custom_tools')
		self._custom_tool_actiongroup.add_actions(actions)

		menulines = ["<menuitem action='%s'/>\n" % tool.key for tool in manager]
		toollines = ["<toolitem action='%s'/>\n" % tool.key for tool in manager if tool.showintoolbar]
		textlines = ["<menuitem action='%s'/>\n" % tool.key for tool in manager if tool.showincontextmenu == 'Text']
		pagelines = ["<menuitem action='%s'/>\n" % tool.key for tool in manager if tool.showincontextmenu == 'Page']
		ui = """\
<ui>
	<menubar name='menubar'>
		<menu action='tools_menu'>
			<placeholder name='custom_tools'>
			 %s
			</placeholder>
		</menu>
	</menubar>
	<toolbar name='toolbar'>
		<placeholder name='tools'>
		%s
		</placeholder>
	</toolbar>
	<popup name='text_popup'>
		<placeholder name='tools'>
		%s
		</placeholder>
	</popup>
	<popup name='page_popup'>
		<placeholder name='tools'>
		%s
		</placeholder>
	</popup>
</ui>
""" % (
	''.join(menulines), ''.join(toollines),
	''.join(textlines), ''.join(pagelines)
)

		self.uimanager.insert_action_group(self._custom_tool_actiongroup, 0)
		self._custom_tool_ui_id = self.uimanager.add_ui_from_string(ui)

	def _exec_custom_tool(self, action):
		manager = CustomToolManager()
		tool = manager.get_tool(action.get_name())
		logger.info('Execute custom tool %s', tool.name)
		args = (self.notebook, self.page, self.mainwindow.pageview)
		try:
			if tool.isreadonly:
				tool.spawn(args)
			elif tool.replaceselection:
				output = tool.pipe(args)
				logger.debug('Replace output with %s', output)
				pageview = self.mainwindow.pageview # XXX
				buffer = pageview.view.get_buffer() # XXX
				if buffer.get_has_selection():
					start, end = buffer.get_selection_bounds()
					with buffer.user_action:
						buffer.delete(start, end)
						buffer.insert_at_cursor(''.join(output))
				else:
					pass # error here ??
			else:
				tool.run(args)
				self.reload_page()
				self.notebook.index.update_async()
				# TODO instead of using run, use spawn and show dialog
				# with cancel button. Dialog blocks ui.
		except Exception, error:
			ErrorDialog(self, error).run()

	def show_help(self, page=None):
		'''Menu action to show the user manual. Will start a new zim
		instance showing the notebook with the manual.
		@param page: manual page to show (string)
		'''
		if page:
			get_zim_application('--manual', page).spawn()
		else:
			get_zim_application('--manual').spawn()

	def show_help_faq(self):
		'''Menu action to show the 'FAQ' page in the user manual'''
		self.show_help('FAQ')

	def show_help_keys(self):
		'''Menu action to show the 'Key Bindings' page in the user manual'''
		self.show_help('Help:Key Bindings')

	def show_help_bugs(self):
		'''Menu action to show the 'Bugs' page in the user manual'''
		self.show_help('Bugs')

	def show_about(self):
		'''Menu action to show the "about" dialog'''
		gtk.about_dialog_set_url_hook(lambda d, l: self.open_url(l))
		gtk.about_dialog_set_email_hook(lambda d, l: self.open_url(l))
		dialog = gtk.AboutDialog()
		try: # since gtk 2.12
			dialog.set_program_name('Zim')
		except AttributeError:
			pass

		import zim
		dialog.set_version(zim.__version__)
		dialog.set_comments(_('A desktop wiki'))
			# T: General description of zim itself
		file = data_file('zim.png')
		pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
		dialog.set_logo(pixbuf)
		dialog.set_copyright(zim.__copyright__)
		dialog.set_license(zim.__license__)
		dialog.set_authors([zim.__author__])
		dialog.set_translator_credits(_('translator-credits'))
			# T: This string needs to be translated with names of the translators for this language
		dialog.set_website(zim.__url__)
		dialog.run()
		dialog.destroy()

# Need to register classes defining gobject signals
gobject.type_register(GtkInterface)


class ResourceOpener(object):

	def __init__(self, window):
		self.window = window

	def open_page(self, path, new_window=False):
		if new_window:
			self.window.ui.open_new_window(path) # XXX
		else:
			self.window.ui.open_page(path) # XXX

		return self.window.pageview # XXX

	def open_dir(self, dir):
		self.window.ui.open_dir(dir)

	def open_file(self, url):
		self.window.ui.open_file(url)

	def open_url(self, url):
		self.window.ui.open_url(url)


class MainWindow(Window):
	'''This class implements the main window of the application. It
	contains the main L{PageView} and the side pane with a L{PageIndex}.
	Also includes the menubar, toolbar, L{PathBar}, statusbar etc.

	@ivar pageview: the L{PageView} object
	@ivar pageindex: the L{PageIndex} object
	@ivar pathbar: the L{PathBar} object

	@signal: C{fullscreen-changed ()}: emitted when switching to or from fullscreen state
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'fullscreen-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		'init-uistate': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, ui, preferences=None, fullscreen=False, geometry=None):
		'''Constructor
		@param ui: the L{GtkInterFace}
		@param preferences: a C{ConfigDict} with preferences
		@param fullscreen: if C{True} the window is shown fullscreen,
		if C{None} the previous state is restored
		@param geometry: the window geometry as string in format
		"C{WxH+X+Y}", if C{None} the previous state is restored
		'''
		Window.__init__(self)
		self.isfullscreen = False
		self.ui = ui

		self.preferences = preferences # XXX should be just prefernces dict - use "config" otherwise
		self.preferences.connect('changed', self.do_preferences_changed)

		ui.connect('open-page', self.on_open_page)
		ui.connect('close-page', self.on_close_page)

		self._block_toggle_panes = False
		self._sidepane_autoclose = False
		self._switch_focus_accelgroup = None

		self.maximized = False

		# Catching this signal prevents the window to actually be destroyed
		# when the user tries to close it. The action for close should either
		# hide or destroy the window.
		def do_delete_event(*a):
			logger.debug('Action: close (delete-event)')
			self.hide() # look more responsive
			ui.close()
			return True # Do not destroy - let close() handle it
		self.connect('delete-event', do_delete_event)

		# setup the window layout
		from zim.gui.widgets import TOP, BOTTOM, TOP_PANE, LEFT_PANE

		# setup menubar and toolbar
		self.add_accel_group(ui.uimanager.get_accel_group())
		self.menubar = ui.uimanager.get_widget('/menubar')
		self.toolbar = ui.uimanager.get_widget('/toolbar')
		self.toolbar.connect('popup-context-menu', self.do_toolbar_popup)
		self.add_bar(self.menubar, TOP)
		self.add_bar(self.toolbar, TOP)

		self.pageindex = PageIndex(ui)
		self.add_tab(_('Index'), self.pageindex, LEFT_PANE) # T: Label for pageindex tab

		self.pathbar = None
		self.pathbar_box = gtk.HBox()
		self.add_widget(self.pathbar_box, (TOP_PANE, TOP))

		self.pageview = PageView(ui)
		self.pageview.view.connect_after(
			'toggle-overwrite', self.do_textview_toggle_overwrite)
		self.add(self.pageview)

		# create statusbar
		hbox = gtk.HBox(spacing=0)
		self.add_bar(hbox, BOTTOM)

		self.statusbar = gtk.Statusbar()
		if ui_environment['platform'] == 'maemo':
			# Maemo windows aren't resizeable so it makes no sense to show the resize grip
			self.statusbar.set_has_resize_grip(False)
		self.statusbar.push(0, '<page>')
		hbox.add(self.statusbar)

		def statusbar_element(string, size):
			frame = gtk.Frame()
			frame.set_shadow_type(gtk.SHADOW_IN)
			self.statusbar.pack_end(frame, False)
			label = gtk.Label(string)
			label.set_size_request(size, 10)
			label.set_alignment(0.1, 0.5)
			frame.add(label)
			return label

		# specify statusbar elements right-to-left
		self.statusbar_style_label = statusbar_element('<style>', 100)
		self.statusbar_insert_label = statusbar_element('INS', 60)

		# and build the widget for backlinks
		self.statusbar_backlinks_button = \
			BackLinksMenuButton(self.ui, status_bar_style=True)
		frame = gtk.Frame()
		frame.set_shadow_type(gtk.SHADOW_IN)
		self.statusbar.pack_end(frame, False)
		frame.add(self.statusbar_backlinks_button)

		# add a second statusbar widget - somehow the corner grip
		# does not render properly after the pack_end for the first one
		#~ statusbar2 = gtk.Statusbar()
		#~ statusbar2.set_size_request(25, 10)
		#~ hbox.pack_end(statusbar2, False)

		self.do_preferences_changed()

		self._geometry_set = False
		self._set_fullscreen = False
		if geometry:
			try:
				self.parse_geometry(geometry)
				self._geometry_set = True
			except:
				logger.exception('Parsing geometry string failed:')
		elif fullscreen:
			self._set_fullscreen = True

		# Init mouse settings
		self.preferences['GtkInterface'].setdefault('mouse_nav_button_back', 8)
		self.preferences['GtkInterface'].setdefault('mouse_nav_button_forw', 9)

	def do_update_statusbar(self, *a):
		page = self.pageview.get_page()
		if not page:
			return
		label = page.name
		if page.modified:
			label += '*'
		if self.ui.readonly or page.readonly:
			label += ' ['+_('readonly')+']' # T: page status in statusbar
		self.statusbar.pop(0)
		self.statusbar.push(0, label)

	def do_window_state_event(self, event):
		#~ print 'window-state changed:', event.changed_mask
		#~ print 'window-state new state:', event.new_window_state

		if bool(event.changed_mask & gtk.gdk.WINDOW_STATE_MAXIMIZED):
			self.maximized = bool(event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED)

		isfullscreen = gtk.gdk.WINDOW_STATE_FULLSCREEN
		if bool(event.changed_mask & isfullscreen):
			# Did not find property for this - so tracking state ourself
			wasfullscreen = self.isfullscreen
			self.isfullscreen = bool(event.new_window_state & isfullscreen)
			logger.debug('Fullscreen changed: %s', self.isfullscreen)
			self._set_widgets_visable()
			if self.actiongroup:
				# only do this after we initalize
				self.toggle_fullscreen(show=self.isfullscreen)

			if wasfullscreen:
				# restore uistate
				if self.uistate['windowsize']:
					w, h = self.uistate['windowsize']
					self.resize(w, h)
				if self.uistate['windowpos']:
					x, y = self.uistate['windowpos'] # Should we use _windowpos?
					self.move(x, y)

			if wasfullscreen != self.isfullscreen:
				self.emit('fullscreen-changed')
				schedule_on_idle(lambda : self.pageview.scroll_cursor_on_screen())
					# HACK to have this scroll done after all updates to
					# the gui are done...

		# Maemo UI bugfix: If ancestor method is not called the window
		# will have borders when fullscreen
		# But is virtual method on other platforms
		try:
			Window.do_window_state_event(self, event)
		except NotImplementedError:
			pass

	def do_preferences_changed(self, *a):
		if self._switch_focus_accelgroup:
			self.remove_accel_group(self._switch_focus_accelgroup)

		space = gtk.gdk.unicode_to_keyval(ord(' '))
		group = gtk.AccelGroup()

		self.preferences['GtkInterface'].setdefault('toggle_on_altspace', False)
		if self.preferences['GtkInterface']['toggle_on_altspace']:
			# Hidden param, disabled because it causes problems with
			# several international layouts (space mistaken for alt-space,
			# see bug lp:620315)
			group.connect_group( # <Alt><Space>
				space, gtk.gdk.MOD1_MASK, gtk.ACCEL_VISIBLE,
				self.toggle_sidepane_focus)

		# Toggled by preference menu, also causes issues with international
		# layouts - esp. when switching input method on Ctrl-Space
		if self.preferences['GtkInterface']['toggle_on_ctrlspace']:
			group.connect_group( # <Ctrl><Space>
				space, gtk.gdk.CONTROL_MASK, gtk.ACCEL_VISIBLE,
				self.toggle_sidepane_focus)

		self.add_accel_group(group)
		self._switch_focus_accelgroup = group

	def get_selected_path(self):
		'''Get the selected page path. Depends on focus in the window:
		if the focus is on the current page, this path is returned,
		but if the focus is on the index or the pathbar the selected
		path of those widgets is returned.

		@returns: a L{Path} object or C{None}
		'''
		# FIXME - this method is bound to break again - to unstable
		widget = self.get_focus()
		#~ print '>>>', widget
		if widget == self.pageindex.treeview:
			logger.debug('Pageindex has focus')
			return self.pageindex.get_selected_path()
		elif widget == self.pathbar:
			logger.debug('Pathbar has focus')
			return self.pathbar.get_selected_path()
		elif widget == self.pageview.view:
			logger.debug('Pageview has focus')
			return self.ui.page
		else:
			logger.debug('No path in focus mainwindow')
			return None

	def toggle_menubar(self, show=None):
		'''Menu action to toggle the visibility of the menu bar
		@param show: when C{True} or C{False} force the visibility,
		when C{None} toggle based on current state
		'''
		self.do_toggle_menubar(show=show)

	def do_toggle_menubar(self, show=None):
		if show is None:
			show = not self.uistate['show_menubar']

		if show:
			self.menubar.set_no_show_all(False)
			self.menubar.show()
		else:
			self.menubar.hide()
			self.menubar.set_no_show_all(True)

		if self.isfullscreen:
			self.uistate['show_menubar_fullscreen'] = show
		else:
			self.uistate['show_menubar'] = show

	def toggle_toolbar(self, show=None):
		'''Menu action to toggle the visibility of the tool bar
		@param show: when C{True} or C{False} force the visibility,
		when C{None} toggle based on current state
		'''
		action = self.actiongroup.get_action('toggle_toolbar')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_toolbar(show=show)

	def do_toggle_toolbar(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_toolbar')
			show = action.get_active()

		if show:
			self.toolbar.set_no_show_all(False)
			self.toolbar.show()
		else:
			self.toolbar.hide()
			self.toolbar.set_no_show_all(True)

		if self.isfullscreen:
			self.uistate['show_toolbar_fullscreen'] = show
		else:
			self.uistate['show_toolbar'] = show

	def do_toolbar_popup(self, toolbar, x, y, button):
		'''Show the context menu for the toolbar'''
		menu = self.ui.uimanager.get_widget('/toolbar_popup')
		menu.popup(None, None, None, button, 0)

	def toggle_statusbar(self, show=None):
		'''Menu action to toggle the visibility of the status bar
		@param show: when C{True} or C{False} force the visibility,
		when C{None} toggle based on current state
		'''
		action = self.actiongroup.get_action('toggle_statusbar')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_statusbar(show=show)

	def do_toggle_statusbar(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_statusbar')
			show = action.get_active()

		if show:
			self.statusbar.set_no_show_all(False)
			self.statusbar.show()
		else:
			self.statusbar.hide()
			self.statusbar.set_no_show_all(True)

		if self.isfullscreen:
			self.uistate['show_statusbar_fullscreen'] = show
		else:
			self.uistate['show_statusbar'] = show

	def toggle_fullscreen(self, show=None):
		'''Menu action to toggle the fullscreen state of the window.
		@param show: when C{True} or C{False} force the state
		when C{None} toggle based on current state
		'''
		action = self.actiongroup.get_action('toggle_fullscreen')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_fullscreen(show=show)

	def do_toggle_fullscreen(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_fullscreen')
			show = action.get_active()

		if show:
			self.save_uistate()
			self.fullscreen()
		else:
			self.unfullscreen()
			# uistate is restored in do_window_state_event()

	def do_pane_state_changed(self, pane, *a):
		if not hasattr(self, 'actiongroup') \
		or self._block_toggle_panes:
			return

		action = self.actiongroup.get_action('toggle_panes')
		visible = bool(self.get_visible_panes())
		if visible != action.get_active():
			action.set_active(visible)

	def toggle_panes(self, show=None):
		'''Menu action to toggle the visibility of the all panes
		@param show: when C{True} or C{False} force the visibility,
		when C{None} toggle based on current state
		'''
		action = self.actiongroup.get_action('toggle_panes')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_panes(show=show)
		Window.save_uistate(self)

	def do_toggle_panes(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_panes')
			show = action.get_active()

		self._block_toggle_panes = True
		Window.toggle_panes(self, show)
		self._block_toggle_panes = False

		if show:
			self.focus_last_sidepane() or self.pageindex.grab_focus()
		else:
			self.pageview.grab_focus()

		self._sidepane_autoclose = False

	#~ def do_set_focus(self, widget):
		#~ if widget == self.pageview.view \
		#~ and self._sidepane_autoclose:
			#~ # Sidepane open and should close automatically
			#~ self.toggle_panes(show=False)
		#~ return Window.do_set_focus(self, widget)

	def toggle_sidepane_focus(self, *a):
		'''Switch focus between the textview and the page index.
		Automatically opens the sidepane if it is closed
		(but sets a property to automatically close it again).
		This method is used for the (optional) <Ctrl><Space> keybinding.
		'''
		action = self.actiongroup.get_action('toggle_panes')
		if action.get_active():
			# side pane open
			if self.pageview.view.is_focus():
				self.focus_last_sidepane() or self.pageindex.grab_focus()
			else:
				self.pageview.grab_focus()
				if self._sidepane_autoclose:
					self.toggle_panes(show=False)
		else:
			# open the pane
			self.toggle_panes(show=True)
			self._sidepane_autoclose = True

	def set_pathbar(self, type):
		'''Set the pathbar type

		@param type: the type of pathbar, one of:
			- C{PATHBAR_NONE} to hide the pathbar
			- C{PATHBAR_RECENT} to show recent pages
			- C{PATHBAR_RECENT_CHANGED} to show recently changed pagesF
			- C{PATHBAR_HISTORY} to show the history
			- C{PATHBAR_PATH} to show the namespace path
		'''
		self.actiongroup.get_action('set_pathbar_'+type).activate()

	def do_set_pathbar(self, name):
		style = name[12:] # len('set_pathbar_') == 12

		if style == PATHBAR_NONE:
			self.pathbar_box.hide()
			klass = None
		elif style == PATHBAR_HISTORY:
			klass = HistoryPathBar
		elif style == PATHBAR_RECENT:
			klass = RecentPathBar
		elif style == PATHBAR_RECENT_CHANGED:
			klass = RecentChangesPathBar
		elif style == PATHBAR_PATH:
			klass = NamespacePathBar
		else:
			assert False, 'BUG: Unknown pathbar type %s' % style

		if not style == PATHBAR_NONE:
			if not (self.pathbar and self.pathbar.__class__ == klass):
				for child in self.pathbar_box.get_children():
					self.pathbar_box.remove(child)
				self.pathbar = klass(self.ui)
				self.pathbar.set_history(self.ui.history)
				self.pathbar_box.add(self.pathbar)
			self.pathbar_box.show_all()

		if self.isfullscreen:
			self.uistate['pathbar_type_fullscreen'] = style
		else:
			self.uistate['pathbar_type'] = style

	def set_toolbar_style(self, style):
		'''Set the toolbar style
		@param style: can be either:
			- C{TOOLBAR_ICONS_AND_TEXT}
			- C{TOOLBAR_ICONS_ONLY}
			- C{TOOLBAR_TEXT_ONLY}
		'''
		assert style in ('icons_and_text', 'icons_only', 'text_only'), style
		self.actiongroup.get_action('set_toolbar_'+style).activate()
		self.do_set_toolbar_style(style)
			# if no configuration set, active may not represent actual case - force activation

	def do_set_toolbar_style(self, name):
		if name.startswith('set_toolbar_'):
			style = name[12:] # len('set_toolbar_') == 12
		else:
			style = name

		if style == TOOLBAR_ICONS_AND_TEXT:
			self.toolbar.set_style(gtk.TOOLBAR_BOTH)
		elif style == TOOLBAR_ICONS_ONLY:
			self.toolbar.set_style(gtk.TOOLBAR_ICONS)
		elif style == TOOLBAR_TEXT_ONLY:
			self.toolbar.set_style(gtk.TOOLBAR_TEXT)
		else:
			assert False, 'BUG: Unkown toolbar style: %s' % style

		self.preferences['GtkInterface']['toolbar_style'] = style

	def set_toolbar_size(self, size):
		'''Set the toolbar style
		@param size: can be either:
			- C{TOOLBAR_ICONS_LARGE}
			- C{TOOLBAR_ICONS_SMALL}
			- C{TOOLBAR_ICONS_TINY}
		'''
		assert size in ('large', 'small', 'tiny'), size
		self.actiongroup.get_action('set_toolbar_icons_'+size).activate()
		self.do_set_toolbar_size(size)
			# if no configuration set, active may not represent actual case - force activation

	def do_set_toolbar_size(self, name):
		if name.startswith('set_toolbar_icons_'):
			size = name[18:] # len('set_toolbar_icons_') == 18
		else:
			size = name

		if size == TOOLBAR_ICONS_LARGE:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_LARGE_TOOLBAR)
		elif size == TOOLBAR_ICONS_SMALL:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_SMALL_TOOLBAR)
		elif size == TOOLBAR_ICONS_TINY:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_MENU)
		else:
			assert False, 'BUG: Unkown toolbar size: %s' % size

		self.preferences['GtkInterface']['toolbar_size'] = size

	def toggle_readonly(self, readonly=None):
		'''Menu action to toggle the read-only state of the application
		@param readonly: when C{True} or C{False} force the state
		when C{None} toggle based on current state
		'''
		action = self.actiongroup.get_action('toggle_readonly')
		if readonly is None or readonly == action.get_active():
			action.activate()
		else:
			active = not readonly
			self.do_toggle_readonly(active=active)

	def do_toggle_readonly(self, active=None):
		if active is None:
			action = self.actiongroup.get_action('toggle_readonly')
			active = action.get_active()
		readonly = not active
		self.ui.set_readonly(readonly)
		self.uistate['readonly'] = readonly

	def show(self):
		self.uistate = self.ui.uistate['MainWindow']
			# HACK - else we wont initialize in show()
		Window.show(self)

	def show_all(self):
		self.uistate = self.ui.uistate['MainWindow']
			# HACK - else we wont initialize in show()
		Window.show_all(self)

	def init_uistate(self):
		# Initialize all the uistate parameters
		# delayed till show or show_all because all this needs real
		# uistate to be in place and plugins to be loaded
		# also pathbar needs history in place
		self.uistate = self.ui.uistate['MainWindow']

		if not self._geometry_set:
			# Ignore this if an explicit geometry was specified to the constructor
			self.uistate.setdefault('windowpos', (None, None), check=value_is_coord)
			x, y = self.uistate['windowpos']
			if (x, y) != (None, None):
				self.move(x, y)
			self.uistate.setdefault('windowsize', (600, 450), check=value_is_coord)
			w, h = self.uistate['windowsize']
			self.set_default_size(w, h)

			self.uistate.setdefault('windowmaximized', False)
			self.maximized = bool(self.uistate['windowmaximized'])
			if self.maximized:
				self.maximize()
		else:
			self.maximized = False

		self.uistate.setdefault('active_tabs', None, tuple)
		self.uistate.setdefault('show_menubar', True)
		self.uistate.setdefault('show_menubar_fullscreen', True)
		self.uistate.setdefault('show_toolbar', True)
		if ui_environment['platform'] == 'maemo':
			# N900 lacks menu and fullscreen hardware buttons, UI must provide them
			self.uistate.setdefault('show_toolbar_fullscreen', True)
		else:
			self.uistate.setdefault('show_toolbar_fullscreen', False)
		self.uistate.setdefault('show_statusbar', True)
		self.uistate.setdefault('show_statusbar_fullscreen', False)
		self.uistate.setdefault('pathbar_type', PATHBAR_RECENT, PATHBAR_TYPES)
		self.uistate.setdefault('pathbar_type_fullscreen', PATHBAR_NONE, PATHBAR_TYPES)

		# For these two "None" means system default, but we don't know what that default is :(
		self.preferences['GtkInterface'].setdefault('toolbar_style', None,
			(TOOLBAR_ICONS_ONLY, TOOLBAR_ICONS_AND_TEXT, TOOLBAR_TEXT_ONLY))
		self.preferences['GtkInterface'].setdefault('toolbar_size', None,
			(TOOLBAR_ICONS_TINY, TOOLBAR_ICONS_SMALL, TOOLBAR_ICONS_LARGE))

		self._set_widgets_visable() # toggle what panes are visible

		Window.init_uistate(self) # takes care of sidepane positions etc

		if self.preferences['GtkInterface']['toolbar_style'] is not None:
			self.set_toolbar_style(self.preferences['GtkInterface']['toolbar_style'])

		if self.preferences['GtkInterface']['toolbar_size'] is not None:
			self.set_toolbar_size(self.preferences['GtkInterface']['toolbar_size'])

		self.toggle_fullscreen(show=self._set_fullscreen)

		self.uistate.setdefault('readonly', False)
		if self.ui.notebook.readonly:
			self.toggle_readonly(readonly=True)
			action = self.actiongroup.get_action('toggle_readonly')
			action.set_sensitive(False)
		else:
			self.toggle_readonly(readonly=self.uistate['readonly'])

		# And hook to notebook properties
		self.on_notebook_properties_changed(self.ui.notebook)
		self.ui.notebook.connect('properties-changed', self.on_notebook_properties_changed)

		# Hook up the statusbar
		self.ui.connect_after('open-page', self.do_update_statusbar)
		self.ui.connect_after('readonly-changed', self.do_update_statusbar)
		self.pageview.connect('modified-changed', self.do_update_statusbar)
		self.ui.notebook.connect_after('stored-page', self.do_update_statusbar)

		# Notify plugins
		self.emit('init-uistate')

	def _set_widgets_visable(self):
		# Convenience method to switch visibility of all widgets
		if self.isfullscreen:
			self.toggle_menubar(show=self.uistate['show_menubar_fullscreen'])
			self.toggle_toolbar(show=self.uistate['show_toolbar_fullscreen'])
			self.toggle_statusbar(show=self.uistate['show_statusbar_fullscreen'])
			self.set_pathbar(self.uistate['pathbar_type_fullscreen'])
		else:
			self.toggle_menubar(show=self.uistate['show_menubar'])
			self.toggle_toolbar(show=self.uistate['show_toolbar'])
			self.toggle_statusbar(show=self.uistate['show_statusbar'])
			self.set_pathbar(self.uistate['pathbar_type'])

	def save_uistate(self):
		if not self.isfullscreen:
			self.uistate['windowpos'] = self.get_position()
			self.uistate['windowsize'] = self.get_size()
			self.uistate['windowmaximized'] = self.maximized

		Window.save_uistate(self) # takes care of sidepane positions etc.

	def get_resource_opener(self):
		return ResourceOpener(self)

	def on_notebook_properties_changed(self, notebook):
		self.set_title(notebook.name + ' - Zim')
		if notebook.icon:
			try:
				self.set_icon_from_file(notebook.icon)
			except gobject.GError:
				logger.exception('Could not load icon %s', notebook.icon)

	def on_open_page(self, ui, page, path):
		'''Signal handler for open-page, updates the pageview'''

		if path and isinstance(path, HistoryPath) and not path.cursor is None:
			cursor = path.cursor
		elif self.preferences['GtkInterface']['always_use_last_cursor_pos']:
			cursor, _ = self.ui.history.get_state(page)
		else:
			cursor = None

		self.pageview.set_page(page, cursor)

		n = ui.notebook.index.n_list_links(page, LINK_DIR_BACKWARD)
		label = self.statusbar_backlinks_button.label
		label.set_text_with_mnemonic(
			ngettext('%i _Backlink...', '%i _Backlinks...', n) % n)
			# T: Label for button with backlinks in statusbar
		if n == 0:
			self.statusbar_backlinks_button.set_sensitive(False)
		else:
			self.statusbar_backlinks_button.set_sensitive(True)

		self.pageview.grab_focus()

		#TODO: set toggle_readonly insensitive when page is readonly

	def on_close_page(self, ui, page, final):
		self.save_uistate()

	def do_textview_toggle_overwrite(self, view):
		state = view.get_overwrite()
		if state: text = 'OVR'
		else: text = 'INS'
		self.statusbar_insert_label.set_text(text)

	def do_button_press_event(self, event):
		## Try to capture buttons for navigation
		if event.button > 3:
			if event.button == self.preferences['GtkInterface']['mouse_nav_button_back']:
				self.ui.open_page_back()
			elif event.button == self.preferences['GtkInterface']['mouse_nav_button_forw']:
				self.ui.open_page_forward()
			else:
				logger.debug("Unused mouse button %i", event.button)
		#~ return Window.do_button_press_event(self, event)

# Need to register classes defining gobject signals or overloading methods
gobject.type_register(MainWindow)


class BackLinksMenuButton(MenuButton):

	def __init__(self, ui, status_bar_style=False):
		label = '%i _Backlinks...' % 0 # Translated above
		MenuButton.__init__(self, label, gtk.Menu(), status_bar_style)
		self.ui = ui

	def popup_menu(self, event=None):
		# Create menu on the fly
		self.menu = gtk.Menu()
		index = self.ui.notebook.index
		links = list(index.list_links(self.ui.page, LINK_DIR_BACKWARD))
		if not links:
			return

		self.menu.add(gtk.TearoffMenuItem())
			# TODO: hook tearoff to trigger search dialog
		links.sort(key=lambda a: a.source.name)
		for link in links:
			item = gtk.MenuItem(link.source.name)
			item.connect_object('activate', self.ui.open_page, link.source)
			self.menu.add(item)

		MenuButton.popup_menu(self, event)


class PageWindow(Window):
	'''Secondary window, showing a single page'''

	def __init__(self, ui, page):
		Window.__init__(self)
		self.ui = ui

		self.set_title(page.name + ' - Zim')
		if ui.notebook.icon:
			try:
				self.set_icon_from_file(ui.notebook.icon)
			except gobject.GError:
				logger.exception('Could not load icon %s', ui.notebook.icon)


		page = ui.notebook.get_page(page)

		self.uistate = ui.uistate['PageWindow']
			# TODO remember for separate windows separately
			# e.g. use PageWindow1, PageWindow2, etc
		self.uistate.setdefault('windowsize', (500, 400), check=value_is_coord)
		w, h = self.uistate['windowsize']
		self.set_default_size(w, h)

		self.pageview = PageView(ui, secondary=True)
		self.pageview.set_page(page)
		self.add(self.pageview)


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


class SavePageErrorDialog(ErrorDialog):
	'''Error dialog used when we hit an error while trying to save a page.
	Allow to save a copy or to discard changes. Includes a timer which
	delays the action buttons becoming sensitive. Reason for this timer is
	that the dialog may popup from auto-save while the user is typing, and
	we want to prevent an accidental action.
	'''

	def __init__(self, ui, error, page):
		msg = _('Could not save page: %s') % page.name
			# T: Heading of error dialog
		desc = unicode(error).encode('utf-8').strip() \
				+ '\n\n' \
				+ _('''\
To continue you can save a copy of this page or discard
any changes. If you save a copy changes will be also
discarded, but you can restore the copy later.''')
			# T: text in error dialog when saving page failed
		ErrorDialog.__init__(self, ui, (msg, desc), buttons=gtk.BUTTONS_NONE)

		self.page = page
		self.error = error
		self.ui = ui

		self.timer_label = gtk.Label()
		self.timer_label.set_alignment(0.9, 0.5)
		self.timer_label.set_sensitive(False)
		self.timer_label.show()
		self.vbox.add(self.timer_label)

		cancel_button = gtk.Button(stock=gtk.STOCK_CANCEL)
		self.add_action_widget(cancel_button, gtk.RESPONSE_CANCEL)

		self._done = False
		def discard(self):
			self.ui.mainwindow.pageview.clear()
				# issue may be caused in pageview - make sure it unlocks
			self.ui.notebook.revert_page(self.page)
			self._done = True

		def save(self):
			if SaveCopyDialog(self, page=self.page).run():
				discard(self)

		discard_button = gtk.Button(_('_Discard Changes'))
			# T: Button in error dialog
		discard_button.connect_object('clicked', discard, self)
		self.add_action_widget(discard_button, gtk.RESPONSE_OK)

		save_button = Button(label=_('_Save Copy'), stock=gtk.STOCK_SAVE_AS)
			# T: Button in error dialog
		save_button.connect_object('clicked', save, self)
		self.add_action_widget(save_button, gtk.RESPONSE_OK)

		for button in (cancel_button, discard_button, save_button):
			button.set_sensitive(False)
			button.show()

	def do_response_ok(self):
		return self._done

	def run(self):
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
		id = gobject.timeout_add(1000, timer, self)
		ErrorDialog.run(self)
		gobject.source_remove(id)


class OpenPageDialog(Dialog):
	'''Dialog to go to a specific page. Also known as the "Jump to" dialog.
	Prompts for a page name and navigate to that page on 'Ok'.
	'''

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Jump to'), # T: Dialog title
			button=(None, gtk.STOCK_JUMP_TO),
		)

		self.add_form(
			[('page', 'page', _('Jump to Page'), ui.page)] # T: Label for page input
		)

	def do_response_ok(self):
		path = self.form['page']
		if path:
			self.ui.open_page(path)
			return True
		else:
			return False


class NewPageDialog(Dialog):
	'''Dialog used to create a new page, functionally it is almost the same
	as the OpenPageDialog except that the page is saved directly in order
	to create it.
	'''

	def __init__(self, ui, path=None, subpage=False):
		if subpage: title = _('New Sub Page') # T: Dialog title
		else: title = _('New Page') # T: Dialog title

		Dialog.__init__(self, ui, title,
			help_text=_(
				'Please note that linking to a non-existing page\n'
				'also creates a new page automatically.'),
			# T: Dialog text in 'new page' dialog
			help=':Help:Pages'
		)

		self.path = path or ui.page

		key = self.path or ''
		default = ui.notebook.namespace_properties[key]['template']
		templates = [t[0] for t in list_templates('wiki')]
		if not default in templates:
			templates.insert(0, default)

		self.add_form([
			('page', 'page', _('Page Name'), (path or ui.page)), # T: Input label
			('template', 'choice', _('Page Template'), templates) # T: Choice label
		])
		self.form['template'] = default
		# TODO: reset default when page input changed -
		# especially if namespace has other template

		self.form.set_default_activate('page') # close dialog on <Enter> immediatly, do not select template

		if subpage:
			self.form.widgets['page'].subpaths_only = True

	def do_response_ok(self):
		path = self.form['page']
		if not path:
			return False

		page = self.ui.notebook.get_page(path)
		if page.hascontent or page.haschildren:
			raise Error, _('Page exists')+': %s' % page.name
				# T: Error when creating new page

		template = get_template('wiki', self.form['template'])
		tree = self.ui.notebook.eval_new_page_template(page, template)
		page.set_parsetree(tree)
		self.ui.open_page(page)
		self.ui.mainwindow.pageview.set_cursor_pos(-1) # HACK set position to end of template
		self.ui.save_page() # Save new page directly
		return True


class SaveCopyDialog(FileDialog):

	def __init__(self, ui, page=None):
		FileDialog.__init__(self, ui, _('Save Copy'), gtk.FILE_CHOOSER_ACTION_SAVE)
			# T: Dialog title of file save dialog
		self.filechooser.set_current_name(self.ui.page.name + '.txt')
		if page is None:
			page = self.ui.page
		self.page = page
		# TODO also include headers
		# TODO add droplist with native formats to choose + hook filters

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False
		format = 'wiki'
		logger.info("Saving a copy of %s using format '%s'", self.page, format)
		lines = self.page.dump(format)
		file.writelines(lines)
		self.result = True
		return True


class ImportPageDialog(FileDialog):
	# TODO how to properly detect file types for other formats ?

	def __init__(self, ui):
		FileDialog.__init__(self, ui, _('Import Page')) # T: Dialog title
		self.add_filter(_('Text Files'), '*.txt') # T: File filter for '*.txt'
		# TODO add input for namespace, format

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False

		basename = file.basename
		if basename.endswith('.txt'):
			basename = basename[:-4]

		path = self.ui.notebook.resolve_path(basename)
		page = self.ui.notebook.get_page(path)
		if page.hascontent:
			path = self.ui.notebook.index.get_unique_path(path)
			page = self.ui.notebook.get_page(path)
			assert not page.hascontent

		page.parse('wiki', file.readlines())
		self.ui.notebook.store_page(page)
		self.ui.open_page(page)
		return True


class MovePageDialog(Dialog):

	def __init__(self, ui, path):
		assert path, 'Need a page here'
		Dialog.__init__(self, ui, _('Move Page')) # T: Dialog title
		self.path = path

		self.ui.assert_save_page_if_modified()

		self.vbox.add(gtk.Label(_('Move page "%s"') % self.path.name))
			# T: Heading in 'move page' dialog - %s is the page name

		indexpath = self.ui.notebook.index.lookup_path(self.path)
		if indexpath:
			i = self.ui.notebook.index.n_list_links_to_tree(
					indexpath, LINK_DIR_BACKWARD )
		else:
			i = 0

		label = ngettext(
			'Update %i page linking to this page',
			'Update %i pages linking to this page', i) % i
			# T: label in MovePage dialog - %i is number of backlinks
			# TODO update label to reflect that links can also be to child pages
		self.add_form([
			('parent', 'namespace', _('Section'), self.path.parent),
				# T: Input label for the section to move a page to
			('update', 'bool', label),
				# T: option in 'move page' dialog
		])

		if i == 0:
			self.form['update'] = False
			self.form.widgets['update'].set_sensitive(False)
		else:
			self.form['update'] = True

	def do_response_ok(self):
		parent = self.form['parent']
		update = self.form['update']
		newpath = parent + self.path.basename
		self.hide() # hide this dialog before showing the progressbar
		ok = self.ui.do_move_page(self.path, newpath, update)
		if ok:
			return True
		else:
			self.show() # prompt again
			return False


class RenamePageDialog(Dialog):

	def __init__(self, ui, path):
		assert path, 'Need a page here'
		Dialog.__init__(self, ui, _('Rename Page')) # T: Dialog title
		self.path = path
		page = self.ui.notebook.get_page(self.path)

		self.vbox.add(gtk.Label(_('Rename page "%s"') % self.path.name))
			# T: label in 'rename page' dialog - %s is the page name

		indexpath = self.ui.notebook.index.lookup_path(self.path)
		if indexpath:
			i = self.ui.notebook.index.n_list_links_to_tree(
					indexpath, LINK_DIR_BACKWARD )
		else:
			i = 0

		label = ngettext(
			'Update %i page linking to this page',
			'Update %i pages linking to this page', i) % i
			# T: label in MovePage dialog - %i is number of backlinks
			# TODO update label to reflect that links can also be to child pages

		self.add_form([
			('name', 'string', _('Name')),
				# T: Input label in the 'rename page' dialog for the new name
			('head', 'bool', _('Update the heading of this page')),
				# T: Option in the 'rename page' dialog
			('update', 'bool', label),
				# T: Option in the 'rename page' dialog
		], {
			'name': self.path.basename,
			'head': page.heading_matches_pagename(),
			'update': True,
		})

		if not page.exists():
			self.form['head'] = False
			self.form.widgets['head'].set_sensitive(False)

		if i == 0:
			self.form['update'] = False
			self.form.widgets['update'].set_sensitive(False)

	def do_response_ok(self):
		name = self.form['name']
		head = self.form['head']
		update = self.form['update']
		self.hide() # hide this dialog before showing the progressbar
		ok = self.ui.do_rename_page(self.path, name, head, update)
		if ok:
			return True
		else:
			self.show() # prompt again
			return False


class DeletePageDialog(Dialog):

	def __init__(self, ui, path):
		assert path, 'Need a page here'
		Dialog.__init__(self, ui, _('Delete Page')) # T: Dialog title
		self.path = path

		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)

		img = gtk.image_new_from_stock(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_DIALOG)
		hbox.pack_start(img, False)

		vbox = gtk.VBox(spacing=5)
		hbox.pack_start(vbox, False)

		label = gtk.Label()
		short = _('Delete page "%s"?') % self.path.basename
			# T: Heading in 'delete page' dialog - %s is the page name
		long = _('Page "%s" and all of it\'s\nsub-pages and attachments will be deleted') % self.path.name
			# T: Text in 'delete page' dialog - %s is the page name
		label.set_markup('<b>'+short+'</b>\n\n'+long)
		vbox.pack_start(label, False)

		indexpath = self.ui.notebook.index.lookup_path(self.path)
		if indexpath:
			i = self.ui.notebook.index.n_list_links_to_tree(
					indexpath, LINK_DIR_BACKWARD )
		else:
			i = 0

		label = ngettext(
			'Remove links from %i page linking to this page',
			'Remove links from %i pages linking to this page', i) % i
			# T: label in DeletePage dialog - %i is number of backlinks
			# TODO update label to reflect that links can also be to child pages
		self.links_checkbox = gtk.CheckButton(label=label)
		vbox.pack_start(self.links_checkbox, False)

		if i == 0:
			self.links_checkbox.set_active(False)
			self.links_checkbox.set_sensitive(False)
		else:
			self.links_checkbox.set_active(True)


		# TODO use expander here
		dir = self.ui.notebook.get_attachments_dir(self.path)
		text = dir.get_file_tree_as_text(raw=True)
		n = len([l for l in text.splitlines() if not l.endswith('/')])

		string = ngettext('%i file will be deleted', '%i files will be deleted', n) % n
			# T: label in the DeletePage dialog to warn user of attachments being deleted
		if n > 0:
			string = '<b>'+string+'</b>'

		label = gtk.Label()
		label.set_markup('\n'+string+':')
		self.vbox.add(label)
		window, textview = ScrolledTextView(text, monospace=True)
		window.set_size_request(250, 200)
		self.vbox.add(window)

	def do_response_ok(self):
		update_links = self.links_checkbox.get_active()

		dialog = ProgressBarDialog(self, _('Removing Links'))
			# T: Title of progressbar dialog
		callback = lambda p, **kwarg: dialog.pulse(p.name, **kwarg)

		with dialog:
			self.ui.notebook.delete_page(self.path, update_links, callback)

		return True


class AttachFileDialog(FileDialog):

	def __init__(self, ui, path):
		assert path, 'Need a page here'
		FileDialog.__init__(self, ui, _('Attach File'), multiple=True) # T: Dialog title
		self.uistate.setdefault('last_attachment_folder','~')
		self.filechooser.set_current_folder(self.uistate['last_attachment_folder'])
		self.path = path

		dir = self.ui.notebook.get_attachments_dir(self.path)
		if dir is None:
			ErrorDialog(_('Page "%s" does not have a folder for attachments') % self.path)
				# T: Error dialog - %s is the full page name
			raise Exception, 'Page "%s" does not have a folder for attachments' % self.path

		self.uistate.setdefault('insert_attached_images', True)
		checkbox = gtk.CheckButton(_('Insert images as link'))
			# T: checkbox in the "Attach File" dialog
		checkbox.set_active(not self.uistate['insert_attached_images'])
		self.filechooser.set_extra_widget(checkbox)

	def do_response_ok(self):
		files = self.get_files()
		if not files:
			return False

		checkbox = self.filechooser.get_extra_widget()
		self.uistate['insert_attached_images'] = not checkbox.get_active()
		last_folder = self.filechooser.get_current_folder()
		if last_folder:
			# e.g. "Recent Used" view in dialog does not have a current folder
			self.uistate['last_attachment_folder'] = last_folder
		# Similar code in zim.gui.pageview.InsertImageDialog

		for file in files:
			file = self.ui.do_attach_file(self.path, file)
			if file is None:
				return False # overwrite dialog was canceled

			pageview = self.ui.mainwindow.pageview
			if self.uistate['insert_attached_images'] and file.isimage():
				ok = pageview.insert_image(file, interactive=False)
				if not ok: # image type not supported?
					logger.info('Could not insert image: %s', file)
					pageview.insert_links([file])
			else:
				pageview.insert_links([file])

		return True
