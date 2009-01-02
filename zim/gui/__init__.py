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
from zim import NotebookInterface
from zim.notebook import PageNameError
from zim.utils import data_file, config_file
from zim.gui import pageindex, pageview

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
	('path_bar_menu', None, 'P_athbar type'),

	# name, stock id, label, accelerator, tooltip
	('new_page',  'gtk-new', '_New Page', '<ctrl>N', 'New page'),
	('open_notebook', 'gtk-open', '_Open Another Notebook...', '<ctrl>O', 'Open notebook'),
	('save_page', 'gtk-save', '_Save', '<ctrl>S', 'Save page'),
	('save_version', 'gtk-save-as', 'S_ave Version...', '<ctrl><shift>S', 'Save Version'),
	('show_versions', None, '_Versions...', None, 'Versions'),
	('show_export',  None, 'E_xport...', None, 'Export'),
	('email_page', None, '_Send To...', None, 'Mail page'),
	('copy_page', None, '_Copy Page...', None, 'Copy page'),
	('rename_page', None, '_Rename Page...', 'F2', 'Rename page'),
	('delete_page', None, '_Delete Page', None, 'Delete page'),
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
	('toggle_sidepane',  'gtk-index', '_Index', 'F9', 'Show index', None, False),
)

ui_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_pathbar_recent', None, '_Recent pages', None, None, 0),
	('set_pathbar_history', None, '_History',  None, None, 1),
	('set_pathbar_namespace', None, '_Namespace', None, None, 2),
	('set_pathbar_hidden', None, 'H_idden',  None, None, 3),
)


