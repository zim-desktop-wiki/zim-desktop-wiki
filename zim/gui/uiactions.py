
# Copyright 2008-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GdkPixbuf
from gi.repository import Pango

import logging

logger = logging.getLogger('zim.gui')


from zim.actions import action

from zim.main import ZIM_APPLICATION

from zim.parsing import url_encode, URL_ENCODE_DATA
from zim.templates import list_templates, get_template

from zim.config import data_file, ConfigManager
from zim.notebook import PageExistsError, NotebookOperation
from zim.notebook.index import IndexNotFoundError, LINK_DIR_BACKWARD

from zim.actions import get_gtk_actiongroup
from zim.gui.widgets import Dialog, FileDialog, ProgressDialog, ErrorDialog, ScrolledTextView
from zim.gui.applications import open_url, open_folder, open_folder_prompt_create, edit_file

PAGE_EDIT_ACTIONS = 'page_edit'
PAGE_ACCESS_ACTIONS = 'page_access'
PAGE_ROOT_ACTIONS = 'page_root'


def _get_xml_for_menu(name):
	# Need to get sub-set of ui definition
	# Simple parser assumes we pretty-format input file per line
	file_name = 'menubar.xml'
	xml = iter(l.strip() for l in data_file(file_name).readlines())
	menu = []

	for line in xml:
		if line.startswith('<popup name=\'%s\'>' % name):
			menu.append(line)
			for line in xml:
				menu.append(line)
				if line.startswith('</popup>'):
					return '<ui>\n%s\n</ui>\n' % '\n'.join(menu)
	else:
		raise ValueError('No such popup defined in %s: %s' % (file_name, name))


