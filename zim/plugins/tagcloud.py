# -*- coding: utf-8 -*-

import gtk
import logging

from zim.plugins import PluginClass
from zim.gui.pageindex import PageTreeStore, PageTreeIter, PageTreeView
from zim.index import IndexPath
from zim.gui.widgets import LEFT_PANE


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




class TagCloudItem(gtk.ToggleButton):
	
	def __init__(self, indextag):
		gtk.ToggleButton.__init__(self, indextag.name)
		self.set_relief(gtk.RELIEF_NONE)
		self.indextag = indextag



class TagCloudWidget(gtk.TextView):
	'''
	Text-view based list of tags, where each tag is represented by a button 
	inserted as a child in the textview.
	'''
	
	def __init__(self, ui):
		gtk.TextView.__init__(self, None) # Create TextBuffer implicitly
		self.set_name('zim-tagcloud-tagcloud')
		self._signals = ()

		self.set_editable(False)
		self.set_cursor_visible(False)
		self.set_wrap_mode(gtk.WRAP_CHAR)

		self.ui = ui
		self.ui.connect_after('open-notebook', self.do_set_notebook)
		if not self.ui.notebook is None:
			self.do_set_notebook(self.ui, self.ui.notebook)


	def do_set_notebook(self, ui, notebook):
		'''
		Initialise view with a new notebook
		@param ui: Zim GUI
		@param notebook: The new notebook
		'''
		self.__disconnect()
		self.__clear_all()
		self.index = notebook.index
		self.__connect()
		self.__insert_all()


	def list_pages(self, offset = None, limit = 20, return_id = False):
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
			if not row['basename'] == '':
				if return_id:
					yield row['id']
				else:					
					yield self.index.lookup_id(row['id'])


	def __do_toggle(self, widget, data = None):
		#logger.debug("%s was toggled %s" % (data, ("OFF", "ON")[widget.get_active()]))
		self.__update_cloud()


	def __update_cloud(self):
		items = self.get_children()
		filter = self.get_filter_tags(items)
		pages = self.get_filtered_pages(filter)
		tags = self.get_filtered_tags(pages)
		for item in items:
			if item.indextag.id in tags:
				item.show()
			else:
				item.hide()


	def get_filter_tags(self, items = None):
		if items is None:
			items = self.get_children()
		result = []
		for item in items:
			if item.get_active():
				result.append(item.indextag.id)
		#logger.debug("filter tags: %s" % (str(result),))
		return result
	
	
	def get_filtered_pages(self, filter_tags = None):
		'''
		Determines which pages are listed according to the selected tags
		@return A list of page IDs
		'''
		if filter_tags is None:
			filter_tags = self.__get_filter_tags()
		all = set(self.list_pages(None, return_id = True))
		sets = [set(self.index.list_tagged(tagid, return_id = True)) for tagid in filter_tags]
		result = reduce(lambda a, b: a & b, sets, all)
		#logger.debug("filtered pages: %s" % (str(result),))
		return result
	
	
	def get_filtered_tags(self, pages):
		if len(pages):
			sets = [set(self.index.list_tags(page, return_id = True)) for page in pages]
			result = reduce(lambda a, b: a | b, sets)
		else:
			result = set(self.index.list_tags(None, return_id = True))
		#logger.debug("filtered tags: %s" % (str(result),))
		return result
	
		
	def __get_item(self, iter):
		anchor = iter.get_child_anchor()
		widgets = anchor.get_widgets()
		return widgets[0]


	def __insert_all(self):
		indextags = list(self.index.list_tags(None))
		buffer = self.get_buffer()
		iter = buffer.get_start_iter()
		for indextag in indextags:
			self.__insert(indextag, iter)
		
		
	def __insert(self, indextag, iter = None):
		if iter is None:
			iter = self.__get_iter(indextag)
		buffer = self.get_buffer()
		anchor = buffer.create_child_anchor(iter)
		child = TagCloudItem(indextag)
		child.connect("toggled", self.__do_toggle, indextag)
		self.add_child_at_anchor(child, anchor)
		
		
	def __remove(self, indextag, iter = None):
		if iter is None:
			iter = self.__get_iter(indextag)
		buffer = self.get_buffer()
		end = iter.copy()
		end.forward_char()
		buffer.delete(iter, end)


	def __get_iter(self, indextag):
		'''
		Find the position of the tag button in the textview
		@param indextag: The tag representation in the index
		'''
		tagids = [t.id for t in self.index.list_tags(None)]
		pos = tagids.index(indextag.id)
		buffer = self.get_buffer()
		iter = buffer.get_iter_at_offset(pos)
		return iter 


	def __clear_all(self):
		'''
		Clears the cloud
		'''
		buffer = self.get_buffer()
		buffer.delete(buffer.get_start_iter(), buffer.get_end_iter())


	def __connect(self):
		'''
		Connect to index signals
		'''
		
		def on_tag_created(o, indextag):
			self.__insert(indextag)
			self.__update_cloud()
			
		def on_tag_to_be_deleted(o, indextag):
			self.__remove(indextag)

		self._signals = (
			self.index.connect('tag-created', on_tag_created),
			self.index.connect('tag-to-be-deleted', on_tag_to_be_deleted),
		)


	def __disconnect(self):
		'''
		Stop the model from listening to the index. Used to unhook the model
		before reloading the index.
		'''
		for id in self._signals:
			self.index.disconnect(id)

			
			

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
				
		self.taglistview = TagCloudWidget(self.plugin.ui)
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
			self.ui.mainwindow.add_tab(_('Tag Cloud'), self.sidepane_widget, LEFT_PANE)
			self.sidepane_widget.show_all()


	def disconnect_embedded_widget(self):
		if not self.sidepane_widget is None:
			sidepane = self.ui.mainwindow.sidepane
			pagenum = sidepane.page_num(self.sidepane_widget)
			if not pagenum is None: 
				sidepane.remove_page(pagenum)
			self.sidepane_widget = None

