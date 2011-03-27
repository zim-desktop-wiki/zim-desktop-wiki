# -*- coding: utf-8 -*-

# Copyright 2010 Fabian Moser
# Copyright 2011 Jaap Karssenberg


import gobject
import gtk
import pango

import logging

from zim.plugins import PluginClass
from zim.gui.pageindex import PageTreeStore, PageTreeIter, PageTreeView, \
	NAME_COL, PATH_COL, EMPTY_COL, STYLE_COL, FGCOLOR_COL
from zim.index import IndexPath, IndexTag
from zim.gui.widgets import LEFT_PANE


logger = logging.getLogger('zim.plugins.tags')


# TODO: put this methof in the index ? Maybe we can do without it..
def index_list_pages(index, offset = None, limit = 20, return_id = False):
	'''
	Query the index for a flat page list
	@param offset: Offset in the list for segmented queries
	@param limit: Limit of the segment size for segmented queries.
	'''
	cursor = index.db.cursor()

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
				yield index.lookup_id(row['id'])


def index_list_tags_ordered(index, tags=None):
	'''Returns a list of tuples where first item is an IndexTag object
	and second item is the number of occurences for this tag.

	When a list of tags is given only tags are listed in the result that
	occur on pages that match the given tag set. This is used to narrow
	down possible supersets that are not empty.
	'''
	cursor = index.db.cursor()
	if tags:
		tag_ids = '(' + ','.join(str(t.id) for t in tags) + ')'
		cursor.execute(
			# The sub-query filters on pages that match all of the given tags
			# The main query selects all tags occuring on those pages and sorts
			# them by number of matching pages
			'SELECT t.id, t.name, count(*) hits'
			' FROM tags t INNER JOIN tagsources s ON t.id = s.tag'
			' WHERE s.source IN ('
			'   SELECT source FROM tagsources'
			'   WHERE tag IN %s'
			'   GROUP BY source'
			'   HAVING count(tag) = ?'
			' )'
			' GROUP BY s.tag'
			' ORDER BY count(*) DESC' % tag_ids, (len(tags),)
		)
	else:
		cursor.execute(
			'SELECT t.id, t.name, count(*) hits'
			' FROM tags t INNER JOIN tagsources s ON t.id = s.tag'
			' GROUP BY s.tag'
			' ORDER BY count(*) DESC'
		)
	for row in cursor:
		yield IndexTag(row['name'], row['id'], row), row['hits']


class PageTreeTagIter(object):
	'''Simple wrapper for IndexTag objects used as tree iters

	This class is used mixed with PageTreeIter but does not derive
	from it. Any method that assumes PageTreeIter will fail if it
	suddenly encounters a PageTreeTagIter, this is intentional.
	'''

	__slots__ = ('indextag', 'treepath', 'n_children')

	def __init__(self, treepath, indextag):
		self.treepath = treepath
		self.indextag = indextag
		self.n_children = None # None means unknown

	def __repr__(self):
		return '<PageTreeTagIter, %s, %s>' % (self.treepath, self.indextag.name)


