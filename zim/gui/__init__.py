# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''


import gobject
import gtk

from zim import Application, Component
from zim.utils import data_file, config_file

import pageindex
import pageview


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
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-page': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT,) ),
	}

	def __init__(self, **opts):
		'''FIXME'''
		Application.__init__(self, **opts)
		self.window = None

		# set default icon for all windows
		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

	def main(self):
		'''FIXME'''
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

	def do_open_notebook(self, notebook):
		'''FIXME'''
		self.notebook = notebook

		# construct main window to show this notebook
		self.mainwindow = MainWindow(self)
		self.window = self.mainwindow.window

		# TODO load history and set intial page
		self.open_page(notebook.get_home_page())

	def open_page(self, page):
		'''FIXME'''
		assert self.notebook
		if isinstance(page, basestring):
			self.debug('Open page: %s' % page)
			page = self.notebook.get_page(page)
		else:
			self.debug('Open page: %s (object)' % page.name)
		self.emit('open-page', page)

	def do_open_page(self, page):
		'''FIXME'''
		self.page = page

# Need to register classes defining gobject signals
gobject.type_register(GtkApplication)


class MainWindow(gtk.Window, Component):
	'''FIXME'''

	def __init__(self, app):
		'''FIXME'''
		gtk.Window.__init__(self)

		self.app = app
		app.connect('open-page', self.do_open_page)

		self.set_default_size(600, 450)
		self.connect("destroy", self.destroy)
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


	def destroy(self, widget, data=None):
		'''FIXME'''
		# really destructive
		gtk.main_quit()

	def do_open_page(self, app, page):
		'''FIXME'''
		self.pageview.set_page(page)
