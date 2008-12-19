# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains the notebook dialog which is used for the
"open another notebook" action and which is shown if you start zim without
argument. The dialog directly modifies the notebook table obtained from
zim.notebook.get_notebook_table(). It re-uses the properties dialog to
modify the notebook properties. A special dropdown allows settign the special
entry for _default_ which will be openend directly the next time zim is
started without arguments.
'''

import gtk
import pango

from zim import notebook
from zim.utils import data_file
from zim.gui import gtkutils


NAME_COL = 0  # column with notebook name
OPEN_COL = 1  # column with boolean if notebook is open alreadys


class NotebookTreeModel(gtk.ListStore):
	'''TreeModel that wraps a notebook list given as a ConfigList'''

	def __init__(self, notebooks=None):
		'''Constructor. If "notebooks" is None, the default list as provided
		by zim.notebook.get_notebook_table() is used.
		'''
		gtk.ListStore.__init__(self, str, bool) # NAME_COL, OPEN_COL

		if notebooks is None:
			self.notebooks = notebook.get_notebook_table()
		else:
			self.notebooks = notebooks

		for name, path in self.notebooks.items():
			if not (name.startswith('_') and name.endswith('_')):
				self.append((name, False))

	def get_iter_from_notebook(self, notebook):
		'''Returns the TreeIter for a notebook name or None'''
		for row in self:
			if row[NAME_COL] == notebook:
				return row.iter
		else:
			return None

	def get_default(self):
		'''Returns a TreeIter for the default notebook or None'''
		default = self.notebooks['_default_']
		if not default is None:
			return self.get_iter_from_notebook(default)
		else:
			return None

	def set_default(self, iter):
		'''Set the default notebook using a TreeIter,
		set to None to reset the default.
		'''
		if iter is None:
			self.notebooks['_default_'] = None
		else:
			self.notebooks['_default_'] = unicode(self[iter][NAME_COL])
		self.write_list()

	def do_row_inserted(self, path, iter):
		self.write_list()

	# TODO do_rows_reordered

	# TODO do_row_deleted

	def write_list(self):
		list = [unicode(row[NAME_COL]) for row in self]
		self.notebooks.set_order(list)
		print 'SAVE', self.notebooks
		# TODO: self.notebooks.write()


class NotebookTreeView(gtkutils.BrowserTreeView):

	def __init__(self, model=None):
		# TODO: add logic to flag open notebook italic - needs daemon
		if model is None:
			model = NotebookTreeModel()
		gtkutils.BrowserTreeView.__init__(self, model)
		self.set_rules_hint(True)
		self.set_reorderable(True)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('Notebook', cell_renderer, text=NAME_COL)
		column.set_sort_column_id(NAME_COL)
		self.append_column(column)


class NotebookComboBox(gtk.ComboBox):
	'''Combobox showing the a list of notebooks'''

	def __init__(self, model=None):
		'''Constructor, "model" should be a NotebookTreeModel or None to
		use the default list.
		'''
		if model is None:
			model = NotebookTreeModel()
		gtk.ComboBox.__init__(self, model)
		cell_renderer = gtk.CellRendererText()
		self.pack_start(cell_renderer, False)
		self.set_attributes(cell_renderer, text=0)

	def set_notebook(self, notebook):
		iter = self.get_model().get_iter_from_notebook(notebook)
		if iter is None:
			self.set_active(-1)
		else:
			self.set_active_iter(iter)

	def get_notebook(self):
		iter = self.get_active()
		if iter == -1:
			return None
		else:
			model = self.get_model()
			return model[iter][NAME_COL]


class DefaultNotebookComboBox(NotebookComboBox):
	'''Combobox which sets the default notebook'''

	def __init__(self, model=None):
		NotebookComboBox.__init__(self, model)
		self._block_changed = False
		self.do_model_changed(self.get_model())

	def do_changed(self):
		# Set default if triggered by user action
		if not self._block_changed:
			model = self.get_model()
			i = self.get_active()
			if i >= 0:
				model.set_default(iter)
			else:
				model.set_default(None)

	def do_model_changed(self, model):
		# Set the combobox to display the correct row, assume the default
		# is set to the name of one of the other notebooks.
		# This needs to be done everytime the model changes
		self._block_changed = True
		iter = model.get_default()
		if iter is None:
			self.set_active(-1)
		else:
			self.set_active_iter(iter)
		self._block_changed = False


class NotebookDialog(gtk.Dialog):

	def __init__(self, app):
		self.app = app

		# FIXME have helper for creating dialogs
		gtk.Dialog.__init__(self,
			title  = 'Open Notebook - Zim',
			parent = app.mainwindow,
			flags= gtk.DIALOG_NO_SEPARATOR,
		)
		self.set_default_size(500, 400)
		self.set_border_width(10)
		self.vbox.set_spacing(5)
		help = self.add_button(gtk.STOCK_HELP, 9)
		self.add_buttons(
			gtk.STOCK_CANCEL, 0,
			gtk.STOCK_OPEN, 42,
		)
		self.action_area.set_child_secondary(help, True)

		# show some art work in an otherwise boring dialog
		path = data_file('globe_banner_small.png').path
		image = gtk.Image()
		image.set_from_file(path) # new_from_file not in 2.6
		align = gtk.Alignment(0,0.5, 0,0)
		align.add(image)
		self.vbox.pack_start(align, False)

		# split between treeview and vbuttonbox
		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)

		# add notebook list - open notebook on clicking a row
		self.treeview = NotebookTreeView()
		self.treeview.connect('row-activated', lambda *a: self.response(42))

		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		swindow.add(self.treeview)
		hbox.add(swindow)

		# add buttons for modifying the treeview
		vbbox = gtk.VButtonBox()
		vbbox.set_layout(gtk.BUTTONBOX_START)
		hbox.pack_start(vbbox, False)
		add_button = gtk.Button(stock='gtk-add')
		add_button.connect('clicked', self.do_add_notebook)
		edit_button = gtk.Button(stock='gtk-edit')
		edit_button.connect('clicked', self.do_edit_notebook)
		rm_button = gtk.Button(stock='gtk-remove')
		rm_button.connect('clicked', self.do_remove_notebook)
		for b in (add_button, edit_button, rm_button):
			b.set_alignment(0.0, 0.5)
			vbbox.add(b)
		# FIXME buttons for "up" and "down" ?

		# add dropdown to select default
		self.combobox = DefaultNotebookComboBox(self.treeview.get_model())

		# clear button de-selects any item in the combobox
		clear_button = gtkutils.icon_button('gtk-clear')
		clear_button.connect('clicked', lambda o: self.combobox.set_active(-1))

		hbox = gtk.HBox(spacing=5)
		hbox.pack_start(gtk.Label('Default notebook:'), False)
		hbox.pack_start(self.combobox, False)
		hbox.pack_start(clear_button, False)
		self.vbox.pack_start(hbox, False)

	def main(self):
		'''Show and run the dialog. Does not have a return value, actions
		are called directly on the application object.
		'''
		self.show_all()
		self.treeview.grab_focus()

		def do_run():
			id = self.run()
			if id == 42: # Open
				# TODO get notebook selection
				model, iter = self.treeview.get_selection().get_selected()
				if iter is None:
					return True
				name = model[iter][0]
				self.app.open_notebook(name)
				return False
			elif id == 9: # Help
				self.app.show_help(':Usage:Notebooks')
				return True
			else: # Close or destroy
				return False

		while do_run():
			pass

		self.hide()

	def do_add_notebook(self, *a):
		# TODO: add "new" notebook in list and select it
		self.edit_notebook()

	def do_edit_notebook(self, *a):
		model, iter = self.treeview.get_selection().get_selected()
		if iter is None: return
		notebook = self.notebooks[model[iter][NAME_COL]]
		print 'TODO: run properties dialog'
		self._save_notebook_list() # directory could have changed

	def do_remove_notebook(self, *a):
		model, iter = self.treeview.get_selection().get_selected()
		if iter is None: return
		print 'DEL', model[iter][NAME_COL]
		#~ del model[iter]
		self._save_notebook_list()

