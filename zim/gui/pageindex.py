# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a class to display an index of pages.
This widget is used primarily in the side pane of the main window,
but also e.g. for the page lists in the search dialog.
'''

import gobject
import gtk
import pango
import logging

from zim.index import IndexPath
from zim.gui.widgets import BrowserTreeView


logger = logging.getLogger('zim.gui.pageindex')


NAME_COL = 0  # column with short page name (page.basename)
PATH_COL = 1  # column with the zim IndexPath itself

# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVAL_C = gtk.gdk.unicode_to_keyval(ord('c'))
KEYVAL_L = gtk.gdk.unicode_to_keyval(ord('l'))


class PageTreeStore(gtk.GenericTreeModel, gtk.TreeDragSource, gtk.TreeDragDest):
	'''Custom TreeModel that is integrated closely with the Index object.
	In fact it is jsut an API layer translating between the gtk.TreeView and
	the zim Index interfaces. It fetches data on the fly when requested and
	does not keep it's own cache. This allows scaling to very large notebooks.

	Note: Be aware that in this interface there are two classes both referred
	to as "paths". The first is gtk.TreePath and the second is
	zim.notebook.Path . When a TreePath is intended the argument is called
	explicitly "treepath", while arguments called "path" refer to a zim Path.

	TODO: see python gtk-2.0 tutorial for remarks about reference leaking !
	'''

	def __init__(self, index):
		gtk.GenericTreeModel.__init__(self)
		self.index = index
		#~ def log(o, p, m): print '!!', m, p, p._indexpath
		#~ index.connect('page-inserted', log, 'page-inserted')
		index.connect('page-inserted',
			lambda o, p: self.emit('row-inserted',
				self.get_treepath(p), self.create_tree_iter(p)))
		#~ index.connect('page-updated', log, 'page-updated')
		index.connect('page-updated',
			lambda o, p: self.emit('row-changed',
				self.get_treepath(p), self.create_tree_iter(p)))
		#~ index.connect('page-haschildren-toggled', log, 'page-haschildren-toggled')
		index.connect('page-haschildren-toggled',
			lambda o, p: self.emit('row-has-child-toggled',
				self.get_treepath(p), self.create_tree_iter(p)))
		index.connect('delete',
			lambda o, p: self.emit('row-deleted', self.get_treepath(p)))

	def on_get_flags(self):
		return 0 # no flags

	def on_get_n_columns(self):
		return 2 # two columns

	def on_get_column_type(self, index):
		#~ print '>> on_get_column_type', index
		if index == 0:
			return gobject.TYPE_STRING
		elif index == 1:
			return gobject.TYPE_PYOBJECT

	def on_get_iter(self, treepath):
		'''Returns an IndexPath for a TreePath or None'''
		# Path (0,) is the first item in the root namespace
		# Path (2, 4) is the 5th child of the 3rd item
		#~ print '>> on_get_iter', treepath
		iter = None
		for i in treepath:
			iter = self.on_iter_nth_child(iter, i)
			if iter is None:
				break
		return iter

	def get_treepath(self, path):
		'''Returns a TreePath for a given IndexPath'''
		# There is no TreePath class in pygtk,just return tuple of integers
		# FIXME this method looks quite inefficient, can we optimize it ?
		if not isinstance(path, IndexPath):
			path = self.index.lookup_path(path)
			if path is None or path.isroot:
				raise ValueError
		treepath = []
		for parent in path.parents():
			pagelist = self.index.list_pages(parent)
			treepath.insert(0, pagelist.index(path))
			path = parent
		return tuple(treepath)

	on_get_path = get_treepath # alias for GenericTreeModel API

	def get_indexpath(self, iter):
		'''Returns an IndexPath for a TreeIter'''
		return self.get_user_data(iter)

	def on_get_value(self, path, column):
		'''Returns the data for a specific column'''
		#~ print '>> on_get_value', path, column
		if column == 0:
			return path.basename
		elif column == 1:
			return path

	def on_iter_next(self, path):
		'''Returns the IndexPath for the next row on the same level or None'''
		# Only within one namespace, so not the same as index.get_next()
		#~ print '>> on_iter_next', path
		if not path._pagelist_ref is None:
			pagelist = path._pagelist_ref
			i = path._pagelist_index + 1
		else:
			pagelist = self.index.list_pages(path.parent)
			i = pagelist.index(path) + 1

		if i >= len(pagelist):
			return None
		else:
			next = pagelist[i]
			next._pagelist_ref = pagelist
			next._pagelist_index = i
			return next

	def on_iter_children(self, path=None):
		'''Returns an indexPath for the first child below path or None.
		If path is None returns the first top level IndexPath.
		'''
		#~ print '>> on_iter_children', path
		pagelist = self.index.list_pages(path)
		if pagelist:
			child = pagelist[0]
			child._pagelist_ref = pagelist
			child._pagelist_index = 0
			return child
		else:
			return None

	def on_iter_has_child(self, path):
		'''Returns True if indexPath path has children'''
		if not path.hasdata:
			path = self.index.lookup_data(path)
		return path.haschildren

	def on_iter_n_children(self, path=None):
		'''Returns the number of children in a namespace. As a special case,
		when page is None the number of pages in the root namespace is given.
		'''
		pagelist = self.index.list_pages(path)
		return len(pagelist)

	def on_iter_nth_child(self, path, n):
		'''Returns the nth child for a given IndexPath or None.
		As a special case path can be None to get pages in the root namespace.
		'''
		#~ print '>> on_iter_nth_child', path, n
		pagelist = self.index.list_pages(path)
		if n >= len(pagelist):
			return None
		else:
			child = pagelist[n]
			child._pagelist_ref = pagelist
			child._pagelist_index = n
			return child

	def on_iter_parent(self, child):
		'''Returns a IndexPath for parent node of child or None'''
		parent = child.parent
		if parent.isroot:
			return None
		else:
			return parent

	# Compatibility for older version of GenericTreeModel
	if not hasattr(gtk.GenericTreeModel, 'create_tree_iter'):
		logger.warn('Using work around for older version of GenericTreeModel - may hurt performance')
		def create_tree_iter(self, indexpath):
			'''Turn an IndexPath into a TreeIter'''
			treepath = self.get_treepath(indexpath)
			return self.get_iter(treepath)

	if not hasattr(gtk.GenericTreeModel, 'get_user_data'):
		def get_user_data(self, treeiter):
			'''Turn a TreeIter into an IndexPath'''
			return self.get_value(treeiter, 1)

	def row_draggable(self, path):
		return True

	def drag_data_get(self, path, selection):
		return False

	def drag_data_delete(self, path):
		return False

	def row_drop_possible(self, path, selection):
		return True

	def drag_data_received(self, path, selection):
		return True


class PageTreeView(BrowserTreeView):
	'''Wrapper for a TreeView showing a list of pages.'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self, ui):
		BrowserTreeView.__init__(self)

		if not ui is None: # is None in test case
			self.ui = ui
			self.ui.connect('open-page', lambda o, p, r: self.select_page(p))
			self.ui.connect_after('open-notebook', self.do_set_notebook)
			if not self.ui.notebook is None:
				self.do_set_notebook(self.app, self.ui.notebook)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_pages_', cell_renderer, text=NAME_COL)
		self.append_column(column)
		self.set_headers_visible(False)

		self.set_enable_search(True)
		self.set_search_column(0)

		self.enable_model_drag_source(
			gtk.gdk.BUTTON1_MASK, (('text/x-zim-page-list', 0, 0),),
			gtk.gdk.ACTION_LINK|gtk.gdk.ACTION_MOVE )
		self.enable_model_drag_dest(
			(('text/x-zim-page-list', 0, 0),),
			gtk.gdk.ACTION_LINK )

	def do_set_notebook(self, ui, notebook):
		self.set_model(PageTreeStore(notebook.index))
		if not ui.page is None:
			self.select_page(ui.page)

	def do_row_activated(self, treepath, column):
		'''Handler for the row-activated signal, emits page-activated'''
		model = self.get_model()
		iter = model.get_iter(treepath)
		path = model.get_indexpath(iter)
		self.emit('page-activated', path)

	def do_page_activated(self, path):
		'''Handler for the page-activated signal, calls ui.open_page()'''
		self.ui.open_page(path)

	def do_key_press_event(self, event):
		# Keybindings for the treeview:
		#  Ctrl-C copy link to selected page
		#  Ctrl-L insert link to selected page in pageview
		#  Esc closes the side pane
		# Keybindings for collapsing and expanding items are
		# implemented in the BrowserTreeView parent class
		handled = True
		#~ print 'KEY %s (%i)' % (gtk.gdk.keyval_name(event.keyval), event.keyval)

		# FIXME Ctrl-C ad Ctrl-L are masked by standard actions - need to switch those with focus
		if event.state & gtk.gdk.CONTROL_MASK:
			if event.keyval == KEYVAL_C:
				print 'TODO copy location'
			elif event.keyval == KEYVAL_L:
				print 'TODO insert link'
			else:
				handled = False
		else:
			handled = False

		if handled:
			return True
		else:
			return BrowserTreeView.do_key_press_event(self, event)

	def do_button_release_event(self, event):
		'''Handler for button-release-event, triggers popup menu'''
		if event.button == 3:
			self.emit('popup-menu')# FIXME do we need to pass x/y and button ?
			return True
		else:
			return BrowserTreeView.do_button_release_event(self, event)

	def do_popup_menu(self): # FIXME do we need to pass x/y and button ?
		menu = self.ui.uimanager.get_widget('/page_popup')
		menu.popup(None, None, None, 3, 0)
		return True

	def do_drag_data_get(self, context, selection_data, info, time):
		print 'drag GET'

	def do_drag_data_recieved(self, context, x, y, selection_data, info, time):
		print 'drag PUT'

	def select_page(self, path):
		'''Select a page in the treeview, connected to the open-page signal'''
		model, iter = self.get_selection().get_selected()
		if model is None:
			return # index not yet initialized ...
		#~ if not iter is None and model[iter][PAGE_COL] == pagename:
			#~ return  # this page was selected already

		# TODO unlist temporary listed items
		# TODO temporary list new item if page does not exist

		path = self.ui.notebook.index.lookup_path(path)
		if path is None:
			pass # TODO temporary list the thing in the index
		else:
			treepath = model.get_treepath(path)
			self.expand_to_path(treepath)
			self.get_selection().select_path(treepath)
			self.set_cursor(treepath)
			self.scroll_to_cell(treepath)


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

	def get_selected_path(self):
		'''Returns path currently selected or None'''
		model, iter = self.treeview.get_selection().get_selected()
		if model is None or iter is None:
			return None
		else:
			return model.get_indexpath(iter)
