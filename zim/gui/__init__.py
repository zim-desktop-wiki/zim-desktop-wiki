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


menu_actions = (
	# name  stock id  label
	('FileMenu', None, '_File'),
	('EditMenu', None, '_Edit'),
	('ViewMenu', None, '_View'),
	('InsertMenu', None, '_Insert'),
	('SearchMenu', None, '_Search'),
	('FormatMenu', None, 'For_mat'),
	('ToolsMenu', None, '_Tools'),
	('GoMenu', None, '_Go'),
	('HelpMenu', None, '_Help'),
	('PathBarMenu', None, 'P_athbar type'),

	# name,   stock id, label,  accelerator, tooltip
	('NewPage',  'gtk-new', '_New Page', '<ctrl>N', 'New page'),
	('popup_NewPage', 'gtk-new', '_New Page', None, 'New page'),
	('OpenNotebook', 'gtk-open', '_Open Another Notebook...', '<ctrl>O', 'Open notebook'),
	('Save',  'gtk-save', '_Save', '<ctrl>S', 'Save page'),
	('SaveVersion', 'gtk-save-as', 'S_ave Version...', '<ctrl><shift>S', 'Save Version'),
	('Versions', None, '_Versions...', None, 'Versions'),
	('Export',  None, 'E_xport...', None, 'Export'),
	('EmailPage', None, '_Send To...', None, 'Mail page'),
	('CopyPage', None, '_Copy Page...', None, 'Copy page'),
	('popup_CopyPage', None, '_Copy Page...', None, 'Copy page'),
	('RenamePage', None, '_Rename Page...', 'F2', 'Rename page'),
	('popup_RenamePage', None, '_Rename Page...', None, 'Rename page'),
	('DeletePage', None, '_Delete Page', None, 'Delete page'),
	('popup_DeletePage', None, '_Delete Page', None, 'Delete page'),
	('Props',  'gtk-properties', 'Proper_ties', None, 'Properties dialog'),
	('Close',  'gtk-close', '_Close', '<ctrl>W', 'Close window'),
	('Quit',  'gtk-quit', '_Quit', '<ctrl>Q', 'Quit'),
	('Search',  'gtk-find', '_Search...', '<shift><ctrl>F', 'Search'),
	('SearchBL', None, 'Search _Backlinks...', None, 'Search Back links'),
	('CopyLocation', None, 'Copy Location', '<shift><ctrl>L', 'Copy location'),
	('Prefs',  'gtk-preferences', 'Pr_eferences', None, 'Preferences dialog'),
	('Reload',  'gtk-refresh', '_Reload', '<ctrl>R', 'Reload page'),
	('OpenFolder', 'gtk-open', 'Open Document _Folder', None, 'Open document folder'),
	('OpenRootFolder', 'gtk-open', 'Open Document _Root', None, 'Open document root'),
	('AttachFile', 'mail-attachment', 'Attach _File', None, 'Attach external file'),
	('EditSource', 'gtk-edit', 'Edit _Source', None, 'Open source'),
	('RBIndex', None, 'Re-build Index', None, 'Rebuild index'),
	('GoBack', 'gtk-go-back', '_Back', '<alt>Left', 'Go page back'),
	('GoForward', 'gtk-go-forward', '_Forward', '<alt>Right', 'Go page forward'),
	('GoParent', 'gtk-go-up', '_Parent', '<alt>Up', 'Go to parent page'),
	('GoChild', 'gtk-go-down', '_Child', '<alt>Down', 'Go to child page'),
	('GoPrev', None, '_Previous in index', '<alt>Page_Up', 'Go to previous page'),
	('GoNext', None, '_Next in index', '<alt>Page_Down', 'Go to next page'),
	('GoHome', 'gtk-home', '_Home', '<alt>Home', 'Go home'),
	('JumpTo', 'gtk-jump-to', '_Jump To...', '<ctrl>J', 'Jump to page'),
	('ShowHelp', 'gtk-help', '_Contents', 'F1', 'Help contents'),
	('ShowHelpFAQ', None, '_FAQ', None, 'FAQ'),
	('ShowHelpKeys', None, '_Keybindings', None, 'Key bindings'),
	('ShowHelpBugs', None, '_Bugs', None, 'Bugs'),
	('About', 'gtk-about', '_About', None, 'About'),
)

toggle_actions = (
	# name,  stock id, label,  accelerator, tooltip
	('TToolBar', None, '_Toolbar',  None, 'Show toolbar'),
	('TStatusBar', None, '_Statusbar', None, 'Show statusbar'),
	('TPane',  'gtk-index', '_Index', 'F9', 'Show index'),
)

