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
from zim.notebook import Path
from zim.gui.widgets import BrowserTreeView, ErrorDialog
from zim.gui.clipboard import \
	INTERNAL_PAGELIST_TARGET_NAME, INTERNAL_PAGELIST_TARGET, \
	pack_urilist, unpack_urilist


logger = logging.getLogger('zim.gui.pageindex')


NAME_COL = 0  # column with short page name (page.basename)
PATH_COL = 1  # column with the zim IndexPath itself
EMPTY_COL = 2 # column to flag if the page is empty or not
STYLE_COL = 3 # column to specify style (based on empty or not)
FGCOLOR_COL = 4 # column to specify color (based on empty or not)

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

	# We inherit from gtk.TreeDragSource and gtk.TreeDragDest even though
	# we do not actually implement them. Somehow this is needed to get
	# the TreeView to understand we support drag-and-drop even though
	# actual work is implemented in the treeview itself.

	# FIXME: Figure out how to bind cellrendere style to the
	# EMPTY_COL so we do not need the separate style and fgcolor cols.
	# This will also allow making style for empty pages configurable.

	COLUMN_TYPES = (
		gobject.TYPE_STRING, # NAME_COL
		gobject.TYPE_PYOBJECT, # PATH_COL
		bool, # EMPTY_COL
		pango.Style, # STYLE_COL
		gtk.gdk.Color, # FGCOLOR_COL
	)

	style = gtk.Label().get_style() # HACK - how to get default style ?
	NORMAL_COLOR = style.text[gtk.STATE_NORMAL]
	EMPTY_COLOR = style.text[gtk.STATE_INSENSITIVE]

	def __init__(self, index):
		gtk.GenericTreeModel.__init__(self)
		self.index = index

		self.set_property('leak-references', False)
			# We do our own memory management, thank you very much
		self._refs = {}

		def on_changed(o, path, signal):
			#~ print '!!', signal, path
			self._flush()
			treepath = self.get_treepath(path)
			treeiter = self.create_tree_iter(self._ref(path))
			self.emit(signal, treepath, treeiter)

		def on_deleted(o, path):
			#~ print '!! delete', path
			self._flush()
			treepath = self.get_treepath(path)
			self.emit('row-deleted', treepath)

		index.connect('page-inserted', on_changed, 'row-inserted')
		index.connect('page-updated', on_changed, 'row-changed')
		index.connect('page-haschildren-toggled', on_changed, 'row-has-child-toggled')
		index.connect('delete', on_deleted)
		index.connect('end-update', lambda o: self._flush())

	def _ref(self, path):
		# Make sure we keep ref to paths long enough while they
		# are used in an iter
		if path.id in self._refs:
			return self._refs[path.id]
		else:
			self._refs[path.id] = path
			return path

	def _flush(self):
		# Drop references and free memory
		#~ print '!! Freeing %i refs' % len(self._refs)
		self.invalidate_iters()
		del self._refs
		self._refs = {}

	def on_get_flags(self):
		return 0 # no flags

	def on_get_n_columns(self):
		return len(self.COLUMN_TYPES)

	def on_get_column_type(self, i):
		#~ print '>> on_get_column_type', index
		return self.COLUMN_TYPES[i]

	def on_get_value(self, path, column):
		'''Returns the data for a specific column'''
		#~ print '>> on_get_value', path, column
		if column == NAME_COL:
			return path.basename
		elif column == PATH_COL:
			return path
		elif column == EMPTY_COL:
			return path.hascontent or path.haschildren
		elif column == STYLE_COL:
			if path.hascontent or path.haschildren:
				return pango.STYLE_NORMAL
			else:
				return pango.STYLE_ITALIC
		elif column == FGCOLOR_COL:
			if path.hascontent or path.haschildren:
				return self.NORMAL_COLOR
			else:
				return self.EMPTY_COLOR

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
		# There is no TreePath class in pygtk, just return tuple of integers
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
			return self._ref(next)

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
			return self._ref(child)
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
		if path is None:
			path = Path(':')
		return self.index.n_list_pages(path)

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
			return self._ref(child)

	def on_iter_parent(self, child):
		'''Returns a IndexPath for parent node of child or None'''
		parent = child.parent
		if parent.isroot:
			return None
		else:
			return self._ref(parent)

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

# Need to register classes defining gobject signals or overloading methods
gobject.type_register(PageTreeStore)


