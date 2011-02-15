# -*- coding: utf-8 -*-

import gobject
import gtk
import logging
import pango

from zim.plugins import PluginClass
from zim.gui.pageindex import PageTreeStore, PageTreeIter, PageTreeView, NAME_COL, STYLE_COL, FGCOLOR_COL
from zim.index import IndexPath, IndexTag
from zim.gui.widgets import LEFT_PANE, SingleClickTreeView, gtk_get_style


logger = logging.getLogger('zim.plugins.tagcloud')



class PageListStore(PageTreeStore):
	'''
	A TreeModel that lists all Zim pages in a flat list. Pages with	associated 
	sub-pages still show them as sub-nodes.
	'''
	
	def __init__(self, index):
		PageTreeStore.__init__(self, index)
		self._reverse_cache = {}
	
	
	def _connect(self):
		def on_page_changed(o, path, signal):
			self._flush()
			treepaths = self.get_treepaths(path)
			for treepath in treepaths:
				treeiter = self.get_iter(treepath)
				self.emit(signal, treepath, treeiter)

		def on_page_deleted(o, path):
			treepaths = self.get_treepaths(path)
			for treepath in treepaths:
				self.emit('row-deleted', treepath)
			self._flush()

		self._signals = (
			self.index.connect('page-inserted', on_page_changed, 'row-inserted'),
			self.index.connect('page-updated', on_page_changed, 'row-changed'),
			self.index.connect('page-haschildren-toggled', on_page_changed, 'row-has-child-toggled'),
			self.index.connect('page-to-be-deleted', on_page_deleted),
		)


	def list_pages(self, offset = None, limit = 20):
		'''
		Query the index for a flat page list
		@param offset: Offset in the list for segmented queries
		@param limit: Limit of the segment size for segmented queries.
		'''
		cursor = self.index.db.cursor()
		
		if offset is None:
			cursor.execute('select * from pages order by lower(basename)')
		else:
			cursor.execute('select * from pages order by lower(basename) limit ? offset ?', (limit, offset + 1))
			
		for row in cursor:
			page = self.index.lookup_id(row['id'])
			if not page is None and not page.isroot:
				yield page

	
	def _get_iter(self, treepath):
		'''
		Cached conversion of the tree hierarchy to a PageTreeIter.
		
		@param treepath: A tuple of int e.g. (0,) is the first item in the root namespace.
		@return: A PageTreeIter instance corresponding to the given path
		'''
		if not treepath in self._cache:
			parent = None
			
			for i in xrange(1, len(treepath) + 1):
				leveltreepath = treepath[:i]
				
				if not leveltreepath in self._cache:
					parenttreepath = leveltreepath[:-1]
					offset = leveltreepath[-1]
				
					if parent is None:
						pages = self.list_pages(offset, limit = 20)
					else:
						pages = self.index.list_pages_n(parent, offset, limit=20)
						
					for j, path in enumerate(pages):
						childtreepath = parenttreepath + (offset + j,)
						iter = PageTreeIter(childtreepath, path)
						self._cache.setdefault(childtreepath, iter)
						
				if leveltreepath in self._cache:
					parent = self._cache[leveltreepath].indexpath
				else:
					return None
				
		self._schedule_flush() # Clear the cache when idle
		return self._cache.get(treepath, None)
	
	
	def _flush(self):
		self._reverse_cache = {}
		return PageTreeStore._flush(self)
	
	
	def get_treepaths(self, path):
		'''
		Cached conversion of a Zim path to a node in the tree hierarchy, i.e.
		the inverse operation of _get_iter.
		
		@param path: Usually an IndexPath instance
		@return: A list of tuples of ints (one page can be represented many times)
		'''
		if path.isroot:
			raise ValueError # There can be no tree node for the tree root

		if not isinstance(path, IndexPath):
			path = self.index.lookup_path(path)
			if path is None:
				return None

		# See if it is in cache already
		if path in self._reverse_cache:
			return self._reverse_cache[path]

		paths = [path] + list(path.parents())[:-1] # Zim paths for the path and all parents (except root)		
		child = None
		childpath = ()
		treepaths = []
		all_pages = list(self.list_pages())
		
		for p in paths:
			if not child is None:
				childpath += (list(self.index.list_pages(p)).index(child),)
			treepaths.append((all_pages.index(p),) + childpath)
			child = p
			
		self._reverse_cache.setdefault(path, treepaths)			
		self._schedule_flush()
		return treepaths
	


