# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import gtk

import logging

from zim.fs import File
from zim.plugins import PluginClass
from zim.errors import Error
from zim.applications import Application
from zim.config import value_is_coord
from zim.gui.widgets import ErrorDialog, QuestionDialog, Dialog, \
	PageEntry, IconButton, SingleClickTreeView, scrolled_text_view

# FUTURE allow vcs modules like bzr to have their own UI classes
# these can add additional menu items e.g. Tools->Bazaar-> ...
# or use their own graphical interfaces, like bzr gdiff

# FUTURE add option to also pull & push versions automatically

logger = logging.getLogger('zim.plugins.versioncontrol')


ui_xml = '''
<ui>
<menubar name='menubar'>
	<menu action='file_menu'>
		<placeholder name='versioning_actions'>
			<menuitem action='save_version'/>
			<menuitem action='show_versions'/>
		</placeholder>
	</menu>
</menubar>
</ui>
'''


ui_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('save_version', 'gtk-save-as', _('S_ave Version...'), '<ctrl><shift>S', '', False), # T: menu item
	('show_versions', None, _('_Versions...'), '', '', True), # T: menu item
)


def async_commit_with_error(ui, vcs, msg, skip_no_changes=False):
	'''Convenience method to wrap vcs.commit_async'''
	def callback(ok, error, exc_info, data):
		if error:
			if isinstance(error, NoChangesError) and skip_no_changes:
				logger.debug('No autosave version needed - no changes')
			else:
				logger.error('Error during async commit', exc_info=exc_info)
				ErrorDialog(ui, error).run()
	vcs.commit_async(msg, callback=callback)


class NoChangesError(Error):

	description = _('There are no changes in this notebook since the last version that was saved') # T: verbose error description

	def __init__(self, root):
		self.msg = _('No changes since last version')
		# T: Short error descriotion


