# -*- coding: utf-8 -*-

import gtk

from zim.plugins import PluginClass
from zim.gui.pageindex import *
from zim.index import IndexTag


class TagTreeStore(PageTreeStore):
	
	def __init__(self, index):
		self._reverse_cache = {}
		PageTreeStore.__init__(self, index)
	
	def _connect(self):
		def on_page_changed(o, path, signal):
			#~ print '!!', signal, path
			self._flush()
			treepaths = self.get_treepaths(path)
			for treepath in treepaths:
				#~ print '!!', signal, path, treepath
				treeiter = self.get_iter(treepath)
				self.emit(signal, treepath, treeiter)

		def on_page_deleted(o, path):
			#~ print '!! page delete', path
			treepaths = self.get_treepaths(path)
			for treepath in treepaths:
				self.emit('row-deleted', treepath)
			self._flush()

		def on_tag_created(o, tag):
			self._flush()
			all_tags = [t.id for t in self.index.list_tags(None)]
			treepath = (all_tags.index(tag.id),)
			treeiter = self.get_iter(treepath)
			#~ print '!! tag created', tag, treepath
			self.row_inserted(treepath, treeiter)
			
		def on_tag_inserted(o, tag, path):
			self._flush()
			all_tags = [t.id for t in self.index.list_tags(None)]
			all_tagged = [p.id for p in self.index.list_tagged(tag)]
			treepath = (all_tags.index(tag.id), all_tagged.index(path.id))
			treeiter = self.get_iter(treepath)
			#~ print '!! tag inserted', tag, treepath
			self.row_inserted(treepath, treeiter)
			if not path.hasdata:
				path = self.index.lookup_data(path)
			if path.haschildren:
				self.row_has_child_toggled(treepath, treeiter)

		def on_tag_removed(o, tag, path):
			all_tags = [t.id for t in self.index.list_tags(None)]
			all_tagged = [p.id for p in self.index.list_tagged(tag)]
			treepath = (all_tags.index(tag.id), all_tagged.index(path.id))
			#~ print '!! tag removed', tag, treepath
			self.row_deleted(treepath)
			self._flush()
			
		def on_tag_deleted(o, tag):
			all_tags = [t.id for t in self.index.list_tags(None)]
			treepath = (all_tags.index(tag.id),)
			#~ print '!! tag deleted', tag, treepath
			self.row_deleted(treepath)
			self._flush()

		self._signals = (
			self.index.connect('page-inserted', on_page_changed, 'row-inserted'),
			self.index.connect('page-updated', on_page_changed, 'row-changed'),
			self.index.connect('page-haschildren-toggled', on_page_changed, 'row-has-child-toggled'),
			self.index.connect('page-to-be-deleted', on_page_deleted),
			# TODO: Treat tag-inserted and new tag differently
			self.index.connect('tag-created', on_tag_created),
			self.index.connect('tag-inserted', on_tag_inserted),
			self.index.connect('tag-to-be-removed', on_tag_removed),
			self.index.connect('tag-to-be-deleted', on_tag_deleted),
		)
		# The page-to-be-deleted signal is a hack so we have time to ensure we know the
		# treepath of this indexpath - once we get page-deleted it is to late to get this
	
	def _get_iter(self, treepath):
		'''Convert the tree hierarchy to a PageTreeIter'''
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
					if parent is None:
						# The first tree level are tags
						#~ print '>>>> Load taglist'
						pages = self.index.list_tags_n(None, offset, limit=20)
					else:
						#~ print '>>>> Load pagelist for', parent, 'offset', offset
						if isinstance(parent, IndexTag):
							pages = self.index.list_tagged_n(parent, offset, limit=20)
						else:
							pages = self.index.list_pages_n(parent, offset, limit=20)
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
	
	def _flush(self):
		self._reverse_cache = {}
		return PageTreeStore._flush(self)
	
	def get_treepaths(self, path):
		'''Convert a Zim path to tree hierarchy, in general results in multiple
		 matches
		'''
		if path.isroot:
			raise ValueError

		if not isinstance(path, IndexPath):
			path = self.index.lookup_path(path)
			if path is None:
				return None

		# See if it is in cache already
		if path in self._reverse_cache:
			#~ print '>>> Return from cache', reverse_cache[path]
			return self._reverse_cache[path]

		# Try getting it while populating cache
		paths = list(path.parents())
		paths.pop() # get rid of root namespace as parent
		paths.insert(0, path)
		
		child = None
		childpath = ()
		treepaths = []
		all_tags = [t.id for t in self.index.list_tags(None)]
		
		for p in paths:
			if not child is None:
				childpath += (list(self.index.list_pages(p)).index(child),)
			# Get tags of this path
			for t in self.index.list_tags(p):
				ttagged = list(self.index.list_tagged(t))
				treepaths.append((all_tags.index(t.id), ttagged.index(p)) + childpath)
			child = p 
			
		self._reverse_cache.setdefault(p, treepaths)

		#~ print '>>> Return', treepath
		self._schedule_flush()
		return treepaths

	def on_iter_has_child(self, iter):
		'''Returns True if the iter has children'''
		if isinstance(iter.indexpath, IndexTag):
			all_tags = [t.id for t in self.index.list_tags(None)]
			return iter.indexpath.id in all_tags
		else:
			return PageTreeStore.on_iter_has_child(self, iter)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of tags is given.
		'''
		if iter is None:
			# Number of tags
			cursor = self.db.cursor()
			cursor.execute('select count(*) from tags')
			row = cursor.fetchone()
			return int(row[0])
		elif isinstance(iter.indexpath, IndexTag):
			# Number of tagged pages
			cursor = self.db.cursor()
			cursor.execute('select count(*) from tagsources where tag==?', (iter.id,))
			row = cursor.fetchone()
			return int(row[0])
		else:
			return PageTreeStore.on_iter_n_children(self, iter)

	def on_get_value(self, iter, column):
		'''Returns the data for a specific column'''
		if isinstance(iter.indexpath, IndexTag):
			tag = iter.indexpath
			if column == NAME_COL:
				return tag.name
			elif column == PATH_COL:
				return tag
			elif column == EMPTY_COL:
				return False
			elif column == STYLE_COL:
				return pango.STYLE_NORMAL
			elif column == FGCOLOR_COL:
				return self.NORMAL_COLOR
		else:
			return PageTreeStore.on_get_value(self, iter, column)


class TagTreeView(PageTreeView):
	
	def do_set_notebook(self, ui, notebook):
		self._cleanup = None # else it might be pointing to old model
		self.set_model(TagTreeStore(notebook.index))
		if not ui.page is None:
			self.on_open_page(ui.page)
		self.get_model().connect('row-inserted', self.on_row_inserted)

	def on_open_page(self, path):
		self.get_model()
	
	def do_row_activated(self, treepath, column):
		'''Handler for the row-activated signal, emits page-activated if a 
		it is really a page'''
		model = self.get_model()
		iter = model.get_iter(treepath)
		if len(treepath) > 1:
			# Only pages (no tags) can be activated
			path = model.get_indexpath(iter)		
			self.emit('page-activated', path)
			
	def select_page(self, path):
		'''Select a page in the treeview, returns the treepath or None'''
		#~ print '!! SELECT', path
		model, iter = self.get_selection().get_selected()
		if model is None:
			return None # index not yet initialized ...

		if iter and model[iter][PATH_COL] == path:
			return model.get_path(iter) # this page was selected already

		return None # No multiple selection

class TagviewPlugin(PluginClass):

	plugin_info = {
		'name': _('Tagview'), # T: plugin name
		'description': _('''\
This plugin loads the tag user interface.
'''), # T: plugin description
		'author': 'Fabian Moser',
		'help': 'Plugins:Tagview',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None # For the embedded version

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.connect_embedded_widget()

	def disconnect(self):
		self.disconnect_embedded_widget()
		PluginClass.disconnect(self)

	def connect_embedded_widget(self):
		if not self.sidepane_widget:
			sidepane = self.ui.mainwindow.sidepane
			self.sidepane_widget = TagviewPluginWidget(self)
			sidepane.add(self.sidepane_widget)
			self.sidepane_widget.show_all()

	def disconnect_embedded_widget(self):
		if self.sidepane_widget:
			sidepane = self.ui.mainwindow.sidepane
			sidepane.remove(self.sidepane_widget)
			self.sidepane_widget = None


class TagviewPluginWidget(gtk.ScrolledWindow):

	def __init__(self, plugin):
		gtk.ScrolledWindow.__init__(self)
		self.plugin = plugin

		self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)
		
		self.treeview = TagTreeView(self.plugin.ui)
		self.treeview.set_name('zim-tagindex')
		self.add(self.treeview)
				