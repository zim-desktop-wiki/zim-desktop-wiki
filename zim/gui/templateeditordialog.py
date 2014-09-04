# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import gtk

from zim.fs import TrashNotSupportedError
from zim.config import XDG_DATA_HOME, data_file
from zim.templates import list_template_categories, list_templates
from zim.gui.widgets import Dialog, BrowserTreeView, Button, ScrolledWindow


class TemplateEditorDialog(Dialog):
	'''Dialog with a tree of available templates for export and new pages.
	Allows edit, delete, and create new templates. Uses external editor.
	'''

	def __init__(self, ui):
		Dialog.__init__(self, ui,
			_('Templates'), help='Help:Templates', buttons=gtk.BUTTONS_CLOSE,
			defaultwindowsize=(400, 450))
			# T: Dialog title

		label = gtk.Label()
		label.set_markup('<b>'+_('Templates')+'</b>')
			# T: Section in dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False)

		hbox = gtk.HBox()
		self.vbox.add(hbox)

		self.view = TemplateListView()
		self.view.connect('row-activated', self.on_selection_changed)
		hbox.add(ScrolledWindow(self.view))

		vbbox = gtk.VButtonBox()
		vbbox.set_layout(gtk.BUTTONBOX_START)
		hbox.pack_start(vbbox, False)

		view_button = Button(stock='gtk-file', label=_('_View')) # T: button label
		view_button.connect('clicked', self.on_view)

		copy_button = Button(stock='gtk-copy')
		copy_button.connect('clicked', self.on_copy)

		edit_button = Button(stock='gtk-edit')
		edit_button.connect('clicked', self.on_edit)

		delete_button = gtk.Button(stock='gtk-remove')
		delete_button.connect('clicked', self.on_delete)

		for b in (view_button, copy_button, edit_button, delete_button):
			b.set_alignment(0.0, 0.5)
			vbbox.add(b)

		browse_button = Button(_('Browse')) # T: button label
		browse_button.connect('clicked', self.on_browse)
		self.add_extra_button(browse_button)

		self._buttonbox = vbbox
		self._delete_button = delete_button
		self.on_selection_changed()

		## Same button appears in export dialog
		if gtk.gtk_version >= (2, 10):
			url_button = gtk.LinkButton(
				'https://github.com/jaap-karssenberg/zim-wiki/wiki/Templates',
				_('Get more templates online') # T: label for button with URL
			)
			self.vbox.pack_start(url_button, False)

	def on_selection_changed(self, *a):
		# Set sensitivity of the buttons
		# All insensitive if category (folder) is selected
		# Delete insensitive if only a default
		custom, default = self.view.get_selected()
		for button in self._buttonbox.get_children():
			button.set_sensitive(custom is not None)

		if custom is None:
			return

		if not custom.exists():
			self._delete_button.set_sensitive(False)

	def on_view(self, *a):
		# Open the file, witout waiting for editor to return
		custom, default = self.view.get_selected()
		if custom is None:
			return # Should not have been sensitive

		if custom.exists():
			self.ui.open_file(custom)
		else:
			assert default and default.exists()
			self.ui.open_file(default)

	def on_copy(self, *a):
		# Create a new template in this category
		custom, default = self.view.get_selected()
		if custom is None:
			return # Should not have been sensitive

		if custom.exists():
			source = custom
		else:
			assert default and default.exists()
			source = default

		name = PromptNameDialog(self).run()
		_, ext = custom.basename.rsplit('.', 1)
		basename = name + '.' + ext
		newfile = custom.dir.file(basename)

		source.copyto(newfile)

		self.view.refresh()

	def on_edit(self, *a):
		custom, default = self.view.get_selected()
		if custom is None:
			return # Should not have been sensitive

		if not custom.exists():
			# Copy default
			default.copyto(custom)

		self.ui.edit_file(custom, istextfile=True, dialog=self)
		self.view.refresh()

	def on_delete(self, *a):
		# Only delete custom, may result in reset to default
		custom, default = self.view.get_selected()
		if custom is None or not custom.exists():
			return # Should not have been sensitive

		try:
			custom.trash()
		except TrashNotSupportedError:
			# TODO warnings
			custom.remove()

		self.view.refresh()

	def on_browse(self, *a):
		dir = XDG_DATA_HOME.subdir(('zim', 'templates'))
		self.ui.open_dir(dir)


class PromptNameDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Copy Template')) # T: Dialog title
		self.add_form([
			('name', 'string', _('Name')),
				# T: Input label for the new name when copying a template
		])

	def do_response_ok(self):
		self.result = self.form['name']
		if self.result:
			return True


class TemplateListView(BrowserTreeView):

	BASENAME_COL = 0
	FILE_COL = 1
	DEFAULT_COL = 2

	def __init__(self):
		BrowserTreeView.__init__(self)
		model = gtk.TreeStore(str, object, object)
			# BASENAME_COL, FILE_COL, DEFAULT_COL
		self.set_model(model)
		self.set_headers_visible(False)

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn('_template_', cell_renderer, text=self.BASENAME_COL)
		self.append_column(column)

		self.refresh()

	def get_selected(self):
		# Returns (base, default file) or (None, None)
		model, iter = self.get_selection().get_selected()
		if model is None or iter is None:
			return None, None
		else:
			return model[iter][self.FILE_COL], model[iter][self.DEFAULT_COL]

	def refresh(self):
		model = self.get_model()
		model.clear()
		for category in list_template_categories():
			parent = model.append(None, (category, None, None))
			for name, basename in list_templates(category):
				base = XDG_DATA_HOME.file(('zim', 'templates', category, basename))
				default = data_file(('templates', category, basename)) # None if not existing
				#~ print '>>>', name, base, default
				model.append(parent, (name, base, default))

		self.expand_all()
