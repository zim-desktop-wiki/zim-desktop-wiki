# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a class to display an index of pages.
This widget is used primarily in the side pane of the main window,
but also e.g. for the page lists in the search dialog.
'''


import gobject
import gtk
import pango

from zim import Component
from zim.gui import gtkutils

NAME_COL = 0  # column with short page name (page.basename)
PAGE_COL = 1  # column with the full page name (page.name)

class PageIndex(gtk.ScrolledWindow, Component):
	'''Wrapper for a TreeView showing a list of pages.'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING,) ),
	}

	def __init__(self, app):
		'''Simple constructor'''
		self.app = app
		gtk.ScrolledWindow.__init__(self)
		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.treemodel = gtk.TreeStore(str, str) # NAME_COL, PAGE_COL
		self.treeview = gtkutils.BrowserTreeView(self.treemodel)
		self.add(self.treeview)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_pages_', cell_renderer, text=NAME_COL)
		self.treeview.append_column(column)
		self.treeview.set_headers_visible(False)
		#~ self.treeview.set_search_column(1)
		#~ self.treeview.set_search_equal_func(...)

		# TODO drag & drop stuff
		# TODO popup menu for pages

		def do_row_activated(treeview, path, column):
			model = treeview.get_model()
			iter = model.get_iter(path)
			pagename = model[iter][1]
			self.emit('page-activated', pagename)

		self.treeview.connect('row-activated', do_row_activated)

	def set_pages(self, pagelist):
		'''Set the page list. This can by e.g. a Namespace object.'''
		# TODO use idle loop to delay loading long lists

		if len(self.treemodel):
			self.debug('Flush index')
			self.treemodel = gtk.TreeStore(str, str) # NAME_COL, PAGE_COL
			self.treeview.set_model(self.treemodel)

		def add_page(parent, page):
			row = (page.basename, page.name)
			iter = self.treemodel.append(parent, row)
			if page.children:
				for child in page.children:
					add_page(iter, child) # recurs

		for page in pagelist:
			add_page(None, page)


# Need to register classes defining gobject signals
gobject.type_register(PageIndex)
