
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango

from .generictreemodel import GenericTreeModel

import logging

from functools import partial

from zim.notebook import Path
from zim.notebook.index.pages import PagesTreeModelMixin, PageIndexRecord, IndexNotFoundError, IS_PAGE

from zim.plugins import PluginClass
from zim.actions import PRIMARY_MODIFIER_MASK

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import BrowserTreeView, ScrolledWindow, \
	encode_markup_text, ErrorDialog, \
	WindowSidePaneWidget, LEFT_PANE, PANE_POSITIONS
from zim.gui.clipboard import Clipboard, pack_urilist, unpack_urilist, \
	INTERNAL_PAGELIST_TARGET_NAME, INTERNAL_PAGELIST_TARGET
from zim.gui.uiactions import UIActions, PAGE_EDIT_ACTIONS, PAGE_ROOT_ACTIONS


logger = logging.getLogger('zim.gui.pageindex')


NAME_COL = 0  #: Column with short page name (page.basename)
PATH_COL = 1  #: Column with the zim PageIndexRecord itself
EXISTS_COL = 2 #: Column to flag if the page is a placeholder or not
STYLE_COL = 3 #: Column to specify style (based on empty or not)
WEIGHT_COL = 4 #: Column to specify the font weight (open page in bold)
N_CHILD_COL = 5 #: Column with the number of child pages
TIP_COL = 6 #: Column with the name to be used in the tooltip

# Check the (undocumented) list of constants in Gtk.keysyms to see all names
KEYVAL_C = Gdk.unicode_to_keyval(ord('c'))
KEYVAL_L = Gdk.unicode_to_keyval(ord('l'))


