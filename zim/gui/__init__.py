# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains the Gtk user interface for zim.
The main widgets and dialogs are seperated out in sub-modules.
Included here are the main class for the zim GUI, which
contains most action handlers and the main window class.

TODO document UIManager / Action usage
'''

import logging
import gobject
import gtk
import gtk.keysyms
import pango

import zim
from zim.fs import *
from zim import NotebookInterface
from zim.notebook import Path, Page, PageNameError
from zim.index import LINK_DIR_BACKWARD
from zim.config import data_file, config_file, data_dirs, ListDict
import zim.history
import zim.gui.pathbar
import zim.gui.pageindex
from zim.gui.widgets import Button, MenuButton
from zim.gui.applications import get_application

logger = logging.getLogger('zim.gui')

ui_actions = (
	('file_menu', None, _('_File')), # T: Menu title
	('edit_menu', None, _('_Edit')), # T: Menu title
	('view_menu', None, _('_View')), # T: Menu title
	('insert_menu', None, _('_Insert')), # T: Menu title
	('search_menu', None, _('_Search')), # T: Menu title
	('format_menu', None, _('For_mat')), # T: Menu title
	('tools_menu', None, _('_Tools')), # T: Menu title
	('go_menu', None, _('_Go_')), # T: Menu title
	('help_menu', None, _('_Help')), # T: Menu title
	('pathbar_menu', None, _('P_athbar')), # T: Menu title
	('toolbar_menu', None, _('_Toolbar')), # T: Menu title

	# name, stock id, label, accelerator, tooltip
	('new_page',  'gtk-new', _('_New Page'), '<ctrl>N', ''), # T: Menu item
	('new_sub_page',  'gtk-new', _('New S_ub Page'), '', ''), # T: Menu item
	('open_notebook', 'gtk-open', _('_Open Another Notebook...'), '<ctrl>O', ''), # T: Menu item
	('import_page', None, _('_Import Page'), '', ''), # T: Menu item
	('save_page', 'gtk-save', _('_Save'), '<ctrl>S', ''), # T: Menu item
	('save_copy', None, _('Save a _Copy...'), '', ''), # T: Menu item
	('save_version', 'gtk-save-as', _('S_ave Version...'), '<ctrl><shift>S', ''), # T: Menu item
	('show_versions', None, _('_Versions...'), '', ''), # T: Menu item
	('show_export',  None, _('E_xport...'), '', ''), # T: Menu item
	('email_page', None, _('_Send To...'), '', ''), # T: Menu item
	('move_page', None, _('_Move Page...'), '', ''), # T: Menu item
	('rename_page', None, _('_Rename Page...'), 'F2', ''), # T: Menu item
	('delete_page', None, _('_Delete Page'), '', ''), # T: Menu item
	('show_properties',  'gtk-properties', _('Proper_ties'), '', ''), # T: Menu item
	('close',  'gtk-close', _('_Close'), '<ctrl>W', ''), # T: Menu item
	('quit',  'gtk-quit', _('_Quit'), '<ctrl>Q', ''), # T: Menu item
	('show_search',  'gtk-find', _('_Search...'), '<shift><ctrl>F', ''), # T: Menu item
	('show_search_backlinks', None, _('Search _Backlinks...'), '', ''), # T: Menu item
	('copy_location', None, _('Copy Location'), '<shift><ctrl>L', ''), # T: Menu item
	('show_preferences',  'gtk-preferences', _('Pr_eferences'), '', ''), # T: Menu item
	('reload_page',  'gtk-refresh', _('_Reload'), '<ctrl>R', ''), # T: Menu item
	('open_attachments_folder', 'gtk-open', _('Open Attachments _Folder'), '', ''), # T: Menu item
	('open_document_root', 'gtk-open', _('Open _Document Root'), '', ''), # T: Menu item
	('attach_file', 'zim-attachment', _('Attach _File'), '', _('Attach external file')), # T: Menu item
	('edit_page_source', 'gtk-edit', _('Edit _Source'), '', ''), # T: Menu item
	('show_server_gui', None, _('Start _Web Server'), '', ''), # T: Menu item
	('reload_index', None, _('Re-build Index'), '', ''), # T: Menu item
	('open_page_back', 'gtk-go-back', _('_Back'), '<alt>Left', _('Go page back')), # T: Menu item
	('open_page_forward', 'gtk-go-forward', _('_Forward'), '<alt>Right', _('Go page forward')), # T: Menu item
	('open_page_parent', 'gtk-go-up', _('_Parent'), '<alt>Up', _('Go to parent page')), # T: Menu item
	('open_page_child', 'gtk-go-down', _('_Child'), '<alt>Down', _('Go to child page')), # T: Menu item
	('open_page_previous', None, _('_Previous in index'), '<alt>Page_Up', _('Go to previous page')), # T: Menu item
	('open_page_next', None, _('_Next in index'), '<alt>Page_Down', _('Go to next page')), # T: Menu item
	('open_page_home', 'gtk-home', _('_Home'), '<alt>Home', _('Go home')), # T: Menu item
	('open_page', 'gtk-jump-to', _('_Jump To...'), '<ctrl>J', ''), # T: Menu item
	('show_help', 'gtk-help', _('_Contents'), 'F1', ''), # T: Menu item
	('show_help_faq', None, _('_FAQ'), '', ''), # T: Menu item
	('show_help_keys', None, _('_Keybindings'), '', ''), # T: Menu item
	('show_help_bugs', None, _('_Bugs'), '', ''), # T: Menu item
	('show_about', 'gtk-about', _('_About'), '', ''), # T: Menu item
)

ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, None, initial state
	('toggle_toolbar', None, _('_Toolbar'),  None, '', None, True), # T: Menu item
	('toggle_statusbar', None, _('_Statusbar'), None, '', None, True), # T: Menu item
	('toggle_sidepane',  'gtk-index', _('_Index'), 'F9', _('Show index'), None, True), # T: Menu item
)

ui_pathbar_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_pathbar_none', None, _('_None'),  None, None, 0), # T: Menu item
	('set_pathbar_recent', None, _('_Recent pages'), None, None, 1), # T: Menu item
	('set_pathbar_history', None, _('_History'),  None, None, 2), # T: Menu item
	('set_pathbar_path', None, _('N_amespace'), None, None, 3), # T: Menu item
)

PATHBAR_NONE = 'none'
PATHBAR_RECENT = 'recent'
PATHBAR_HISTORY = 'history'
PATHBAR_PATH = 'path'

ui_toolbar_style_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_toolbar_icons_and_text', None, _('Icons _and Text'), None, None, 0), # T: Menu item
	('set_toolbar_icons_only', None, _('_Icons Only'), None, None, 1), # T: Menu item
	('set_toolbar_text_only', None, _('_Text Only'), None, None, 2), # T: Menu item
)

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

ui_preferences = (
	# section, key, type, category, label, default
	('tearoff_menus', 'bool', 'Interface', _('Add \'tearoff\' strips to the menus'), False),
		# T: Option in the preferences dialog
	('toggle_on_ctrlspace', 'bool', 'Interface', _('Use <Ctrl><Space> to switch to the side pane\n(If disabled you can still use <Alt><Space>)'), True),
		# T: Option in the preferences dialog
)

# Load custom application icons as stock
try:
	factory = gtk.IconFactory()
	factory.add_default()
	for dir in data_dirs(('pixmaps')):
		for file in dir.list():
			i = file.rindex('.')
			name = 'zim-'+file[:i] # e.g. checked-box.png -> zim-checked-box
			pixbuf = gtk.gdk.pixbuf_new_from_file(str(dir+file))
			set = gtk.IconSet(pixbuf=pixbuf)
			factory.add(name, set)
except Exception:
	import sys
	logger.warn('Got exception while loading application icons')
	sys.excepthook(*sys.exc_info())


class GtkInterface(NotebookInterface):
	'''Main class for the zim Gtk interface. This object wraps a single
	notebook and provides actions to manipulate and access this notebook.

	Signals:
	* open-page (page, path)
	  Called when opening another page, see open_page() for details
	* save-page (page)
	  Called when a page is saved
	* close-page (page)
	  Called when closing a page, typically just before a new page is opened
	  and before closing the application
	* preferences-changed
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-page': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
		'save-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'close-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'preferences-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	ui_type = 'gtk'

	def __init__(self, notebook=None, page=None, **opts):
		NotebookInterface.__init__(self, **opts)
		self.preferences_register = ListDict()
		self.page = None
		self.history = None
		self._save_page_in_progress = False

		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

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
		self.preferences['GtkInterface'].setdefault('file_browser', 'xdg-open')
		self.preferences['GtkInterface'].setdefault('web_browser', 'xdg-open')
		self.preferences['GtkInterface'].setdefault('email_client', 'xdg-email')

		self.mainwindow = MainWindow(self)

		self.add_actions(ui_actions, self)
		self.add_toggle_actions(ui_toggle_actions, self.mainwindow)
		self.add_radio_actions(ui_pathbar_radio_actions,
								self.mainwindow, 'do_set_pathbar')
		self.add_radio_actions(ui_toolbar_style_radio_actions,
								self.mainwindow, 'do_set_toolbar_style')
		self.add_radio_actions(ui_toolbar_size_radio_actions,
								self.mainwindow, 'do_set_toolbar_size')
		self.add_ui(data_file('menubar.xml').read(), self)

		accelmap = config_file('accelmap')
		if accelmap.exists():
			gtk.accel_map_load(accelmap.path)
		#~ gtk.accel_map_get().connect(
			#~ 'changed', lambda o: gtk.accelmap_save(accelmap.path) )

		self.load_plugins()

		if not notebook is None:
			self.open_notebook(notebook)

		if not page is None:
			assert self.notebook, 'Can not open page without notebook'
			if isinstance(page, basestring):
				page = self.notebook.resolve_path(page)
				if not page is None:
					self.open_page(page)
			else:
				assert isinstance(page, Path)
				self.open_page(page)

	def main(self):
		'''Wrapper for gtk.main(); does not return untill program has ended.'''
		if self.notebook is None:
			self.open_notebook()
			if self.notebook is None:
				# Close application. Either the user cancelled the notebook
				# dialog, or the notebook was opened in a different process.
				return

		if self.page is None:
			path = self.history.get_current()
			if path:
				self.open_page(path)
			else:
				self.open_page_home()

		def autosave():
			page = self.mainwindow.pageview.get_page()
			if page.modified:
				self.save_page(page)
			return False # remove signal

		def schedule_autosave():
			gobject.idle_add(autosave)
			return True # keep ticking

		self._autosave_timer = None
		try:
			gobject.timeout_add_seconds(5, schedule_autosave)
		except AttributeError:
			# older gobject version doesn't know about seconds
			gobject.timeout_add(5000, schedule_autosave)

		self.uimanager.ensure_update()
			# prevent flashing when the toolbar is after showing the window
		self.mainwindow.show_all()
		self.mainwindow.pageview.grab_focus()
		gtk.main()

	def close(self):
		# TODO: logic to hide the window
		self.quit()

	def quit(self):
		assert self.close_page(self.page)
		self.mainwindow.destroy()
		gtk.main_quit()

	def add_actions(self, actions, handler, methodname=None):
		'''Wrapper for gtk.ActionGroup.add_actions(actions),
		"handler" is the object that has the methods for these actions.

		Each action is mapped to a like named method of the handler
		object. If the object not yet has an actiongroup this is created first,
		attached to the uimanager and put in the "actiongroup" attribute.
		'''
		group = self.init_actiongroup(handler)
		group.add_actions(actions)
		self._connect_actions(actions, group, handler)

	def add_toggle_actions(self, actions, handler):
		'''Wrapper for gtk.ActionGroup.add_toggle_actions(actions),
		"handler" is the object that has the methods for these actions.

		Differs for add-actions() in that in the mapping from action name
		to method name is prefixed with "do_". The reason for this is that
		in order to keep the state of toolbar and menubar widgets stays in
		sync with the internal state. Therefore the method of the same name
		as the action should just call activate() on the action, while the
		actual logic is implamented in the handler which is prefixed with
		"do_".
		'''
		group = self.init_actiongroup(handler)
		group.add_toggle_actions(actions)
		self._connect_actions(actions, group, handler, is_toggle=True)

	def init_actiongroup(self, handler):
		'''Initializes the actiongroup for 'handler' if it does not already
		exist and returns the actiongroup.
		'''
		if not hasattr(handler, 'actiongroup') or handler.actiongroup is None:
			name = handler.__class__.__name__
			handler.actiongroup = gtk.ActionGroup(name)
			self.uimanager.insert_action_group(handler.actiongroup, 0)
		return handler.actiongroup

	@staticmethod
	def _log_action(action, *a):
		logger.debug('Action: %s', action.get_name())

	def _connect_actions(self, actions, group, handler, is_toggle=False):
		for name in [a[0] for a in actions if not a[0].endswith('_menu')]:
			action = group.get_action(name)
			if is_toggle: name = 'do_' + name
			assert hasattr(handler, name), 'No method defined for action %s' % name
			method = getattr(handler.__class__, name)
			action.connect('activate', self._log_action)
			action.connect_object('activate', method, handler)

	def add_radio_actions(self, actions, handler, methodname):
		'''Wrapper for gtk.ActionGroup.add_radio_actions(actions),
		"handler" is the object that these actions belong to and
		"methodname" gives the callback to be called on changes in this group.
		(See doc on gtk.RadioAction 'changed' signal for this callback.)
		'''
		# A bit different from the other two methods since radioactions
		# come in mutual exclusive groups. Only need to connect to one
		# action to get signals from whole group.
		group = self.init_actiongroup(handler)
		group.add_radio_actions(actions)
		assert hasattr(handler, methodname), 'No such method %s' % methodname
		method = getattr(handler.__class__, methodname)
		action = group.get_action(actions[0][0])
		action.connect('changed', self._log_action)
		action.connect_object('changed', method, handler)

	def add_ui(self, xml, handler):
		'''Wrapper for gtk.UIManager.add_ui_from_string(xml)'''
		self.uimanager.add_ui_from_string(xml)

	def remove_actions(handler):
		'''Removes all ui actions for a specific handler'''
		# TODO remove action group
		# TODO remove ui

	def register_preferences(self, section, preferences):
		'''Registers user preferences. Registering means that a
		preference will show up in the preferences dialog.
		The section given is the section to locate these preferences in the
		config file. Each preference is a tuple consisting of:

		* the key in the config file
		* an option type (see Dialog.add_fields() for more details)
		* a category (the tab in which the option will be shown)
		* a label to show in the dialog
		* a default value
		'''
		register = self.preferences_register
		for p in preferences:
			key, type, category, label, default = p
			self.preferences[section].setdefault(key, default)
			register.setdefault(category, [])
			register[category].append((section, key, type, label))

	def get_path_context(self):
		'''Returns the current 'context' for actions that want a path to start
		with. Asks the mainwindow for a selected page, defaults to the
		current page if any.
		'''
		return self.mainwindow.get_selected_path() or self.page

	def open_notebook(self, notebook=None):
		'''Open a new notebook. If this is the first notebook the open-notebook
		signal is emitted and the notebook is opened in this process. Otherwise
		we let another instance handle it. If notebook=None the notebookdialog
		is run to prompt the user.'''
		if notebook is None:
			# Handle menu item for open_notebook, prompt user. The notebook
			# dialog will call this method again after a selection is made.
			logger.debug('No notebook given, showing notebookdialog')
			import zim.gui.notebookdialog
			if self.mainwindow.get_property('visible'):
				# this dialog does not need to run modal
				zim.gui.notebookdialog.NotebookDialog(self).show_all()
			else:
				# main loop not yet started
				zim.gui.notebookdialog.NotebookDialog(self).run()
		elif self.notebook is None:
			# No notebook has been set, so we open this notebook ourselfs
			# TODO also check if notebook was open through demon before going here
			logger.info('Open notebook: %s', notebook)
			NotebookInterface.open_notebook(self, notebook)
		else:
			# We are already intialized, let another process handle it
			# TODO put this in the same package as the daemon code
			self.spawn('zim', notebook)

	def do_open_notebook(self, notebook):
		'''Signal handler for open-notebook.'''
		NotebookInterface.do_open_notebook(self, notebook)
		self.history = zim.history.History(notebook, self.uistate)
		self.on_notebook_properties_changed(notebook)

		# Start a lightweight background check of the index
		self.notebook.index.update(background=True, checkcontents=False)

	def on_notebook_properties_changed(self, notebook):
		has_doc_root = not notebook.get_document_root() is None
		action = self.actiongroup.get_action('open_document_root')
		action.set_sensitive(has_doc_root)

	def open_page(self, path=None):
		'''Emit the open-page signal. The argument 'path' can either be a Page
		or a Path object. If 'page' is None a dialog is shown
		to specify the page. If 'path' is a HistoryRecord we assume that this
		call is the result of a history action and the page is not added to
		the history. The original path object is given as the second argument
		in the signal, so handlers can inspect how this method was called.
		'''
		assert self.notebook
		if path is None:
			# the dialog will call us in turn with an argument
			return OpenPageDialog(self).run()

		assert isinstance(path, Path)
		logger.info('Open page: %s', path)
		if isinstance(path, Page):
			page = path
		else:
			page = self.notebook.get_page(path)
		if self.page:
			assert self.close_page(self.page)
		self.emit('open-page', page, path)

	def do_open_page(self, page, path):
		'''Signal handler for open-page.'''
		is_first_page = self.page is None
		self.page = page

		back = self.actiongroup.get_action('open_page_back')
		forward = self.actiongroup.get_action('open_page_forward')
		parent = self.actiongroup.get_action('open_page_parent')
		child = self.actiongroup.get_action('open_page_child')

		if isinstance(path, zim.history.HistoryRecord):
			self.history.set_current(path)
			back.set_sensitive(not path.is_first())
			forward.set_sensitive(not path.is_last())
		else:
			self.history.append(page)
			back.set_sensitive(not is_first_page)
			forward.set_sensitive(False)

		parent.set_sensitive(len(page.namespace) > 0)
		child.set_sensitive(page.haschildren)

	def close_page(self, page=None):
		'''Emits the 'close-page' signal and returns boolean for success'''
		if page is None:
			page = self.page
		self.emit('close-page', page)
		return not page.modified

	def do_close_page(self, page):
		if page.modified:
			self.save_page(page)

		def save_uistate():
			if self.uistate.modified:
				self.uistate.write()
			return False # only run once

		gobject.idle_add(save_uistate)

	def open_page_back(self):
		record = self.history.get_previous()
		if not record is None:
			self.open_page(record)
			return True
		else:
			return False

	def open_page_forward(self):
		record = self.history.get_next()
		if not record is None:
			self.open_page(record)
			return True
		else:
			return False

	def open_page_parent(self):
		namespace = self.page.namespace
		if namespace:
			self.open_page(Path(namespace))
			return True
		else:
			return False

	def open_page_child(self):
		if not self.page.haschildren:
			return False

		record = self.history.get_child(self.page)
		if not record is None:
			self.open_page(record)
		else:
			child = self.notebook.index.list_pages(self.page)[0]
			self.open_page(child)
		return True

	def open_page_previous(self):
		path = self.notebook.index.get_previous(self.page)
		if not path is None:
			self.open_page(path)
			return True
		else:
			return False

	def open_page_next(self):
		path = self.notebook.index.get_next(self.page)
		if not path is None:
			self.open_page(path)
			return True
		else:
			return False

	def open_page_home(self):
		self.open_page(self.notebook.get_home_page())

	def new_page(self):
		'''opens a dialog like 'open_page(None)'. Subtle difference is
		that this page is saved directly, so it is pesistent if the user
		navigates away without first adding content. Though subtle this
		is expected behavior for users not yet fully aware of the automatic
		create/save/delete behavior in zim.
		'''
		NewPageDialog(self).run()

	def new_sub_page(self):
		'''Same as new_page() but sets the namespace widget one level deeper'''
		NewPageDialog(self, namespace=self.get_path_context()).run()

	def save_page(self, page=None):
		'''Save 'page', or current page when 'page' is None, by emitting the
		'save-page' signal. Returns boolean for success.
		'''
		if self._save_page_in_progress:
			# We need this check as the SavePageErrorDialog has a timer
			# and auto-save may trigger while we are waiting for that one...
			return False

		self._save_page_in_progress = True
		try:
			if page is None:
				page = self.mainwindow.pageview.get_page()
			self.emit('save-page', page)
		except:
			self._save_page_in_progress = False
			raise
		else:
			self._save_page_in_progress = False
			return not page.modified

	def do_save_page(self, page):
		logger.debug('Saving page: %s', page)
		try:
			self.notebook.store_page(page)
		except Exception, error:
			logger.warn('Failed to save page: %s', page.name)
			SavePageErrorDialog(self, error, page).run()

	def save_copy(self):
		'''Offer to save a copy of a page in the source format, so it can be
		imported again later. Subtly different from export.
		'''
		SaveCopyDialog(self).run()

	def save_version(self):
		pass

	def show_versions(self):
		import zim.gui.versionsdialog
		zim.gui.versionsdialog.VersionDialog(self).run()

	def show_export(self):
		import zim.gui.exportdialog
		zim.gui.exportdialog.ExportDialog(self).run()

	def email_page(self):
		text = ''.join(page.dump(format='wiki')).encode('utf-8')
		# TODO url encoding - replace \W with sprintf('%%%02x')
		url = 'mailto:?subject=%s&body=%s' % (page.name, text)
		# TODO open url

	def import_page(self):
		'''Import a file from outside the notebook as a new page.'''
		ImportPageDialog(self).run()

	def move_page(self, path=None):
		MovePageDialog(self, path=path).run()

	def rename_page(self, path=None):
		RenamePageDialog(self, path=path).run()

	def delete_page(self, path=None):
		DeletePageDialog(self, path=path).run()

	def show_properties(self):
		import zim.gui.propertiesdialog
		zim.gui.propertiesdialog.PropertiesDialog(self).run()

	def show_search(self, query=None):
		import zim.gui.searchdialog
		zim.gui.searchdialog.SearchDialog(self).main(query)

	def show_search_backlinks(self):
		query = 'LinksTo: "%s"' % self.page.name
		self.show_search(query)

	def copy_location(self):
		'''Puts the name of the current page on the clipboard.'''
		import zim.gui.clipboard
		zim.gui.clipboard.Clipboard().set_pagelink(self.notebook, self.page)

	def show_preferences(self):
		from zim.gui.preferencesdialog import PreferencesDialog
		PreferencesDialog(self).run()

	def save_preferences(self):
		if self.preferences.modified:
			self.preferences.write()
			self.emit('preferences-changed')

	def do_preferences_changed(self):
		self.uimanager.set_add_tearoffs(
			self.preferences['GtkInterface']['tearoff_menus'] )

	def reload_page(self):
		if self.page.modified:
			assert self.save_page(self.page)
		self.notebook.flush_page_cache(self.page)
		self.open_page(self.notebook.get_page(self.page))

	def attach_file(self, path=None):
		AttachFileDialog(self, path=path).run()

	def open_folder(self, dir):
		assert isinstance(dir, Dir)
		return self._openwith(self.preferences['GtkInterface']['file_browser'], (dir,))

	def open_file(self, file):
		assert isinstance(file, (File, Dir))
		return self._openwith(self.preferences['GtkInterface']['file_browser'], (file,))

	def open_url(self, url):
		assert isinstance(url, basestring)
		if url.startswith('file:/'):
			self.open_file(File(url))
		elif url.startswith('mailto:'):
			self._openwith(self.preferences['GtkInterface']['email_client'], (url,))
		else:
			self._openwith(self.preferences['GtkInterface']['web_browser'], (url,))

	def _openwith(self, appname, args):
		app = get_application(appname)
		cmd = app.parse_exec(args)
		self.spawn(*cmd)

	def open_attachments_folder(self):
		dir = self.notebook.get_attachments_dir(self.page)
		if dir is None:
			error = _('This page does not have an attachments folder')
				# T: Error message
			ErrorDialog(self, error).run()
		elif dir.exists():
			self.open_folder(dir)
		else:
			question = (
				_('Create folder?'),
					# T: Heading in a question dialog for creating a folder
				_('The attachments folder for this page does not yet exist.\nDo you want to create it now?'))
					# T: Text in a question dialog for creating a folder
			create = QuestionDialog(self, question).run()
			if create:
				dir.touch()
				self.open_folder(dir)

	def open_document_root(self):
		dir = self.notebook.get_documents_dir()
		if dir and dir.exists():
			self.open_folder(dir)

	def edit_page_source(self):
		pass

	def show_server_gui(self):
		self.spawn('zim', '--server', '--gui', self.notebook.name)

	def reload_index(self):
		dialog = ProgressBarDialog(self, _('Updating index'))
			# T: Title of progressbar dialog
		dialog.show_all()
		self.notebook.index.update(callback=lambda p: dialog.pulse(p.name))
		dialog.destroy()

	def show_help(self, page=None):
		if page:
			self.spawn('zim', '--manual', page)
		else:
			self.spawn('zim', '--manual')

	def show_help_faq(self):
		self.show_help('FAQ')

	def show_help_keys(self):
		self.show_help('Help:KeyBindings')

	def show_help_bugs(self):
		self.show_help('Bugs')

	def show_about(self):
		gtk.about_dialog_set_url_hook(lambda d, l: self.open_url(l))
		gtk.about_dialog_set_email_hook(lambda d, l: self.open_url(l))
		dialog = gtk.AboutDialog()
		try: # since gtk 2.12
			dialog.set_program_name('Zim')
		except AttributeError:
			pass
		dialog.set_version(zim.__version__)
		dialog.set_comments(_('A desktop wiki'))
			# T: General description of zim itself
		dialog.set_copyright(zim.__copyright__)
		dialog.set_license(zim.__license__)
		dialog.set_authors([zim.__author__])
		dialog.set_translator_credits(_('translator-credits'))
		dialog.set_website(zim.__url__)
		dialog.run()
		dialog.destroy()

