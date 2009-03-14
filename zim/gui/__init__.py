# -*- coding: utf8 -*-

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

import zim
import zim.fs
from zim import NotebookInterface
from zim.notebook import Path, Page, PageNameError
from zim.config import data_file, config_file
import zim.history
import zim.gui.pathbar
import zim.gui.pageindex
import zim.gui.pageview

logger = logging.getLogger('zim.gui')

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
	('pathbar_menu', None, 'P_athbar'),
	('toolbar_menu', None, '_Toolbar'),

	# name, stock id, label, accelerator, tooltip
	('new_page',  'gtk-new', '_New Page', '<ctrl>N', 'New page'),
	('open_notebook', 'gtk-open', '_Open Another Notebook...', '<ctrl>O', 'Open notebook'),
	('import_page', None, '_Import Page', None, 'Import a file as a page'),
	('save_page', 'gtk-save', '_Save', '<ctrl>S', 'Save page'),
	('save_copy', None, 'Save a _Copy...', None, 'Save a copy'),
	('save_version', 'gtk-save-as', 'S_ave Version...', '<ctrl><shift>S', 'Save Version'),
	('show_versions', None, '_Versions...', None, 'Versions'),
	('show_export',  None, 'E_xport...', None, 'Export'),
	('email_page', None, '_Send To...', None, 'Mail page'),
	('move_page', None, '_Move Page...', None, 'Move page'),
	('rename_page', None, '_Rename Page...', 'F2', 'Rename page'),
	('delete_page', None, '_Delete Page', None, 'Delete page'),
	('show_properties',  'gtk-properties', 'Proper_ties', None, 'Properties dialog'),
	('close',  'gtk-close', '_Close', '<ctrl>W', 'Close window'),
	('quit',  'gtk-quit', '_Quit', '<ctrl>Q', 'Quit'),
	('show_search',  'gtk-find', '_Search...', '<shift><ctrl>F', 'Search'),
	('show_search_backlinks', None, 'Search _Backlinks...', None, 'Search Back links'),
	('copy_location', None, 'Copy Location', '<shift><ctrl>L', 'Copy location'),
	('show_plugins',  None, 'P_lugins', None, 'Plugins dialog'),
	('show_preferences',  'gtk-preferences', 'Pr_eferences', None, 'Preferences dialog'),
	('reload_page',  'gtk-refresh', '_Reload', '<ctrl>R', 'Reload page'),
	('open_attachments_folder', 'gtk-open', 'Open Document _Folder', None, 'Open document folder'),
	('open_documents_folder', 'gtk-open', 'Open Document _Root', None, 'Open document root'),
	('attach_file', 'mail-attachment', 'Attach _File', None, 'Attach external file'),
	('edit_page_source', 'gtk-edit', 'Edit _Source', None, 'Open source'),
	('show_server_gui', None, 'Start _Web Server', None, 'Start web server'),
	('reload_index', None, 'Re-build Index', None, 'Rebuild index'),
	('open_page_back', 'gtk-go-back', '_Back', '<alt>Left', 'Go page back'),
	('open_page_forward', 'gtk-go-forward', '_Forward', '<alt>Right', 'Go page forward'),
	('open_page_parent', 'gtk-go-up', '_Parent', '<alt>Up', 'Go to parent page'),
	('open_page_child', 'gtk-go-down', '_Child', '<alt>Down', 'Go to child page'),
	('open_page_previous', None, '_Previous in index', '<alt>Page_Up', 'Go to previous page'),
	('open_page_next', None, '_Next in index', '<alt>Page_Down', 'Go to next page'),
	('open_page_home', 'gtk-home', '_Home', '<alt>Home', 'Go home'),
	('open_page', 'gtk-jump-to', '_Jump To...', '<ctrl>J', 'Jump to page'),
	('show_help', 'gtk-help', '_Contents', 'F1', 'Help contents'),
	('show_help_faq', None, '_FAQ', None, 'FAQ'),
	('show_help_keys', None, '_Keybindings', None, 'Key bindings'),
	('show_help_bugs', None, '_Bugs', None, 'Bugs'),
	('show_about', 'gtk-about', '_About', None, 'About'),
)

ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, None, initial state
	('toggle_toolbar', None, '_Toolbar',  None, 'Show toolbar', None, True),
	('toggle_statusbar', None, '_Statusbar', None, 'Show statusbar', None, True),
	('toggle_sidepane',  'gtk-index', '_Index', 'F9', 'Show index', None, True),
)

ui_pathbar_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_pathbar_none', None, '_None',  None, None, 0),
	('set_pathbar_recent', None, '_Recent pages', None, None, 1),
	('set_pathbar_history', None, '_History',  None, None, 2),
	('set_pathbar_path', None, 'N_amespace', None, None, 3),
)

