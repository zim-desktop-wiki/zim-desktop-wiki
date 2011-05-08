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


class DuplicatePageTreeStore(PageTreeStore):
	'''Sub-class of PageTreeStore that allows for the same page appearing
	multiple times in the tree.
	'''

	def get_treepath(self, path):
		'''Just returns the first treepath matching notebook path 'path' '''
		treepaths = self.get_treepaths(path)
		if treepaths:
			return treepaths[0]
		else:
			return None

	def get_treepaths(self, path):
		'''Return all treepaths matching notebook path 'path' '''
		raise NotImplementedError


class TagsPageTreeStore(DuplicatePageTreeStore):
	'''Subclass of the PageTreeStore that shows tags as the top level
	for sub-sets of the page tree.

	A special top level item 'untagged' is created with all the
	untagged (top level) pages.
	'''

	filter_depth = 2 # tag filter applies to top two levels

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
			treepath = (self.index.get_tag_index(tag) + 1,)
			treeiter = self.get_iter(treepath)
			#~ print '!! tag created', tag, treepath
			self.row_inserted(treepath, treeiter)

		def on_tag_to_be_inserted(o, tag, path, first):
			if first and not path.namespace:
				# Remove from untagged branch
				treepath = (0, self.index.get_untagged_root_page_index(path))
				#~ print '!! removed from untagged', treepath
				self.row_deleted(treepath)
				self._flush()

		def on_tag_inserted(o, tag, path, first):
			if first and not path.namespace:
				# Finish update of untagged branch
				if not self.index.n_list_untagged_root_pages():
					treeiter = self.get_iter((0,))
					self.row_has_child_toggled((0,), treeiter)

			# Add to tag branch
			self._flush()
			tagindex = self.index.get_tag_index(tag)
			pageindex = self.index.get_tagged_page_index(tag, path)
			treepath = (tagindex + 1, pageindex)
			treeiter = self.get_iter(treepath)
			#~ print '!! tag inserted', tag, treepath
			self.row_inserted(treepath, treeiter)
			if not path.hasdata:
				path = self.index.lookup_data(path)
			if path.haschildren:
				self.row_has_child_toggled(treepath, treeiter)

		def on_tag_to_be_removed(o, tag, path, last):
			# Remove from tag branch
			tagindex = self.index.get_tag_index(tag)
			pageindex = self.index.get_tagged_page_index(tag, path)
			treepath = (tagindex + 1, pageindex)
			#~ print '!! tag removed', tag, treepath
			self.row_deleted(treepath)
			self._flush()

		def on_tag_removed(o, tag, path, last):
			if last and not path.namespace:
				# Add to untagged
				pageindex = self.index.get_untagged_root_page_index(path)
				treepath = (0, pageindex)
				treeiter = self.get_iter(treepath)
				#~ print '!! new untagged', treepath
				if self.index.n_list_untagged_root_pages() == 1:
					treeiter = self.get_iter((0,))
					self.row_has_child_toggled((0,), treeiter)
				self.row_inserted(treepath, treeiter)

		def on_tag_to_be_deleted(o, tag):
			treepath = (self.index.get_tag_index(tag) + 1,)
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
						if offset == 0:
							iter = PageTreeTagIter((0,), self.untagged)
							self._cache.setdefault((0,), iter)
						else:
							tags = self.index.list_all_tags(offset-1, limit=20)
								# offset -1 because we use 0 for untagged

							for j, path in enumerate(tags):
								childtreepath = parenttreepath + (offset + j,)
								iter = PageTreeTagIter(childtreepath, path)
								self._cache.setdefault(childtreepath, iter)
					else:
						#~ print '>>>> Load pagelist for', parent, 'offset', offset
						if isinstance(parent, IndexTag):
							if parent == self.untagged:
								pages = self.index.list_untagged_root_pages(offset, limit=20)
							else:
								pages = self.index.list_tagged_pages(parent, offset, limit=20)
						else:
							pages = self.index.list_pages(parent, offset, limit=20)

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
				return (self.index.get_tag_index(path) + 1,)
		else:
			return DuplicatePageTreeStore.get_treepath(self, path)

	def get_treepaths(self, path):
		'''Convert a Zim path to tree hierarchy, in general results in multiple
		 matches
		'''
		if isinstance(path, IndexTag):
			treepath = self.get_treepath(path)
			if treepath:
				return (treepath,)
			else:
				return ()

		if path.isroot:
			raise ValueError

		if not isinstance(path, IndexPath):
			path = self.index.lookup_path(path)
			if path is None:
				return ()

		# See if it is in cache already
		if path in self._reverse_cache:
			#~ print '>>> Return from cache', reverse_cache[path]
			return self._reverse_cache[path]

		# Try getting it while populating cache
		paths = list(path.parents())
		paths.pop() # get rid of root namespace as parent
		paths.insert(0, path)

		child = None
		childpath = () # partial treepath for child part
		treepaths = []

		for p in paths: # iter from child to parents
			if child:
				pageindex = self.index.get_page_index(child)
				childpath = (pageindex,) + childpath

			# Get tags of this path
			tags = list(self.index.list_tags(p))
			for t in tags:
				tagindex = self.index.get_tag_index(t) + 1 # +1 due to untagged
				pageindex = self.index.get_tagged_page_index(t, p)
				treepaths.append((tagindex, pageindex) + childpath)

			child = p

		root_page = paths[-1]
		try:
			pageindex = self.index.get_untagged_root_page_index(root_page)
		except ValueError:
			pass
		else:
			treepaths.append((0, pageindex) + childpath)

		treepaths.sort()
		self._reverse_cache.setdefault(path, treepaths)
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
				return self.index.n_list_untagged_root_pages() > 0
			else:
				return self.index.n_list_tagged_pages(iter.indextag) > 0
		else:
			return PageTreeStore.on_iter_has_child(self, iter)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of tags is given.
		'''
		if iter is None:
			return self.index.n_list_all_tags() + 1 # +1 to include untagged
		elif isinstance(iter, PageTreeTagIter):
			if iter.indextag == self.untagged:
				return self.index.n_list_untagged_root_pages()
			else:
				return self.index.n_list_tagged_pages(iter.indextag)
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


class TaggedPageTreeStore(DuplicatePageTreeStore):
	'''
	A TreeModel that lists all Zim pages in a flat list filtered by tags.
	Pages with	associated sub-pages still show them as sub-nodes.
	'''

	filter_depth = 1 # tag filter only applies to top level

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
						pages = self.index.list_all_pages(offset, limit = 20)
					else:
						pages = self.index.list_pages(parent, offset, limit=20)

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
				return ()

		# See if it is in cache already
		if path in self._reverse_cache:
			return self._reverse_cache[path]

		paths = [path] + list(path.parents())[:-1] # Zim paths for the path and all parents (except root)
		child = None
		childpath = ()
		treepaths = []

		for p in paths:
			if child:
				pageindex = self.index.get_page_index(child)
				childpath = (pageindex,) + childpath
			pageindex = self.index.get_all_pages_index(p)
			treepaths.append((pageindex,) + childpath)
			child = p

		treepaths.sort()
		self._reverse_cache.setdefault(path, treepaths)
		self._schedule_flush()
		return treepaths

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of pages in the root namespace is given.
		'''
		if iter is None:
			return self.index.n_list_all_pages()
		else:
			return PageTreeStore.on_iter_n_children(self, iter)