# Need to register classes defining gobject signals
gobject.type_register(GtkInterface)


class MainWindow(gtk.Window):
	'''Main window of the application, showing the page index in the side
	pane and a pageview with the current page. Alse includes the menubar,
	toolbar, statusbar etc.
	'''

	def __init__(self, ui):
		'''Constructor'''
		gtk.Window.__init__(self)
		self.ui = ui

		ui.connect_after('open-notebook', self.do_open_notebook)
		ui.connect('open-page', self.do_open_page)
		ui.connect('close-page', self.do_close_page)

		# Catching this signal prevents the window to actually be destroyed
		# when the user tries to close it. The action for close should either
		# hide or destroy the window.
		def do_delete_event(*a):
			logger.debug('Action: close (delete-event)')
			ui.close()
			return True
		self.connect('delete-event', do_delete_event)

		vbox = gtk.VBox()
		self.add(vbox)

		# setup menubar and toolbar
		self.add_accel_group(ui.uimanager.get_accel_group())
		self.menubar = ui.uimanager.get_widget('/menubar')
		self.toolbar = ui.uimanager.get_widget('/toolbar')
		self.toolbar.connect('popup-context-menu', self.do_toolbar_popup)
		vbox.pack_start(self.menubar, False)
		vbox.pack_start(self.toolbar, False)

		# split window in side pane and editor
		self.hpane = gtk.HPaned()
		self.hpane.set_position(175)
		vbox.add(self.hpane)
		self.pageindex = zim.gui.pageindex.PageIndex(ui)
		self.hpane.add1(self.pageindex)

		self.pageindex.connect('key-press-event',
			lambda o, event: event.keyval == gtk.keysyms.Escape
				and logger.debug('TODO: hide side pane'))

		vbox2 = gtk.VBox()
		self.hpane.add2(vbox2)

		self.pathbar = None
		self.pathbar_box = gtk.HBox() # FIXME other class for this ?
		self.pathbar_box.set_border_width(3)
		vbox2.pack_start(self.pathbar_box, False)

		from zim.gui.pageview import PageView
			# imported here to prevent circular dependency
		self.pageview = PageView(ui)
		self.pageview.view.connect(
			'toggle-overwrite', self.do_textview_toggle_overwrite)
		vbox2.add(self.pageview)

		# create statusbar
		hbox = gtk.HBox(spacing=0)
		vbox.pack_start(hbox, False, True, False)

		self.statusbar = gtk.Statusbar()
		#~ self.statusbar.set_has_resize_grip(False)
		self.statusbar.push(0, '<page>')
		hbox.add(self.statusbar)

		def update_statusbar(*a):
			page = self.pageview.get_page()
			label = page.name
			# TODO if page is read-only
			if page.modified:
				label += '*'
			self.statusbar.pop(0)
			self.statusbar.push(0, label)

		self.pageview.connect('modified-changed', update_statusbar)
		self.ui.connect_after('open-page', update_statusbar)
		self.ui.connect_after('save-page', update_statusbar)

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

	def get_selected_path(self):
		'''Returns a selected path either from the side pane or the pathbar
		if any or None.
		'''
		child = self.hpane.get_focus_child()
		if child == self.pageindex:
			logger.debug('Pageindex has focus')
			return self.pageindex.get_selected_path()
		else: # right hand pane has focus
			while isinstance(child, gtk.Box):
				child = child.get_focus_child()
				if child == self.pathbar:
					logger.debug('Pathbar has focus')
					return self.pathbar.get_selected_path()
				elif child == self.pageview:
					logger.debug('Pageview has focus')
					return self.ui.page

			logger.debug('No path in focus mainwindow')
			return None

	def toggle_toolbar(self, show=None):
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

		self.uistate['show_toolbar'] = show

	def do_toolbar_popup(self, toolbar, x, y, button):
		'''Show the context menu for the toolbar'''
		menu = self.ui.uimanager.get_widget('/toolbar_popup')
		menu.popup(None, None, None, button, 0)

	def toggle_statusbar(self, show=None):
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

		self.uistate['show_statusbar'] = show

	def toggle_sidepane(self, show=None):
		action = self.actiongroup.get_action('toggle_sidepane')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_sidepane(show=show)

	def do_toggle_sidepane(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_sidepane')
			show = action.get_active()

		if show:
			self.pageindex.set_no_show_all(False)
			self.pageindex.show_all()
			self.hpane.set_position(self.uistate['sidepane_pos'])
			self.pageindex.grab_focus()
		else:
			self.uistate['sidepane_pos'] = self.hpane.get_position()
			self.pageindex.hide_all()
			self.pageindex.set_no_show_all(True)
			self.pageview.grab_focus()

		self.uistate['show_sidepane'] = show

	def set_pathbar(self, style):
		'''Set the pathbar. Style can be either PATHBAR_NONE,
		PATHBAR_RECENT, PATHBAR_HISTORY or PATHBAR_PATH.
		'''
		assert style in ('none', 'recent', 'history', 'path')
		self.actiongroup.get_action('set_pathbar_'+style).activate()

	def do_set_pathbar(self, action):
		name = action.get_name()
		style = name[12:] # len('set_pathbar_') == 12

		if style == PATHBAR_NONE:
			self.pathbar_box.hide()
			return
		elif style == PATHBAR_HISTORY:
			klass = zim.gui.pathbar.HistoryPathBar
		elif style == PATHBAR_RECENT:
			klass = zim.gui.pathbar.RecentPathBar
		elif style == PATHBAR_PATH:
			klass = zim.gui.pathbar.NamespacePathBar
		else:
			assert False, 'BUG: Unknown pathbar type %s' % style

		if not (self.pathbar and self.pathbar.__class__ == klass):
			for child in self.pathbar_box.get_children():
				self.pathbar_box.remove(child)
			self.pathbar = klass(self.ui, spacing=3)
			self.pathbar.set_history(self.ui.history)
			self.pathbar_box.add(self.pathbar)
		self.pathbar_box.show_all()

		self.uistate['pathbar_type'] = style

	def set_toolbar_style(self, style):
		'''Set the toolbar style. Style can be either
		TOOLBAR_ICONS_AND_TEXT, TOOLBAR_ICONS_ONLY or TOOLBAR_TEXT_ONLY.
		'''
		assert style in ('icons_and_text', 'icons_only', 'text_only'), style
		self.actiongroup.get_action('set_toolbar_'+style).activate()

	def do_set_toolbar_style(self, action):
		name = action.get_name()
		style = name[12:] # len('set_toolbar_') == 12

		if style == TOOLBAR_ICONS_AND_TEXT:
			self.toolbar.set_style(gtk.TOOLBAR_BOTH)
		elif style == TOOLBAR_ICONS_ONLY:
			self.toolbar.set_style(gtk.TOOLBAR_ICONS)
		elif style == TOOLBAR_TEXT_ONLY:
			self.toolbar.set_style(gtk.TOOLBAR_TEXT)
		else:
			assert False, 'BUG: Unkown toolbar style: %s' % style

		self.uistate['toolbar_style'] = style

	def set_toolbar_size(self, size):
		'''Set the toolbar style. Style can be either
		TOOLBAR_ICONS_LARGE, TOOLBAR_ICONS_SMALL or TOOLBAR_ICONS_TINY.
		'''
		assert size in ('large', 'small', 'tiny'), size
		self.actiongroup.get_action('set_toolbar_icons_'+size).activate()

	def do_set_toolbar_size(self, action):
		name = action.get_name()
		size = name[18:] # len('set_toolbar_icons_') == 18

		if size == TOOLBAR_ICONS_LARGE:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_LARGE_TOOLBAR)
		elif size == TOOLBAR_ICONS_SMALL:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_SMALL_TOOLBAR)
		elif size == TOOLBAR_ICONS_TINY:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_MENU)
		else:
			assert False, 'BUG: Unkown toolbar size: %s' % size

		self.uistate['toolbar_size'] = size


	def do_open_notebook(self, ui, notebook):
		# delayed till here because all this needs real uistate to be in place
		# also pathbar needs history in place
		self.uistate = ui.uistate['MainWindow']

		self.uistate.setdefault('windowsize', (600, 450), self.uistate.is_coord)
		w, h = self.uistate['windowsize']
		self.set_default_size(w, h)

		self.uistate.setdefault('show_sidepane', True)
		self.uistate.setdefault('sidepane_pos', 200)
		self.toggle_sidepane(show=self.uistate['show_sidepane'])

		self.uistate.setdefault('show_toolbar', True)
		self.toggle_toolbar(show=self.uistate['show_toolbar'])
		if 'toolbar_style' in self.uistate:
			self.set_toolbar_style(self.uistate['toolbar_style'])
		# else trust system default
		if 'toolbar_size' in self.uistate:
			self.set_toolbar_size(self.uistate['toolbar_size'])
		# else trust system default

		self.uistate.setdefault('show_statusbar', True)
		self.toggle_statusbar(show=self.uistate['show_statusbar'])

		self.uistate.setdefault('pathbar_type', PATHBAR_RECENT)
		self.set_pathbar(self.uistate['pathbar_type'])

	def do_open_page(self, ui, page, record):
		'''Signal handler for open-page, updates the pageview'''
		self.pageview.set_page(page)

		n = ui.notebook.index.n_list_links(page, zim.index.LINK_DIR_BACKWARD)
		label = self.statusbar_backlinks_button.label
		label.set_text_with_mnemonic(_('%i _Backlinks...') % n)
			# T: Label for button with backlinks in statusbar
		if n == 0:
			self.statusbar_backlinks_button.set_sensitive(False)
		else:
			self.statusbar_backlinks_button.set_sensitive(True)

	def do_close_page(self, ui, page):
		w, h = self.get_size()
		self.uistate['windowsize'] = (w, h)
		self.uistate['sidepane_pos'] = self.hpane.get_position()

	def do_textview_toggle_overwrite(self, view):
		state = view.get_overwrite()
		if state: text = 'OVR'
		else: text = 'INS'
		self.statusbar_insert_label.set_text(text)


