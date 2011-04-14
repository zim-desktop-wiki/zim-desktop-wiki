# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
from zim.gui.widgets import ui_environment, BrowserTreeView, \
	ErrorDialog, gtk_get_style
from zim.gui.clipboard import \
	Clipboard, \
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


#~ import gc
#~ gc.set_debug(gc.DEBUG_LEAK)
#~ gc.set_debug(gc.DEBUG_STATS)


class PageTreeIter(object):
	'''Simple wrapper for IndexPath objects used as tree iters'''

	__slots__ = ('indexpath', 'treepath', 'n_children')

	def __init__(self, treepath, indexpath):
		self.treepath = treepath
		self.indexpath = indexpath
		self.n_children = None # None means unknown

	def __repr__(self):
		return '<PageTreeIter, %s, %s>' % (self.treepath, self.indexpath.name)


class PageTreeStore(gtk.GenericTreeModel, gtk.TreeDragSource, gtk.TreeDragDest):
	'''Custom TreeModel that is integrated closely with the Index object.
	In fact it is jsut an API layer translating between the gtk.TreeView and
	the zim Index interfaces. It fetches data on the fly when requested and
	does not keep it's own cache. This allows scaling to very large notebooks.

	Note: Be aware that in this interface there are two classes both referred
	to as "paths". The first is gtk.TreePath and the second is
	zim.notebook.Path . When a TreePath is intended the argument is called
	explicitly "treepath", while arguments called "path" refer to a zim Path.
	'''

	# We inherit from gtk.TreeDragSource and gtk.TreeDragDest even though
	# we do not actually implement them. Somehow this is needed to get
	# the TreeView to understand we support drag-and-drop even though
	# actual work is implemented in the treeview itself.

	# FIXME: Figure out how to bind cellrendere style to the
	# EMPTY_COL so we do not need the separate style and fgcolor cols.
	# This will also allow making style for empty pages configurable.

	# This model does it own memory management for outstanding treeiter
	# objects. The reason is that we otherwise leak references and as
	# a result leak a huge number of unused IndexPath objects, consuming
	# a lot of memory. The downside is that we now need to track the
	# IndexPath objects ourselves to ensure they are not collected by
	# the garbage collectore while still being used. And we need to
	# flush regularly to prevent collecting a huge number of these objects
	# again. Ideally we want to flush after every operation using treeiters.
	# We achieve this by scheduling the flushing on the main loop idle
	# event. This has the result that iters are valid within the same
	# operation but can not be caried between events. (Of course you
	# should not do that in the first place and use a TreeRowReference
	# instead.)

	# In addition we do caching of results within the same operation.
	# We cache partial page lists because of the observation that the
	# TreeView frequently calls iter_next when redrawing the widget.
	# We also use the cache to avoid duplicate lookups of the
	# same treepath. Caching relies on the assumption that any change
	# of the index will trigger a flush, invalidating our chached
	# iterators. So the cache is always in sync with the index state.

	COLUMN_TYPES = (
		gobject.TYPE_STRING, # NAME_COL
		gobject.TYPE_PYOBJECT, # PATH_COL
		bool, # EMPTY_COL
		pango.Style, # STYLE_COL
		gtk.gdk.Color, # FGCOLOR_COL
	)

	style = gtk_get_style()
	NORMAL_COLOR = style.text[gtk.STATE_NORMAL]
	EMPTY_COLOR = style.text[gtk.STATE_INSENSITIVE]

	def __init__(self, index):
		gtk.GenericTreeModel.__init__(self)
		self.index = index

		self.set_property('leak-references', False)
			# We do our own memory management, thank you very much
		self._cache = {}
		self._flush_scheduled = False

		self._connect()

	def _connect(self):
		'''May be overridden by descendants (e.g. TagTreeStore).'''

		def on_changed(o, path, signal):
			#~ print '!!', signal, path
			self._flush()
			treepath = self.get_treepath(path)
			if treepath:
				#~ print '!!', signal, path, treepath
				treeiter = self.get_iter(treepath)
				self.emit(signal, treepath, treeiter)
			# If treepath is None the row does not exist anymore

		def on_deleted(o, path):
			#~ print '!! delete', path
			treepath = self.get_treepath(path)
			if treepath:
				self.emit('row-deleted', treepath)
			# If treepath is None the row does not exist anymore
			self._flush()

		self._signals = (
			self.index.connect('page-inserted', on_changed, 'row-inserted'),
			self.index.connect('page-updated', on_changed, 'row-changed'),
			self.index.connect('page-haschildren-toggled', on_changed, 'row-has-child-toggled'),
			self.index.connect('page-to-be-deleted', on_deleted),
		)
		# The page-to-be-deleted signal is a hack so we have time to ensure we know the
		# treepath of this indexpath - once we get page-deleted it is to late to get this

	def disconnect_index(self):
		'''Stop the model from listening to the inxed. Used to
		unhook the model before reloading the index.
		'''
		for id in self._signals:
			self.index.disconnect(id)
		self._signals = ()

	def on_get_flags(self):
		return 0 # no flags

	def on_get_n_columns(self):
		return len(self.COLUMN_TYPES)

	def on_get_column_type(self, i):
		#~ print '>> on_get_column_type', index
		return self.COLUMN_TYPES[i]

	def on_get_value(self, iter, column):
		'''Returns the data for a specific column'''
		#~ print '>> on_get_value', iter, column
		path = iter.indexpath
		if column == NAME_COL:
			return path.basename
		elif column == PATH_COL:
			return path
		elif column == EMPTY_COL:
			return not path.hascontent and not path.haschildren
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
		#~ print '>> on_get_iter', treepath
		return self._get_iter(treepath)

	def on_get_path(self, iter):
		#~ print '>> on_get_path', iter
		return iter.treepath

	def _get_iter(self, treepath):
		# Take care of caching and make sure we keep ref to paths long
		# enough while they are used in an iter. Also schedule a flush
		# to be execute as soon as the loop is idle again.
		# The cache is a dict which takes treepath tuples as keys and
		# has pagetreeiter objects as values, it is filled on demand.
		# No TreePath gtk object, treepaths are just tuples of ints
		# Path (0,) is the first item in the root namespace
		# Path (2, 4) is the 5th child of the 3rd item
		#~ print '>>> Lookup path', treepath
		if not treepath in self._cache:
			parent = None
			for i in range(1, len(treepath)+1):
				mytreepath = treepath[:i]
				if not mytreepath in self._cache:
					parenttreepath = treepath[:i-1]
					offset = mytreepath[-1]
					#~ print '>>>> Load pagelist for', parent, 'offset', offset
					pages = self.index.list_pages(parent, offset, limit=20)
					for j, path in enumerate(pages):
						childtreepath = parenttreepath + (offset + j,)
						iter = PageTreeIter(childtreepath, path)
						self._cache.setdefault(childtreepath, iter)
				try:
					parent = self._cache[mytreepath].indexpath
				except KeyError:
					return None

		#~ print '>>> Return', self._cache.get(treepath, None)
		self._schedule_flush()
		return self._cache.get(treepath, None)

	def _schedule_flush(self):
		# Schedule a flush with some timeout to try to take advantage
		# of known cache for repeated requests. Cache can grow very big
		# on scroll, so don't make the time constant to large.
		if not self._flush_scheduled:
			def idle_add():
				gobject.idle_add(self._flush)
				return False # delete timeout

			gobject.timeout_add(500, idle_add)
			self._flush_scheduled = True

	def _flush(self):
		# Drop references and free memory
		# Cache is populated by either _get_iter() or get_treepath()
		#~ print '!! Freeing %i refs' % len(self._cache)
		#~ print '=' * 60
		self.invalidate_iters()
		self._cache = {} # del _cache - keep no ref to this dict
		self._flush_scheduled = False
		return False # In case we are called from idle signal

	def get_treepath(self, path):
		'''Returns a TreePath for a given IndexPath or None if the
		path does not appear in the index.
		'''
		# There is no TreePath class in pygtk, just return tuple of integers
		assert isinstance(path, Path)
		if path.isroot:
			raise ValueError

		if not isinstance(path, IndexPath):
			path = self.index.lookup_path(path)
			if path is None:
				return None

		paths = list(path.parents())
		paths.pop() # get rid of root namespace as parent
		paths.reverse()
		paths.append(path)
		treepath = ()
		for path in paths:
			n = self.index.get_page_index(path)
			treepath += (n,)

		return treepath

	def get_indexpath(self, treeiter):
		'''Returns an IndexPath for a TreeIter'''
		# Note that iter is TreeIter here, not PageTreeIter
		iter = self.get_user_data(treeiter)
		return iter.indexpath

	def on_iter_next(self, iter):
		'''Returns the IndexPath for the next row on the same level or None'''
		# Only within one namespace, so not the same as index.get_next()
		#~ print '>> on_iter_next', iter
		treepath = list(iter.treepath)
		treepath[-1] += 1
		treepath = tuple(treepath)
		return self._get_iter(treepath)

	def on_iter_children(self, iter):
		'''Returns an indexPath for the first child below path or None.
		If path is None returns the first top level IndexPath.
		'''
		#~ print '>> on_iter_children', iter
		if iter is None:
			treepath = (0,)
		else:
			treepath = iter.treepath + (0,)
		return self._get_iter(treepath)

	def on_iter_has_child(self, iter):
		'''Returns True if indexPath path has children'''
		path = iter.indexpath
		if not path.hasdata:
			path = self.index.lookup_data(path)
		return bool(path.haschildren)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of pages in the root namespace is given.
		'''
		#~ print '>> on_iter_n_children', iter
		if iter is None:
			path = Path(':')
		else:
			path = iter.indexpath
		return self.index.n_list_pages(path)

	def on_iter_nth_child(self, iter, n):
		'''Returns the nth child for a given IndexPath or None.
		As a special case iter can be None to get pages in the root namespace.
		'''
		#~ print '>> on_iter_nth_child', iter, n
		if iter is None:
			treepath = (n,)
		else:
			treepath = iter.treepath + (n,)
		return self._get_iter(treepath)

	def on_iter_parent(self, iter):
		'''Returns a IndexPath for parent node the iter or None'''
		#~ print '>> on_iter_parent', iter
		treepath = iter.treepath[:-1]
		if len(treepath) > 0:
			return self._get_iter(treepath)
		else:
			return None


	# Compatibility for older version of GenericTreeModel
	if not hasattr(gtk.GenericTreeModel, 'create_tree_iter'):
		logger.warn('Using work around for older version of GenericTreeModel - may hurt performance')
		def create_tree_iter(self, iter):
			'''Turn an PageTreeIter into a TreeIter'''
			# Use GenericTreeModel API to wrap the iter
			return self.get_iter(iter.treepath)

	if not hasattr(gtk.GenericTreeModel, 'get_user_data'):
		def get_user_data(self, treeiter):
			'''Turn a TreeIter into an PageTreeIter'''
			# Use GenericTreeModel API to unwrap the iter
			treepath = self.get_path(treeiter)
			return self._cache[treepath]

# Need to register classes defining gobject signals or overloading methods
gobject.type_register(PageTreeStore)


class PageTreeView(BrowserTreeView):
	'''Wrapper for a TreeView showing a list of pages.

	Signals:
	  * page-activated (path): emitted when a page is clicked
	  * populate-popup (menu): hook to populate the context menu
	  * copy (): copy the current selection to the clipboard
	  * insert-link (path): called when the user pressed <Ctrl>L on page
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'populate-popup': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'insert-link': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'copy': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, ui, model=None):
		BrowserTreeView.__init__(self)
		self.set_name('zim-pageindex')
		self.ui = ui
		self._cleanup = None # temporary created path that needs to be removed later

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

		if ui_environment['platform'] == 'maemo':
			# Maemo gtk UI bugfix: expanders are hidden by default
			self.set_property('level-indentation', 0)
			self.set_property('show-expanders', 1)

		if model:
			self.set_model(model)

	def disconnect_index(self):
		'''Stop the view & model from listening to the index. Used to
		unhook the model before reloading the index. Call L{set_model}
		again to re-connect.
		'''
		model = self.get_model()
		if isinstance(model, gtk.TreeModelFilter):
			model = model.get_model() # get childmodel
		model.disconnect_index()

	def set_model(self, model):
		self._cleanup = None # else it might be pointing to old model
		BrowserTreeView.set_model(self, model)
		if self.ui.page:
			self.select_page(self.ui.page, vivificate=True)

		model.connect('row-inserted', self.on_row_inserted)

	def on_row_inserted(self, model, treepath, iter):
		path = model.get_indexpath(iter)
		if path and path == self.ui.page:
			self.select_treepath(treepath)

	def do_row_activated(self, treepath, column):
		'''Handler for the row-activated signal, emits page-activated'''
		model = self.get_model()
		iter = model.get_iter(treepath)
		path = model.get_indexpath(iter)
		if path:
			self.emit('page-activated', path)

	def do_page_activated(self, path):
		'''Handler for the page-activated signal, calls ui.open_page()'''
		self.ui.open_page(path)

	def do_key_press_event(self, event):
		# Keybindings for the treeview:
		#  Ctrl-C copy link to selected page
		#  Ctrl-L insert link to selected page in pageview
		# Keybindings for collapsing and expanding items are
		# implemented in the BrowserTreeView parent class
		# And MainWindow hooks Esc to close side pane
		handled = False
		#~ print 'KEY %s (%i)' % (gtk.gdk.keyval_name(event.keyval), event.keyval)

		if event.state & gtk.gdk.CONTROL_MASK:
			if event.keyval == KEYVAL_C:
				self.emit('copy')
				handled = True
			elif event.keyval == KEYVAL_L:
				path = self.get_selected_path()
				#~ print '!! insert-link', path
				self.emit('insert-link', path)
				handled = True

		return handled \
			or BrowserTreeView.do_key_press_event(self, event)

	def do_button_release_event(self, event):
		'''Handler for button-release-event, triggers popup menu'''
		if event.button == 3:
			self.emit('popup-menu')# FIXME do we need to pass x/y and button ?
			return True
		else:
			return BrowserTreeView.do_button_release_event(self, event)

	def do_popup_menu(self): # FIXME do we need to pass x/y and button ?
		menu = gtk.Menu()
		self.ui.populate_popup('page_popup', menu)
		self.emit('populate-popup', menu)
		menu.show_all()
		menu.popup(None, None, None, 3, 0)
		return True

	def do_copy(self):
		'''Copy current selection to clipboard'''
		#~ print '!! copy location'
		page = self.get_selected_path()
		if page:
			Clipboard().set_pagelink(self.ui.notebook, page)

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

	def select_page(self, path, vivificate=False):
		'''Select a page in the treeview

		@param path: a notebook L{Path} object for the page
		@keyword vivificate: when C{True} the path is created
		temporarily when it did not yet exist

		@returns: a treepath tuple or C{None}
		'''
		#~ print '!! SELECT', path
		model, iter = self.get_selection().get_selected()
		if model is None:
			return None # index not yet initialized ...

		if iter and model[iter][PATH_COL] == path:
			return model.get_path(iter) # this page was selected already

		treepath = model.get_treepath(path)
		if treepath:
			self.select_treepath(treepath)
		elif vivificate:
			path = model.index.touch(path)
			treepath = self.select_page(path)
			assert treepath, 'BUG: failed to touch placeholder'
		else:
			return None

		rowreference = gtk.TreeRowReference(model, treepath)
			# make reference before cleanup - path may change

		if self._cleanup and self._cleanup.valid():
			mytreepath = self._cleanup.get_path()
			indexpath = model.get_indexpath( model.get_iter(mytreepath) )
			#~ print '!! CLEANUP', indexpath
			model.index.cleanup(indexpath)

		self._cleanup = rowreference

		return treepath

	def select_treepath(self, treepath):
		'''Select a give treepath and scroll it into view

		@param treepath: a treepath tuple
		'''
		self.expand_to_path(treepath)
		self.get_selection().select_path(treepath)
		self.set_cursor(treepath)
		self.scroll_to_cell(treepath, use_align=True, row_align=0.9)

	def get_selected_path(self):
		'''Returns path currently selected or None'''
		model, iter = self.get_selection().get_selected()
		if model is None or iter is None:
			return None
		else:
			return model.get_indexpath(iter)