class TagsPageTreeView(PageTreeView):

	def __init__(self, ui, model=None):
		PageTreeView.__init__(self, ui)
		self.set_name('zim-tags-pagelist')
		self._tag_filter = None

		if model:
			self.set_model(model)

	def set_model(self, model):
		'''Set the model to be used'''
		# disconnect previous model
		oldmodel = self.get_model()
		if oldmodel:
			childmodel = oldmodel.get_model()
			childmodel.disconnect_index()

		# set new model
		def func(model, iter):
			index = self.ui.notebook.index
			if self._tag_filter is None:
				return True # no filtering
			else:
				iter = model.get_user_data(iter)
				if len(iter.treepath) > model.filter_depth:
					return True # deeper levels are not filtered at all
				else:
					if isinstance(iter, PageTreeTagIter): # -> tag
						return iter.indextag in self._tag_filter[1] # show filtered tags
					else: # PageTreeIter -> page
						tags = frozenset(index.list_tags(iter.indexpath))
						return tags >= self._tag_filter[0] # match all selected tags

		filtermodel = model.filter_new(root = None)
		filtermodel.set_visible_func(func)

		# HACK add some methods and attributes
		# (can not subclass gtk.TreeModelFilter because it lacks a constructor)
		def get_indexpath(treeiter):
			return model.get_indexpath(
				filtermodel.convert_iter_to_child_iter(treeiter) )

		def get_treepath(path):
			for treepath in model.get_treepaths(path):
				filtered = filtermodel.convert_child_path_to_path(treepath)
				if not filtered is None:
					return filtered
			else:
				return None

		def get_treepaths(path):
			treepaths = model.get_treepaths(path)
			if treepaths:
				treepaths = map(filtermodel.convert_child_path_to_path, treepaths)
				return tuple(t for t in treepaths if not t is None)
			else:
				return ()

		filtermodel.get_indexpath = get_indexpath
		filtermodel.get_treepath = get_treepath
		filtermodel.get_treepaths = get_treepaths
		filtermodel.index = model.index

		PageTreeView.set_model(self, filtermodel)

	def set_tag_filter(self, filter):
		'''Sets the tags to filter on. The filter should be a tuple of
		two lists of tags, or None to not do any filtering.
		'''
		if not filter:
			self._tag_filter = None
		else:
			self._tag_filter = (frozenset(filter[0]), frozenset(filter[1]))

		model = self.get_model()
		if model:
			model.refilter()

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
gobject.type_register(TagsPageTreeView)


