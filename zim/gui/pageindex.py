# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''


import gobject
import gtk


class PageIndex(gtk.ScrolledWindow):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING,) ),
	}

	def __init__(self):
		'''FIXME'''
		gtk.ScrolledWindow.__init__(self)
		self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.treemodel = gtk.TreeStore(str, str) # 2 columns
		self.treeview = gtk.TreeView(self.treemodel)
		self.add(self.treeview)

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn('_pages_', cell_renderer, text=0)
		self.treeview.append_column(column)
		self.treeview.get_selection().set_mode(gtk.SELECTION_BROWSE)
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
		# TODO clear model
		# TODO use idle loop to delay loading long lists

		def add_page(parent, page):
			iter = self.treemodel.append(parent, row=(page.basename, page.name))
			if page.children:
				for child in page.children:
					add_page(iter, child) # recurs

		for page in pagelist:
			add_page(None, page)


# Need to register classes defining gobject signals
gobject.type_register(PageIndex)