class BackLinksMenuButton(MenuButton):

	def __init__(self, ui, status_bar_style=False):
		label = _('%i _Backlinks...') % 0
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

		for link in links:
			item = gtk.MenuItem(link.source.name)
			item.connect_object('activate', self.ui.open_page, link.source)
			self.menu.add(item)

		MenuButton.popup_menu(self, event)


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


def format_title(title):
	'''Formats a window title (in fact just adds " - Zim" to the end).'''
	assert not title.lower().endswith(' zim')
	return '%s - Zim' % title


class ErrorDialog(gtk.MessageDialog):

	def __init__(self, ui, error):
		'''Constructor. 'ui' can either be the main application or some
		other dialog from which the error originates. 'error' is the error
		object.
		'''
		self.error = error
		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_CLOSE,
			message_format=unicode(self.error)
		)
		# TODO set_secondary_text with details from error ?

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


class SavePageErrorDialog(ErrorDialog):
	'''Error dialog used when we hit an error while trying to save a page.
	Allow to save a copy or to discard changes. Includes a timer which
	delays the action buttons becoming sensitive. Reason for this timer is
	that the dialog may popup from auto-save while the user is typing, and
	we want to prevent an accidental action.
	'''

	def __init__(self, ui, error, page):
		title = _('Could not save page: %s') % page.name
			# T: Heading of error dialog
		explanation = _('''\
To continue you can save a copy of this page or discard
any changes. If you save a copy changes will be also
discarded, but you can restore the copy later.''')
		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_NONE,
			message_format=title
		)
		#~ self.set_default_size(450, -1)
		self.format_secondary_text(
			unicode(error).encode('utf-8').strip()+'\n\n'+explanation)

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
			page.get_parsetree() # make sure PageView understands we tried...
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

		try:
			id = gobject.timeout_add_seconds(1, timer, self)
		except AttributeError:
			# older gobject version doesn't know about seconds
			id = gobject.timeout_add(1000, timer, self)
		ErrorDialog.run(self)
		gobject.source_remove(id)


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