class PageListView(PageTreeView):
	'''
	A slightly modified version of the purely hierarchical page index using
	a flat page list for the top level nodes.
	'''
	
	def do_set_notebook(self, ui, notebook):
		self._cleanup = None # else it might be pointing to old model
		self.set_model(PageListStore(notebook.index))
		if not ui.page is None:
			self.on_open_page(ui.page)
		self.get_model().connect('row-inserted', self.on_row_inserted)



class TagListIter(object):
	'''
	Simple wrapper for IndexTag objects used as list iters
	'''

	__slots__ = ('indextag', 'treepath')

	def __init__(self, treepath, indextag):
		self.treepath = treepath
		self.indextag = indextag

	def __repr__(self):
		return '<TagListIter, %s, %s>' % (self.treepath, self.indextag.name)



class TagListStore(gtk.GenericTreeModel):
	'''
	A tree model interfacing directly to the tag index database.
	'''

	COLUMN_TYPES = (
		gobject.TYPE_STRING, # NAME_COL
	)

	style = gtk_get_style()
	NORMAL_COLOR = style.text[gtk.STATE_NORMAL]


	def __init__(self, index):
		'''
		Initialise the TreeModel and declare custom memory management
		@param index: The notebook index
		'''
		gtk.GenericTreeModel.__init__(self)
		self.index = index
		self.set_property('leak-references', False)
		self._cache = {}
		self._flush_scheduled = False
		self._connect()


	def _connect(self):
		'''
		Connect to index signals
		'''
		
		def on_tag_created(o, tag):
			self._flush()
			all_tags = [t.id for t in self.index.list_tags(None)]
			treepath = (all_tags.index(tag.id),)
			treeiter = self.get_iter(treepath)
			self.row_inserted(treepath, treeiter)
			
		def on_tag_to_be_deleted(o, tag):
			all_tags = [t.id for t in self.index.list_tags(None)]
			treepath = (all_tags.index(tag.id),)
			self.row_deleted(treepath)
			self._flush()

		self._signals = (
			self.index.connect('tag-created', on_tag_created),
			self.index.connect('tag-to-be-deleted', on_tag_to_be_deleted),
		)


	def disconnect(self):
		'''
		Stop the model from listening to the index. Used to unhook the model
		before reloading the index.
		'''
		for id in self._signals:
			self.index.disconnect(id)
			

	def on_get_flags(self):
		return 0 # no flags


	def on_get_n_columns(self):
		return len(self.COLUMN_TYPES)


	def on_get_column_type(self, i):
		return self.COLUMN_TYPES[i]


	def on_get_value(self, iter, column):
		tag = iter.indextag
		if column == NAME_COL:
			return tag.name


	def on_get_iter(self, treepath):
		return self._get_iter(treepath)


	def on_get_path(self, iter):
		return iter.treepath
	

	def _get_iter(self, treepath):
		if not treepath in self._cache:
			offset = treepath[0]
			indextags = self.index.list_tags(None, offset, limit=20)
			for i, indextag in enumerate(indextags):
				itreepath = (offset + i,)
				iter = TagListIter(itreepath, indextag)
				self._cache.setdefault(itreepath, iter)

		self._schedule_flush()
		return self._cache.get(treepath, None)


	def _schedule_flush(self):
		'''
		Schedule a flush with some timeout to try to take advantage of known
		cache for repeated requests. Cache can grow very big on scroll, so don't
		make the time constant to large.
		'''
		if not self._flush_scheduled:
			def idle_add():
				gobject.idle_add(self._flush)
				return False # delete timeout

			gobject.timeout_add(500, idle_add)
			self._flush_scheduled = True


	def _flush(self):
		'''
		Drop references and free memory. Cache is populated by either 
		_get_iter() or get_treepath()
		'''
		self.invalidate_iters()
		self._cache = {} # del _cache - keep no ref to this dict
		self._flush_scheduled = False
		return False # In case we are called from idle signal


	def get_treepath(self, tag):
		'''
		Get the location of a tag in the tree/list
		@param tag: An IndexTag instance
		@return: The tree path corresponding the the given tag or None
		'''
		if not isinstance(tag, IndexTag):
			tag = self.index.lookup_tag(tag)
			if tag is None:
				return None

		# See if it is in cache already
		reverse_cache = dict([(i.indextag, k) for k, i in self._cache.items()])
		if tag in reverse_cache:
			return reverse_cache[tag]

		all_tags = list(self.index.list_tags(None))
		treepath = (all_tags.index(tag),)
		iter = TagListIter(treepath, tag)
		self._cache.setdefault(treepath, iter)
		reverse_cache.setdefault(tag, treepath)
		
		self._schedule_flush()
		return treepath
	

	def on_iter_next(self, iter):
		'''
		@return: The TagListIter for the next row or None
		'''
		treepath = (iter.treepath[0] + 1,)
		return self._get_iter(treepath)


	def on_iter_children(self, iter):
		'''
		@return: A TagListIter for the first child below path or None.
		'''
		if iter is None:
			return self._get_iter((0,))
		else:
			return None


	def on_iter_has_child(self, iter):
		False
		

	def on_iter_n_children(self, iter):
		'''
		Returns the number of children in a namespace. As a special case,
		when iter is None the number of pages in the root namespace is given.
		'''
		if iter is None:
			return self.index.n_list_tags(None)
		else:
			return 0


	def on_iter_nth_child(self, iter, n):
		'''
		Returns the nth child for a given IndexPath or None.
		As a special case iter can be None to get pages in the root namespace.
		'''
		if iter is None:
			return self._get_iter((n,))
		else:
			return None


	def on_iter_parent(self, iter):
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
gobject.type_register(TagListStore) #@UndefinedVariable