class GtkInterface(NotebookInterface):
	'''Main class for the zim Gtk interface. This object wraps a single
	notebook and provides actions to manipulate and access this notebook.

	Signals:
	* open-page (page, historyrecord)
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
		self.add_radio_actions(ui_radio_actions, self.mainwindow)
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

	def add_radio_actions(self, actions, handler):
		'''Wrapper for gtk.ActionGroup.add_radio_actions(actions),
		"handler" is the object that has the methods for these actions.
		'''
		group = self._init_actiongroup(handler)
		group.add_radio_actions(actions)
		self._connect_actions(actions, group, handler)

	def _init_actiongroup(self, handler):
		'''Initializes the actiongroup for handler if it does not already
		exist and returns the actiongroup.
		'''
		if not hasattr(handler, 'actiongroup') or handler.actiongroup is None:
			name = handler.__class__.__name__
			handler.actiongroup = gtk.ActionGroup(name)
			self.uimanager.insert_action_group(handler.actiongroup, 0)
		return handler.actiongroup

	def _connect_actions(self, actions, group, handler, is_toggle=False):
		def log_action(action):
			logger.debug('Action: %s', action.get_name())

		for name in [a[0] for a in actions if not a[0].endswith('_menu')]:
			action = group.get_action(name)
			if is_toggle:
				name = 'do_' + name
			assert hasattr(handler, name), 'No method defined for action %s' % name
			method = getattr(handler.__class__, name)
			action.connect('activate', log_action)
			action.connect_object('activate', method, handler)

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
			logger.debug('Open notebook: %s', notebook)
			NotebookInterface.open_notebook(self, notebook)
		else:
			# We are already intialized, let another process handle it
			# TODO put this in the same package as the daemon code
			self.spawn('zim', notebook)

	def do_open_notebook(self, notebook):
		'''Signal handler for open-notebook.'''
		self.notebook = notebook
		self.history = notebook.get_history()

		# TODO load history and set intial page
		self.open_page_home()

	def open_page(self, page=None, historyrecord=None):
		'''Emit the open-page signal. The argument 'page' can either be a page
		object or an absolute page name. If 'page' is None a dialog is shown
		to specify the page. The 'historyrecord' argument is used to pass a
		position in the history for the page, if this is None the page will be
		appended to the history.
		'''
		assert self.notebook
		if page is None:
			# the dialog will call us in turn with an argument
			return OpenPageDialog(self).run()

		if isinstance(page, basestring):
			logger.debug('Open page: %s', page)
			page = self.notebook.get_page(page)
		else:
			logger.debug('Open page: %s (object)', page.name)
		self.emit('open-page', page, historyrecord)

	def do_open_page(self, page, historyrecord):
		'''Signal handler for open-page.'''
		is_first_page = self.page is None
		self.page = page

		back = self.actiongroup.get_action('open_page_back')
		forward = self.actiongroup.get_action('open_page_forward')
		parent = self.actiongroup.get_action('open_page_parent')
		child = self.actiongroup.get_action('open_page_child')

		if historyrecord is None:
			self.history.append(page)
			back.set_sensitive(not is_first_page)
			forward.set_sensitive(False)
		else:
			self.history.set_current(historyrecord)
			back.set_sensitive(not historyrecord.is_first())
			forward.set_sensitive(not historyrecord.is_last())

		parent.set_sensitive(len(page.namespace) > 0)
		child.set_sensitive(not page.children is None)

	def open_page_back(self):
		record = self.history.get_previous()
		if not record is None:
			self.open_page(record.name, record)

	def open_page_forward(self):
		record = self.history.get_next()
		if not record is None:
			self.open_page(record.name, record)

	def open_page_parent(self):
		namespace = self.page.namespace
		if len(namespace) > 1: # not just ":"
			self.open_page(namespace)

	def open_page_child(self):
		if not self.page.children:
			return

		record = self.history.get_child(self.page)
		if not record is None:
			self.open_page(record.name, record)
		else:
			child = self.page.children[0]
			self.open_page(child)

	def open_page_previous(self):
		page = self.notebook.get_previous(self.page)
		if not page is None:
			self.open_page(page)

	def open_page_next(self):
		page = self.notebook.get_next(self.page)
		if not page is None:
			self.open_page(page)

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
		self.save_page_if_modified()
		text = page.get_text(format='wiki')
		# TODO url encoding - replace \W with sprintf('%%%02x')
		url = 'mailto:?subject=%s&body=%s' % (page.name, text)
		# TODO open url

	def save_page_if_modified(self):
		pass

	def save_version(self):
		pass

	def show_versions(self):
		import zim.gui.versionsdialog
		zim.gui.versionsdialog.VersionDialog(self).run()

	def show_export(self):
		import zim.gui.exportdialog
		zim.gui.exportdialog.ExportDialog(self).run()

	def email_page(self):
		pass

	def copy_page(self):
		pass

	def rename_page(self):
		pass

	def delete_page(self):
		pass

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
		pass

	def show_preferences(self):
		import zim.gui.preferencesdialog
		zim.gui.preferencesdialog.PreferencesDialog(self).run()

	def reload_page(self):
		self.save_page_if_modified()
		self.open_page(self.page.name)

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
		# TODO flush cache
		self.mainwindow.pageindex.set_pages(self.notebook.get_root())

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

		ui.connect('open-notebook', self.do_open_notebook)
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
		vbox.pack_start(self.menubar, False)
		vbox.pack_start(self.toolbar, False)

		# split window in side pane and editor
		hpane = gtk.HPaned()
		hpane.set_position(175)
		vbox.add(hpane)
		self.pageindex = pageindex.PageIndex(ui)
		hpane.add1(self.pageindex)
		# TODO start with hidden path index, fill data only when needed

		self.pageindex.connect('key-press-event',
			lambda o, event: event.keyval == gtk.keysyms.Escape
				and logger.debug('TODO: hide side pane'))

		vbox2 = gtk.VBox()
		hpane.add2(vbox2)

		# TODO pathbar

		self.pageview = pageview.PageView(ui)
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

	def set_pathbar_recent(self): pass

	def set_pathbar_history(self): pass

	def set_pathbar_namespace(self): pass

	def set_pathbar_hidden(self): pass

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
		self.pageindex.treeview.set_pages( notebook.get_root() )

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


def _get_window(ui):
	if isinstance(ui, gtk.Window):
		return ui
	elif hasattr(ui, 'mainwindow'):
		return ui.mainwindow
	else:
		return None


class ErrorDialog(gtk.MessageDialog):

	def __init__(self, ui, error):
		'''Constructor. 'ui' can either be the main application or some
		other dialog from which the error originates. 'error' is the error
		object.
		'''
		self.error = error
		gtk.MessageDialog.__init__(
			self, parent=_get_window(ui),
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
		assert not title.lower().endswith(' zim')
		self.ui = ui
		self.inputs = {}
		gtk.Dialog.__init__(
			self, parent=_get_window(self.ui),
			title='%s - Zim' % title,
			flags=gtk.DIALOG_NO_SEPARATOR,
		)
		self.set_border_width(10)
		self.vbox.set_spacing(5)

		if buttons is None or buttons == gtk.BUTTONS_NONE:
			pass
		elif buttons == gtk.BUTTONS_OK_CANCEL:
			self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
			self.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
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
		label = gtk.Label()
		label.set_markup('<i>%s</i>' % text)
		self.vbox.add(label)

	def add_fields(self, fields, table=None):
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

		return table

	def get_fields(self):
		'''Returns a dict with values of the fields.'''
		values = {}
		for name, entry in self.inputs.items():
			values[name] = entry.get_text()
		return values

	def run(self):
		self.show_all()
		gtk.Dialog.run(self)

	def show_all(self):
		logger.debug('Opening dialog "%s"', self.title[:-6])
		gtk.Dialog.show_all(self)

	def do_response(self, id):
		if id == gtk.RESPONSE_OK:
			logger.debug('Dialog response OK')
			close = self.do_response_ok()
		else:
			close = True

		if close:
			self.destroy()
			logger.debug('Closed dialog "%s"', self.title[:-6])

# Need to register classes defining gobject signals
gobject.type_register(Dialog)


class OpenPageDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, 'Jump to')
		self.add_fields([('name', 'page', 'Jump to Page', None)])
		# TODO custom "jump to" button

	def do_response_ok(self):
		try:
			name = self.get_fields()['name']
			name = self.ui.notebook.resolve_name(name)
		except PageNameError, error:
			ErrorDialog(self, error).run()
			return False
		else:
			self.ui.open_page(name)
			return True


class NewPageDialog(OpenPageDialog):

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
