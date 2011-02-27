# -*- coding: utf-8 -*-

import gobject
import gtk
import logging

from zim.plugins import PluginClass
from zim.gui.pageindex import PageTreeStore, PageTreeIter, PageTreeView, PATH_COL
from zim.index import IndexPath
from zim.gui.widgets import LEFT_PANE


logger = logging.getLogger('zim.plugins.tagcloud')



class PageListStore(PageTreeStore):
	'''
	A TreeModel that lists all Zim pages in a flat list. Pages with	associated 
	sub-pages still show them as sub-nodes.
	'''
	
	def __init__(self, index, cloud):
		PageTreeStore.__init__(self, index)
		self._reverse_cache = {}
		self.cloud = cloud
	
	
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
		
		return self.cloud.list_pages(offset = offset, limit = limit)
	
	
	def n_list_pages(self):
		'''
		Returns the total number of pages
		'''
		cursor = self.index.db.cursor()
		cursor.execute('select count(*) from pages')
		row = cursor.fetchone()
		return int(row[0])-1

	
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
				childpath = (list(self.index.list_pages(p)).index(child),) + childpath
			treepaths.append((all_pages.index(p),) + childpath)
			child = p
			
		self._reverse_cache.setdefault(path, treepaths)			
		self._schedule_flush()
		return treepaths


	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of pages in the root namespace is given.
		'''
		if iter is None:
			return self.n_list_pages()
		else:
			return PageTreeStore.on_iter_n_children(self, iter)



class PageListView(PageTreeView):
	'''
	A slightly modified version of the purely hierarchical page index using
	a flat page list for the top level nodes.
	'''
	
	def __init__(self, ui, cloud):
		self.cloud = cloud
		self._cloud_signals = ()
		self._filtered_pages = []
		PageTreeView.__init__(self, ui)
		self.set_name('zim-tagcloud-pagelist')
	
	
	def do_set_notebook(self, ui, notebook):
		
		def func(model, iter):
			childiter = model.get_user_data(iter)
			result = len(childiter.treepath) > 1 or childiter.indexpath.id in self._filtered_pages
			return result
		
		self._disonnect_cloud()
		self._cleanup = None # else it might be pointing to old model
		
		treemodel = PageListStore(notebook.index, self.cloud)
		treemodelfilter = treemodel.filter_new(root = None)
		self._filtered_pages = self.cloud.get_filtered_pages()
		treemodelfilter.set_visible_func(func)

		self.set_model(treemodelfilter)
		if not ui.page is None:
			self.on_open_page(ui.page)
		self.get_model().connect('row-inserted', self.on_row_inserted)
		self._connect_cloud()
		
		
	def _connect_cloud(self):
		
		def on_cloud_updated(o, pages):
			self._filtered_pages = pages
			self.get_model().refilter()
		
		self._cloud_signals = (
			self.cloud.connect('cloud-updated', on_cloud_updated),
		)
		
		
	def _disonnect_cloud(self):
		for id in self._cloud_signals:
			self.cloud.disconnect(id)
		
		
	def on_row_inserted(self, model, treepath, iter):
		childmodel = model.get_model()
		childiter = model.convert_iter_to_child_iter(iter)
		path = childmodel.get_indexpath(childiter)
		if path == self.ui.page:
			self.on_open_page(self.ui.page)
		
		
	def do_row_activated(self, treepath, column):
		'''Handler for the row-activated signal, emits page-activated'''
		model = self.get_model()
		iter = model.get_iter(treepath)
		childmodel = model.get_model()
		childiter = model.convert_iter_to_child_iter(iter)
		path = childmodel.get_indexpath(childiter)
		self.emit('page-activated', path)
		
		
	def on_open_page(self, path):
		pass
		

	def select_page(self, path):
		'''
		Select a page in the treeview, returns the treepath or None
		'''
		model, iter = self.get_selection().get_selected()
		if model is None:
			return None # index not yet initialized ...

		if iter and model[iter][PATH_COL] == path:
			return model.get_path(iter) # this page was selected already

		return None # No multiple selection


# Need to register classes defining gobject signals
gobject.type_register(PageListView) #@UndefinedVariable



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
	
	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'cloud-updated': (gobject.SIGNAL_RUN_LAST, None, (object,)), #@UndefinedVariable
	}
	
	
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
		self._disconnect_index()
		self._clear_all()
		
		self.index = notebook.index
		self._connect_index()
		self.update_cloud()


	def _connect_index(self):
		'''
		Connect to index signals
		'''
		
		def on_index_change(o, indextag):
			self.update_cloud()

		self._signals = (
			self.index.connect('tag-created', on_index_change),
			self.index.connect('tag-deleted', on_index_change),
		)


	def _disconnect_index(self):
		'''
		Stop the model from listening to the index. Used to unhook the model
		before reloading the index.
		'''
		for id in self._signals:
			self.index.disconnect(id)


	def _clear_all(self):
		'''
		Clears the cloud
		'''
		def remove(o, child, data):
			o.remove(child)
			
		self.foreach(remove)
		buffer = self.get_buffer()
		buffer.delete(buffer.get_start_iter(), buffer.get_end_iter())


	def list_pages(self, offset = None, limit = 20, return_id = False):
		'''
		Query the index for a flat page list
		@param offset: Offset in the list for segmented queries
		@param limit: Limit of the segment size for segmented queries.
		'''
		cursor = self.index.db.cursor()

		query = 'select * from pages order by lower(basename)'
		if offset is None:
			cursor.execute(query)
		else:
			cursor.execute(query + ' limit ? offset ?', (limit, offset + 1))
			
		for row in cursor:
			if not row['basename'] == '':
				if return_id:
					yield row['id']
				else:					
					yield self.index.lookup_id(row['id'])


	def get_tags_ordered(self):
		'''
		Defines the order of the displayed tags
		'''
		cursor = self.index.db.cursor()
			
        # Ordererd by name		
#		cursor.execute('select * from tags order by lower(name)')
#		for row in cursor:
#			yield row['id']
		
		# Ordererd by occurences
		cursor.execute('select *, count(tag) as occurances from tagsources group by tag order by occurances desc')
		for row in cursor:
			yield row['tag']


	def _get_selected_tags(self):
		'''
		Determines which tags are selected in the cloud
		'''
		result = []
		buffer = self.get_buffer()
		iter = buffer.get_start_iter()
		while not iter.is_end():
			anchor = iter.get_child_anchor()
			if not anchor is None:
				widgets = anchor.get_widgets()
				if len(widgets) > 0:
					if widgets[0].get_active():
						result.append(widgets[0].indextag.id)
			iter.forward_char()		
		#logger.debug("Selected tags: %s" % (str(result),))
		return result
	
	
	def get_filtered_pages(self, selected_tags = None, offset = None, limit = 20):
		'''
		Determines which pages are listed according to the selected tags
		@return A list of page IDs
		'''
		if selected_tags is None:
			selected_tags = self._get_selected_tags()
		result = list(self.list_pages(offset, limit, True))
		if len(selected_tags):
			sets = [set(self.index.list_tagged(tagid, return_id = True)) for tagid in selected_tags]
			chosen = reduce(lambda a, b: a & b, sets)
			result = filter(lambda i: i in chosen, result)
		#logger.debug("Filtered pages: %s" % (str(result),))
		return result
	
	
	def get_filtered_tags(self, filtered_pages = None):
		if filtered_pages is None:
			filtered_pages = self.get_filtered_pages()
		result = list(self.get_tags_ordered())
		if len(filtered_pages):
			sets = [set(self.index.list_tags(page, return_id = True)) for page in filtered_pages]
			chosen = reduce(lambda a, b: a | b, sets)
			result = filter(lambda i: i in chosen, result)
		#logger.debug("Filtered tags: %s" % (str(result),))
		return result


	def update_cloud(self):
		buffer = self.get_buffer()
		
		def do_toggle(o, data = None):
			#logger.debug("%s was toggled %s" % (data, ("OFF", "ON")[o.get_active()]))
			self.update_cloud()
		
		def get_item_at_iter(iter):
			result = None
			anchor = iter.get_child_anchor()
			if not anchor is None:
				widgets = anchor.get_widgets()
				if len(widgets) > 0:
					result = widgets[0] 
			return result
		
		def insert_item(id, iter):
			anchor = buffer.create_child_anchor(iter)
			indextag = self.index.lookup_tagid(id)
			item = TagCloudItem(indextag)
			self.add_child_at_anchor(item, anchor)
			item.connect("toggled", do_toggle, indextag)
			
		def remove_item(item, iter):
			self.remove(item)
			end = iter.copy()
			end.forward_char()
			buffer.delete(iter, end)
		
		pages = self.get_filtered_pages()
		tags = list(self.get_filtered_tags(pages))
		
		for pos, id in enumerate(tags):
			item = None
			iter = buffer.get_iter_at_offset(pos)
			
			# Remove items that shouldn't be here
			while not iter.is_end():
				item = get_item_at_iter(iter)
				if not item.indextag.id in tags:
					remove_item(item, iter)
				else:
					break
				iter = buffer.get_iter_at_offset(pos)			
			
			# Insert item if not yet there	
			if item is None or item.indextag.id != id:
				insert_item(id, iter)
		
		# Remove trailing items
		iter = buffer.get_iter_at_offset(len(tags))
		while not iter.is_end():
			item = get_item_at_iter(iter)
			remove_item(item, iter)
			iter = buffer.get_iter_at_offset(len(tags))
			
		self.show_all()
		self.emit('cloud-updated', pages)
				
				
# Need to register classes defining gobject signals
gobject.type_register(TagCloudWidget) #@UndefinedVariable
				
				

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
				
		self.tagcloud = TagCloudWidget(self.plugin.ui)
		add_scrolled(self.tagcloud)
		
		self.pagelistview = PageListView(self.plugin.ui, self.tagcloud)
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
			self.ui.mainwindow.remove(self.sidepane_widget)
			self.sidepane_widget = None