class PageTreeView(BrowserTreeView):
	'''Wrapper for a TreeView showing a list of pages.'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self, ui):
		BrowserTreeView.__init__(self)
		self._vivivied = None

		if not ui is None: # is None in test case
			self.ui = ui
			self.ui.connect('open-page',
				lambda o, p, r: self.select_page(p, vivify=True) )
			self.ui.connect_after('open-notebook', self.do_set_notebook)
			if not self.ui.notebook is None:
				self.do_set_notebook(self.app, self.ui.notebook)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_pages_', cell_renderer,
			text=NAME_COL, style=STYLE_COL, foreground_gdk=FGCOLOR_COL)
		self.append_column(column)
		#~ column = gtk.TreeViewColumn('_style_', cell_renderer, text=EXISTS_COL)
		#~ self.append_column(column)
		self.set_headers_visible(False)

		self.set_enable_search(True)
		self.set_search_column(0)

		self.enable_model_drag_source(
			gtk.gdk.BUTTON1_MASK, (INTERNAL_PAGELIST_TARGET,),
			gtk.gdk.ACTION_LINK | gtk.gdk.ACTION_MOVE )
		self.enable_model_drag_dest(
			(INTERNAL_PAGELIST_TARGET,),
			gtk.gdk.ACTION_MOVE )

		if gtk.gtk_version > (2, 10, 0):
			self.set_enable_tree_lines(True)
			# TODO: add ui preference for this
			# need to grey out preference for gtk < 2.10
			# so need signal after construction preferenes dialog


	def do_set_notebook(self, ui, notebook):
		self.set_model(PageTreeStore(notebook.index))
		if not ui.page is None:
			self.select_page(ui.page)
		self.get_model().connect('row-inserted', self.on_row_inserted)

	def on_row_inserted(self, model, treepath, iter):
		path = model.get_indexpath(iter)
		if path == self.ui.page:
			self.select_page(self.ui.page)

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

	def do_drag_data_get(self, dragcontext, selectiondata, info, time):
		assert selectiondata.target == INTERNAL_PAGELIST_TARGET_NAME
		model, iter = self.get_selection().get_selected()
		path = model.get_indexpath(iter)
		logger.debug('Drag data requested, we have internal path "%s"', path.name)
		data = pack_urilist((path.name,))
		selectiondata.set(INTERNAL_PAGELIST_TARGET_NAME, 8, data)

	def do_drag_data_received(self, dragcontext, x, y, selectiondata, info, time):
		assert selectiondata.target == INTERNAL_PAGELIST_TARGET_NAME
		names = unpack_urilist(selectiondata.data)
		assert len(names) == 1
		source = Path(names[0])

		treepath, position = self.get_dest_row_at_pos(x, y)
		model = self.get_model()
		iter = model.get_iter(treepath)
		path = model.get_indexpath(iter)

		if position == gtk.TREE_VIEW_DROP_BEFORE:
			logger.debug('Dropped %s before %s', source, path)
			dest = path.parent + source.basename
		elif position == gtk.TREE_VIEW_DROP_AFTER:
			logger.debug('Dropped %s after %s', source, path)
			dest = path.parent + source.basename
		else:
			# gtk.TREE_VIEW_DROP_INTO_OR_BEFORE
			# or gtk.TREE_VIEW_DROP_INTO_OR_AFTER
			logger.debug('Dropped %s into %s', source, path)
			dest = path + source.basename

		if path == source or dest == source:
			# TODO - how to get the row image float back like when drop is not allowed ?
			if path == source:
				logger.debug('Dropped page onto itself')
			else:
				logger.debug('Paths have same namespace, no reordering')
			dragcontext.finish(False, False, time) # NOK
			return

		if self.ui.do_move_page(source, dest, update_links=True):
			dragcontext.finish(True, False, time) # OK
		else:
			dragcontext.finish(False, False, time) # NOK

	def select_page(self, path, vivify=False):
		'''Select a page in the treeview, connected to the open-page signal.

		If 'vivify' is True a placeholder for the path will be created
		if it doesn't yet exist. However this placeholder is cleaned
		up when another page is selected with this method unless the
		path was modified in the mean time.
		'''
		model, iter = self.get_selection().get_selected()
		if model is None:
			return # index not yet initialized ...

		if iter and model[iter][PATH_COL] == path:
			return  # this page was selected already

		index = self.ui.notebook.index
		if self._vivivied:
			index.cleanup(self._vivivied)
			self._vivivied = None

		indexpath = index.lookup_path(path)
		if indexpath is None:
			indexpath = index.touch(path)
			self._vivivied = indexpath

		treepath = model.get_treepath(indexpath)
		self.expand_to_path(treepath)
		self.get_selection().select_path(treepath)
		self.set_cursor(treepath)
		self.scroll_to_cell(treepath, use_align=True, row_align=0.9)

# Need to register classes defining gobject signals
gobject.type_register(PageTreeView)


class PageIndex(gtk.ScrolledWindow):

	def __init__(self, ui):
		gtk.ScrolledWindow.__init__(self)
		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.treeview = PageTreeView(ui)
		self.add(self.treeview)

		ui.connect('open-notebook', self.on_open_notebook)

	def on_open_notebook(self, ui, notebook):
		index = notebook.index
		index.connect('start-update',
			lambda o: ui.mainwindow.statusbar.push(2, _('Updating index...')) )
			# T: statusbar message
		index.connect('end-update',
			lambda o: ui.mainwindow.statusbar.pop(2) )

	def is_focus(self):
		return self.treeview.is_focus()

	def grab_focus(self):
		return self.treeview.grab_focus()

	def get_selected_path(self):
		'''Returns path currently selected or None'''
		model, iter = self.treeview.get_selection().get_selected()
		if model is None or iter is None:
			return None
		else:
			return model.get_indexpath(iter)
