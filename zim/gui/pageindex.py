# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a class to display an index of pages.
This widget is used primarily in the side pane of the main window,
but also e.g. for the page lists in the search dialog.
'''

import gobject
import gtk
import pango

from zim.gui.widgets import BrowserTreeView

NAME_COL = 0  # column with short page name (page.basename)

class PageTreeStore(gtk.GenericTreeModel):
	'''FIXME

	Note: Be aware that in this interface there are two classes both referred
	to as "paths". The first is gtk.TreePath and the second is
	zim.notebook.Path . When a TreePath is intended the argument is called
	explicitly "treepath", while arguments called "path" refer to a zim Path.

	TODO see python gtk-2.0 tutorial for remarks about reference leaking !
	'''

	def __init__(self, index):
		gtk.GenericTreeModel.__init__(self)
		self.index = index

	def on_get_flags(self):
		return 0 # no flags

	def on_get_n_columns(self):
		return 1 # only one column

	def on_get_column_type(self, index):
		assert index == 0
		return unicode

	def on_get_iter(self, path):
		iter = None
		for i in path:
			iter = self.on_iter_nth_child(iter, i)
		return iter

	def get_treepath(self, path):
		'''Returns a treepath for a given path'''
		treepath = []
		while path:
			parent = self.index.get_parent(path)
			pagelist = self.index.get_pagelist(parent)
			treepath.append(pagelist.index(path))
			path = parent
		treepath.reverse()
		return treepath

	on_get_path = get_treepath # alias for GenericTreeModel API

	def on_get_value(self, path, column):
		assert column == 0
		return path.name

	def on_iter_next(self, path):
		# Only within one namespace, so not the same as index.get_next()
		if hasattr(path, '_pagelist'):
			pagelist = path._pagelist
			i = path._i
		else:
			parent = self.index.get_parent(path)
			pagelist = self.index.get_pagelist(parent)
			i = pagelist.index(path) + 1
		try:
			next = pagelist[i]
			next._pagelist = pagelist
			next._i = i
			return next
		except IndexError:
			return None

	def on_iter_children(self, path):
		pagelist = self.index.get_pagelist(path)
		child = pagelist[0]
		child._pagelist = pagelist
		child._i = 0
		return child

	def on_iter_has_child(self, path):
		return path.haschildren

	def on_iter_n_children(self, path):
		pagelist = self.index.get_pagelist(path)
		return len(pagelist)

	def on_iter_nth_child(self, parent, n):
		pagelist = self.index.get_pagelist(path)
		try:
			return pagelist[n]
		except IndexError:
			return None

	def on_iter_parent(self, child):
		return self.index.get_parent(child)


class PageTreeView(BrowserTreeView):
	'''Wrapper for a TreeView showing a list of pages.'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, None, (str,)),
	}

	def __init__(self, app):
		BrowserTreeView.__init__(self)
		self.app = app
		self.app.connect('open-page', lambda o, p, r: self.select_page(p))

		self.set_model(PageTreeStore())
		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_pages_', cell_renderer, text=NAME_COL)
		self.append_column(column)
		self.set_headers_visible(False)

		# TODO drag & drop stuff
		# TODO popup menu for pages

	def do_row_activated(self, path, column):
		'''Handler for the row-activated signal, emits page-activated'''
		pagename = self.get_model().get_page_from_path(path)
		self.emit('page-activated', pagename)

	def do_page_activated(self, pagename):
		'''Handler for the page-activated signal, calls app.open_page()'''
		self.app.open_page(pagename)

	def do_key_press_event(self, event):
		'''Handler for key presses'''
		if BrowserTreeView.do_key_press_event(self, event):
			return True

		try:
			key = chr(event.keyval)
		except ValueError:
			return False

		if event.state == gtk.gdk.CONTROL_MASK:
			if   key == 'c':
				print 'TODO copy location'
			elif key == 'l':
				print 'TODO insert link'
			else:
				return False
		else:
			return False

	def do_button_release_event(self, event):
		'''Handler for button-release-event, triggers popup menu'''
		if event.button == 3:
			self.emit('popup-menu')# FIXME do we need to pass x/y and button ?
			return True
		else:
			return BrowserTreeView.do_button_release_event(self, event)

	def do_popup_menu(self): # FIXME do we need to pass x/y and button ?
		print 'TODO: trigger popup for page'
		return True

	def select_page(self, page):
		'''Select a page in the treeview, connected to the open-page signal'''
		model, iter = self.get_selection().get_selected()
		if not isinstance(page, basestring):
			pagename = page.name
		else:
			pagename = page

		#~ if not iter is None and model[iter][PAGE_COL] == pagename:
			#~ return  # this page was selected already

		# TODO unlist temporary listed items
		# TODO temporary list new item if page does not exist

		path = model.get_path_from_page(pagename)
		self.expand_to_path(path)
		self.get_selection().select_path(path)
		self.set_cursor(path)
		self.scroll_to_cell(path)


# Need to register classes defining gobject signals
gobject.type_register(PageTreeView)


class PageIndex(gtk.ScrolledWindow):

	def __init__(self, app):
		gtk.ScrolledWindow.__init__(self)
		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.treeview = PageTreeView(app)
		self.add(self.treeview)

	def grab_focus(self):
		self.treeview.grab_focus()