class Dialog(gtk.Dialog):
	'''Wrapper around gtk.Dialog used for most zim dialogs.
	It adds a number of convenience routines to build dialogs.
	The default behavior is modified in such a way that dialogs are
	destroyed on response if the response handler returns True.
	'''

	def __init__(self, ui, title, buttons=gtk.BUTTONS_OK_CANCEL):
		'''Constructor. 'ui' can either be the main application or some
		other dialog from which this dialog is spwaned. 'title' is the dialog
		title.
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

		if isinstance(ui, NotebookInterface) and ui.uistate:
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
		if buttons is None or buttons == gtk.BUTTONS_NONE:
			self._no_ok_action = True
		elif buttons == gtk.BUTTONS_OK_CANCEL:
			self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
			self.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
		elif buttons == gtk.BUTTONS_CLOSE:
			self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_OK)
			self._no_ok_action = True
		else:
			assert False, 'TODO - parse different button types'

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
		'string', 'page', 'namespace', 'dir', 'file' and 'image'.

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
			elif type in ('string', 'page', 'namespace', 'dir', 'file', 'image'):
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
		'''
		raise NotImplementedError


# Need to register classes defining gobject signals
gobject.type_register(Dialog)


class FileDialog(Dialog):
	'''File chooser dialog, adds a filechooser widget to Dialog.'''

	def __init__(self, ui, title, action=gtk.FILE_CHOOSER_ACTION_OPEN, **opts):
		Dialog.__init__(self, ui, title, **opts)
		if self.uistate['windowsize'] == (-1, -1):
			self.uistate['windowsize'] = (500, 400)
			self.set_default_size(500, 400)
		self.filechooser = gtk.FileChooserWidget(action=action)
		self.filechooser.set_do_overwrite_confirmation(True)
		self.filechooser.connect('file-activated', lambda o: self.response_ok())
		self.vbox.add(self.filechooser)
		# FIXME hook to expander to resize window

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


