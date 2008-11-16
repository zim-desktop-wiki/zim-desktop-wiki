# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains the Gtk user interface for zim.
The main components and dialogs are seperated out in sub-modules.
Included here are the application class for the zim GUI and the main window.
'''

import sys
import os
import gobject
import gtk

from zim import Application, Component
from zim.utils import data_file, config_file
from zim.gui import pageindex, pageview

# First we define all menu items specifying icons, labels and keybindings.
# For each of these items (except the one ending in _menu) a like named method
# should be defined in the main application object.
ui_actions = (
	('file_menu', None, '_File'),
	('edit_menu', None, '_Edit'),
	('view_menu', None, '_View'),
	('insert_menu', None, '_Insert'),
	('search_menu', None, '_Search'),
	('format_menu', None, 'For_mat'),
	('tools_menu', None, '_Tools'),
	('go_menu', None, '_Go'),
	('help_menu', None, '_Help'),
	('path_bar_menu', None, 'P_athbar type'),

	# name, stock id, label, accelerator, tooltip
	('new_page',  'gtk-new', '_New Page', '<ctrl>N', 'New page'),
	('popup_new_page', 'gtk-new', '_New Page', None, 'New page'),
	('open_notebook', 'gtk-open', '_Open Another Notebook...', '<ctrl>O', 'Open notebook'),
	('save_page', 'gtk-save', '_Save', '<ctrl>S', 'Save page'),
	('save_version', 'gtk-save-as', 'S_ave Version...', '<ctrl><shift>S', 'Save Version'),
	('show_versions', None, '_Versions...', None, 'Versions'),
	('show_export',  None, 'E_xport...', None, 'Export'),
	('email_page', None, '_Send To...', None, 'Mail page'),
	('copy_page', None, '_Copy Page...', None, 'Copy page'),
	('popup_copy_page', None, '_Copy Page...', None, 'Copy page'),
	('rename_page', None, '_Rename Page...', 'F2', 'Rename page'),
	('popup_rename_page', None, '_Rename Page...', None, 'Rename page'),
	('delete_page', None, '_Delete Page', None, 'Delete page'),
	('popup_delete_page', None, '_Delete Page', None, 'Delete page'),
	('show_properties',  'gtk-properties', 'Proper_ties', None, 'Properties dialog'),
	('close',  'gtk-close', '_Close', '<ctrl>W', 'Close window'),
	('quit',  'gtk-quit', '_Quit', '<ctrl>Q', 'Quit'),
	('show_search',  'gtk-find', '_Search...', '<shift><ctrl>F', 'Search'),
	('show_search_backlinks', None, 'Search _Backlinks...', None, 'Search Back links'),
	('copy_location', None, 'Copy Location', '<shift><ctrl>L', 'Copy location'),
	('show_preferences',  'gtk-preferences', 'Pr_eferences', None, 'Preferences dialog'),
	('reload_page',  'gtk-refresh', '_Reload', '<ctrl>R', 'Reload page'),
	('open_attachments_folder', 'gtk-open', 'Open Document _Folder', None, 'Open document folder'),
	('open_documents_folder', 'gtk-open', 'Open Document _Root', None, 'Open document root'),
	('attach_file', 'mail-attachment', 'Attach _File', None, 'Attach external file'),
	('edit_page_source', 'gtk-edit', 'Edit _Source', None, 'Open source'),
	('reload_index', None, 'Re-build Index', None, 'Rebuild index'),
	('go_page_back', 'gtk-go-back', '_Back', '<alt>Left', 'Go page back'),
	('go_page_forward', 'gtk-go-forward', '_Forward', '<alt>Right', 'Go page forward'),
	('go_page_parent', 'gtk-go-up', '_Parent', '<alt>Up', 'Go to parent page'),
	('go_page_child', 'gtk-go-down', '_Child', '<alt>Down', 'Go to child page'),
	('go_page_prev', None, '_Previous in index', '<alt>Page_Up', 'Go to previous page'),
	('go_page_next', None, '_Next in index', '<alt>Page_Down', 'Go to next page'),
	('go_page_home', 'gtk-home', '_Home', '<alt>Home', 'Go home'),
	('open_page', 'gtk-jump-to', '_Jump To...', '<ctrl>J', 'Jump to page'),
	('show_help', 'gtk-help', '_Contents', 'F1', 'Help contents'),
	('show_help_faq', None, '_FAQ', None, 'FAQ'),
	('show_help_keys', None, '_Keybindings', None, 'Key bindings'),
	('show_help_bugs', None, '_Bugs', None, 'Bugs'),
	('show_about', 'gtk-about', '_About', None, 'About'),
)

ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip
	('toggle_toolbar', None, '_Toolbar',  None, 'Show toolbar'),
	('toggle_statusbar', None, '_Statusbar', None, 'Show statusbar'),
	('toggle_sidepane',  'gtk-index', '_Index', 'F9', 'Show index'),
)

ui_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_pathbar_recent', None, '_Recent pages', None, None, 0),
	('set_pathbar_history', None, '_History',  None, None, 1),
	('set_pathbar_namespace', None, '_Namespace', None, None, 2),
	('set_pathbar_hidden', None, 'H_idden',  None, None, 3),
)


class GtkApplication(Application, Component):
	'''Appliction object for the zim GUI. This object wraps a single notebook
	and provides actions to manipulate and access this notebook.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-page': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT,) ),
	}

	def __init__(self, **opts):
		'''Constructor'''
		Application.__init__(self, **opts)
		self.window = None

		# set default icon for all windows
		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

	def dispatch_action(self, action):
		'''Default handler for ui actions. Argument should be a gtk.Action
		object. Will call the like named method on this object.
		'''
		assert isinstance(action, gtk.Action)
		action = action.get_property('name')
		if action.endswith('_menu'):
			pass # these occur when opening a menu, ignore silently
		else:
			self.debug('ACTION: ', action)
			try:
				method = getattr(self, action)
			except AttributeError:
				self.debug('BUG: No handler defined for action %s' % action)
			else:
				method()

	def main(self):
		'''Wrapper for gtk.main(); does not return untill program has ended.'''
		if self.notebook is None:
			self.open_notebook()
			if self.notebook is None:
				# Close application. Either the user cancelled the notebook
				# dialog, or the notebook was opened in a different process.
				return

		self.mainwindow.show_all()
		gtk.main()

	def close(self):
		# TODO: logic to hide the window
		self.quit()

	def quit(self):
		self.mainwindow.destroy()
		gtk.main_quit()

	def open_notebook(self, notebook=None):
		'''Open a new notebook. If this is the first notebook the open-notebook
		signal is emitted and the notebook is opened in this process. Otherwise
		we let another instance handle it. If notebook=None the notebookdialog
		is run to prompt the user.'''
		if notebook is None:
			# Handle menu item for open_notebook, prompt user. The notebook
			# dialog will call this method again after a selection is made.
			self.debug('No notebook given, showing notebookdialog')
			import notebookdialog
			notebookdialog.NotebookDialog(self).main()
		elif self.notebook is None:
			# No notebook has been set, so we open this notebook ourselfs
			# TODO also check if notebook was open through demon before going here
			self.debug('Open notebook:', notebook)
			Application.open_notebook(self, notebook)
		else:
			# We are already intialized, let another process handle it
			# TODO get rid of sys here - put argv[0] in Application object
			# TODO put this in the same package as the daemon code
			self.debug('Spawning new process: %s %s' % (sys.argv[0], notebook))
			os.spawnlp(os.P_NOWAIT, sys.argv[0], sys.argv[0], notebook)

	def do_open_notebook(self, notebook):
		'''Signal handler for open-notebook. Initializes the main window.'''
		self.notebook = notebook

		# construct main window to show this notebook
		self.mainwindow = MainWindow(self)
		self.window = self.mainwindow.window

		# TODO load history and set intial page
		self.open_page(notebook.get_home_page())

	def open_page(self, page=None):
		'''Emit the open-page signal. The argument 'page' can either be a page
		object or a page name. If 'page' is None a dialog is shown to
		specify the page.
		'''
		assert self.notebook
		if page is None:
			print 'TODO: show JumpTo dialog'
			return

		if isinstance(page, basestring):
			self.debug('Open page: %s' % page)
			page = self.notebook.get_page(page)
		else:
			self.debug('Open page: %s (object)' % page.name)
		self.emit('open-page', page)

	def do_open_page(self, page):
		'''Signal handler for open-page.'''
		self.page = page

	def new_page(self):
		pass

	def popup_new_page(self):
		pass

	def save_page(self):
		pass

	def save_version(self):
		pass

	def show_versions(self):
		pass

	def show_export(self):
		pass

	def email_page(self):
		pass

	def copy_page(self):
		pass

	def popup_copy_page(self):
		pass

	def rename_page(self):
		pass

	def popup_rename_page(self):
		pass

	def delete_page(self):
		pass

	def popup_delete_page(self):
		pass

	def show_properties(self):
		pass

	def show_search(self):
		pass

	def show_search_backlinks(self):
		pass

	def copy_location(self):
		pass

	def show_preferences(self):
		pass

	def reload_page(self):
		pass

	def open_attachments_folder(self):
		pass

	def open_documents_folder(self):
		pass

	def attach_file(self):
		pass

	def edit_page_source(self):
		pass

	def reload_index(self):
		pass

	def go_page_back(self):
		pass

	def go_page_forward(self):
		pass

	def go_page_parent(self):
		pass

	def go_page_child(self):
		pass

	def go_page_prev(self):
		pass

	def go_page_next(self):
		pass

	def go_page_home(self):
		pass

	def show_help(self):
		pass

	def show_help_faq(self):
		pass

	def show_help_keys(self):
		pass

	def show_help_bugs(self):
		pass

	def show_about(self):
		pass


