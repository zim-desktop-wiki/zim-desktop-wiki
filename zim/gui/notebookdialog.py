# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gobject
import gtk

from zim.utils import data_file, config_file, ConfigList


class NotebookDialog(object):
	'''FIXME'''

	def __init__(self, app):
		'''FIXME'''
		self.app = app

		# FIXME have helper for creating dialogs
		self.dialog = gtk.Dialog(
			title  = 'Open Notebook - Zim',
			parent = app.window,
			flags= gtk.DIALOG_NO_SEPARATOR,
		)
		self.dialog.set_default_size(500, 350)
		self.dialog.set_border_width(10)
		self.dialog.vbox.set_spacing(5)
		help = self.dialog.add_button(gtk.STOCK_HELP, 9)
		self.dialog.add_buttons(
			gtk.STOCK_CANCEL, 0,
			gtk.STOCK_OPEN, 42,
		)
		self.dialog.action_area.set_child_secondary(help, True)

		# show some art work in an otherwise boring dialog
		path = data_file('globe_banner_small.png').path
		image = gtk.image_new_from_file(path)
		align = gtk.Alignment(0,0.5, 0,0)
		align.add(image)
		self.dialog.vbox.pack_start(align, expand=False)

		# add notebook list
		# TODO need helper class to wrap treeviews - my own SimpleTreeView
		# TODO: add logic to flag open notebook italic - needs daemon
		self.treemodel = gtk.ListStore(gobject.TYPE_STRING)
		self.treeview = gtk.TreeView(self.treemodel)
		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn('Notebook', cell_renderer, text=0)
		self.treeview.append_column(column)
		self.treeview.get_selection().set_mode(gtk.SELECTION_BROWSE)

		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		swindow.add(self.treeview)
		self.dialog.vbox.add(swindow)

		def do_row_activated(*args):
			self.dialog.response(42) # Open notebook
		self.treeview.connect('row-activated', do_row_activated)

	def run(self):
		'''FIXME'''
		self.load_notebook_list()
		self.dialog.show_all()
		self.treeview.grab_focus()

		def do_run():
			id = self.dialog.run()
			if id == 42: # Open
				# TODO get notebook selection
				model, iter = self.treeview.get_selection().get_selected()
				if iter is None:
					return True
				name = model.get_value(iter, 0)
				self.app.open_notebook(name)
				return False
			elif id == 9: # Help
				self.show_help()
				return True
			else: # Close or destroy
				return False

		while do_run():
			pass

		self.dialog.destroy()

	def load_notebook_list(self):
		'''FIXME'''
		self.notebooks = ConfigList()
		self.notebooks.read(config_file('notebooks.list'))
		#~ print self.notebooks
		for name, path in self.notebooks.items():
			if not (name.startswith('_') and name.endswith('_')):
				self.treemodel.append((name,))

	def save_notebook_list(self):
		'''FIXME'''
		# TODO

	def show_help(self):
		'''FIXME'''
		# TODO: open help window