class VersionControlPlugin(PluginClass):

	plugin_info = {
		'name': _('Version Control'), # T: plugin name
		'description': _('''\
This plugin adds version control for notebooks.

This plugin is based on the Bazaar version control system.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Version Control',
	}

	plugin_preferences = (
		('autosave', 'bool', _('Autosave version on regular intervals'), False), # T: Label for plugin preference
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.vcs = None
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.actiongroup.get_action('show_versions').set_sensitive(False)
			if self.ui.notebook:
				self.detect_vcs()
			else:
				self.ui.connect_after('open-notebook',
					lambda o, n: self.detect_vcs() )

			def on_quit(o):
				if self.preferences['autosave']:
					self.autosave()
			self.ui.connect('quit', on_quit)

	@classmethod
	def check_dependencies(klass):
		return [('bzr',Application(('bzr',)).tryexec())]

	def detect_vcs(self):
		dir = self._get_notebook_dir()
		self.vcs = self._detect_vcs(dir)
		if self.vcs:
			self.actiongroup.get_action('show_versions').set_sensitive(True)
			if self.preferences['autosave']:
				self.autosave()

	def _get_notebook_dir(self):
		notebook  = self.ui.notebook
		if notebook.dir:
			return notebook.dir
		elif notebook.file:
			return notebook.file.dir
		else:
			assert 'Notebook is not based on a file or folder'

	@staticmethod
	def _detect_vcs(dir):
		# split off because it is easier to test this way
		vcs = None

		for path in reversed(list(dir)):
			if path.subdir('.bzr').exists():
				from zim.plugins.versioncontrol.bzr import BazaarVCS
				vcs = BazaarVCS(path)
			#~ elif path.subdir('.svn'):
			#~ elif path.subdir('CVS'):
			else:
				continue

		if vcs:
			logger.info('VCS detected: %s', vcs)
		else:
			logger.info('No VCS detected')

		return vcs

	def autosave(self):
		assert self.vcs

		if self.ui.page and self.ui.page.modified:
			self.ui.save_page()

		logger.info('Automatically saving version')
		with self.ui.notebook.lock:
			async_commit_with_error(self.ui, self.vcs,
				_('Automatically saved version from zim'),
				skip_no_changes=True )
				# T: default version comment for auto-saved versions

	def save_version(self):
		if not self.vcs:
			# TODO choice from multiple version control systems
			if QuestionDialog(self, (
				_("Enable Version Control?"), # T: Question dialog
				_("Version control is currently not enabled for this notebook.\n"
				  "Do you want to enable it?" ) # T: Detailed question
			) ).run():
				self.init_vcs('bzr')
			else:
				return

		if self.ui.page.modified:
			self.ui.save_page()

		with self.ui.notebook.lock:
			SaveVersionDialog(self.ui, self.vcs).run()

	def init_vcs(self, vcs):
		dir = self._get_notebook_dir()
		if vcs == 'bzr':
			from zim.plugins.versioncontrol.bzr import BazaarVCS
			self.vcs = BazaarVCS(dir)
		else:
			assert False, 'Unkown VCS: %s' % vcs

		if self.vcs:
			with self.ui.notebook.lock:
				self.vcs.init()
			self.actiongroup.get_action('show_versions').set_sensitive(True)

	def show_versions(self):
		dialog = VersionsDialog.unique(self, self.ui, self.vcs)
		dialog.present()


#~ class VersionControlInitDialog(Dialog):
	#~ pass


class SaveVersionDialog(Dialog):

	def __init__(self, ui, vcs):
		Dialog.__init__(self, ui, _('Save Version'), # T: dialog title
			button=(None, 'gtk-save'), help='Plugins:Version Control')
		self.vcs = vcs

		self.vbox.pack_start(
			gtk.Label(_("Please enter a comment for this version")), False)  # T: Dialog text

		vpaned = gtk.VPaned()
		self.vbox.add(vpaned)

		window, self.textview = scrolled_text_view(_('Saved version from zim'))
			# T: default version comment in the "save version" dialog
		self.textview.set_editable(True)
		vpaned.add1(window)

		vbox = gtk.VBox()
		vpaned.add2(vbox)

		label = gtk.Label('<b>'+_('Details')+'</b>')
			# T: section for version details in "save version" dialog
		label.set_use_markup(True)
		label.set_alignment(0, 0.5)
		vbox.pack_start(label, False)

		status = self.vcs.get_status()
		window, textview = scrolled_text_view(text=''.join(status), monospace=True)
		vbox.add(window)


	def do_response_ok(self):
		# notebook.lock already set by plugin.save_version()
		buffer = self.textview.get_buffer()
		start, end = buffer.get_bounds()
		msg = buffer.get_text(start, end, False).strip()
		if msg:
			async_commit_with_error(self.ui, self.vcs, msg)
			return True
		else:
			return False


class VersionsDialog(Dialog):

	# TODO put state in uistate ..

	def __init__(self, ui, vcs):
		Dialog.__init__(self, ui, _('Versions'), # T: dialog title
			buttons=gtk.BUTTONS_CLOSE, help='Plugins:Version Control')
		self.vcs = vcs

		self.uistate.setdefault('windowsize', (600, 500), check=value_is_coord)
		self.uistate.setdefault('vpanepos', 300)

		self.vpaned = gtk.VPaned()
		self.vpaned.set_position(self.uistate['vpanepos'])
		self.vbox.add(self.vpaned)

		vbox = gtk.VBox(spacing=5)
		self.vpaned.pack1(vbox, resize=True)

		# Choice between whole notebook or page
		label = gtk.Label('<b>'+_('Versions')+':</b>') # section label
		label.set_use_markup(True)
		label.set_alignment(0, 0.5)
		vbox.pack_start(label, False)

		self.notebook_radio = gtk.RadioButton(None, _('Complete _notebook'))
			# T: Option in versions dialog to show version for complete notebook
		self.page_radio = gtk.RadioButton(self.notebook_radio, _('_Page')+':')
			# T: Option in versions dialog to show version for single page
		#~ recursive_box = gtk.CheckButton('Recursive')
		vbox.pack_start(self.notebook_radio, False)

		# Page entry
		hbox = gtk.HBox(spacing=5)
		vbox.pack_start(hbox, False)
		hbox.pack_start(self.page_radio, False)
		self.page_entry = PageEntry(self.ui.notebook)
		self.page_entry.set_path(ui.page)
		hbox.pack_start(self.page_entry, False)

		# View annotated button
		ann_button = gtk.Button(_('View _Annotated')) # T: Button label
		ann_button.connect('clicked', lambda o: self.show_annotated())
		hbox.pack_start(ann_button, False)

		# Help text
		label = gtk.Label('<i>\n'+_( '''\
Select a version to see changes between that version and the current
state. Or select multiple versions to see changes between those versions.
''' ).strip()+'</i>') # T: Help text in versions dialog
		label.set_use_markup(True)
		#~ label.set_alignment(0, 0.5)
		vbox.pack_start(label, False)

		# Version list
		self.versionlist = VersionsTreeView()
		self.versionlist.load_versions(vcs.list_versions())
		scrolled = gtk.ScrolledWindow()
		scrolled.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		scrolled.set_shadow_type(gtk.SHADOW_IN)
		scrolled.add(self.versionlist)
		vbox.add(scrolled)

		# -----
		vbox = gtk.VBox(spacing=5)
		self.vpaned.pack2(vbox, resize=False)

		frame = gtk.Frame()
		label = gtk.Label('<b>'+_('Comment')+'</b>') # T: version details
		label.set_use_markup(True)
		frame.set_label_widget(label)
		vbox.add(frame)

		# Comment text
		window, textview = scrolled_text_view()
		self.comment_textview = textview
		window.set_border_width(10)
		frame.add(window)

		buttonbox = gtk.HButtonBox()
		buttonbox.set_layout(gtk.BUTTONBOX_END)
		vbox.pack_start(buttonbox, False)

		# Restore version button
		revert_button = gtk.Button(_('_Restore Version')) # T: Button label
		revert_button.connect('clicked', lambda o: self.restore_version())
		buttonbox.add(revert_button)

		# Notebook Changes button
		diff_button = gtk.Button(_('Show _Changes'))
			# T: button in versions dialog for diff
		diff_button.connect('clicked', lambda o: self.show_changes())
		buttonbox.add(diff_button)

		# Compare page button
		comp_button = gtk.Button(_('_Side by Side'))
			# T: button in versions dialog for side by side comparison
		comp_button.connect('clicked', lambda o: self.show_side_by_side())
		buttonbox.add(comp_button)


		# UI interaction between selections and buttons

		def on_row_activated(o, iter, path):
			model = self.versionlist.get_model()
			comment = model[iter][3]
			buffer = textview.get_buffer()
			buffer.set_text(comment)

		self.versionlist.connect('row-activated', on_row_activated)


		def on_ui_change(o):
			usepage = self.page_radio.get_active()
			self.page_entry.set_sensitive(usepage)
			ann_button.set_sensitive(usepage)

			# side by side comparison can only be done for one page
			# revert can only be done to one version, not multiple
			selection = self.versionlist.get_selection()
			model, rows = selection.get_selected_rows()
			if not rows:
				revert_button.set_sensitive(False)
				diff_button.set_sensitive(False)
				comp_button.set_sensitive(False)
			elif len(rows) == 1:
				revert_button.set_sensitive(usepage)
				diff_button.set_sensitive(True)
				comp_button.set_sensitive(usepage)
			else:
				revert_button.set_sensitive(False)
				diff_button.set_sensitive(True)
				comp_button.set_sensitive(usepage)

		self.page_radio.connect('toggled', on_ui_change)
		selection = self.versionlist.get_selection()
		selection.connect('changed', on_ui_change)

		# select last version
		self.versionlist.get_selection().select_path((0,))
		col = self.versionlist.get_column(0)
		self.versionlist.row_activated(0, col)

	def save_uistate(self):
		self.uistate['vpanepos'] = self.vpaned.get_position()

	def _get_file(self):
		if self.notebook_radio.get_active():
			if self.ui.page.modified:
				self.ui.save_page()

			return None
		else:
			path = self.page_entry.get_path()
			if path:
				page = self.ui.notebook.get_page(path)
				if page == self.ui.page and page.modified:
					self.ui.save_page()
			else:
				return None # TODO error message valid page name?

			if page \
			and hasattr(page, 'source') \
			and isinstance(page.source, File) \
			and page.source.ischild(self.vcs.root):
				return page.source
			else:
				return None # TODO error message ?

	def show_annotated(self):
		# TODO check for gannotated
		file = self._get_file()
		assert not file is None
		annotated = self.vcs.get_annotated(file)
		TextDialog(self, _('Annotated Page Source'), annotated).run()
			# T: dialog title

	def restore_version(self):
		file = self._get_file()
		path = self.page_entry.get_path()
		version = self.versionlist.get_versions()[0]
		assert not file is None
		if QuestionDialog(self, (
			_('Restore page to saved version?'), # T: Confirmation question
			_('Do you want to restore page: %(page)s\n'
			  'to saved version: %(version)s ?\n\n'
			  'All changes since the last saved version will be lost !')
			  % {'page': path.name, 'version': str(version)}
			  # T: Detailed question, "%(page)s" is replaced by the page, "%(version)s" by the version id
		) ).run():
			self.vcs.revert(file=file, version=version)
			self.ui.reload_page()

	def show_changes(self):
		# TODO check for gdiff
		file = self._get_file()
		versions = self.versionlist.get_versions()
		diff = self.vcs.get_diff(file=file, versions=versions)
		TextDialog(self, _('Changes'), diff).run()
			# T: dialog title

	def show_side_by_side(self):
		print 'TODO - need config for an application like meld'


class TextDialog(Dialog):

	def __init__(self, ui, title, lines):
		Dialog.__init__(self, ui, title, buttons=gtk.BUTTONS_CLOSE)
		self.set_default_size(600, 300)
		window, textview = scrolled_text_view(''.join(lines), monospace=True)
		self.vbox.add(window)


class VersionsTreeView(SingleClickTreeView):

	# We are on purpose _not_ a subclass of the BrowserTreeView widget
	# because we utilize multiple selection to select versions for diffs

	def __init__(self):
		model = gtk.ListStore(int, str, str, str) # rev, date, user, msg
		gtk.TreeView.__init__(self, model)

		self.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		self.set_rubber_banding(True)

		cell_renderer = gtk.CellRendererText()
		for name, i in (
			(_('Rev'), 0), # T: Column header versions dialog
			(_('Date'), 1), # T: Column header versions dialog
			(_('Author'), 2), # T: Column header versions dialog
		):
			column = gtk.TreeViewColumn(name, cell_renderer, text=i)
			column.set_sort_column_id(i)
			if i == 0:
				column.set_expand(True)
			self.append_column(column)

		model.set_sort_column_id(0, gtk.SORT_DESCENDING)
			# By default sort by rev

	def load_versions(self, versions):
		model = self.get_model()
		for version in versions:
			model.append(version)

	def get_versions(self):
		model, rows = self.get_selection().get_selected_rows()
		if len(rows) == 1:
			rev = int(model[rows[0]][0])
			return (rev,)
		else:
			rev = map(int, [model[path][0] for path in rows])
			return (min(rev), max(rev))