class UIActions(object):
	'''Container for all kind of actions that can be triggered from the
	menubar, but do not directly link to a L{MainWindow} object.
	'''

	def __init__(self, widget, notebook, page, navigation):
		'''Constructor
		@param widget: owning gtk widget or C{None}, only used to determine
		parent window for dialogs
		@param notebook: L{Notebook} object for actions to act on
		@param page: L{Page} object that reflects the _default_ page for actions
		to act on.
		@param navigation: a L{NavigationModel}
		'''
		self.widget = widget
		self.notebook = notebook
		self.page = page
		self.navigation = navigation
		self.notebook.properties.connect('changed', self.on_notebook_properties_changed)

	def on_notebook_properties_changed(self, propeties):
		group = get_gtk_actiongroup(self)
		action = self.actiongroup.get_action('open_document_root')
		action.set_sensitive(self.notebook.document_root is not None)

	def populate_menu_with_actions(self, scope, menu):
		assert scope in (PAGE_EDIT_ACTIONS, PAGE_ROOT_ACTIONS, PAGE_ACCESS_ACTIONS)

		uimanager = Gtk.UIManager()
		group = get_gtk_actiongroup(self)
		uimanager.insert_action_group(group, 0)
		xml = _get_xml_for_menu(scope + '_popup')
		uimanager.add_ui_from_string(xml)

		tmp_menu = uimanager.get_widget('/' + scope + '_popup')
		assert isinstance(tmp_menu, Gtk.Menu)
		for item in tmp_menu.get_children():
			item.reparent(menu)

	@action(_('_New Page...'), '<Primary>N', menuhints='notebook:edit') # T: Menu item
	def new_page(self):
		'''Menu action to create a new page, shows the L{NewPageDialog},

		Difference with L{open_page()} is that the page is saved
		directly, so it exists and is stays visible if the user
		navigates away without first adding content. Though subtle this
		is expected behavior for users.
		'''
		NewPageDialog(self.widget, self.navigation, self.notebook, path=self.page).run()

	@action(_('New S_ub Page...'), '<shift><Primary>N', menuhints='notebook:edit') # T: Menu item
	def new_sub_page(self):
		'''Menu action to create a new page, shows the L{NewPageDialog}.
		Like L{new_page()} but forces a child page of the current
		page.
		'''
		NewPageDialog(self.widget, self.navigation, self.notebook, path=self.page, subpage=True).run()

	@action(_('_New Page Here...'), menuhints='notebook:edit') # T: Menu item
	def new_page_here(self):
		# Variant used for popup menu, context can either be page or notebook
		if self.page is None or self.page.isroot or self.page.parent.isroot:
			NewPageDialog(self.widget, self.navigation, self.notebook).run()
		else:
			NewPageDialog(self.widget, self.navigation, self.notebook, path=self.page.parent, subpage=True).run()

	@action(_('_Open Another Notebook...'), '<Primary>O') # T: Menu item
	def show_open_notebook(self):
		'''Show the L{NotebookDialog} dialog'''
		from zim.gui.notebookdialog import NotebookDialog
		NotebookDialog.unique(self, self.widget, callback=self.open_notebook).present()

	def open_notebook(self, location, pagename=None):
		'''Open another notebook.
		@param location: notebook location as uri or object with "uri" attribute
		@param pagename: optional page name
		'''
		assert isinstance(location, str) or hasattr(location, 'uri')
		assert pagename is None or isinstance(pagename, str)

		uri = location.uri if hasattr(location, 'uri') else location
		if pagename:
			ZIM_APPLICATION.run('--gui', uri, pagename)
		else:
			ZIM_APPLICATION.run('--gui', uri)

	@action(_('_Import Page...'), menuhints='notebook:edit') # T: Menu item
	def import_page(self):
		'''Menu action to show an L{ImportPageDialog}'''
		ImportPageDialog(self.widget, self.navigation, self.notebook, self.page).run()

	@action(_('Open in New _Window')) # T: Menu item
	def open_new_window(self, page=None):
		'''Menu action to open a page in a secondary L{PageWindow}
		@param page: the page L{Path}, deafults to current selected
		'''
		from zim.gui.mainwindow import PageWindow

		PageWindow(
			self.notebook,
			page or self.page,
			self.navigation
		).present()

	@action(_('Save A _Copy...')) # T: Menu item
	def save_copy(self):
		'''Menu action to show a L{SaveCopyDialog}'''
		SaveCopyDialog(self.widget, self.notebook, self.page).run()

	@action(_('E_xport...')) # T: Menu item
	def show_export(self):
		'''Menu action to show an L{ExportDialog}'''
		from zim.gui.exportdialog import ExportDialog
		if self.ensure_index_uptodate():
			ExportDialog(self.widget, self.notebook, self.page).run()

	@action(_('_Send To...')) # T: Menu item
	def email_page(self, _callback=open_url):
		'''Menu action to open an email containing the current page.
		Encodes the current page as "mailto:" URI and calls L{open_url()}
		to start the preferred email client.
		'''
		text = ''.join(self.page.dump(format='plain'))
		url = 'mailto:?subject=%s&body=%s' % (
			url_encode(self.page.name, mode=URL_ENCODE_DATA),
			url_encode(text, mode=URL_ENCODE_DATA),
		)
		_callback(self.widget, url)

	@action(_('_Rename Page...'), accelerator='F2', menuhints='notebook:edit') # T: Menu item
	def rename_page(self, path=None):
		'''Menu action to show the L{RenamePageDialog}
		@param path: a L{Path} object, or C{None} for the current
		selected page
		'''
		if self.ensure_index_uptodate():
			RenamePageDialog(self.widget, self.notebook, path or self.page).run()

	@action(_('_Move Page...'), menuhints='notebook:edit') # T: Menu item
	def move_page(self, path=None):
		'''Menu action to show the L{MovePageDialog}
		@param path: a L{Path} object, or C{None} to move to current
		selected page
		'''
		if self.ensure_index_uptodate():
			MovePageDialog(self.widget, self.notebook, path or self.page).run()

	@action(_('_Delete Page'), menuhints='notebook:edit') # T: Menu item
	def delete_page(self, path=None):
		'''Delete a page by either trashing it, or permanent deletion after
		confirmation of a L{DeletePageDialog}. When trashing the update behavior
		depends on the "remove_links_on_delete" preference.

		@param path: a L{Path} object, or C{None} for the current selected page
		'''
		# Difficulty here is that we want to avoid unnecessary prompts.
		# So ideally we want to know whether trash is supported, but we only
		# know for sure when we try. Thus we risk prompting twice: once for
		# trash and once for deletion if trash fails.
		# On windows the system will also prompt to confirm trashing, once
		# for the file and once for the folder. So adding our own prompt
		# will make it worse.
		# So we first attempt to trash and only if it fails we prompt for
		# to confirm for permanent deletion. From the application point of
		# view this is not perfect since we can't undo deletion from within
		# the application.
		from zim.newfs.helpers import TrashNotSupportedError

		path = path or self.page
		assert path is not None

		if not self.ensure_index_uptodate():
			return

		preferences = ConfigManager.preferences['GtkInterface']
		update_links = preferences.setdefault('remove_links_on_delete', True)
		op = NotebookOperation(
			self.notebook,
			_('Removing Links'), # T: Title of progressbar dialog
			self.notebook.trash_page_iter(path, update_links)
		)
		dialog = ProgressDialog(self.widget, op)
		try:
			dialog.run()
		except TrashNotSupportedError:
			pass # only during test, else error happens in idle handler

		if op.exception and isinstance(op.exception, TrashNotSupportedError):
			logger.info('Trash not supported: %s', op.exception.msg)
			DeletePageDialog(self.widget, self.notebook, path, update_links=update_links).run()

	@action(_('Proper_ties')) # T: Menu item
	def show_properties(self):
		'''Menu action to show the L{PropertiesDialog}'''
		from zim.gui.propertiesdialog import PropertiesDialog
		PropertiesDialog(self.widget, self.notebook).run()

		# Changing plugin properties can modify the index state
		if not self.notebook.index.is_uptodate:
			self.reload_index(update_only=True)

	@action(_('_Quit'), '<Primary>Q') # T: Menu item
	def quit(self):
		'''Menu action for quit.
		@emits: quit
		'''
		if Gtk.main_level() > 0:
			Gtk.main_quit()
		# We expect the application to call "destroy" on all windows once
		# it is bumped out of the main loop

	@action(_('Copy _Location'), accelerator='<shift><Primary>L') # T: Menu item
	def copy_location(self):
		'''Menu action to copy the current page name to the clipboard'''
		from zim.gui.clipboard import Clipboard
		Clipboard.set_pagelink(self.notebook, self.page)

	@action(_('_Templates')) # T: Menu item
	def show_templateeditor(self):
		'''Menu action to show the L{TemplateEditorDialog}'''
		from zim.gui.templateeditordialog import TemplateEditorDialog
		TemplateEditorDialog(self.widget).run()

	@action(_('Pr_eferences')) # T: Menu item
	def show_preferences(self):
		'''Menu action to show the L{PreferencesDialog}'''
		from zim.gui.preferencesdialog import PreferencesDialog
		PreferencesDialog(self.widget).run()

		# Loading plugins can modify the index state
		if not self.notebook.index.is_uptodate:
			self.reload_index(update_only=True)

	@action(_('_Search...'), '<shift><Primary>F') # T: Menu item
	def show_search(self, query=None):
		'''Menu action to show the L{SearchDialog}
		@param query: the search query to show
		'''
		from zim.gui.searchdialog import SearchDialog
		if query is None and hasattr(self.widget, 'pageview'):
			query = self.widget.pageview.get_selection() # XXX unauthorized access to pageview

		dialog = SearchDialog(self.widget, self.notebook, self.page, self.navigation)
		dialog.present()

		if query is not None:
			dialog.search(query)

	@action(_('Search this section')) # T: Menu item for search a sub-set of the notebook
	def show_search_section(self, page=None):
		page = page or self.page
		self.show_search(query='Section: "%s"' % page.name)

	@action(_('Search _Backlinks...')) # T: Menu item
	def show_search_backlinks(self, page=None):
		'''Menu action to show the L{SearchDialog} with a query for
		backlinks
		'''
		page = page or self.page
		self.show_search(query='LinksTo: "%s"' % page.name)

	@action(_('Recent Changes...')) # T: Menu item
	def show_recent_changes(self):
		'''Menu action to show the L{RecentChangesDialog}'''
		from .recentchangesdialog import RecentChangesDialog
		dialog = RecentChangesDialog.unique(self, self.widget, self.notebook, self.navigation)
		dialog.present()

	@action(_('Attach _File'), verb_icon='zim-attachment', menuhints='notebook:edit') # T: Menu item
	def attach_file(self, path=None):
		'''Menu action to show the L{AttachFileDialog}
		@param path: a L{Path} object, or C{None} for the current
		selected page
		'''
		AttachFileDialog(self.widget, self.notebook, path or self.page).run()

	@action(_('Open Attachments _Folder')) # T: Menu item
	def open_attachments_folder(self):
		'''Menu action to open the attachment folder for the current page'''
		dir = self.notebook.get_attachments_dir(self.page)
		if dir is None:
			error = _('This page does not have an attachments folder')
				# T: Error message
			ErrorDialog(self.widget, error).run()
		else:
			open_folder_prompt_create(self.widget, dir)

	@action(_('Open _Notebook Folder')) # T: Menu item
	def open_notebook_folder(self):
		'''Menu action to open the notebook folder'''
		open_folder(self.widget, self.notebook.folder)

	@action(_('Open _Document Root')) # T: Menu item
	def open_document_root(self):
		'''Menu action to open the document root folder'''
		# TODO: should be insensitive if document_root is not defined
		dir = self.notebook.document_root
		if dir is None:
			error = _('No document root defined for this notebook')
				# T: Error message
			ErrorDialog(self.widget, error).run()
		else:
			open_folder_prompt_create(self.widget, dir)

	@action(_('Edit _Source'), menuhints='tools:edit') # T: Menu item
	def edit_page_source(self, page=None):
		'''Menu action to edit the page source in an external editor.
		See L{edit_file} for details.

		@param page: the L{Page} object, or C{None} for te current page
		'''
		# This could also be defined as a custom tool, but we want to determine
		# the editor dynamically because we assume that the default app for a
		# text file is a editor and not e.g. a viewer or a browser.
		# Of course users can still define a custom tool for other editors.
		page = page or self.page

		edit_file(self.widget, self.page.source, istextfile=True)
		page.check_source_changed()

	@action(_('Start _Web Server')) # T: Menu item
	def show_server_gui(self):
		'''Menu action to show the server interface from
		L{zim.gui.server}. Spawns a new zim instance for the server.
		'''
		ZIM_APPLICATION.run('--server', '--gui', self.notebook.uri)

	def ensure_index_uptodate(self):
		if not self.notebook.index.is_uptodate:
			re = self.reload_index(update_only=True)
			assert re is not None # check we really get bool
			return re
		else:
			return True

	@action(_('Update Index')) # T: Menu item
	def reload_index(self, update_only=False):
		'''Check the notebook for changes and update the index.
		Shows an progressbar while updateing.
		@param update_only: if C{True} only updates are done, if C{False} also
		check is done for all files
		@returns: C{True} unless the user cancelled the update
		'''
		from zim.notebook.index import IndexCheckAndUpdateOperation, IndexUpdateOperation
		from zim.notebook.operations import ongoing_operation

		op = ongoing_operation(self.notebook)

		if isinstance(op, IndexUpdateOperation):
			dialog = ProgressDialog(self.widget, op)
			dialog.run()

			if update_only or isinstance(op, IndexCheckAndUpdateOperation):
				return not dialog.cancelled
			else:
				# ongoing op was update only but we want check, so try again
				if not dialog.cancelled:
					return self.reload_index() # recurs
				else:
					return False

		else:
			op = IndexCheckAndUpdateOperation(self.notebook)
			dialog = ProgressDialog(self.widget, op)
			dialog.run()

			return not dialog.cancelled

	@action(_('Custom _Tools')) # T: Menu item
	def manage_custom_tools(self):
		'''Menu action to show the L{CustomToolManagerDialog}'''
		from zim.gui.customtools import CustomToolManagerDialog
		CustomToolManagerDialog(self.widget).run()

	@action(_('_Contents'), 'F1') # T: Menu item
	def show_help(self, page=None):
		'''Menu action to show the user manual. Will start a new zim
		instance showing the notebook with the manual.
		@param page: manual page to show (string)
		'''
		if page:
			ZIM_APPLICATION.run('--manual', page)
		else:
			ZIM_APPLICATION.run('--manual')

	@action(_('_FAQ')) # T: Menu item
	def show_help_faq(self):
		'''Menu action to show the 'FAQ' page in the user manual'''
		self.show_help('FAQ')

	@action(_('_Keybindings')) # T: Menu item
	def show_help_keys(self):
		'''Menu action to show the 'Key Bindings' page in the user manual'''
		self.show_help('Help:Key Bindings')

	@action(_('_Bugs')) # T: Menu item
	def show_help_bugs(self):
		'''Menu action to show the 'Bugs' page in the user manual'''
		self.show_help('Bugs')

	@action(_('_About')) # T: Menu item
	def show_about(self):
		'''Menu action to show the "about" dialog'''
		dialog = MyAboutDialog(self.widget)
		dialog.run()
		dialog.destroy()


