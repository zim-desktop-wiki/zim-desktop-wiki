# -*- coding: utf-8 -*-

# Copyright 2011 Stefan Muthers <smu@z107.de>
# License:  same as zim (gpl)


import gtk
import pango
import logging

from zim.parsing import link_type
from zim.fs import File
from zim.gui.widgets import Dialog, MessageDialog


logger = logging.getLogger('zim.gui')

SEL_COL    = 0	# File selected or not
PAGE_COL   = 1	# Page the file belongs to
SNAME_COL  = 2	# Basename of the file
NAME_COL   = 3	# Full file name


ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('open_file', 'zim-clean-notebook', _('Open File'), '', _('Open File'), True), # T: menu item
	('open_folder', 'zim-clean-notebook', _('Open Folder'), '', _('Open Folder'), True), # T: menu item
	('delete_file', 'zim-clean-notebook', _('Delete File'), '', _('Delete'), True), # T: menu item
)

ui_xml='''
	<ui>
	<popup name='clean_notebook_popup'>
	  <placeholder name='tools'>
		<menuitem action='open_file'/>
		<menuitem action='open_folder'/>
		<menuitem action='delete_file'/>
	  </placeholder>
	</popup>
	</ui>'''


def extract_links(element):
	'''Returns any file links for a parsetree element'''
	links = []
	if element.tag == 'img':
		return [element.attrib['src']]
	elif element.tag == 'link' and link_type(element.text) == 'file':
		return [element.attrib['href']]
	else:
		for child in element.getchildren():
			if child.tag in ('p','ul','li', 'img', 'link'):
				l = extract_links(child)
				if l:
					links = links + l
		return links


def get_orphaned_files(notebook):
	'''Returns a dict with orphaned attachments per pages'''
	files = {}
	linked = set()

	for page in notebook.walk():
		# collect attached files
		dir = notebook.get_attachments_dir(page)
		if dir.exists():
			files[page.name] = set()
			for name in dir.list():
				file = dir.file(name)
				if not file.isdir():
					files[page.name].add(file.path)

		# extract links from pages
		if page.hascontent:
			tree = page.get_parsetree()
			for link in extract_links(tree.getroot()):
				try:
					file = notebook.resolve_file(link, page)
				except AssertionError:
					pass
				else:
					linked.add(file.path)

	# compare attached files with existing links
	for file_set in files.values():
		file_set -= linked

	return files


class OrphanedFilesTreeModel(gtk.ListStore):
	''' A gtk.ListStore for the orphaned files'''

	def __init__(self, filelist):
		gtk.ListStore.__init__(self, bool, str, str, str) # SEL_COL, PAGE_COL, SNAME_COL, NAME_COL

		self._loading = True
		self.clear()
		#~ w, h = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)
		for page in filelist:
			for file in filelist[page]:
				basename = File(file).basename
				self.append((False, page, basename, file))
		self._loading = False

	def get_selected(self):
		selection = []
		for row in self:
			if row[SEL_COL]:
				selection.append(row[NAME_COL])
		return selection



class OrphanedFilesTreeView(gtk.TreeView):
	def __init__(self, ui):

		self.orphaned_files = get_orphaned_files(ui.notebook)
		self.model = OrphanedFilesTreeModel(self.orphaned_files)
		self.ui = ui

		gtk.TreeView.__init__(self, self.model)
		self.get_selection().set_mode(gtk.SELECTION_BROWSE)
		self.set_rules_hint(True)
		self.set_reorderable(True)

		cell_renderer = gtk.CellRendererToggle()
		cell_renderer.set_property('activatable', True)
		cell_renderer.connect( 'toggled', self.toggled_selection)
		column = gtk.TreeViewColumn(_("Selection"), cell_renderer)
			## T: Column heading in 'Oprhaned Files' dialog
		column.add_attribute( cell_renderer, "active", SEL_COL)
		self.append_column(column)


		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn(_('Filename'), cell_renderer, text=SNAME_COL)
			# T: Column heading in 'Oprhaned Files' dialog
		column.set_sort_column_id(NAME_COL)
		column.set_resizable(True)
		column.set_expand(True)
		self.append_column(column)

		cell_renderer = gtk.CellRendererText()
		#~ cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn(_('Page'), cell_renderer, text=PAGE_COL)
			# T: Column heading in 'Oprhaned Files' dialog
		column.set_sort_column_id(PAGE_COL)
		column.set_resizable(True)
		self.append_column(column)

	def toggled_selection(self, cell, path):
		self.model[path][SEL_COL] = not self.model[path][SEL_COL]
		logger.debug("Toggle '%s' to: %s" % (self.model[path][SNAME_COL], self.model[path][0],))
		return



class CleanNotebookDialog(Dialog):
	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Cleanup Attachments'), buttons=None) # T: dialog title
		self.set_default_size(600, 400)
		#self.set_help(':Help:Clean_Notebook') #TODO
		self.ui = ui

		self.ui.add_actions(ui_actions, self)
		self.ui.add_ui(ui_xml,self)

		# Buttons
		# [cancel] [delete]
		self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
		self.add_button('Delete', gtk.RESPONSE_OK)
		self._no_ok_action = False

		button = gtk.Button(_('Invert Selection'))
    		# T: Button in "Clean Notebook" dialog
		button.connect('clicked', self.do_response_toggle)
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

		self.add_help_text(_(
				'The files below were found in the attachment directory of zim but are no longer \n'
				'linked in the notebook. '
		) ) # T: help text in "Clean Notebook" dialog

		self.treeview = OrphanedFilesTreeView(ui)
		self.treeview.connect_object(
					'button-press-event', self.__class__.on_treeview_click, self)

		hbox = gtk.HBox(spacing=5)
		self.vbox.add(hbox)

		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		swindow.add(self.treeview)
		hbox.add(swindow)

	def run(self):
		if len(self.treeview.model) == 0:
			logger.info("No orphaned files found.")
			MessageDialog(self.ui, _('No orphaned files found.')).run() # T: Message dialog in "Clean Attachments"
			self.destroy()
			return True
		else:
			return super(CleanNotebookDialog, self).run()

	def on_treeview_click(self, event):
		if event.button == 3:
			x = int(event.x)
			y = int(event.y)
			path = self.treeview.get_path_at_pos(x, y)
			if path:
				self.path = path
				iter = self.treeview.model.get_iter(path[0])
				self.iter = iter

				self.selected_file = self.treeview.model.get(iter, NAME_COL)
				self.selected_file = File(self.selected_file[0])
				menu = self.ui.uimanager.get_widget('/clean_notebook_popup')
				menu.popup(None, None, None, event.button, event.time)
				return True

	def open_file(self, file=None):
		if not file:
			file = self.selected_file
		logger.debug('Try to open %s' % file)
		try:
			self.ui.open_file(file)
		except Exception, error:
			logger.warn('Opening %s failed: %s' % (file, error))

	def open_folder(self):
		file = self.selected_file
		self.open_file(file.dir)

	def delete_file(self, file=None, refresh=False):
		'''Deletes a file and refreshes the treeview if refresh == True'''
		if not file:
			file = self.selected_file
			refresh = True
		logger.debug('Deleting %s' % file)
		file = File(file)
		if file.exists():
			file.cleanup()
		if refresh:
			self.treeview.model.remove(self.iter)

	def do_response_toggle(self, button):
		for path in self.treeview.model:
			path[SEL_COL] = not path[SEL_COL]

	def do_response_ok(self):
		model = self.treeview.model
		selected_files = model.get_selected()
		if selected_files:
			for file in selected_files:
				self.delete_file(file)
		self.destroy()