class TagsPageTreeStore(PageTreeStore):
	'''Subclass of the PageTreeStore that shows tags as the top level
	for sub-sets of the page tree.
	'''

	def __init__(self, index):
		self._reverse_cache = {}
		self.untagged = IndexTag(_('untagged'), -1)
			# T: label for untagged pages in side pane
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
			treepath = (all_tags.index(tag.id)+1,)
			treeiter = self.get_iter(treepath)
			#~ print '!! tag created', tag, treepath
			self.row_inserted(treepath, treeiter)

		def on_tag_to_be_inserted(o, tag, path, first):
			if first:
				# Remove from untagged branch
				untagged = [p.id for p in self.index.list_untagged()]
				treepath = (0, untagged.index(path.id))
				#~ print '!! removed from untagged', treepath
				self.row_deleted(treepath)
				self._flush()

		def on_tag_inserted(o, tag, path, first):
			if first:
				# Finish update of untagged branch
				if not self.index.n_list_untagged():
					treeiter = self.get_iter((0,))
					self.row_has_child_toggled((0,), treeiter)

			# Add to tag branch
			self._flush()
			all_tags = [t.id for t in self.index.list_tags(None)]
			all_tagged = [p.id for p in self.index.list_tagged(tag)]
			treepath = (all_tags.index(tag.id)+1, all_tagged.index(path.id))
			treeiter = self.get_iter(treepath)
			#~ print '!! tag inserted', tag, treepath
			self.row_inserted(treepath, treeiter)
			if not path.hasdata:
				path = self.index.lookup_data(path)
			if path.haschildren:
				self.row_has_child_toggled(treepath, treeiter)

		def on_tag_to_be_removed(o, tag, path, last):
			# Remove from tag branch
			all_tags = [t.id for t in self.index.list_tags(None)]
			all_tagged = [p.id for p in self.index.list_tagged(tag)]
			treepath = (all_tags.index(tag.id)+1, all_tagged.index(path.id))
			#~ print '!! tag removed', tag, treepath
			self.row_deleted(treepath)
			self._flush()

		def on_tag_removed(o, tag, path, last):
			if last:
				# Add to untagged
				untagged = [p.id for p in self.index.list_untagged()]
				treepath = (0, untagged.index(path.id))
				treeiter = self.get_iter(treepath)
				#~ print '!! new untagged', treepath
				if len(untagged) == 1:
					treeiter = self.get_iter((0,))
					self.row_has_child_toggled((0,), treeiter)
				self.row_inserted(treepath, treeiter)

		def on_tag_to_be_deleted(o, tag):
			all_tags = [t.id for t in self.index.list_tags(None)]
			treepath = (all_tags.index(tag.id)+1,)
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
			self.index.connect('tag-to-be-inserted', on_tag_to_be_inserted),
			self.index.connect('tag-inserted', on_tag_inserted),
			self.index.connect('tag-to-be-removed', on_tag_to_be_removed),
			self.index.connect('tag-removed', on_tag_removed),
			self.index.connect('tag-to-be-deleted', on_tag_to_be_deleted),
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
						tags = self.index.list_tags(None, max(0, offset-1), limit=20)
						if offset == 0:
							iter = PageTreeTagIter((0,), self.untagged)
							self._cache.setdefault((0,), iter)
							offset = 1

						for j, path in enumerate(tags):
							childtreepath = parenttreepath + (offset + j,)
							iter = PageTreeTagIter(childtreepath, path)
							self._cache.setdefault(childtreepath, iter)

					else:
						#~ print '>>>> Load pagelist for', parent, 'offset', offset
						if isinstance(parent, IndexTag):
							if parent == self.untagged:
								pages = self.index.list_untagged(offset, limit=20)
							else:
								pages = self.index.list_tagged(parent, offset, limit=20)
						else:
							pages = self.index.list_pages_n(parent, offset, limit=20)

						for j, path in enumerate(pages):
							childtreepath = parenttreepath + (offset + j,)
							iter = PageTreeIter(childtreepath, path)
							self._cache.setdefault(childtreepath, iter)
				try:
					iter = self._cache[mytreepath]
				except KeyError:
					return None
				else:
					if isinstance(iter, PageTreeTagIter):
						parent = iter.indextag
					else:
						parent = iter.indexpath

		#~ print '>>> Return', self._cache.get(treepath, None)
		self._schedule_flush()
		return self._cache.get(treepath, None)

	def _flush(self):
		self._reverse_cache = {}
		return PageTreeStore._flush(self)

	def get_treepath(self, path):
		if isinstance(path, IndexTag):
			if path == self.untagged:
				return (0,)
			else:
				all_tags = list(self.index.list_tags(None))
				i = all_tags.index(path)
				return (i+1,)
		else:
			treepaths = self.get_treepaths(path)
			if treepaths:
				return treepaths[0]
			else:
				return None

	def get_treepaths(self, path):
		'''Convert a Zim path to tree hierarchy, in general results in multiple
		 matches
		'''
		if isinstance(path, IndexTag):
			treepath = self.get_treepath(path)
			if treepath:
				return (treepath,)
			else:
				return None

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
				childpath = (list(self.index.list_pages(p)).index(child),) + childpath
			# Get tags of this path
			tags = list(self.index.list_tags(p))
			if len(tags) > 0:
				for t in tags:
					ttagged = list(self.index.list_tagged(t))
					treepaths.append((all_tags.index(t.id)+1, ttagged.index(p)) + childpath)
			else:
				untagged = list(self.index.list_untagged())
				treepaths.append((0, untagged.index(p)) + childpath)
			child = p

		self._reverse_cache.setdefault(path, treepaths)

		#~ print '>>> Return', treepath
		self._schedule_flush()
		return treepaths

	def get_indexpath(self, treeiter):
		'''Returns an IndexPath for a TreeIter or None'''
		# Note that iter is TreeIter here, not PageTreeIter
		iter = self.get_user_data(treeiter)
		if isinstance(iter, PageTreeIter):
			return iter.indexpath
		else:
			return None

	def get_indextag(self, treeiter):
		'''Returns an IndexTag for a TreeIter or None'''
		# Note that iter is TreeIter here, not PageTreeIter
		iter = self.get_user_data(treeiter)
		if isinstance(iter, PageTreeTagIter):
			return iter.indextag
		else:
			return None

	def on_iter_has_child(self, iter):
		'''Returns True if the iter has children'''
		if isinstance(iter, PageTreeTagIter):
			if iter.indextag == self.untagged:
				return self.index.n_list_untagged() > 0
			else:
				return self.index.n_list_tagged(iter.indextag) > 0
		else:
			return PageTreeStore.on_iter_has_child(self, iter)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of tags is given.
		'''
		if iter is None:
			return self.index.n_list_tags(None) + 1 # Include untagged
		elif isinstance(iter, PageTreeTagIter):
			if iter.indextag == self.untagged:
				return self.index.n_list_untagged()
			else:
				return self.index.n_list_tagged(iter.indextag)
		else:
			return PageTreeStore.on_iter_n_children(self, iter)

	def on_get_value(self, iter, column):
		'''Returns the data for a specific column'''
		if isinstance(iter, PageTreeTagIter):
			tag = iter.indextag
			if column == NAME_COL:
				return tag.name
			elif column == PATH_COL:
				return tag
			elif column == EMPTY_COL:
				return tag == self.untagged
			elif column == STYLE_COL:
				if tag == self.untagged:
					return pango.STYLE_ITALIC
				else:
					return pango.STYLE_NORMAL
			elif column == FGCOLOR_COL:
				if tag == self.untagged:
					return self.EMPTY_COLOR
				else:
					return self.NORMAL_COLOR
		else:
			return PageTreeStore.on_get_value(self, iter, column)


class TagsPageTreeView(PageTreeView):

	def __init__(self, ui, cloud):
		PageTreeView.__init__(self, ui)
		self.set_name('zim-tags-pagelist')


	def do_set_notebook(self, ui, notebook):
		self._cleanup = None # else it might be pointing to old model
		self.set_model(TagsPageTreeStore(notebook.index))
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

	def do_drag_data_get(self, dragcontext, selectiondata, info, time):
		assert selectiondata.target == INTERNAL_PAGELIST_TARGET_NAME
		model, iter = self.get_selection().get_selected()
		path = model.get_indexpath(iter)
		if isinstance(path, IndexTag):
			link = '@' + path.name
		else:
			link = path.name
		logger.debug('Drag data requested, we have internal tag/path "%s"', link)
		data = pack_urilist((link,))
		selectiondata.set(INTERNAL_PAGELIST_TARGET_NAME, 8, data)


# Need to register classes defining gobject signals
gobject.type_register(TagsPageTreeView) #@UndefinedVariable


class TaggedPageTreeStore(PageTreeStore):
	'''
	A TreeModel that lists all Zim pages in a flat list filtered by tags.
	Pages with	associated sub-pages still show them as sub-nodes.
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
		return index_list_pages(self.index, offset = offset, limit = limit)


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

	def get_treepath(self, path):
		treepaths = self.get_treepaths(path)
		if treepaths:
			return treepaths[0]
		else:
			return None

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