PATHBAR_NONE = 'none'
PATHBAR_RECENT = 'recent'
PATHBAR_HISTORY = 'history'
PATHBAR_PATH = 'path'

ui_toolbar_style_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_toolbar_icons_and_text', None, 'Icons _and Text', None, None, 0),
	('set_toolbar_icons_only', None, '_Icons Only', None, None, 1),
	('set_toolbar_text_only', None, '_Text Only', None, None, 2),
)

ui_toolbar_size_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_toolbar_icons_large', None, '_Large Icons', None, None, 0),
	('set_toolbar_icons_small', None, '_Small Icons', None, None, 1),
	('set_toolbar_icons_tiny', None, '_Tiny Icons', None, None, 2),
)

TOOLBAR_ICONS_AND_TEXT = 'icons_and_text'
TOOLBAR_ICONS_ONLY = 'icons_only'
TOOLBAR_TEXT_ONLY = 'text_only'

TOOLBAR_ICONS_LARGE = 'large'
TOOLBAR_ICONS_SMALL = 'small'
TOOLBAR_ICONS_TINY = 'tiny'


class GtkInterface(NotebookInterface):
	'''Main class for the zim Gtk interface. This object wraps a single
	notebook and provides actions to manipulate and access this notebook.

	Signals:
	* open-page (page, path)
	  Called when opening another page, see open_page() for details
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-page': (gobject.SIGNAL_RUN_LAST, None, (object, object))
	}

	ui_type = 'gtk'

	def __init__(self, notebook=None, page=None, **opts):
		NotebookInterface.__init__(self, **opts)
		self.page = None
		self.history = None
		self.load_config()

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

		self.load_plugins()

		if not notebook is None:
			self.open_notebook(notebook)

		if not page is None:
			assert notebook, 'Can not open page without notebook'
			self.open_page(page)

	def main(self):
		'''Wrapper for gtk.main(); does not return untill program has ended.'''
		if self.notebook is None:
			self.open_notebook()
			if self.notebook is None:
				# Close application. Either the user cancelled the notebook
				# dialog, or the notebook was opened in a different process.
				return

		self.uimanager.ensure_update()
			# prevent flashing when the toolbar is after showing the window
		self.mainwindow.show_all()
		self.mainwindow.pageview.grab_focus()
		gtk.main()

	def close(self):
		# TODO: logic to hide the window
		self.quit()

	def quit(self):
		self.mainwindow.destroy()
		gtk.main_quit()

	def add_actions(self, actions, handler):
		'''Wrapper for gtk.ActionGroup.add_actions(actions),
		"handler" is the object that has the methods for these actions.

		Each action is mapped to a like named method of the handler object.
		If the object not yet has an actiongroup this is created first,
		attached to the uimanager and put in the "actiongroup" attribute.
		'''
		group = self._init_actiongroup(handler)
		group.add_actions(actions)
		self._connect_actions(actions, group, handler)

	def add_toggle_actions(self, actions, handler):
		'''Wrapper for gtk.ActionGroup.add_toggle_actions(actions),
		"handler" is the object that has the methods for these actions.

		Differs for add-actions() in that in the mapping from action name
		to method name is prefixed with "do_". The reason for this is that
		in order to keep the state of toolbar andmenubar widgets stays in
		sync with the internal state. Therefore the method of the same name
		as the action should just call activate() on the action, while the
		actual logic is implamented in the handler which is prefixed with
		"do_".
		'''
		group = self._init_actiongroup(handler)
		group.add_toggle_actions(actions)
		self._connect_actions(actions, group, handler, is_toggle=True)

	def _init_actiongroup(self, handler):
		'''Initializes the actiongroup for handler if it does not already
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
			if is_toggle:
				name = 'do_' + name
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
		group = self._init_actiongroup(handler)
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

	def open_notebook(self, notebook=None):
		'''Open a new notebook. If this is the first notebook the open-notebook
		signal is emitted and the notebook is opened in this process. Otherwise
		we let another instance handle it. If notebook=None the notebookdialog
		is run to prompt the user.'''
		if notebook is None:
			# Handle menu item for open_notebook, prompt user. The notebook
			# dialog will call this method again after a selection is made.
			logger.debug('No notebook given, showing notebookdialog')
			import notebookdialog
			if self.mainwindow.get_property('visible'):
				# this dialog does not need to run modal
				notebookdialog.NotebookDialog(self).show_all()
			else:
				# main loop not yet started
				notebookdialog.NotebookDialog(self).run()
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
		self.notebook = notebook
		self.history = zim.history.History(notebook)

		self.notebook.index.update(background=True)

		# TODO load history and set intial page
		self.open_page_home()

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

	def open_page_back(self):
		record = self.history.get_previous()
		if not record is None:
			self.open_page(record)

	def open_page_forward(self):
		record = self.history.get_next()
		if not record is None:
			self.open_page(record)

	def open_page_parent(self):
		namespace = self.page.namespace
		if namespace:
			self.open_page(Path(namespace))

	def open_page_child(self):
		if not self.page.haschildren:
			return

		record = self.history.get_child(self.page)
		if not record is None:
			self.open_page(record)
		else:
			child = self.notebook.index.list_pages(self.page)[0]
			self.open_page(child)

	def open_page_previous(self):
		path = self.notebook.index.get_previous(self.page)
		if not path is None:
			self.open_page(path)

	def open_page_next(self):
		path = self.notebook.index.get_next(self.page)
		if not path is None:
			self.open_page(path)

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

	def save_page(self):
		pass

	def save_page_if_modified(self):
		pass

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
		self.save_page_if_modified()
		text = page.get_text(format='wiki')
		# TODO url encoding - replace \W with sprintf('%%%02x')
		url = 'mailto:?subject=%s&body=%s' % (page.name, text)
		# TODO open url

	def import_page(self):
		'''Import a file from outside the notebook as a new page.'''
		ImportPageDialog(self).run()

	def move_page(self, page=None):
		MovePageDialog(self, page=page).run()

	def rename_page(self, page=None):
		RenamePageDialog(self, page=page).run()

	def delete_page(self, page=None):
		if page is None:
			page = self.page
		# TODO confirmation dialog is MessageDialog style
		#~ self.notebook.delete_page(page)

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
		zim.gui.clipboard.Clipboard().set_pagelink(self.page)

	def show_plugins(self):
		import zim.gui.pluginsdialog
		zim.gui.pluginsdialog.PluginsDialog(self).run()

	def show_preferences(self):
		import zim.gui.preferencesdialog
		zim.gui.preferencesdialog.PreferencesDialog(self).run()

	def reload_page(self):
		self.save_page_if_modified()
		self.open_page(self.page)

	def attach_file(self):
		pass

	def open_attachments_folder(self):
		pass

	def open_documents_folder(self):
		pass

	def edit_page_source(self):
		pass

	def show_server_gui(self):
		self.spawn('zim', '--server', '--gui', self.notebook.name)

	def reload_index(self):
		self.notebook.index.update(fullcheck=True)
		# TODO use callback argument to present a progressbar

	def show_help(self, page=None):
		if page:
			self.spawn('zim', '--manual', page)
		else:
			self.spawn('zim', '--manual')

	def show_help_faq(self):
		self.show_help('FAQ')

	def show_help_keys(self):
		self.show_help('Usage:KeyBindings')

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
		dialog.set_comments('A desktop wiki')
		dialog.set_copyright(zim.__copyright__)
		dialog.set_license(zim.__license__)
		dialog.set_authors([zim.__author__])
		#~ dialog.set_translator_credits(_('translator-credits')) # FIXME
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

		# Catching this signal prevents the window to actually be destroyed
		# when the user tries to close it. The action for close should either
		# hide or destroy the window.
		def do_delete_event(*a):
			logger.debug('Action: close (delete-event)')
			ui.close()
			return True
		self.connect('delete-event', do_delete_event)

		self.set_default_size(600, 450)
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
		hpane = gtk.HPaned()
		hpane.set_position(175)
		vbox.add(hpane)
		self.pageindex = zim.gui.pageindex.PageIndex(ui)
		hpane.add1(self.pageindex)

		self.pageindex.connect('key-press-event',
			lambda o, event: event.keyval == gtk.keysyms.Escape
				and logger.debug('TODO: hide side pane'))

		vbox2 = gtk.VBox()
		hpane.add2(vbox2)

		self.pathbar = None
		self.pathbar_box = gtk.HBox() # FIXME other class for this ?
		self.pathbar_box.set_border_width(3)
		vbox2.pack_start(self.pathbar_box, False)

		self.pageview = zim.gui.pageview.PageView(ui)
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

		def statusbar_element(string, size, eventbox=False):
			frame = gtk.Frame()
			frame.set_shadow_type(gtk.SHADOW_IN)
			self.statusbar.pack_end(frame, False)
			label = gtk.Label(string)
			label.set_size_request(size, 10)
			label.set_alignment(0.1, 0.5)
			if eventbox:
				box = gtk.EventBox()
				box.add(label)
				frame.add(box)
			else:
				frame.add(label)
			return label

		# specify statusbar elements right-to-left
		self.style_label = statusbar_element('<style>', 100)
		self.insert_label = statusbar_element('INS', 60)
		self.backlinks_label = statusbar_element('<backlinks>', 120, True)

		# add a second statusbar widget - somehow the corner grip
		# does not render properly after the pack_end for the first one
		#~ statusbar2 = gtk.Statusbar()
		#~ statusbar2.set_size_request(25, 10)
		#~ hbox.pack_end(statusbar2, False)

	def toggle_toolbar(self):
		self.actiongroup.get_action('toggle_toolbar').activate()

	def do_toggle_toolbar(self):
		if self.toolbar.get_property('visible'):
			self.toolbar.hide()
		else:
			self.toolbar.show()

	def do_toolbar_popup(self, toolbar, x, y, button):
		'''Show the context menu for the toolbar'''
		menu = self.ui.uimanager.get_widget('/toolbar_popup')
		menu.popup(None, None, None, button, 0)

	def toggle_statusbar(self):
		self.actiongroup.get_action('toggle_statusbar').activate()

	def do_toggle_statusbar(self):
		if self.statusbar.get_property('visible'):
			self.statusbar.hide()
		else:
			self.statusbar.show()

	def toggle_sidepane(self):
		self.actiongroup.get_action('toggle_sidepane').activate()

	def do_toggle_sidepane(self):
		if self.pageindex.get_property('visible'):
			self.hide_sidepane()
		else:
			self.show_sidepane()

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
			self.pathbar_box.pack_start(self.pathbar, False)
		self.pathbar_box.show_all()

	def set_toolbar_style(self, style):
		'''Set the toolbar style. Style can be either
		TOOLBAR_ICONS_AND_TEXT, TOOLBAR_ICONS_ONLY or TOOLBAR_TEXT_ONLY.
		'''
		assert style in ('icons_and_text', 'icons_only', 'text_only')
		self.actiongroup.get_action('set_toolbar_style_'+style).activate()

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

	def set_toolbar_size(self, size):
		'''Set the toolbar style. Style can be either
		TOOLBAR_ICONS_LARGE, TOOLBAR_ICONS_SMALL or TOOLBAR_ICONS_TINY.
		'''
		assert size in ('large', 'small', 'tiny')
		self.actiongroup.get_action('set_toolbar_size_'+size).activate()

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

	def show_sidepane(self):
		self.pageindex.show_all()
		# TODO restore pane position
		self.pageindex.grab_focus()
		# TODO action_show_active('toggle_sidepane', True)

	def hide_sidepane(self):
		# TODO save pane position
		self.pageindex.hide_all()
		self.pageview.grab_focus()
		# TODO action_show_active('toggle_sidepane', False)

	def do_open_notebook(self, ui, notebook):
		# delayed till here because the pathbar needs the history to be in place
		self.set_pathbar(PATHBAR_RECENT) # TODO get this from preferences

	def do_open_page(self, ui, page, record):
		'''Signal handler for open-page, updates the pageview'''
		self.pageview.set_page(page)

		self.statusbar.pop(0)
		self.statusbar.push(0, page.name)
		# TODO set backlinks label

		self.pageview.view.get_buffer().connect(
			'textstyle-changed', lambda o, s: self.style_label.set_text(s))

	def do_textview_toggle_overwrite(self, view):
		state = view.get_overwrite()
		if state: text = 'OVR'
		else: text = 'INS'
		self.insert_label.set_text(text)


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
		logger.error(self.error)
		gtk.MessageDialog.run(self)
		self.destroy()


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
		self.inputs = {}
		gtk.Dialog.__init__(
			self, parent=get_window(self.ui),
			title=format_title(title),
			flags=gtk.DIALOG_NO_SEPARATOR,
		)
		self.set_border_width(10)
		self.vbox.set_spacing(5)

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

	def add_fields(self, fields, table=None):
		'''Add a number of fields to the dialog, convenience method to
		construct simple forms. The argument 'fields' should be a list of
		field definitions; each definition is a tupple of:

			* The field name
			* The field type (e.g. 'page')
			* The label to put in front of the input field
			* The initial value of the field

		If 'table' is specified the fields are added to that table, otherwise
		a new table is constructed and added to the dialog. Returns the table
		to allow building a form in multiple calls.
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
			label = gtk.Label(label+':')
			label.set_alignment(0.0, 0.5)
			table.attach(label, 0,1, i,i+1, xoptions=gtk.FILL)
			entry = gtk.Entry()
			if not value is None:
				entry.set_text(value)
			self.inputs[name] = entry
			table.attach(entry, 1,2, i,i+1)
			i += 1

		# TODO: hook last field to call response 'Ok' on activate

		return table

	def get_field(self, name):
		'''Returns the value of a single field'''
		return self.get_fields()[name]

	def get_fields(self):
		'''Returns a dict with values of the fields.'''
		values = {}
		for name, entry in self.inputs.items():
			values[name] = entry.get_text()
		return values

	def run(self):
		'''Calls show_all() followed by gtk.Dialog.run()'''
		self.show_all()
		gtk.Dialog.run(self)

	def show_all(self):
		'''Logs debug info and calls gtk.Dialog.show_all()'''
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
		if id == gtk.RESPONSE_OK:
			logger.debug('Dialog response OK')
			close = self.do_response_ok()
		else:
			close = True

		if close:
			self.destroy()
			logger.debug('Closed dialog "%s"', self.title[:-6])

	def do_response_ok(self):
		'''Function to be overloaded in child classes. Called when the
		user clicks the 'Ok' button or the equivalent of such a button.
		'''
		if self._no_ok_action:
			return True
		else:
			raise NotImplementedError


# Need to register classes defining gobject signals
gobject.type_register(Dialog)


class FileDialog(Dialog):
	'''File chooser dialog, adds a filechooser widget to Dialog.'''

	def __init__(self, ui, title, action=gtk.FILE_CHOOSER_ACTION_OPEN, **opts):
		Dialog.__init__(self, ui, title, **opts)
		self.filechooser = gtk.FileChooserWidget(action=action)
		self.filechooser.connect('file-activated', lambda o: self.response_ok())
		self.vbox.add(self.filechooser)
		# FIXME hook to expander to resize window


class OpenFileDialog(FileDialog):

	def __init__(self, ui, title='Select File'):
		FileDialog.__init__(self, ui, title)

	def get_filename(self):
		'''Run the dialog and return the filename directly.'''
		response = self.run()
		if response == gtk.RESPONSE_OK:
			return self.filechooser.get_filename()
		else:
			return None

	def do_response_ok(self):
		return True


class OpenPageDialog(Dialog):
	'''Dialog to go to a specific page. Also known as the "Jump to" dialog.
	Prompts for a page name and navigate to that page on 'Ok'.
	'''

	def __init__(self, ui):
		Dialog.__init__(self, ui, 'Jump to')
		self.add_fields([('name', 'page', 'Jump to Page', None)])
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


class NewPageDialog(OpenPageDialog):
	'''Dialog used to create a new page, functionally it is almost the same
	as the OpenPageDialog except that the page is saved directly in order
	to create it.
	'''

	def __init__(self, ui):
		Dialog.__init__(self, ui, 'New Page')
		self.add_text('Please note that linking to a non-existing page\nalso creates a new page automatically.')
		self.add_fields([('name', 'page', 'Page Name', None)])
		self.set_help(':Usage:Pages')

	def do_response_ok(self):
		ok = OpenPageDialog.do_response_ok(self)
		if ok and not self.ui.page.exists():
			self.ui.save_page()
		return ok


class SaveCopyDialog(FileDialog):

	def __init__(self, ui):
		FileDialog.__init__(self, ui, 'Save Copy', gtk.FILE_CHOOSER_ACTION_SAVE)
		self.filechooser.set_current_name(self.ui.page.name + '.txt')
		# TODO add droplist with native formats to choose + hook filters
		# TODO change "Ok" button to "Save"

	def do_response_ok(self):
		self.ui.save_page_if_modified()
		path = self.filechooser.get_filename()
		format = 'wiki'
		logger.info("Saving a copy at %s using format '%s'", path, format)
		text = self.ui.page.get_text(format)
		file = zim.fs.File(path)
		file.write(text)
		return True


class ImportPageDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, 'Import Page')
		# TODO add input for filename, pagename, namespace, file type

	# TODO trigger file selection menu directly on run()


class MovePageDialog(Dialog):

	def __init__(self, ui, page=None):
		Dialog.__init__(self, ui, 'Move Page')
		if page is None:
			self.page = self.ui.page
		else:
			self.page = page
		# TODO Add namespace selector

	def do_response_ok(self):
		namespace = self.get_field('namespace')
		self.ui.notebook.move_page(self.page, namespace)


class RenamePageDialog(Dialog):

	def __init__(self, ui, page=None):
		Dialog.__init__(self, ui, 'Rename Page')
		if page is None:
			self.page = self.ui.page
		else:
			self.page = page
		# TODO add name input

	def do_response_ok(self):
		name = self.get_field('name')
		self.ui.notebook.rename_page(self.page, name)