radio_actions = (
	# name,  stock id, label,  accelerator, tooltip
	('PBRecent', None, '_Recent pages', None, None, 0),
	('PBHistory', None, '_History',  None, None, 1),
	('PBNamespace', None, '_Namespace', None, None, 2),
	('PBHidden', None, 'H_idden',  None, None, 3),
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

	def main(self):
		'''Wrapper for gtk.main(); does not return untill program has ended.'''
		if self.notebook is None:
			self.debug('No notebook given, starting notebookdialog')
			import notebookdialog
			notebookdialog.NotebookDialog(self).main()
			# notebookdialog should trigger open_notebook()

		if self.notebook is None:
			# Close application. Either the user cancelled the notebook dialog,
			# or the notebook was opened in a different process.
			return

		self.mainwindow.show_all()
		gtk.main()

	def open_notebook(self, notebook):
		'''Open a new notebook. If this is the first notebook the open-notebook
		signal is emitted and the notebook is opened in this process. Otherwise
		we let another instance handle it.'''
		if self.notebook is None:
			Application.open_notebook(self, notebook)
		else:
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

	def open_page(self, page):
		'''Emit the open-page signal.
		'page' can either be a page object or a page name
		'''
		assert self.notebook
		if isinstance(page, basestring):
			self.debug('Open page: %s' % page)
			page = self.notebook.get_page(page)
		else:
			self.debug('Open page: %s (object)' % page.name)
		self.emit('open-page', page)

	def do_open_page(self, page):
		'''Signal handler for open-page.'''
		self.page = page

	def dispatch_action(self, action):
		'''FIXME'''
		if isinstance(action, gtk.Action):
			action = action.get_property('name')
		else:
			assert isinstance(action, basestring)

		if action.endswith('Menu'):
			return # these occur when opening a menu, ignore silently
		else:
			self.debug('ACTION: ', action)
			try:
				method = getattr(self, action)
			except AttributeError:
				self.debug('No handler defined for action %s' % action)
			else:
				method()

	def NewPage(self):
		'''FIXME'''


	def OpenNotebook(self):
		'''FIXME'''
		import notebookdialog
		notebookdialog.NotebookDialog(self).main()

	def Save(self):
		'''FIXME'''


	def SaveVersion(self):
		'''FIXME'''


	def Versions(self):
		'''FIXME'''


	def Export(self):
		'''FIXME'''


	def EmailPage(self):
		'''FIXME'''


	def CopyPage(self):
		'''FIXME'''


	def RenamePage(self):
		'''FIXME'''


	def DeletePage(self):
		'''FIXME'''


	def Props(self):
		'''FIXME'''


	def Close(self):
		'''FIXME'''
		self.Quit()

	def Quit(self):
		'''FIXME'''
		self.mainwindow.destroy()
		gtk.main_quit()

	def Search(self):
		'''FIXME'''


	def SearchBL(self):
		'''FIXME'''


	def CopyLocation(self):
		'''FIXME'''


	def Prefs(self):
		'''FIXME'''


	def Reload(self):
		'''FIXME'''


	def OpenFolder(self):
		'''FIXME'''


	def OpenRootFolder(self):
		'''FIXME'''


	def AttachFile(self):
		'''FIXME'''


	def EditSource(self):
		'''FIXME'''


	def RBIndex(self):
		'''FIXME'''


	def GoBack(self):
		'''FIXME'''


	def GoForward(self):
		'''FIXME'''


	def GoParent(self):
		'''FIXME'''


	def GoChild(self):
		'''FIXME'''


	def GoPrev(self):
		'''FIXME'''


	def GoNext(self):
		'''FIXME'''


	def GoHome(self):
		'''FIXME'''


	def JumpTo(self):
		'''FIXME'''


	def ShowHelp(self):
		'''FIXME'''


	def ShowHelpFAQ(self):
		'''FIXME'''


	def ShowHelpKeys(self):
		'''FIXME'''


	def ShowHelpBugs(self):
		'''FIXME'''


	def About(self):
		'''FIXME'''


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
			self.debug('ACTION: Close (delete-event)')
			self.app.Close()
			return True
		self.connect('delete-event', do_delete_event)

		self.set_default_size(600, 450)
		vbox = gtk.VBox()
		self.add(vbox)

		# setup menubar and toolbar
		uimanager = gtk.UIManager()
		self.add_accel_group(uimanager.get_accel_group())

		actions = gtk.ActionGroup('Foo')
		actions.add_actions(menu_actions)
		actions.add_toggle_actions(toggle_actions)
		actions.add_radio_actions(radio_actions)
		uimanager.insert_action_group(actions, 0)

		for action in actions.list_actions():
				action.connect('activate', self.app.dispatch_action)

		uimanager.add_ui_from_file(data_file('menubar.xml').path)
		menubar = uimanager.get_widget('/MenuBar')
		toolbar = uimanager.get_widget('/ToolBar')
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