class TagCloudItem(gtk.ToggleButton):
	'''Button item used on the tag cloud widget'''

	def __init__(self, indextag):
		gtk.ToggleButton.__init__(self, indextag.name)
		self.set_relief(gtk.RELIEF_NONE)
		self.indextag = indextag

		def update_label(self):
			# Make button text bold when active
			label = self.get_child()
			if self.get_active():
				label.set_markup('<b>'+label.get_text()+'</b>')
			else:
				label.set_text(label.get_text())
					# get_text() gives string without markup

		self.connect_after('toggled', update_label)


class TagCloudWidget(gtk.TextView):
	'''Text-view based list of tags, where each tag is represented by a
	button inserted as a child in the textview.

	Signals:
	  * selection-changed: emitted when tag selection changes
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'selection-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, index=None):
		gtk.TextView.__init__(self, None) # Create TextBuffer implicitly
		self.set_name('zim-tags-tagcloud')
		self.index = None
		self._signals = ()

		self.set_editable(False)
		self.set_cursor_visible(False)
		self.set_wrap_mode(gtk.WRAP_CHAR)

		if index:
			self.set_index(index)

	def set_index(self, index):
		'''Connect to an Index object'''
		self.disconnect_index() # just to be sure
		self.index = index
		self._signals = (
			self.index.connect('tag-created', self._update),
			self.index.connect('tag-deleted', self._update),
		)
		self._update()

	def disconnect_index(self):
		'''Stop the model from listening to the index. Used to unhook
		the model before reloading the index.
		'''
		for id in self._signals:
			self.index.disconnect(id)
		self._signals = ()
		self._clear()
		self.index = None

	def get_tag_filter(self):
		'''Returns a tuple with two lists of tags; the first gives all
		tags that are selected, the second gives all tags shown in the
		cloud. By definition the first list is a subset of the second.
		If no tags are selected returns None instead.
		'''
		selected = []
		filtered = []
		for button in self.get_children():
			filtered.append(button.indextag)
			if button.get_active():
				selected.append(button.indextag)
		if selected:
			return (selected, filtered)
		else:
			return None

	def _clear(self):
		'''Clears the cloud'''
		self.foreach(lambda b: self.remove(b))
		buffer = self.get_buffer()
		buffer.delete(*buffer.get_bounds())

	def _update(self, *a):
		'''Update the cloud to show only tags that share a set of pages
		with the selected tags.'''
		selected = [b.indextag for b in self.get_children() if b.get_active()]
		self._clear()

		buffer = self.get_buffer()
		if selected:
			tags = self.index.list_intersecting_tags(selected)
		else:
			tags = self.index.list_all_tags_by_score()

		for tag in tags:
			iter = buffer.get_end_iter()
			anchor = buffer.create_child_anchor(iter)
			button = TagCloudItem(tag)
			button.set_active(tag in selected)
			button.connect("toggled", lambda b: self._update())
			self.add_child_at_anchor(button, anchor)

		self.show_all()
		self.emit('selection-changed')

# Need to register classes defining gobject signals
gobject.type_register(TagCloudWidget)


class TagsPluginWidget(gtk.VPaned):
	'''Widget combining a tag cloud and a tag based page treeview'''

	def __init__(self, plugin):
		gtk.VPaned.__init__(self)
		self.plugin = plugin

		self.plugin.uistate.setdefault('treeview', 'tagged', set(['tagged', 'tags']))

		def add_scrolled(widget):
			sw = gtk.ScrolledWindow()
			sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
			sw.set_shadow_type(gtk.SHADOW_IN)
			sw.add(widget)
			self.add(sw)
			return sw

		self.tagcloud = TagCloudWidget()
		add_scrolled(self.tagcloud)

		self.treeview = TagsPageTreeView(self.plugin.ui)
		add_scrolled(self.treeview)

		self.treeview.connect('populate-popup', self.on_populate_popup)
		self.tagcloud.connect('selection-changed', self.on_cloud_selection_changed)

		if self.plugin.ui.notebook:
			self.reload_model()
		else:
			self.plugin.ui.connect_after('open-notebook', lambda *a: self.reload_model())

		self.plugin.ui.connect('start-index-update', lambda o: self.disconnect_model())
		self.plugin.ui.connect('end-index-update', lambda o: self.reload_model())

	def toggle_treeview(self):
		'''Toggle the treeview type in the widget'''
		if self.plugin.uistate['treeview'] == 'tagged':
			self.plugin.uistate['treeview'] = 'tags'
		else:
			self.plugin.uistate['treeview'] = 'tagged'

		self.reload_model()

	def on_populate_popup(self, treeview, menu):
		# Add a popup menu item to switch the treeview mode
		menu.prepend(gtk.SeparatorMenuItem())

		item = gtk.CheckMenuItem(_('Sort pages by tags')) # T: menu option
		item.set_active(self.plugin.uistate['treeview'] == 'tags')
		item.connect_object('toggled', self.__class__.toggle_treeview, self)
		menu.prepend(item)

		menu.show_all()

	def on_cloud_selection_changed(self, cloud):
		filter = cloud.get_tag_filter()
		self.treeview.set_tag_filter(filter)

	def disconnect_model(self):
		'''Stop the model from listening to the inxed. Used to
		unhook the model before reloading the index. Typically
		should be followed by reload_model().
		'''
		self.treeview.disconnect_index()
		self.tagcloud.disconnect_index()

	def reload_model(self):
		'''Re-initialize the treeview model. This is called when
		reloading the index to get rid of out-of-sync model errors
		without need to close the app first.
		'''
		assert self.plugin.uistate['treeview'] in ('tagged', 'tags')

		if self.tagcloud.index is None:
			self.tagcloud.set_index(self.plugin.ui.notebook.index)

		if self.plugin.uistate['treeview'] == 'tagged':
			model = TaggedPageTreeStore(self.plugin.ui.notebook.index) # FIXME clean up law of D
		else: # tags
			model = TagsPageTreeStore(self.plugin.ui.notebook.index) # FIXME clean up law of D

		self.treeview.set_model(model)


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
