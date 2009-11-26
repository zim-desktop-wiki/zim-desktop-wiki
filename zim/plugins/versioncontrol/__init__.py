# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import gtk

import logging

from zim.fs import File
from zim.plugins import PluginClass

from zim.gui.widgets import SingleClickTreeView, Dialog, PageEntry, IconButton, scrolled_text_view

# FUTURE allow vcs modules like bzr to have their own UI classes
# these can add additional menu items e.g. Tools->Bazaar-> ...
# or use their own graphical interfaces, like bzr gdiff


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
	('show_versions', None, _('_Versions...'),  '', '', True), # T: menu item
)


class VersionControlPlugin(PluginClass):

	plugin_info = {
		'name': _('Version Control'), # T: plugin name
		'description': _('''\
This plugin adds version control for notebooks.

This plugin is based on the Bazaar version control system.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.actiongroup.get_action('show_versions').set_sensitive(False)
			self.ui.connect_after('open-notebook',
				lambda o, n: self.detect_vcs(n) )

	def detect_vcs(self, notebook):
		if notebook.dir:
			dir = notebook.dir
		elif notebook.file:
			dir = notebook.file.dir
		else:
			assert 'Notebook is not based on a file or folder'

		self.vcs = self._detect_vcs(dir)
		if self.vcs:
			self.actiongroup.get_action('show_versions').set_sensitive(True)


	@staticmethod
	def _detect_vcs(dir):
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

	def save_version(self):
		if self.vcs:
			SaveVersionDialog.run()
		else:
			VersionControlInitDialog.run()

	def show_versions(self):
		dialog = VersionsDialog.unique(self, self.ui, self.vcs)
		dialog.present()


class VersionControlInitDialog(Dialog):
	pass


class SaveVersionDialog(Dialog):
	pass

	# _("Save Version") # T: Dialog title

	# _("Please enter a comment for this version") # T: Dialog text

	# Comment box
	#-- vpane
	# Box with details

	# Notebook Changes button

	# Help, Cancel, SAve


class VersionsDialog(Dialog):

	# TODO put state in uistate ..

	def __init__(self, ui, vcs):
		Dialog.__init__(self, ui, _('Versions'), # T: dialog title
			buttons=gtk.BUTTONS_CLOSE, help='Plugins:Version Control')
		self.vcs = vcs

		vpaned = gtk.VPaned()
		vpaned.set_position(300)
		self.vbox.add(vpaned)

		vbox = gtk.VBox(spacing=5)
		vpaned.pack1(vbox, resize=True)

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
		self.page_entry = PageEntry()
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
''' ).strip()+'</i>')
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
		vpaned.pack2(vbox, resize=False)

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
				revert_button.set_sensitive(True)
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

	def _get_file(self):
		if self.notebook_radio.get_active():
			return None
		else:
			path = self.page_entry.get_path()
			if path:
				page = self.ui.notebook.get_page(path)
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
		pass

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
		model = gtk.ListStore(str, str, str, str) # rev, date, user, msg
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