class OpenPageDialog(Dialog):
	'''Dialog to go to a specific page. Also known as the "Jump to" dialog.
	Prompts for a page name and navigate to that page on 'Ok'.
	'''

	def __init__(self, ui, namespace=None):
		Dialog.__init__(self, ui, _('Jump to')) # T: Dialog title
		self.add_fields([('name', 'page', _('Jump to Page'), None)])
			# T: Label for page input
		# TODO custom "jump to" button

	def do_response_ok(self):
		try:
			name = self.get_field('name')
			path = self.ui.notebook.resolve_path(name)
		except PageNameError, error:
			ErrorDialog(self, error).run()
			return False
		else:
			self.ui.open_page(path)
			return True


class NewPageDialog(Dialog):
	'''Dialog used to create a new page, functionally it is almost the same
	as the OpenPageDialog except that the page is saved directly in order
	to create it.
	'''

	def __init__(self, ui, namespace=None):
		Dialog.__init__(self, ui, _('New Page')) # T: Dialog title
		self.add_text(_('Please note that linking to a non-existing page\nalso creates a new page automatically.'))
			# T: Dialog text in 'new page' dialog
		self.add_fields([('name', 'page', _('Page Name'), None)]) # T: Input label
		self.set_help(':Help:Pages')

	def do_response_ok(self):
		try:
			name = self.get_field('name')
			path = self.ui.notebook.resolve_path(name)
		except PageNameError, error:
			ErrorDialog(self, error).run()
			return False
		else:
			page = self.ui.notebook.get_page(path)
			if page.hascontent or page.haschildren:
				ErrorDialog(self, _('Page exists')).run() # T: error message
				return False
			self.ui.open_page(page)
			self.ui.save_page()
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
		# TODO change "Ok" button to "Save"

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
		self.add_filter(_('Text Files'), '*.txt') # File filter for '*.txt'
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
		self.ui.noetbook.store_page(page)
		self.ui.open_page(page)
		return True


