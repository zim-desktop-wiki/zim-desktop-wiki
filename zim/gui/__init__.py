# -*- coding: utf-8 -*-

# Copyright 2008-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
import re
import logging
import gobject
import gtk
import webbrowser


from zim.fs import File, Dir, adapt_from_newfs
from zim.newfs import FileNotFoundError
from zim.errors import Error
from zim.environ import environ
from zim.notebook import Notebook, NotebookInfo, Path, Page, build_notebook, encode_filename
from zim.notebook.index import IndexUpdateOperation, IndexCheckAndUpdateOperation
from zim.notebook.operations import NotebookOperation, ongoing_operation
from zim.actions import PRIMARY_MODIFIER_STRING
from zim.config import data_file, data_dirs, ConfigDict, ConfigManager, Boolean
from zim.plugins import PluginManager
from zim.history import History, HistoryPath
from zim.templates import get_template

from zim.gui.clipboard import Clipboard

from zim.gui.mainwindow import * # XXX

logger = logging.getLogger('zim.gui')


if gtk.gtk_version >= (2, 10) \
and gtk.pygtk_version >= (2, 10):
	gtk.link_button_set_uri_hook(lambda o, url: webbrowser.open(url))



#: Preferences for the user interface
ui_preferences = (
	# key, type, category, label, default
	('toggle_on_ctrlspace', 'bool', 'Interface', _('Use %s to switch to the side pane') % (PRIMARY_MODIFIER_STRING + '<Space>'), False),
		# T: Option in the preferences dialog - %s will map to either <Control><Space> or <Command><Space> key binding
		# default value is False because this is mapped to switch between
		# char sets in certain international key mappings
	('remove_links_on_delete', 'bool', 'Interface', _('Remove links when deleting pages'), True),
		# T: Option in the preferences dialog
	('always_use_last_cursor_pos', 'bool', 'Interface', _('Always use last cursor position when opening a page'), True),
		# T: Option in the preferences dialog
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
			name = 'zim-' + file[:-4] # e.g. checked-box.png -> zim-checked-box
			icon_theme = gtk.icon_theme_get_default()
			try:
			    pixbuf = icon_theme.load_icon(name, 24, 0)
			except:
			    pixbuf = gtk.gdk.pixbuf_new_from_file(str(dir + file))

			try:
			    set = gtk.IconSet(pixbuf)
			    factory.add(name, set)
			except Exception:
				logger.exception('Got exception while loading application icons')

load_zim_stock_icons()


class GtkInterface(object):
	'''Deprecated class

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
	@ivar history: the L{History} object
	@ivar preferences_register: a L{ConfigDict} with preferences to show
	in the preferences dialog, see L{register_preferences()} to add
	to more preferences
	'''

	def __init__(self, notebook, page=None, config=None,
		fullscreen=False, geometry=None):
		'''Constructor

		@param config: a C{ConfigManager} object
		@param notebook: a L{Notebook} object
		@param page: a L{Path} object
		@param fullscreen: if C{True} open fullscreen
		@param geometry: window geometry as string in format "C{WxH+X+Y}"
		'''
		assert isinstance(notebook, Notebook)

		logger.debug('Opening notebook: %s', notebook)
		self.notebook = notebook

		self.config = config or ConfigManager(profile=notebook.profile)
		self.preferences = self.config.get_config_dict('<profile>/preferences.conf') ### preferences attrib should just be one section
		self.preferences['GtkInterface'].define(
			toggle_on_ctrlspace=Boolean(False),
			remove_links_on_delete=Boolean(True),
			always_use_last_cursor_pos=Boolean(True),
		)
		self.preferences['General'].setdefault('plugins',[
			'pageindex', 'pathbar',
			'calendar', 'insertsymbol', 'printtobrowser',
			'versioncontrol', 'osx_menubar'
		])

		self.plugins = PluginManager(self.config)
		self.plugins.extend(notebook)

		self.page = None
		self.history = None
		self.readonly = False
		self.hideonclose = False

		logger.debug('Gtk version is %s' % str(gtk.gtk_version))
		logger.debug('Pygtk version is %s' % str(gtk.pygtk_version))


		# Hidden setting to force the gtk bell off. Otherwise it
		# can bell every time you reach the begin or end of the text
		# buffer. Especially specific gtk version on windows.
		# See bug lp:546920
		self.preferences['GtkInterface'].setdefault('gtk_bell', False)
		if not self.preferences['GtkInterface']['gtk_bell']:
			gtk.rc_parse_string('gtk-error-bell = 0')

		# Init UI
		if notebook.cache_dir:
			# may not exist during tests
			from zim.config import INIConfigFile
			self.uistate = INIConfigFile(
				notebook.cache_dir.file('state.conf'))
		else:
			from zim.config import SectionedConfigDict
			self.uistate = SectionedConfigDict()

		self._mainwindow = MainWindow(self, self.notebook, self.config, fullscreen, geometry)
		self._mainwindow._uiactions._plugins = self.plugins # XXX HACK around ugly dependency XXX
		def on_page_changed(o, page):
			self.page = page
		self._mainwindow.connect('page-changed', on_page_changed)

		self.history = History(notebook, self.uistate)

		if page and isinstance(page, basestring): # IPC call
			page = self.notebook.pages.lookup_from_user_input(page)

		self._first_page = page # XXX HACK - if we call open_page here, plugins are not yet initialized

	def run(self):
		'''Final initialization and show mainwindow'''
		assert self.notebook is not None

		if self._first_page is None:
			self._first_page = self.history.get_current()

		# And here we go!
		self._mainwindow.present()

		# HACK: Delay opening first page till after show_all() -- else plugins are not initialized
		#       FIXME need to do extension & initialization of uistate earlier
		if self._first_page:
			self._mainwindow.open_page(self._first_page)
			del self._first_page
		else:
			self._mainwindow.open_page_home()

		if not self.notebook.index.is_uptodate:
			# Show dialog, do fast foreground update
			self._mainwindow._uiactions.reload_index(update_only=True)
		else:
			# Start a lightweight background check of the index
			# put a small delay to ensure window is shown before we start
			def start_background_check():
				self.notebook.index.start_background_check(self.notebook)
				return False # only run once
			gobject.timeout_add(500, start_background_check)

		self._mainwindow.pageview.grab_focus()

	def get_toplevel(self):
		return self._mainwindow

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
		self._mainwindow.present()

		if page:
			if isinstance(page, basestring):
				page = Path(page)
			self._mainwindow.open_page(page)

		if geometry:
			self._mainwindow.parse_geometry(geometry)
		elif fullscreen:
			self._mainwindow.toggle_fullscreen(True)

	def toggle_present(self):
		'''Present main window if it is not on top, but hide if it is.
		Used by the L{trayicon plugin<zim.plugins.trayicon>} to toggle
		visibility of the window.
		'''
		if self._mainwindow.is_active():
			self._mainwindow.hide()
		else:
			self._mainwindow.present()

	def hide(self):
		'''Hide the main window. Note that this is not the same as
		minimize, when minimized there is still an icon in the task
		bar, if hidden there is no visible trace of the application and
		it can not be accessed by the user anymore until L{present()}
		has been called.
		'''
		self._mainwindow.hide()

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
		# With new multi-window process this is not used anymore by
		# - so get rid of the hack and just return the page
		if not name:
			name = text.strip()[:30]
			if '\n' in name:
				name, _ = name.split('\n', 1)
			name = name.replace(':', '')
		elif isinstance(name, Path):
			name = name.name

		path = self.notebook.pages.lookup_from_user_input(name)
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
				file.copyto(Dir(attachments.path))

	def append_text_to_page(self, name, text):
		'''Append text to an (existing) page. This method is intended
		mainly for remote calls. It is used for
		example by the L{quicknote plugin<zim.plugins.quicknote>}.

		@param name: the page name
		@param text: the content of the page (wiki format)
		@raises PageNotFound: if the page for C{name} can not be opened
		'''
		if isinstance(name, Path):
			name = name.name
		path = self.notebook.pages.lookup_from_user_input(name)
		page = self.notebook.get_page(path) # can raise
		page.parse('wiki', text, append=True) # FIXME format hard coded
		self.notebook.store_page(page)