class TaggedPageTreeView(PageTreeView):
	'''
	A slightly modified version of the purely hierarchical page index using
	a flat page list for the top level nodes.
	'''

	def __init__(self, ui, cloud):
		self.cloud = cloud
		self._cloud_signals = ()
		self._tags = frozenset()
		PageTreeView.__init__(self, ui)
		self.set_name('zim-tags-pagelist')


	def do_set_notebook(self, ui, notebook):

		def func(model, iter):
			childiter = model.get_user_data(iter)
			if len(childiter.treepath) > 1:
				return True
			else:
				tags = frozenset(self.ui.notebook.index.get_tags(childiter.indexpath))
				return tags >= self._tags

		self._disonnect_cloud()
		self._cleanup = None # else it might be pointing to old model

		treemodel = TaggedPageTreeStore(notebook.index)
		treemodelfilter = treemodel.filter_new(root = None)
		self._tags = frozenset(self.cloud.get_selected_tags())
		treemodelfilter.set_visible_func(func)

		self.set_model(treemodelfilter)
		if not ui.page is None:
			self.on_open_page(ui.page)
		self.get_model().connect('row-inserted', self.on_row_inserted)
		self._connect_cloud()


	def _connect_cloud(self):

		def on_cloud_updated(cloud):
			#~ import time
			#~ t1 = time.time()
			self._tags = frozenset(cloud.get_selected_tags())
			self.get_model().refilter()
			#~ t2 = time.time()
			#~ print 'REFILTER', t2 - t1

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
gobject.type_register(TaggedPageTreeView) #@UndefinedVariable



class TagCloudItem(gtk.ToggleButton):

	def __init__(self, indextag):
		gtk.ToggleButton.__init__(self, indextag.name)
		self.set_relief(gtk.RELIEF_NONE)
		self.indextag = indextag

		def update_label(self):
			label = self.get_child()
			if self.get_active():
				label.set_markup('<b>'+label.get_text()+'</b>')
			else:
				label.set_text(label.get_text())
					# get_text() gives string without markup

		self.connect_after('toggled', update_label)