class MovePageDialog(Dialog):

	def __init__(self, ui, path=None):
		Dialog.__init__(self, ui, _('Move Page')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		if isinstance(self.path, Page) and self.path.modified:
			assert self.ui.save_page(self.path)

		self.vbox.add(gtk.Label(_('Move page "%s"') % self.path.name))
			# T: Heading in 'move page' dialog - %s is the page name
		self.add_fields([
			('parent', 'namespace', _('Namespace'), self.path.namespace),
				# T: Input label for namespace to move a file to
			('links', 'bool', _('Update links to this page'), True),
				# T: option in 'move page' dialog
		])

	def do_response_ok(self):
		parent = self.get_field('parent')
		links = self.get_field('links')
		try:
			newpath = self.ui.notebook.resolve_path(parent) + self.path.basename
			self.ui.notebook.move_page(self.path, newpath, update_links=links)
		except Exception, error:
			ErrorDialog(self, error).run()
			return False
		else:
			if self.path == self.ui.page:
				self.ui.open_page(newpath)
			return True

class RenamePageDialog(Dialog):

	def __init__(self, ui, path=None):
		Dialog.__init__(self, ui, _('Rename Page')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		self.vbox.add(gtk.Label(_('Rename page "%s"') % self.path.name))
		self.add_fields([
			('name', 'string', _('Name'), self.path.basename),
				# T: Input label in the 'rename page' dialog for the new name
			('head', 'bool', _('Update the heading of this page'), True),
				# T: Option in the 'rename page' dialog
			('links', 'bool', _('Update links to this page'), True),
				# T: Option in the 'rename page' dialog
		])

	def do_response_ok(self):
		name = self.get_field('name')
		head = self.get_field('head')
		links = self.get_field('links')
		try:
			newpath = self.ui.notebook.rename_page(self.path,
				newbasename=name, update_heading=head, update_links=links)
		except Exception, error:
			ErrorDialog(self, error).run()
			return False
		else:
			if self.path == self.ui.page:
				self.ui.open_page(newpath)
			return True


class DeletePageDialog(Dialog):

	def __init__(self, ui, path=None):
		Dialog.__init__(self, ui, _('Delete Page')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)
		img = gtk.image_new_from_stock(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_DIALOG)
		hbox.add(img)
		label = gtk.Label()
		short = _('Delete page "%s"?') % self.path.basename
			# T: Heading in 'delete page' dialog - %s is the page name
		long = _('Page "%s" and all of it\'s sub-pages and attachments will be deleted') % self.path.name
			# T: Text in 'delete page' dialog - %s is the page name
		label.set_markup('<b>'+short+'</b>\n\n'+long)
		hbox.add(label)

	def do_response_ok(self):
		try:
			self.ui.notebook.delete_page(self.path)
		except Exception, error:
			ErrorDialog(self, error).run()
			return False
		else:
			if self.path == self.ui.page:
				self.ui.open_page_back() \
				or self.ui.open_page_parent \
				or self.ui.open_page_home
			return True


class AttachFileDialog(FileDialog):

	def __init__(self, ui, path=None):
		FileDialog.__init__(self, ui, _('Attach File')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		self.dir = self.ui.notebook.get_attachments_dir(self.path)
		if self.dir is None:
			ErrorDialog(_('Page "%s" does not have a folder for attachments') % self.path)
				# T: Error dialog - %s is the full page name
			raise Exception, 'Page "%s" does not have a folder for attachments' % self.path

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False
		else:
			file.copyto(self.dir)
			file = self.dir.file(file.basename)
			mimetype = file.get_mimetype()
			pageview = self.ui.mainwindow.pageview
			if mimetype.media == 'image':
				try:
					pageview.insert_image(file, interactive=False)
				except:
					logger.exception('Could not insert image')
					pageview.insert_links([file]) # image type not supported?
			else:
				pageview.insert_links([file])
			return True


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
