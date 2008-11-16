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

from zim import Component, notebook
from zim.utils import data_file
from zim.gui import gtkutils


NAME_COL = 0  # column with notebook name
OPEN_COL = 1  # column with boolean if notebook is open alreadys


class NotebookDialog(gtk.Dialog, Component):

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
		image = gtk.image_new_from_file(path)
		align = gtk.Alignment(0,0.5, 0,0)
		align.add(image)
		self.vbox.pack_start(align, False)

		# split between treeview and vbuttonbox
		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)

		# add notebook list
		# TODO: add logic to flag open notebook italic - needs daemon
		self.treemodel = gtk.ListStore(str, bool) # NAME_COL, OPEN_COL
		self.treeview = gtkutils.BrowserTreeView(self.treemodel)
		self.treeview.set_rules_hint(True)
		self.treeview.set_reorderable(True)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('Notebook', cell_renderer, text=NAME_COL)
		column.set_sort_column_id(NAME_COL)
		self.treeview.append_column(column)

		# when the list is re-ordered we save it
		id = self.treemodel.connect_after('row-inserted', self._save_notebook_list)
		self.row_inserted_handler = id

		# open notebook on clicking a row
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
		self.combobox = gtk.ComboBox(model=self.treemodel)
		cell_renderer = gtk.CellRendererText()
		self.combobox.pack_start(cell_renderer, False)
		self.combobox.set_attributes(cell_renderer, text=0)

		def on_set_default(*a):
			i = self.combobox.get_active()
			if i >= 0:
				default = self.treemodel[i][NAME_COL]
				self.notebooks['_default_'] = default
			else:
				self.notebooks['_default_'] = None
			self._save_notebook_list()

		id = self.combobox.connect('changed', on_set_default)
		self.combobox_changed_handler = id

		# clear button de-selects any item in the combobox
		clear_button = gtkutils.icon_button('gtk-clear')
		clear_button.connect('clicked', lambda *a: self.combobox.set_active(-1))

		hbox = gtk.HBox(spacing=5)
		hbox.pack_start(gtk.Label('Default notebook:'), False)
		hbox.pack_start(self.combobox, False)
		hbox.pack_start(clear_button, False)
		self.vbox.pack_start(hbox, False)

	def main(self):
		'''Run the dialog.

		Before this method returns the widget is destroyed, so you can not
		re-use the object after this. Does not have a return value, actions
		are called directly on the application object.
		'''
		self._load_notebook_list()
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

		self.destroy()

	def _load_notebook_list(self):
		self.treemodel.handler_block(self.row_inserted_handler)
		self.notebooks = notebook.get_notebook_table()
		for name, path in self.notebooks.items():
			if not (name.startswith('_') and name.endswith('_')):
				self.treemodel.append((name, False))
		self._set_combobox()
		self.treemodel.handler_unblock(self.row_inserted_handler)

	def _save_notebook_list(self, *a):
		self._set_combobox() # probably the model has changed
		notebooks = [unicode(row[NAME_COL]) for row in self.treemodel]
		self.notebooks.set_order(notebooks)
		print 'SAVE', self.notebooks
		#~ self.notebooks.write()

	def _set_combobox(self):
		# Set the combobox to display the correct row, assume the default
		# is set to the name of one of the other notebooks.
		self.combobox.handler_block(self.combobox_changed_handler)
		default = self.notebooks.get('_default_')
		if default is None:
			self.combobox.set_active(-1)
		else:
			for row in self.treemodel:
				if row[NAME_COL] == default:
					self.combobox.set_active_iter(row.iter)
					break
		self.combobox.handler_unblock(self.combobox_changed_handler)

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

