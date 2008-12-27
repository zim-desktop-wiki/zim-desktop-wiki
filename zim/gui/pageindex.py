# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a class to display an index of pages.
This widget is used primarily in the side pane of the main window,
but also e.g. for the page lists in the search dialog.
'''

import gobject
import gtk
import pango

from zim.gui import gtkutils

NAME_COL = 0  # column with short page name (page.basename)
PAGE_COL = 1  # column with the full page name (page.name)

class PageTreeStore(gtk.TreeStore):

	def __init__(self):
		gtk.TreeStore.__init__(self, str, str) # NAME_COL, PAGE_COL

	def add_pages(self, pagelist):

		def add_page(parent, page):
			row = (page.basename, page.name)
			iter = self.append(parent, row)
			if page.children:
				for child in page.children:
					add_page(iter, child) # recurs

		for page in pagelist:
			add_page(None, page)

	def get_path_from_page(self, page):
		'''Returns the treemodel path for a given page or page name'''
		if not isinstance(page, basestring):
			page = page.name

		iter = None
		path = ''
		for part in page.strip(':').split(':'):
			path += ':'+part
			iter = self.iter_children(iter)
				# will give root iter when iter is None
			if iter is None:
				return None

			while self[iter][PAGE_COL] != path:
				iter = self.iter_next(iter)
				if iter is None:
					return None

		return self.get_path(iter)

	def get_page_from_path(self, path):
		'''Returns the page name for a given path in the treemodel'''
		iter = self.get_iter(path)
		return self[iter][PAGE_COL]


class PageTreeView(gtkutils.BrowserTreeView):
	'''Wrapper for a TreeView showing a list of pages.'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, None, (str,)),
	}

	def __init__(self, app):
		gtkutils.BrowserTreeView.__init__(self)
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

	def set_pages(self, pagelist):
		'''Set the page list. This can by e.g. a Namespace object.'''
		# TODO delay init of actual page tree till it is shown
		# TODO use idle loop to delay loading long lists
		self.set_model(PageTreeStore()) # flush old list
		self.get_model().add_pages(pagelist)

	def do_row_activated(self, path, column):
		'''Handler for the row-activated signal, emits page-activated'''
		pagename = self.get_model().get_page_from_path(path)
		self.emit('page-activated', pagename)

	def do_page_activated(self, pagename):
		'''Handler for the page-activated signal, calls app.open_page()'''
		self.app.open_page(pagename)

	def do_key_press_event(self, event):
		'''Handler for key presses'''
		if gtkutils.BrowserTreeView.do_key_press_event(self, event):
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
			return gtkutils.BrowserTreeView.do_button_release_event(self, event)

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

		if not iter is None and model[iter][PAGE_COL] == pagename:
			return  # this page was selected already

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