class NewPageDialog(Dialog):
	'''Dialog used to create a new page, functionally it is almost the same
	as the OpenPageDialog except that the page is saved directly in order
	to create it.
	'''

	def __init__(self, widget, navigation, notebook, path=None, subpage=False):
		if subpage:
			title = _('New Page in %s') % path # T: Dialog title
		else:
			title = _('New Page') # T: Dialog title

		Dialog.__init__(self, widget, title,
			help_text=_(
				'Please note that linking to a non-existing page\n'
				'also creates a new page automatically.'),
			# T: Dialog text in 'new page' dialog
			help=':Help:Pages'
		)
		self.notebook = notebook
		self.navigation = navigation

		default = notebook.get_page_template_name(path)
		templates = [t[0] for t in list_templates('wiki')]
		if not default in templates:
			templates.insert(0, default)

		self.add_form([
			('page', 'page', _('Page Name'), path), # T: Input label
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

		page = self.notebook.get_page(path) # can raise PageNotFoundError
		if page.exists():
			raise PageExistsError(path)

		template = get_template('wiki', self.form['template'])
		tree = self.notebook.eval_new_page_template(page, template)
		page.set_parsetree(tree)
		self.notebook.store_page(page)

		pageview = self.navigation.open_page(page)
		if pageview is not None:
			pageview.set_cursor_pos(-1) # HACK set position to end of template
		return True


class ImportPageDialog(FileDialog):
	# TODO how to properly detect file types for other formats ?

	def __init__(self, widget, navigation, notebook, page=None):
		FileDialog.__init__(self, widget, _('Import Page')) # T: Dialog title
		self.navigation = navigation
		self.notebook = notebook

		self.add_filter(_('Text Files'), '*.txt') # T: File filter for '*.txt'

		if page is not None:
			self.add_shortcut(notebook, page)

		# TODO add input for namespace, format

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False

		basename = file.basename
		if basename.endswith('.txt'):
			basename = basename[:-4]

		path = self.notebook.pages.lookup_from_user_input(basename)
		page = self.notebook.get_new_page(path)
		assert not page.exists()

		page.parse('wiki', file.readlines())
		self.notebook.store_page(page)
		self.navigation.open_page(page)
		return True


class SaveCopyDialog(FileDialog):

	def __init__(self, widget, notebook, page):
		FileDialog.__init__(self, widget, _('Save Copy'), Gtk.FileChooserAction.SAVE)
			# T: Dialog title of file save dialog
		self.page = page
		self.filechooser.set_current_name(page.name + '.txt')
		self.add_shortcut(notebook, page)

		# TODO also include headers
		# TODO add droplist with native formats to choose + hook filters

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False
		format = 'wiki'
		logger.info("Saving a copy of %s using format '%s'", self.page, format)
		lines = self.page.dump(format)
		file.writelines(lines)
		self.result = True
		return True


class RenamePageDialog(Dialog):

	def __init__(self, widget, notebook, path):
		Dialog.__init__(self, widget, _('Rename Page')) # T: Dialog title
		self.notebook = notebook
		self.path = path
		page = self.notebook.get_page(self.path)

		label = Gtk.Label(label=_('Rename page "%s"') % self.path.name)
			# T: label in 'rename page' dialog - %s is the page name
		label.set_ellipsize(Pango.EllipsizeMode.END)
		self.vbox.add(label)

		try:
			i = self.notebook.links.n_list_links_section(path, LINK_DIR_BACKWARD)
		except IndexNotFoundError:
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

		if name == self.path.basename:
			return False

		self.hide() # hide this dialog before showing the progressbar
		op = NotebookOperation(
			self.notebook,
			_('Updating Links'), # T: label for progress dialog
			self.notebook.rename_page_iter(self.path, name, head, update)
		)
		dialog = ProgressDialog(self, op)
		dialog.run()

		return True


class MovePageDialog(Dialog):

	def __init__(self, widget, notebook, path):
		Dialog.__init__(self, widget, _('Move Page')) # T: Dialog title
		self.notebook = notebook
		self.path = path

		label = Gtk.Label(label=_('Move page "%s"') % self.path.name)
			# T: Heading in 'move page' dialog - %s is the page name
		label.set_ellipsize(Pango.EllipsizeMode.END)
		self.vbox.add(label)

		try:
			i = self.notebook.links.n_list_links_section(path, LINK_DIR_BACKWARD)
		except IndexNotFoundError:
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
		if parent == self.path.parent:
			return False

		self.hide() # hide this dialog before showing the progressbar
		op = NotebookOperation(
			self.notebook,
			_('Updating Links'), # T: label for progress dialog
			self.notebook.move_page_iter(self.path, newpath, update)
		)
		dialog = ProgressDialog(self, op)
		dialog.run()

		return True


class DeletePageDialog(Dialog):

	def __init__(self, widget, notebook, path, update_links=True):
		assert path, 'Need a page here'
		Dialog.__init__(self, widget, _('Delete Page')) # T: Dialog title
		self.notebook = notebook
		self.path = path
		self.update_links = update_links

		hbox = Gtk.HBox(spacing=12)
		self.vbox.add(hbox)

		img = Gtk.Image.new_from_stock(Gtk.STOCK_DIALOG_WARNING, Gtk.IconSize.DIALOG)
		hbox.pack_start(img, False, True, 0)

		vbox = Gtk.VBox(spacing=5)
		hbox.pack_start(vbox, False, True, 0)

		label = Gtk.Label()
		short = _('Delete page "%s"?') % self.path.basename
			# T: Heading in 'delete page' dialog - %s is the page name
		longmsg = _('Page "%s" and all of it\'s\nsub-pages and attachments will be deleted') % self.path.name
			# T: Text in 'delete page' dialog - %s is the page name
		label.set_markup('<b>' + short + '</b>\n\n' + longmsg)
		vbox.pack_start(label, False, True, 0)

		# TODO use expander here
		page = self.notebook.get_page(self.path)
		text = page.source_file.path + '\n'
		n = 1
		dir = self.notebook.get_attachments_dir(self.path)
		if dir.exists():
			text += self._get_file_tree_as_text(dir)
			n = len([l for l in text.splitlines() if l.strip() and not l.endswith('/')])

		string = ngettext('%i file will be deleted', '%i files will be deleted', n) % n
			# T: label in the DeletePage dialog to warn user of attachments being deleted
		if n > 0:
			string = '<b>' + string + '</b>'

		label = Gtk.Label()
		label.set_markup('\n' + string + ':')
		self.vbox.add(label)
		window, textview = ScrolledTextView(text, monospace=True)
		window.set_size_request(250, 100)
		self.vbox.pack_start(window, True, True, 0)

	def _get_file_tree_as_text(self, dir):
		'''Returns an overview of files and folders below this dir
		as text. Used in tests.
		@param dir: a L{Folder} object
		@returns: file listing as string
		'''
		from zim.newfs import Folder
		text = ''
		for child in dir.walk():
			path = child.relpath(dir)
			if isinstance(child, Folder):
				path += '/'
			text += path + '\n'
		return text

	def do_response_ok(self):
		op = NotebookOperation(
			self.notebook,
			_('Removing Links'), # T: Title of progressbar dialog
			self.notebook.delete_page_iter(self.path, self.update_links)
		)
		dialog = ProgressDialog(self, op)
		dialog.run()

		return True


class AttachFileDialog(FileDialog):

	def __init__(self, widget, notebook, path):
		assert path, 'Need a page here'
		FileDialog.__init__(self, widget, _('Attach File'), multiple=True) # T: Dialog title
		self.notebook = notebook
		self.path = path

		self.add_shortcut(notebook, path)
		self.load_last_folder()

		dir = notebook.get_attachments_dir(path)
		if dir is None:
			ErrorDialog(_('Page "%s" does not have a folder for attachments') % self.path)
				# T: Error dialog - %s is the full page name
			raise Exception('Page "%s" does not have a folder for attachments' % self.path)

	def do_response_ok(self):
		files = self.get_files()
		if not files:
			return False

		self.save_last_folder()

		for i, file in enumerate(files):
			file = attach_file(self, self.notebook, self.path, file)
			if file is None:
				return False # overwrite dialog was canceled

		return True


def attach_file(widget, notebook, path, file, force_overwrite=False):
	folder = notebook.get_attachments_dir(path)
	if folder is None:
		raise Error('%s does not have an attachments dir' % path)

	dest = folder.file(file.basename)
	if dest.exists() and not force_overwrite:
		dialog = PromptExistingFileDialog(widget, dest)
		dest = dialog.run()
		if dest is None:
			return None	# dialog was cancelled
		elif dest.exists():
			dest.remove()

	file.copyto(dest)
	return dest


class PromptExistingFileDialog(Dialog):
	'''Dialog that is used e.g. when a file should be attached to zim,
	but a file with the same name already exists in the attachment
	directory. This Dialog allows to suggest a new name or overwrite
	the existing one.

	For this dialog C{run()} will return either the original file
	(for overwrite), a new file, or None when the dialog was canceled.
	'''

	def __init__(self, widget, file):
		Dialog.__init__(self, widget, _('File Exists'), buttons=None) # T: Dialog title
		self.add_help_text( _('''\
A file with the name <b>"%s"</b> already exists.
You can use another name or overwrite the existing file.''' % file.basename),
		) # T: Dialog text in 'new filename' dialog
		self.folder = file.parent()
		self.old_file = file

		suggested_filename = self.folder.new_file(file.basename).basename
		self.add_form((
				('name', 'string', _('Filename')), # T: Input label
			), {
				'name': suggested_filename
			}
		)
		self.form.widgets['name'].set_check_func(self._check_valid)

		# all buttons are defined in this class, to get the ordering right
		# [show folder]      [overwrite] [cancel] [ok]
		button = Gtk.Button.new_with_mnemonic(_('_Browse')) # T: Button label
		button.connect('clicked', self.do_show_folder)
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

		button = Gtk.Button.new_with_mnemonic(_('Overwrite')) # T: Button label
		button.connect('clicked', self.do_response_overwrite)
		self.add_action_widget(button, Gtk.ResponseType.NONE)

		self.add_button(_('_Cancel'), Gtk.ResponseType.CANCEL) # T: Button label
		self.add_button(_('_OK'), Gtk.ResponseType.OK) # T: Button label
		self._no_ok_action = False

		self.form.widgets['name'].connect('focus-in-event', self._on_focus)

	def _on_focus(self, widget, event):
		# filename length without suffix
		length = len(os.path.splitext(widget.get_text())[0])
		widget.select_region(0, length)

	def _check_valid(self, filename):
		# Only valid when same dir and does not yet exist
		file = self.folder.file(filename)
		return file.ischild(self.folder) and not file.exists()

	def do_show_folder(self, *a):
		open_folder(self, self.folder)

	def do_response_overwrite(self, *a):
		logger.info('Overwriting %s', self.old_file.path)
		self.result = self.old_file

	def do_response_ok(self):
		if not self.form.widgets['name'].get_input_valid():
			return False

		newfile = self.folder.file(self.form['name'])
		logger.info('Selected %s', newfile.path)
		assert newfile.ischild(self.folder) # just to be real sure
		assert not newfile.exists() # just to be real sure
		self.result = newfile
		return True


class MyAboutDialog(Gtk.AboutDialog):

	def __init__(self, parent):
		import zim

		GObject.GObject.__init__(self)
		self.set_transient_for(parent.get_toplevel())

		self.set_program_name('Zim')
		self.set_version(zim.__version__)
		self.set_comments(_('A desktop wiki'))
			# T: General description of zim itself
		file = data_file('zim.png')
		pixbuf = GdkPixbuf.Pixbuf.new_from_file(file.path)
		self.set_logo(pixbuf)
		self.set_copyright(zim.__copyright__)
		self.set_license(zim.__license__)
		self.set_authors([zim.__author__])
		self.set_translator_credits(_('translator-credits'))
			# T: This string needs to be translated with names of the translators for this language
		self.set_website(zim.__url__)

	def do_activate_link(self, uri):
		open_url(self, uri)