# Need to register classes defining gobject signals
gobject.type_register(PageTreeView)


class PageIndex(gtk.ScrolledWindow):

	def __init__(self, ui):
		gtk.ScrolledWindow.__init__(self)
		self.ui = ui

		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.treeview = PageTreeView(ui)
		self.add(self.treeview)

		self.treeview.connect('insert-link',
			lambda v, p: self.ui.mainwindow.pageview.insert_links([p]))

		ui.connect('open-notebook', self.on_open_notebook)
		ui.connect('open-page', self.on_open_page)
		ui.connect('start-index-update', lambda o: self.disconnect_model())
		ui.connect('end-index-update', lambda o: self.reload_model())

	def on_open_notebook(self, ui, notebook):
		index = notebook.index

		model = PageTreeStore(index)
		self.treeview.set_model(model)

		index.connect('start-update',
			lambda o: ui.mainwindow.statusbar.push(2, _('Updating index...')) )
			# T: statusbar message
		index.connect('end-update',
			lambda o: ui.mainwindow.statusbar.pop(2) )

	def on_open_page(self, ui, page, path):
		self.treeview.select_page(path, vivificate=True)

	def is_focus(self):
		return self.treeview.is_focus()

	def grab_focus(self):
		return self.treeview.grab_focus()

	def get_selected_path(self):
		'''Returns path currently selected or None'''
		return self.treeview.get_selected_path()

	def disconnect_model(self):
		'''Stop the model from listening to the inxed. Used to
		unhook the model before reloading the index. Typically
		should be followed by reload_model().
		'''
		self.treeview.disconnect_index()

	def reload_model(self):
		'''Re-initialize the treeview model. This is called when
		reloading the index to get rid of out-of-sync model errors
		without need to close the app first.
		'''
		model = PageTreeStore(self.ui.notebook.index)
		self.treeview.set_model(model)
