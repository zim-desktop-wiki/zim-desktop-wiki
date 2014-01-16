# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the page index widget which is normally shown
in the side pane of the main window. L{PageIndex} is the main widget
which contains a L{PageTreeView} which is the actual list view widget.
The L{PageTreeStore} is our custom data model which connects to the
L{index<Index>} to get the page list data and maps it to the TreeView API.
'''

import gobject
import gtk
import pango
import logging

from zim.index import IndexPath
from zim.notebook import Path
from zim.gui.widgets import ui_environment, BrowserTreeView, \
	populate_popup_add_separator, encode_markup_text, \
	ErrorDialog
from zim.gui.clipboard import \
	Clipboard, \
	INTERNAL_PAGELIST_TARGET_NAME, INTERNAL_PAGELIST_TARGET, \
	pack_urilist, unpack_urilist
from zim.signals import ConnectorMixin


logger = logging.getLogger('zim.gui.pageindex')


NAME_COL = 0  #: Column with short page name (page.basename)
PATH_COL = 1  #: Column with the zim IndexPath itself
EMPTY_COL = 2 #: Column to flag if the page is empty or not
STYLE_COL = 3 #: Column to specify style (based on empty or not)
FGCOLOR_COL = 4 #: Column to specify color (based on empty or not)
WEIGHT_COL = 5 #: Column to specify the font weight (open page in bold)
N_CHILD_COL = 6 #: Column with the number of child pages
TIP_COL = 7 #: Column with the name to be used in the tooltip

# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVAL_C = gtk.gdk.unicode_to_keyval(ord('c'))
KEYVAL_L = gtk.gdk.unicode_to_keyval(ord('l'))


#~ import gc
#~ gc.set_debug(gc.DEBUG_LEAK)
#~ gc.set_debug(gc.DEBUG_STATS)


class PageTreeIter(object):
	'''Simple wrapper for L{IndexPath} objects used as tree iters
	in the L{PageTreeStore}
	'''

	__slots__ = ('indexpath', 'treepath', 'n_children')

	def __init__(self, treepath, indexpath):
		'''Constructor

		@param treepath: the tree path (a tuple of integers)
		@param indexpath: the L{IndexPath} object
		'''
		self.treepath = treepath #: the tree path
		self.indexpath = indexpath #: the L{IndexPath}
		self.n_children = None #: number of children, C{None} means unknown

	def __repr__(self):
		return '<PageTreeIter, %s, %s>' % (self.treepath, self.indexpath.name)


class PageTreeStore(ConnectorMixin, gtk.GenericTreeModel, gtk.TreeDragSource, gtk.TreeDragDest):
	'''Custom gtk TreeModel that is integrated closely with the L{Index}
	object of the notebook. This model is mostly an API layer translating
	between the C{gtk.TreeView} and the zim L{Index} interfaces. It
	fetches data on the fly when requested and only keeps a very
	limited cache in memory. This allows scaling to very large notebooks.

	This custom model is based on C{gtk.GenericTreeModel} which takes
	care of the C{C} code wrapper. See the documentation there to
	get the fine details of the API.

	Be aware that in this interface there are two classes both
	referred to as "paths". The first is the gtk TreePath (which is in
	fact just a tuple of integers, without a propr class) and the second
	is L{zim.notebook.Path} (or it's subclass L{IndexPath}). When a
	gtk TreePath is intended the argument is explicitly called
	"treepath", while arguments called "path" refer to a zim Path.

	For all the methods with a name starting with C{on_} the "iter"
	argument is a L{PageTreeIter}. The GenericTreeModel in turn
	wraps these in C{gtk.TreeIter} object. So e.g. the implementation
	of C{get_iter()} calls C{on_get_iter()} and wraps the
	L{PageTreeIter} into a C{gtk.TreeIter}.
	'''

	# We inherit from gtk.TreeDragSource and gtk.TreeDragDest even though
	# we do not actually implement them. Somehow this is needed to get
	# the TreeView to understand we support drag-and-drop even though
	# actual work is implemented in the treeview itself.

	# FIXME: Figure out how to bind cellrenderer style to the
	# EMPTY_COL so we do not need the separate style and fgcolor cols.
	# This will also allow making style for empty pages configurable.

	# This model does it own memory management for outstanding treeiter
	# objects. The reason is that we otherwise leak references and as
	# a result leak a huge number of unused IndexPath objects, consuming
	# a lot of memory. The downside is that we now need to track the
	# IndexPath objects ourselves to ensure they are not collected by
	# the garbage collector while still being used. And we need to
	# flush regularly to prevent collecting a huge number of these objects
	# again. Ideally we want to flush after every operation using treeiters.
	# We achieve this by scheduling the flushing on the main loop idle
	# event. This has the result that iters are valid within the same
	# operation but can not be carried between events. (Of course you
	# should not do that in the first place and use a TreeRowReference
	# instead.)

	# In addition we do caching of results within the same operation.
	# We cache partial page lists because of the observation that the
	# TreeView frequently calls iter_next when redrawing the widget.
	# We also use the cache to avoid duplicate lookups of the
	# same treepath. Caching relies on the assumption that any change
	# of the index will trigger a flush, invalidating our cached
	# iterators. So the cache is always in sync with the index state.

	COLUMN_TYPES = (
		gobject.TYPE_STRING, # NAME_COL
		gobject.TYPE_PYOBJECT, # PATH_COL
		bool, # EMPTY_COL
		pango.Style, # STYLE_COL
		gobject.TYPE_STRING, # FGCOLOR_COL
		int, # WEIGHT_COL
		gobject.TYPE_STRING, # N_CHILD_COL
		gobject.TYPE_STRING, # TIP_COL
	)


	NORMAL_COLOR = None
	EMPTY_COLOR = 'grey' # FIXME set based on style.text[gtk.STATE_INSENSITIVE]

	def __init__(self, index):
		'''Constructor

		@param index: the L{Index} object
		'''
		gtk.GenericTreeModel.__init__(self)
		self.index = index
		self.selected_page = None

		self.set_property('leak-references', False)
			# We do our own memory management, thank you very much
		self._cache = {}
		self._flush_scheduled = False

		self._connect()

	def _connect(self):
		# May be overridden by descendants (e.g. TagTreeStore)

		def on_changed(o, path, signal):
			#~ print '!!', signal, path
			self._flush()
			treepath = self.get_treepath(path)
			if treepath:
				#~ print '!!', signal, path, treepath
				try:
					treeiter = self.get_iter(treepath)
				except:
					logger.exception('BUG: Invalid treepath: %s %s %s', signal, path, treepath)
				else:
					self.emit(signal, treepath, treeiter)
			# If treepath is None the row does not exist anymore

		def on_deleted(o, path):
			#~ print '!! delete', path
			treepath = self.get_treepath(path)
			if treepath:
				self.emit('row-deleted', treepath)
			# If treepath is None the row does not exist anymore
			self._flush()

		self.connectto_all(self.index, (
			('page-inserted', on_changed, 'row-inserted'),
			('page-updated', on_changed, 'row-changed'),
			('page-haschildren-toggled', on_changed, 'row-has-child-toggled'),
			('page-to-be-deleted', on_deleted),
		))
		# The page-to-be-deleted signal is a hack so we have time to ensure we know the
		# treepath of this indexpath - once we get page-deleted it is to late to get this

	def disconnect_index(self):
		'''Stop the model from listening to the index. Used e.g. to
		unhook the model before reloading the index, thus avoiding
		many signals to be processed by both the model and the view.
		After this call the model can not be reconnected.
		'''
		self.disconnect_from(self.index)

	def select_page(self, path):
		'''Set the current open page to highlight it in the index.
		@param path: the L{Path} that is currently open, or C{None} to unset
		'''
		oldpath = self.selected_page
		self.selected_page = path

		for mypath in (oldpath, path):
			if mypath:
				treepath = self.get_treepath(mypath)
				if treepath:
					try:
						treeiter = self.get_iter(treepath)
					except ValueError:
						continue
					else:
						self.emit('row-changed', treepath, treeiter)

	def on_get_flags(self):
		return 0 # no flags

	def on_get_n_columns(self):
		return len(self.COLUMN_TYPES)

	def on_get_column_type(self, i):
		#~ print '>> on_get_column_type', index
		return self.COLUMN_TYPES[i]

	def on_get_value(self, iter, column):
		#~ print '>> on_get_value', iter, column
		path = iter.indexpath
		if column == NAME_COL:
			return path.basename
		elif column == TIP_COL:
			return encode_markup_text(path.basename)
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
		elif column == WEIGHT_COL:
			if path == self.selected_page:
				return pango.WEIGHT_BOLD
			else:
				return pango.WEIGHT_NORMAL
		elif column == N_CHILD_COL:
			if path.haschildren:
				return str(self.index.n_list_pages(path))
			else:
				return '' # not "0", want to keep look bit clean

	def on_get_iter(self, treepath):
		'''Returns a L{PageTreeIter} for a gtk TreePath or None'''
		#~ print '>> on_get_iter', treepath
		return self._get_iter(treepath)

	def on_get_path(self, iter):
		'''Returns a gtk TreePath for a L{PageTreeIter}'''
		#~ print '>> on_get_path', iter
		return iter.treepath

	def _get_iter(self, treepath):
		# Lookup and return the PageTreeIter for an gtk treepath
		#
		# Takes care of caching and makes sure we keep references to
		# paths long enough while they are used in an iter.
		# Also schedule a flush to be execute as soon as the loop is
		# idle again. The cache is a dict which takes treepath tuples
		# as keys and has PageTreeIter objects as values, it is filled
		# on demand.
		#
		# There is no TreePath gtk object, treepaths are just tuples
		# of ints:
		# Path (0,) is the first item in the root namespace
		# Path (2, 4) is the 5th child of the 3rd item
		#
		# All other API methods that need a PageTreeIter use this method
		# to do the actual lookup

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
		# of known cache for repeated requests. Cache can grow very fast
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
		'''Get a gtk TreePath for a given L{IndexPath}

		@param path: a L{Path} or L{IndexPath} object
		@returns: a gtk TreePath (which is a tuple of integers) or
		C{None} if the path does not appear in the index
		'''
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
		'''Get an L{IndexPath} for a C{gtk.TreeIter}

		@param treeiter: a C{gtk.TreeIter}
		@returns: an L{IndexPath} object
		'''
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
		'''Returns an IndexPath for the first child below path or None.
		If path is None returns the IndexPath for first top level item.
		'''
		#~ print '>> on_iter_children', iter
		if iter is None:
			treepath = (0,)
		else:
			treepath = iter.treepath + (0,)
		return self._get_iter(treepath)

	def on_iter_has_child(self, iter):
		'''Returns True if IndexPath for iter has children'''
		path = iter.indexpath
		if not path.hasdata:
			path = self.index.lookup_data(path)
		return bool(path.haschildren)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. When iter
		is None the number of pages in the root namespace is given.
		'''
		#~ print '>> on_iter_n_children', iter
		if iter is None:
			path = Path(':')
		else:
			path = iter.indexpath
		return self.index.n_list_pages(path)

	def on_iter_nth_child(self, iter, n):
		'''Returns the nth child for a given PageTreeIter or None. If
		iter is C{None} the nth item in the root namespace is returned.
		'''
		#~ print '>> on_iter_nth_child', iter, n
		if iter is None:
			treepath = (n,)
		else:
			treepath = iter.treepath + (n,)
		return self._get_iter(treepath)

	def on_iter_parent(self, iter):
		'''Returns a PageTreeIter for parent node of iter or None'''
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
	'''TreeView widget to show a list of pages.

	This view is intended to show a L{PageTreeStore} model, but it
	can also handle filtered models and subclasses that have the
	same columns. (The "tags" plugin uses this same view with
	alternative models.)

	@signal: C{page-activated (path)}: emitted when a page is clicked
	@signal: C{populate-popup (menu)}: hook to populate the context menu
	@signal: C{copy ()}: copy the current selection to the clipboard
	@signal: C{insert-link (path)}: called when the user pressed <Ctrl>L on page
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'insert-link': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'copy': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, ui, model=None):
		'''Constructor

		@param ui: the L{GtkInterface} object
		@param model: a L{PageTreeStore} object
		'''
		BrowserTreeView.__init__(self)
		self.set_name('zim-pageindex')
		self.ui = ui
		self._cleanup = None # temporary created path that needs to be removed later

		column = gtk.TreeViewColumn('_pages_')
		self.append_column(column)

		cr1 = gtk.CellRendererText()
		cr1.set_property('ellipsize', pango.ELLIPSIZE_END)
		column.pack_start(cr1, True)
		column.set_attributes(cr1, text=NAME_COL,
			style=STYLE_COL, foreground=FGCOLOR_COL, weight=WEIGHT_COL)

		cr2 = self.get_cell_renderer_number_of_items()
		column.pack_start(cr2, False)
		column.set_attributes(cr2, text=N_CHILD_COL, weight=WEIGHT_COL)

		if gtk.gtk_version >= (2, 12, 0):
			self.set_tooltip_column(TIP_COL)

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
		'''Stop the widget from listening to the index. Used e.g. to
		unhook the model before reloading the index, thus avoiding
		many signals to be processed by both the model and the view.
		Doing this requires constructing and setting a new model with
		L{set_model()} to get the view in sync with the index again.
		'''
		model = self.get_model()
		if isinstance(model, gtk.TreeModelFilter):
			model = model.get_model() # get childmodel
		model.disconnect_index()

	def set_model(self, model):
		'''Set a new model for the view.

		@param model: a new TreeModel object
		'''
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
		model = self.get_model()
		iter = model.get_iter(treepath)
		path = model.get_indexpath(iter)
		if path:
			self.emit('page-activated', path)

	def do_page_activated(self, path):
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

	def do_initialize_popup(self, menu):
		# TODO get path first and determine what menu options are valid
		path = self.get_selected_path() or Path(':')
		self.ui.populate_popup('page_popup', menu, path)

		populate_popup_add_separator(menu)
		item = gtk.ImageMenuItem('gtk-copy')
		item.connect('activate', lambda o: self.do_copy())
		menu.append(item)
		menu.show_all()

		self.populate_popup_expand_collapse(menu)

	def do_copy(self):
		#~ print '!! copy location'
		page = self.get_selected_path()
		if page:
			Clipboard.set_pagelink(self.ui.notebook, page)

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

		dest_row = self.get_dest_row_at_pos(x, y)
		if dest_row:
			treepath, position = dest_row
		else:
			dragcontext.finish(False, False, time) # NOK
			return
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

		@returns: a gtk TreePath (tuple of intergers) or C{None}
		'''
		#~ print '!! SELECT', path
		model = self.get_model()
		if model is None:
			return None # index not yet initialized ...

		treepath = model.get_treepath(path)
		if treepath:
			# path existed, now select it
			self.select_treepath(treepath)
		elif vivificate:
			# path does not exist, but we can create it
			path = model.index.touch(path)
			treepath = model.get_treepath(path)
			assert treepath, 'BUG: failed to touch placeholder'
			self.select_treepath(treepath)
		else:
			# path does not exist and we are not going to create it
			return None

		rowreference = gtk.TreeRowReference(model, treepath)
			# make reference before cleanup - path may change

		if self._cleanup and self._cleanup.valid():
			mytreepath = self._cleanup.get_path()
			if mytreepath != treepath:
				indexpath = model.get_indexpath( model.get_iter(mytreepath) )
				#~ print '!! CLEANUP', indexpath
				model.index.cleanup(indexpath)

		self._cleanup = rowreference

		model.select_page(path) # highlight in model

		return treepath

	def select_treepath(self, treepath):
		'''Select a gtk TreePath in the view

		@param treepath: a gtk TreePath (tuple of integers)
		'''
		self.expand_to_path(treepath)
		self.get_selection().select_path(treepath)
		self.set_cursor(treepath)
		#~ self.scroll_to_cell(treepath, use_align=True, row_align=0.9)
		# BUG: align 0.9 doesn't behave as one would expect..
		self.scroll_to_cell(treepath)

	def get_selected_path(self):
		'''Get the selected notebook path

		@returns: a L{IndexPath} or C{None} if there was no selection
		'''
		model, iter = self.get_selection().get_selected()
		if model is None or iter is None:
			return None
		else:
			return model.get_indexpath(iter)

# Need to register classes defining gobject signals
gobject.type_register(PageTreeView)


class PageIndex(gtk.ScrolledWindow):
	'''This is the main widget to display a page index.
	It contains a L{PageTreeView} within a scrolled window.

	@ivar treeview: the L{PageTreeView}
	'''

	def __init__(self, ui):
		'''Constructor

		@param ui: the main L{GtkInterface} object
		'''
		gtk.ScrolledWindow.__init__(self)
		self.ui = ui

		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.treeview = PageTreeView(ui)
		self.add(self.treeview)

		self.treeview.connect('insert-link',
			lambda v, p: self.ui.mainwindow.pageview.insert_links([p]))

		if self.ui.notebook:
			self.on_open_notebook(self.ui, self.ui.notebook)
		else:
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
		'''Get the selected notebook path

		@returns: a L{IndexPath} or C{None} if there was no selection
		'''
		return self.treeview.get_selected_path()

	def disconnect_model(self):
		'''Stop the widget from listening to the index. Used e.g. to
		unhook the model before reloading the index, thus avoiding
		many signals to be processed by both the model and the view.
		Typically should be followed by L{reload_model()} to get the
		view in sync with the index again.
		'''
		self.treeview.disconnect_index()

	def reload_model(self):
		'''Re-initialize the treeview model. This is called when
		reloading the index to get rid of out-of-sync model errors
		without need to close the app first.
		'''
		model = PageTreeStore(self.ui.notebook.index)
		self.treeview.set_model(model)