class PageIndexPlugin(PluginClass):

	plugin_info = {
		'name': _('Page Index'), # T: plugin name
		'description': _('''\
This plugin adds the page index pane to the main window.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:PageIndex',
	}

	plugin_preferences = (
		# key, type, label, default
		('pane', 'choice', _('Position in the window'), LEFT_PANE, PANE_POSITIONS),
			# T: preferences option
	)


class PageIndexPageViewExtension(PageViewExtension):

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)
		index = pageview.notebook.index
		model = PageTreeStore(index)
		self.treeview = PageTreeView(pageview.notebook, self.navigation)
		self.treeview.set_model(model)
		self.widget = PageIndexWidget(self.treeview)

		# Connect to ui signals
		#window.connect('start-index-update', lambda o: self.disconnect_model())
		#window.connect('end-index-update', lambda o: self.reload_model())

		self.on_page_changed(pageview, pageview.page)
		self.connectto(pageview, 'page-changed')

		self.add_sidepane_widget(self.widget, 'pane')

		# self.pageindex.treeview.connect('insert-link',
		# 	lambda v, p: self.pageview.insert_links([p]))

	def on_page_changed(self, pageview, page):
		treepath = self.treeview.set_current_page(page, vivificate=True)
		if treepath:
			self.treeview.select_treepath(treepath)

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
		model = PageTreeStore(self.pageview.notebook.index)
		self.treeview.set_model(model)


class PageIndexWidget(Gtk.VBox, WindowSidePaneWidget):

	title = _('Index')	# T: tab label for side pane

	def __init__(self, treeview):
		GObject.GObject.__init__(self)
		self.pack_start(ScrolledWindow(treeview), True, True, 0)


class PageTreeStoreBase(GenericTreeModel, Gtk.TreeDragSource, Gtk.TreeDragDest):
	'''Custom gtk TreeModel that is integrated closely with the L{Index}
	object of the notebook. This model is mostly an API layer translating
	between the C{Gtk.TreeView} and the zim L{Index} interfaces. It
	fetches data on the fly when requested and only keeps a very
	limited cache in memory. This allows scaling to very large notebooks.

	This custom model is based on C{GenericTreeModel} which takes
	care of the C library wrapper. See the documentation there to
	get the fine details of the API.

	Be aware that in this interface there are two classes both
	referred to as "paths". The first is the gtk TreePath (which is in
	fact just a tuple of integers, without a propr class) and the second
	is L{zim.notebook.Path}. When a gtk TreePath is intended the argument is
	explicitly called "treepath", while arguments called "path" refer to a
	zim Path.

	For all the methods with a name starting with C{on_} the "iter"
	argument is a L{MyTreeIter}. The GenericTreeModel in turn
	wraps these in C{Gtk.TreeIter} object. So e.g. the implementation
	of C{get_iter()} calls C{on_get_iter()} and wraps the
	L{MyTreeIter} object into a C{Gtk.TreeIter}.
	'''

	# We inherit from Gtk.TreeDragSource and Gtk.TreeDragDest even though
	# we do not actually implement them. Somehow this is needed to get
	# the TreeView to understand we support drag-and-drop even though
	# actual work is implemented in the treeview itself.

	# This model does it own memory management for outstanding treeiter
	# objects. The reason is that we otherwise leak references and consume
	# a lot of memory. The downside is that we now need to track the
	# MyTreeIter objects ourselves to ensure they are not collected by
	# the garbage collector while still being used. This is handled by the
	# cache dict in PagesTreeModelMixin. We need to flush this cache regularly
	# to prevent collecting the whole index in memory.
	# Ideally we want to flush after every operation using treeiters.
	# We achieve this by scheduling the flushing on the main loop idle
	# event. This has the result that iters are valid within the same
	# operation but can not be carried between events. (Of course you
	# should not do that in the first place and use a TreeRowReference
	# instead.)

	COLUMN_TYPES = (
		GObject.TYPE_STRING, # NAME_COL
		GObject.TYPE_PYOBJECT, # PATH_COL
		GObject.TYPE_BOOLEAN, # EXISTS_COL
		Pango.Style, # STYLE_COL
		GObject.TYPE_INT, # WEIGHT_COL
		GObject.TYPE_STRING, # N_CHILD_COL
		GObject.TYPE_STRING, # TIP_COL
	)

	def __init__(self):
		GenericTreeModel.__init__(self)
		self.current_page = None
		self.set_property('leak-references', False)
			# We do our own memory management, thank you very much
		self._flush_scheduled = False

	def flush_cache(self):
		# Drop references and free memory
		#~ print('!! Freeing %i refs' % len(self._cache))
		#~ print('=' * 60)
		self.invalidate_iters()
		self.cache.clear()
		self._flush_scheduled = False
		return False # In case we are called from idle signal

	def _emit_page_changes(self, path):
		try:
			treepaths = self.find_all(path)
		except IndexNotFoundError:
			return None
		else:
			for treepath in treepaths:
				treeiter = self.get_iter(treepath)
				self.emit('row-changed', treepath, treeiter)
			return treepaths[0]

	def set_current_page(self, path):
		'''Set the current open page to highlight it in the index.
		@param path: the L{Path} that is currently open, or C{None} to unset
		'''
		oldpath = self.current_page
		self.current_page = path
		if oldpath:
			self._emit_page_changes(oldpath)

		if path:
			return self._emit_page_changes(path)
		else:
			return None

	def get_indexpath(self, treeiter):
		'''Get an L{PageIndexRecord} for a C{Gtk.TreeIter}

		@param treeiter: a C{Gtk.TreeIter}
		@returns: an L{PageIndexRecord} object
		'''
		myiter = self.get_user_data(treeiter)
		return PageIndexRecord(myiter.row)

	def on_get_flags(self):
		return 0 # no flags

	def on_get_n_columns(self):
		return len(self.COLUMN_TYPES)

	def on_get_column_type(self, i):
		#~ print('>> on_get_column_type', index)
		return self.COLUMN_TYPES[i]

	def on_get_value(self, iter, column):
		if column == NAME_COL:
			return iter.row['name'].split(':')[-1]
		elif column == TIP_COL:
			basename = iter.row['name'].split(':')[-1]
			return encode_markup_text(basename)
		elif column == PATH_COL:
			return PageIndexRecord(iter.row)
		elif column == EXISTS_COL:
			return not iter.row['is_link_placeholder']
		elif column == STYLE_COL:
			if iter.row['is_link_placeholder']:
				return Pango.Style.ITALIC
			else:
				return Pango.Style.NORMAL
		elif column == WEIGHT_COL:
			if self.current_page and iter.row['name'] == self.current_page.name:
				return Pango.Weight.BOLD
			else:
				return Pango.Weight.NORMAL
		elif column == N_CHILD_COL:
			return str(iter.n_children) if iter.n_children > 0 else ''
				# don't display "0" to keep look bit clean

	def on_get_iter(self, treepath):
		'''Returns an MyTreeIter for a gtk TreePath or None'''
		# Schedule a flush with some timeout to try to take advantage
		# of known cache for repeated requests. Cache can grow very fast
		# on scroll, so don't make the time constant to large.
		if not self._flush_scheduled:
			def idle_add():
				GObject.idle_add(self.flush_cache)
				return False # delete timeout

			GObject.timeout_add(500, idle_add)
			self._flush_scheduled = True

		return self.get_mytreeiter(treepath)

	def on_get_path(self, iter):
		'''Returns a gtk TreePath for an indexpath'''
		#~ print('>> on_get_path', iter)
		return iter.treepath

	def on_iter_next(self, iter):
		'''Returns the PageIndexRecord for the next row on the same level or None'''
		# Only within one namespace, so not the same as index.get_next()
		#~ print('>> on_iter_next', iter)
		treepath = list(iter.treepath)
		treepath[-1] += 1
		treepath = tuple(treepath)
		return self.on_get_iter(treepath)

	def on_iter_children(self, iter):
		'''Returns an PageIndexRecord for the first child below path or None.
		If path is None returns the PageIndexRecord for first top level item.
		'''
		#~ print('>> on_iter_children', iter)
		if iter is None:
			treepath = (0,)
		else:
			treepath = tuple(iter.treepath) + (0,)
		return self.on_get_iter(treepath)

	def on_iter_has_child(self, iter):
		'''Returns True if PageIndexRecord for iter has children'''
		return iter.n_children > 0

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. When iter
		is None the number of pages in the root namespace is given.
		'''
		#~ print('>> on_iter_n_children', iter)
		if iter is None:
			return self.n_children_top()
		else:
			return iter.n_children

	def on_iter_nth_child(self, iter, n):
		'''Returns the nth child or None. If iter is C{None} the
		nth item in the root namespace is returned.
		'''
		#~ print('>> on_iter_nth_child', iter, n)
		if iter is None:
			treepath = (n,)
		else:
			treepath = tuple(iter.treepath) + (n,)
		return self.on_get_iter(treepath)

	def on_iter_parent(self, iter):
		'''Returns an indexpath for parent node or None'''
		#~ print('>> on_iter_parent', iter)
		treepath = iter.treepath[:-1]
		if len(treepath) > 0:
			return self.on_get_iter(treepath)
		else:
			return None


class PageTreeStore(PagesTreeModelMixin, PageTreeStoreBase):

	def __init__(self, index, root=None, reverse=False):
		PagesTreeModelMixin.__init__(self, index, root, reverse)
		PageTreeStoreBase.__init__(self)


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
		'page-activated': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'insert-link': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'copy': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	def __init__(self, notebook, navigation, model=None):
		BrowserTreeView.__init__(self)
		self.set_name('zim-pageindex')
		self.notebook = notebook
		self.navigation = navigation

		column = Gtk.TreeViewColumn('_pages_')
		column.set_expand(True)
		self.append_column(column)

		cr1 = Gtk.CellRendererText()
		cr1.set_property('ellipsize', Pango.EllipsizeMode.END)
		column.pack_start(cr1, True)
		column.set_attributes(cr1, text=NAME_COL,
			style=STYLE_COL, sensitive=EXISTS_COL, weight=WEIGHT_COL)

		column = Gtk.TreeViewColumn('_n_items_')
		self.append_column(column)

		cr2 = self.get_cell_renderer_number_of_items()
		column.pack_start(cr2, False)
		column.set_attributes(cr2, text=N_CHILD_COL, weight=WEIGHT_COL)

		self.set_tooltip_column(TIP_COL)

		self.set_headers_visible(False)

		self.set_enable_search(True)
		self.set_search_column(0)

		self.enable_model_drag_source(
			Gdk.ModifierType.BUTTON1_MASK, (INTERNAL_PAGELIST_TARGET,),
			Gdk.DragAction.LINK | Gdk.DragAction.MOVE)
		self.enable_model_drag_dest(
			(INTERNAL_PAGELIST_TARGET,),
			Gdk.DragAction.MOVE)

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
		if isinstance(model, Gtk.TreeModelFilter):
			model = model.get_model() # get childmodel
		model.teardown()

	def do_row_activated(self, treepath, column):
		model = self.get_model()
		treeiter = model.get_iter(treepath)
		mytreeiter = model.get_user_data(treeiter)
		if mytreeiter.hint == IS_PAGE:
			path = model.get_indexpath(treeiter)
			if path:
				self.emit('page-activated', path)

	def do_page_activated(self, path):
		self.navigation.open_page(path)

	def do_key_press_event(self, event):
		# Keybindings for the treeview:
		#  Ctrl-C copy link to selected page
		#  Ctrl-L insert link to selected page in pageview
		# Keybindings for collapsing and expanding items are
		# implemented in the BrowserTreeView parent class
		# And MainWindow hooks Esc to close side pane
		handled = False
		#~ print('KEY %s (%i)' % (Gdk.keyval_name(event.keyval), event.keyval))

		if event.get_state() & PRIMARY_MODIFIER_MASK:
			if event.keyval == KEYVAL_C:
				self.emit('copy')
				handled = True
			elif event.keyval == KEYVAL_L:
				path = self.get_selected_path()
				#~ print('!! insert-link', path)
				self.emit('insert-link', path)
				handled = True

		return handled \
			or BrowserTreeView.do_key_press_event(self, event)

	def do_initialize_popup(self, menu):
		model, treeiter = self.get_selection().get_selected()
		if treeiter is None:
			popup_name, path = PAGE_ROOT_ACTIONS, None
		else:
			mytreeiter = model.get_user_data(treeiter)
			if mytreeiter.hint == IS_PAGE:
				popup_name = PAGE_EDIT_ACTIONS
				path = self.get_selected_path()
			else:
				popup_name, path = None, None

		if popup_name:
			uiactions = UIActions(
				self,
				self.notebook,
				path,
				self.navigation,
			)
			uiactions.populate_menu_with_actions(popup_name, menu)

		sep = Gtk.SeparatorMenuItem()
		menu.append(sep)
		self.populate_popup_expand_collapse(menu)
		menu.show_all()

	def do_drag_data_get(self, dragcontext, selectiondata, info, time):
		assert selectiondata.get_target().name() == INTERNAL_PAGELIST_TARGET_NAME
		model, iter = self.get_selection().get_selected()
		path = model.get_indexpath(iter)
		logger.debug('Drag data requested, we have internal path "%s"', path.name)
		data = pack_urilist((path.name,))
		selectiondata.set(selectiondata.get_target(), 8, data)

	def do_drag_data_received(self, dragcontext, x, y, selectiondata, info, time):
		assert selectiondata.get_target().name() == INTERNAL_PAGELIST_TARGET_NAME
		names = unpack_urilist(selectiondata.get_data())
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

		if position == Gtk.TreeViewDropPosition.BEFORE:
			logger.debug('Dropped %s before %s', source, path)
			dest = path.parent + source.basename
		elif position == Gtk.TreeViewDropPosition.AFTER:
			logger.debug('Dropped %s after %s', source, path)
			dest = path.parent + source.basename
		else:
			# Gtk.TreeViewDropPosition.INTO_OR_BEFORE
			# or Gtk.TreeViewDropPosition.INTO_OR_AFTER
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

		try:
			self.notebook.move_page(source, dest, update_links=True)
		except:
			logger.exception('Failed to move page %s -> %s', source, dest)
			dragcontext.finish(False, False, time) # NOK
		else:
			dragcontext.finish(True, False, time) # OK

	def set_current_page(self, path, vivificate=False):
		'''Select a page in the treeview

		@param path: a notebook L{Path} object for the page
		@param vivificate: when C{True} the path is created
		temporarily when it did not yet exist

		@returns: a gtk TreePath (tuple of intergers) or C{None}
		'''
		#~ print('!! SELECT', path)
		model = self.get_model()
		if model is None:
			return None # index not yet initialized ...

		treepath = model.set_current_page(path) # highlight in model
		return treepath # can be None

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

		@returns: a L{PageIndexRecord} or C{None} if there was no selection
		'''
		model, iter = self.get_selection().get_selected()
		if model is None or iter is None:
			return None
		else:
			return model.get_indexpath(iter)