class TagCloudWidget(gtk.TextView):
	'''
	Text-view based list of tags, where each tag is represented by a button
	inserted as a child in the textview.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'cloud-updated': (gobject.SIGNAL_RUN_LAST, None, ()), #@UndefinedVariable
	}


	def __init__(self, ui):
		gtk.TextView.__init__(self, None) # Create TextBuffer implicitly
		self.set_name('zim-tags-tagcloud')
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
		self.update()


	def _connect_index(self):
		'''
		Connect to index signals
		'''

		def on_index_change(o, indextag):
			self.update()

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
		self.foreach(lambda b: self.remove(b))
		buffer = self.get_buffer()
		buffer.delete(*buffer.get_bounds())

	def get_selected_tags(self):
		'''Returns a list of tags currently are selected in the cloud'''
		return [b.indextag for b in self.get_children() if b.get_active()]

	def get_filtered_tags(self):
		'''Returns all tags currently shown in the widget'''
		return [b.indextag for b in self.get_children()]

	def update(self):
		selected = self.get_selected_tags()
		tags = [r[0] for r in index_list_tags_ordered(self.index, selected)]
		self._clear_all()

		buffer = self.get_buffer()
		for tag in tags:
			iter = buffer.get_end_iter()
			anchor = buffer.create_child_anchor(iter)
			button = TagCloudItem(tag)
			button.set_active(tag in selected)
			button.connect("toggled", lambda b: self.update())
			self.add_child_at_anchor(button, anchor)

		self.show_all()
		self.emit('cloud-updated')


# Need to register classes defining gobject signals
gobject.type_register(TagCloudWidget) #@UndefinedVariable



class TagsPluginWidget(gtk.VPaned):

	def __init__(self, plugin):
		gtk.VPaned.__init__(self)
		self.plugin = plugin

		def add_scrolled(widget):
			sw = gtk.ScrolledWindow()
			sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
			sw.set_shadow_type(gtk.SHADOW_IN)
			sw.add(widget)
			self.add(sw)
			return sw

		self.tagcloud = TagCloudWidget(self.plugin.ui)
		add_scrolled(self.tagcloud)

		treeview = TaggedPageTreeView(self.plugin.ui, self.tagcloud)
		self.treeviewwindow = add_scrolled(treeview)
			# TODO make initial treeview a uistate

		treeview.connect('populate-popup', self.on_populate_popup)

		plugin.ui.connect('start-index-update', lambda o: self.disconnect_model)
		plugin.ui.connect('end-index-update', lambda o: self.reload_model)

	def on_populate_popup(self, treeview, menu):
		# Add a popup menu item to switch the treeview mode
		menu.prepend(gtk.SeparatorMenuItem())

		current = self.treeviewwindow.get_child()

		item = gtk.CheckMenuItem(_('Sort pages by tags'))
		item.connect_object('toggled', self.__class__.toggle_treeview, self)
		item.set_active(isinstance(current, TagsPageTreeView))
		menu.prepend(item)

		menu.show_all()

	def toggle_treeview(self):
		'''Toggle the treeview type in the widget'''
		current = self.treeviewwindow.get_child()
		self.treeviewwindow.remove(current)
		# FIXME Need to disconnect ?
		if isinstance(current, TaggedPageTreeView):
			self.treeviewwindow.add(
				TagsPageTreeView(self.plugin.ui, self.tagcloud) )
		else:
			self.treeviewwindow.add(
				TaggedPageTreeView(self.plugin.ui, self.tagcloud) )

		self.treeviewwindow.show_all()

	def disconnect_model(self):
		'''Stop the model from listening to the inxed. Used to
		unhook the model before reloading the index. Typically
		should be followed by reload_model().
		'''
		treeview = self.treeviewwindow.get_child()
		treeview.get_model().disconnect()
		self.tagcloud._disconnect_index()

	def reload_model(self):
		'''Re-initialize the treeview model. This is called when
		reloading the index to get rid of out-of-sync model errors
		without need to close the app first.
		'''
		self.tagcloud._connect_index()
		treeview = self.treeviewwindow.get_child()
		treeview.do_set_notebook(self.ui, self.ui.notebook)


class TagsPlugin(PluginClass):

	plugin_info = {
		'name': _('Tags'), # T: plugin name
		'description': _('''\
This plugin provides a page index filtered by means of selecting tags in a cloud.
'''), # T: plugin description
		'author': 'Fabian Moser',
		'help': 'Plugins:Tags',
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
			self.sidepane_widget = TagsPluginWidget(self)
			self.ui.mainwindow.add_tab(_('Tags'), self.sidepane_widget, LEFT_PANE)
			self.sidepane_widget.show_all()


	def disconnect_embedded_widget(self):
		if not self.sidepane_widget is None:
			self.ui.mainwindow.remove(self.sidepane_widget)
			self.sidepane_widget = None