class TagListView(SingleClickTreeView):
	
	def __init__(self, ui):
		SingleClickTreeView.__init__(self)
		
		self.set_name('zim-tagcloud-taglist')
		self._cleanup = None

		self.ui = ui
		self.ui.connect_after('open-notebook', self.do_set_notebook)
		if not self.ui.notebook is None:
			self.do_set_notebook(self.ui, self.ui.notebook)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_tags_', cell_renderer, text = NAME_COL)
		self.append_column(column)

		self.set_headers_visible(False)

		self.set_enable_search(True)
		self.set_search_column(0)


	def do_set_notebook(self, ui, notebook):
		self._cleanup = None # else it might be pointing to old model
		self.set_model(TagListStore(notebook.index))


gobject.type_register(TagListView) #@UndefinedVariable



class TagCloudPluginWidget(gtk.VPaned):

	def __init__(self, plugin):
		gtk.VPaned.__init__(self)
		self.plugin = plugin

		def add_scrolled(widget):
			sw = gtk.ScrolledWindow()
			sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
			sw.set_shadow_type(gtk.SHADOW_IN)
			sw.add(widget)
			self.add(sw)
				
		self.taglistview = TagListView(self.plugin.ui)
		add_scrolled(self.taglistview)
		
		self.pagelistview = PageListView(self.plugin.ui)
		self.pagelistview.set_name('zim-tagcloud-pagelist')
		add_scrolled(self.pagelistview)



class TagCloudPlugin(PluginClass):

	plugin_info = {
		'name': _('Tag Cloud'), # T: plugin name
		'description': _('''\
This plugin provides a page index filtered by means of selecting tags in a cloud.
'''), # T: plugin description
		'author': 'Fabian Moser',
		'help': 'Plugins:Tag Cloud',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.connect_embedded_widget()

	def disconnect(self):
		self.disconnect_embedded_widget()
		PluginClass.disconnect(self)

	def connect_embedded_widget(self):
		if self.sidepane_widget is None:
			self.sidepane_widget = TagCloudPluginWidget(self)
			self.ui.mainwindow.add_tab(_('Tags'), self.sidepane_widget, LEFT_PANE)
			self.sidepane_widget.show_all()

	def disconnect_embedded_widget(self):
		if not self.sidepane_widget is None:
			sidepane = self.ui.mainwindow.sidepane
			pagenum = sidepane.page_num(self.sidepane_widget)
			if not pagenum is None: 
				sidepane.remove_page(pagenum)
			self.sidepane_widget = None


# vim: autoindent noexpandtab shiftwidth=4 tabstop=4