# Need to register classes defining gobject signals
gobject.type_register(GtkApplication)


class MainWindow(gtk.Window, Component):
	'''Main window of the application, showing the page index in the side
	pane and a pageview with the current page. Alse includes the menubar,
	toolbar, statusbar etc.
	'''

	def __init__(self, app):
		'''Constructor'''
		gtk.Window.__init__(self)

		self.app = app
		app.connect('open-page', self.do_open_page)

		# Catching this signal prevents the window to actually be destroyed
		# when the user tries to close it. The action for close should either
		# hide or destroy the window.
		def do_delete_event(*a):
			self.debug('ACTION: close (delete-event)')
			self.app.close()
			return True
		self.connect('delete-event', do_delete_event)

		self.set_default_size(600, 450)
		vbox = gtk.VBox()
		self.add(vbox)

		# setup menubar and toolbar
		uimanager = gtk.UIManager()
		self.add_accel_group(uimanager.get_accel_group())

		actions = gtk.ActionGroup('Foo') # FIXME
		actions.add_actions(ui_actions)
		actions.add_toggle_actions(ui_toggle_actions)
		actions.add_radio_actions(ui_radio_actions)
		uimanager.insert_action_group(actions, 0)

		for action in actions.list_actions():
				action.connect('activate', self.app.dispatch_action)

		uimanager.add_ui_from_file(data_file('menubar.xml').path)
		menubar = uimanager.get_widget('/menubar')
		toolbar = uimanager.get_widget('/toolbar')
		vbox.pack_start(menubar, False)
		vbox.pack_start(toolbar, False)

		# construct side pane and editor
		hpane = gtk.HPaned()
		hpane.set_position(175)
		vbox.add(hpane)
		self.pageindex = pageindex.PageIndex()
		hpane.add1(self.pageindex)

		self.pageindex.connect('page-activated',
			lambda index, pagename: self.app.open_page(pagename) )

		self.pageindex.set_pages( self.app.notebook.get_root() )

		# TODO pathbar

		self.pageview = pageview.PageView()
		hpane.add2(self.pageview)

		# create statusbar
		statusbar = gtk.Statusbar()
		vbox.pack_start(statusbar, False, True, False)
		# TODO label current style
		# TODO event box backlinks

	def do_open_page(self, app, page):
		'''Signal handler for open-page, updates the pageview'''
		self.pageview.set_page(page)
