# -*- coding: utf-8 -*-

# Copyright 2010 Fabian Moser
# Copyright 2011-2015 Jaap Karssenberg


import gobject
import gtk
import pango

import logging

from zim.plugins import PluginClass, extends, WindowExtension
#~ PageTreeIter
from zim.gui.pageindex import PageTreeStore, PageTreeView, \
	NAME_COL, PATH_COL, EMPTY_COL, STYLE_COL, FGCOLOR_COL, WEIGHT_COL, N_CHILD_COL, TIP_COL
from zim.notebook import Path
from zim.notebook.index import IndexPath, IndexTag, IndexNotFoundError
from zim.notebook.index.pages import \
	get_indexpath_for_treepath_flatlist_factory, get_treepaths_for_indexpath_flatlist_factory
from zim.notebook.index.tags import \
	TagsView, \
	get_indexpath_for_treepath_tagged_factory, get_treepaths_for_indexpath_tagged_factory
from zim.gui.widgets import LEFT_PANE, PANE_POSITIONS, populate_popup_add_separator, ScrolledWindow, encode_markup_text
from zim.gui.clipboard import pack_urilist, INTERNAL_PAGELIST_TARGET_NAME
from zim.signals import ConnectorMixin


logger = logging.getLogger('zim.plugins.tags')



class TagsPlugin(PluginClass):

	plugin_info = {
		'name': _('Tags'), # T: plugin name
		'description': _('''\
This plugin provides a page index filtered by means of selecting tags in a cloud.
'''), # T: plugin description
		'author': 'Fabian Moser',
		'help': 'Plugins:Tags',
	}

	plugin_preferences = (
		# key, type, label, default
		('pane', 'choice', _('Position in the window'), LEFT_PANE, PANE_POSITIONS),
			# T: option for plugin preferences
	)


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)

		self.widget = TagsPluginWidget(self.window.ui.notebook.index, self.uistate, self.window.ui) # XXX

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

		self.uistate.setdefault('vpane_pos', 150)
		self.widget.set_position(self.uistate['vpane_pos'])
		def update_uistate(*a):
			self.uistate['vpane_pos'] = self.widget.get_position()
		self.widget.connect('notify::position', update_uistate)

	def on_preferences_changed(self, preferences):
		if self.widget is None:
			return

		try:
			self.window.remove(self.widget)
		except ValueError:
			pass
		self.window.add_tab(_('Tags'), self.widget, preferences['pane'])
		self.widget.show_all()

	def teardown(self):
		self.window.remove(self.widget)
		self.widget.disconnect_all()
		self.widget = None


class TagsPluginWidget(ConnectorMixin, gtk.VPaned):
	'''Widget combining a tag cloud and a tag based page treeview'''

	def __init__(self, index, uistate, ui): # XXX
		gtk.VPaned.__init__(self)
		self.index = index
		self.uistate = uistate

		self.uistate.setdefault('treeview', 'tagged', set(['tagged', 'tags']))
		self.uistate.setdefault('tagcloud_sorting', 'score', set(['alpha', 'score']))
		self.uistate.setdefault('show_full_page_name', True)

		self.tagcloud = TagCloudWidget(self.index, sorting=self.uistate['tagcloud_sorting'])
		self.pack1(ScrolledWindow(self.tagcloud), shrink=False)

		self.treeview = TagsPageTreeView(ui) # XXX
		self._treeview_mode = (None, None)
		self.pack2(ScrolledWindow(self.treeview), shrink=False)

		self.treeview.connect('populate-popup', self.on_populate_popup)
		self.tagcloud.connect('selection-changed', self.on_cloud_selection_changed)
		self.tagcloud.connect('sorting-changed', self.on_cloud_sortin_changed)

		self.connectto_all(ui, ( # XXX
			'open-page',
			('start-index-update', lambda o: self.disconnect_model()),
			('end-index-update', lambda o: self.reload_model()),
		))

		self.reload_model()

	def on_open_page(self, ui, page, path):
		expand = True
		treepath = self.treeview.set_current_page(path, vivificate=True)
		expand = ui.notebook.namespace_properties[path.name].get('auto_expand_in_index', True)
		if treepath and expand:
			# change selection only if necessary
			selected_path = self.treeview.get_selected_path()
			if path == selected_path:
				logger.debug('Already selected: "%s"', path)
			else:
				self.treeview.select_treepath(treepath)

	def toggle_treeview(self):
		'''Toggle the treeview type in the widget'''
		if self.uistate['treeview'] == 'tagged':
			self.uistate['treeview'] = 'tags'
		else:
			self.uistate['treeview'] = 'tagged'

		self.reload_model()

	def toggle_show_full_page_name(self):
		self.uistate['show_full_page_name'] = not self.uistate['show_full_page_name']
		self.reload_model()

	def on_populate_popup(self, treeview, menu):
		# If not a not a page (but e.g. a tag), remove page action
		if not treeview.get_selected_path():
			for item in menu.get_children():
				menu.remove(item)

		# Add a popup menu item to switch the treeview mode
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.CheckMenuItem(_('Show full page name')) # T: menu option
		item.set_active(self.uistate['show_full_page_name'])
		item.connect_object('toggled', self.__class__.toggle_show_full_page_name, self)
		menu.prepend(item)

		item = gtk.CheckMenuItem(_('Sort pages by tags')) # T: menu option
		item.set_active(self.uistate['treeview'] == 'tags')
		item.connect_object('toggled', self.__class__.toggle_treeview, self)
		menu.prepend(item)

		menu.show_all()

	def on_cloud_selection_changed(self, cloud):
		filter = cloud.get_tag_filter()
		type, was_filtered = self._treeview_mode
		is_filtered = (filter is not None)
		if type == 'tagged' and was_filtered != is_filtered:
			# Switch between tag view and normal index or vice versa
			self._reload_model(type, filter)
		else:
			self.treeview.set_tag_filter(filter)

	def on_cloud_sortin_changed(self, cloud, sorting):
		self.uistate['tagcloud_sorting'] = sorting

	def disconnect_model(self):
		'''Stop the model from listening to the index. Used to
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
		assert self.uistate['treeview'] in ('tagged', 'tags')

		if self.tagcloud.index is None:
			self.tagcloud.set_index(self.index)

		type = self.uistate['treeview']
		filter = self.tagcloud.get_tag_filter()
		self._reload_model(type, filter)

	def _reload_model(self, type, filter):
		if type == 'tagged':
			if filter is None:
				model = DuplicatePageTreeStore(self.index)
					# show the normal index in this case
			else:
				model = TaggedPageTreeStore(self.index, self.uistate['show_full_page_name'])
		elif type == 'tags':
			model = TagsPageTreeStore(self.index, self.uistate['show_full_page_name'])
		else:
			assert False

		is_filtered = (filter is not None)
		self._treeview_mode = (type, is_filtered)
		self.treeview.set_model(model, filter)


class DuplicatePageTreeStore(PageTreeStore):
	'''Sub-class of PageTreeStore that allows for the same page appearing
	multiple times in the tree.
	'''

	def set_current_page(self, path):
		'''Since there may be duplicates of each page, highlight all of them'''
		oldpath = self.current_page
		self.current_page = path

		for mypath in (oldpath, path):
			if mypath:
				for treepath in self.get_treepaths(mypath):
					if treepath:
						treeiter = self.get_iter(treepath)
						self.emit('row-changed', treepath, treeiter)

	def get_treepath(self, path):
		# Just returns the first treepath matching notebook path
		if isinstance(path, IndexPath) and path.isroot:
			raise ValueError
		elif isinstance(path, (IndexTag, IndexPath)) \
		and hasattr(path, 'treepath'):
			return path.treepath
		else:
			treepaths = self.get_treepaths(path)
			if treepaths:
				return treepaths[0]
			else:
				return None

	def get_treepaths(self, path):
		'''Return all treepaths matching notebook path 'path'
		Default implementation assumes we are a non-duplicate treeview
		after all and uses L{PageTreeStore.get_treepath()}.
		@implementation: must be overloaded by subclasses that are real
		duplicate stores
		'''
		return [PageTreeStore.get_treepath(self, path)]


class TagsPageTreeStore(DuplicatePageTreeStore):
	'''Subclass of the PageTreeStore that shows tags as the top level
	for sub-sets of the page tree.
	'''

	filter_depth = 2 # tag filter applies to top two levels

	def __init__(self, index, show_full_page_name=True):
		PageTreeStore.__init__(self, index)
		self.show_full_page_name = show_full_page_name
		self._tags = TagsView.new_from_index(index)

	def _connect(self):
		self._get_indexpath_for_treepath = \
			get_indexpath_for_treepath_tagged_factory(self.index, self._cache)
		self._get_treepaths_for_indexpath = \
			get_treepaths_for_indexpath_tagged_factory(self.index, self._cache)

		def on_page_changed(o, path, signal):
			#~ print '!!', signal, path
			self._flush()
			treepaths = self.get_treepaths(path)
			for treepath in sorted(treepaths):
				#~ print '!!', signal, path, treepath
				try:
					treeiter = self.get_iter(treepath)
				except:
					logger.exception('BUG: Invalid treepath: %s %s %s', signal, path, treepath)
				else:
					self.emit(signal, treepath, treeiter)

		def on_page_deleted(o, path):
			#~ print '!! page delete', path
			treepaths = self.get_treepaths(path)
			for treepath in sorted(treepaths):
				self.emit('row-deleted', treepath)
			self._flush()

		def on_tag_created(o, tag):
			self._flush()
			treepath = self._get_treepaths_for_indexpath(tag)[0]
			treeiter = self.get_iter(treepath)
			#~ print '!! tag created', tag, treepath
			self.row_inserted(treepath, treeiter)

		def on_tag_to_be_deleted(o, tag):
			treepath = self._get_treepaths_for_indexpath(tag)[0]
			#~ print '!! tag deleted', tag, treepath
			self.row_deleted(treepath)
			self._flush()

		def on_tag_inserted(o, tag, path):
			# Add to tag branch
			self._flush()
			tagindex = self._get_treepaths_for_indexpath(tag)[0][0]
			for treepath in self._get_treepaths_for_indexpath(path):
				if treepath[0] == tagindex \
				and len(treepath) == len(path.parts) + 1:
					treeiter = self.get_iter(treepath)
					#~ print '!! tag inserted', tag, treepath
					self.row_inserted(treepath, treeiter)

					if path.haschildren:
						self.row_has_child_toggled(treepath, treeiter)

		def on_tag_to_be_removed(o, tag, path):
			# Remove from tag branch
			tagindex = self._get_treepaths_for_indexpath(tag)[0][0]
			for treepath in self._get_treepaths_for_indexpath(path):
				if treepath[0] == tagindex \
				and len(treepath) == len(path.parts) + 1:
					self.row_deleted(treepath)
			self._flush()

		self.connectto_all(self.index, (
			('page-added', on_page_changed, 'row-inserted'),
			('page-changed', on_page_changed, 'row-changed'),
			('page-haschildren-toggled', on_page_changed, 'row-has-child-toggled'),
			('page-to-be-removed', on_page_deleted),

			('tag-created', on_tag_created),
			('tag-to-be-deleted', on_tag_to_be_deleted),
			('tag-added-to-page', on_tag_inserted),
			('tag-removed-from-page', on_tag_to_be_removed),
		))

	def get_treepaths(self, path):
		'''Convert a Zim path to tree hierarchy, in general results in multiple
		 matches
		'''
		if isinstance(path, Path):
			if path.isroot:
				raise ValueError

			if not isinstance(path, IndexPath):
				try:
					path = self._pages.lookup_by_pagename(path)
				except IndexNotFoundError:
					return None

		return self._get_treepaths_for_indexpath(path)

	def get_indexpath(self, treeiter):
		'''Returns an IndexPath for a TreeIter or None'''
		# Note that iter is TreeIter here, not PageTreeIter
		iter = self.get_user_data(treeiter)
		if isinstance(iter, IndexPath):
			return iter
		else:
			return None

	def get_indextag(self, treeiter):
		'''Returns an IndexTag for a TreeIter or None'''
		# Note that iter is TreeIter here, not PageTreeIter
		iter = self.get_user_data(treeiter)
		if isinstance(iter, IndexTag):
			return iter
		else:
			return None

	def on_iter_has_child(self, iter):
		'''Returns True if the iter has children'''
		if isinstance(iter, IndexTag):
			return self._tags.n_list_pages(iter) > 0
		else:
			return PageTreeStore.on_iter_has_child(self, iter)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of tags is given.
		'''
		if iter is None:
			return self._tags.n_list_all_tags()
		elif isinstance(iter, IndexTag):
			return self._tags.n_list_pages(iter)
		else:
			return PageTreeStore.on_iter_n_children(self, iter)

	def on_get_value(self, iter, column):
		'''Returns the data for a specific column'''
		if isinstance(iter, IndexTag):
			if column == NAME_COL:
				return iter.name
			elif column == TIP_COL:
				return encode_markup_text(iter.name)
			elif column == PATH_COL:
				return iter
			elif column == EMPTY_COL:
				return False
			elif column == STYLE_COL:
				return pango.STYLE_NORMAL
			elif column == FGCOLOR_COL:
				return self.NORMAL_COLOR
			elif column == WEIGHT_COL:
				return pango.WEIGHT_NORMAL
			elif column == N_CHILD_COL:
				return ''
		else:
			if column == NAME_COL and self.show_full_page_name:
				# Show top level pages with full contex
				# top level tree is tags, so top level pages len(path) is 2
				if len(iter.treepath) <= 2:
					return iter.name
				else:
					return iter.basename
			else:
				return PageTreeStore.on_get_value(self, iter, column)


class TaggedPageTreeStore(DuplicatePageTreeStore):
	'''
	A TreeModel that lists all Zim pages in a flat list.
	Pages with associated sub-pages still show them as sub-nodes.
	Intended to be filtered by tags.
	'''

	filter_depth = 1 # tag filter only applies to top level

	def __init__(self, index, show_full_page_name=True):
		PageTreeStore.__init__(self, index)
		self.show_full_page_name = show_full_page_name

	def _connect(self):
		self._get_indexpath_for_treepath = \
			get_indexpath_for_treepath_flatlist_factory(self.index, self._cache)
		self._get_treepaths_for_indexpath = \
			get_treepaths_for_indexpath_flatlist_factory(self.index, self._cache)

		def on_page_changed(o, path, signal):
			#~ print ">>", signal, path
			self._flush()
			treepaths = self.get_treepaths(path)
			for treepath in sorted(treepaths):
				treeiter = self.get_iter(treepath)
				self.emit(signal, treepath, treeiter)

		def on_page_deleted(o, path):
			#~ print ">> delete page", path
			treepaths = self.get_treepaths(path)
			for treepath in sorted(treepaths):
				self.emit('row-deleted', treepath)
			self._flush()

		self.connectto_all(self.index, (
			('page-added', on_page_changed, 'row-inserted'),
			('page-changed', on_page_changed, 'row-changed'),
			('page-haschildren-toggled', on_page_changed, 'row-has-child-toggled'),
			('page-to-be-removed', on_page_deleted),
		))

	def get_treepaths(self, path):
		'''
		Cached conversion of a Zim path to a node in the tree hierarchy, i.e.
		the inverse operation of _get_iter.

		@param path: Usually an IndexPath instance
		@returns: A list of tuples of ints (one page can be represented many times)
		'''
		assert isinstance(path, Path)
		if path.isroot:
			raise ValueError # There can be no tree node for the tree root
		else:
			if not isinstance(path, IndexPath):
				try:
					path = self._pages.lookup_by_pagename(path)
				except IndexNotFoundError:
					return None
			return self._get_treepaths_for_indexpath(path)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of pages in the root namespace is given.
		'''
		if iter is None:
			return self._pages.n_all_pages()
		else:
			return iter.n_children

	def on_get_value(self, iter, column):
		'''Returns the data for a specific column'''
		if column == NAME_COL and self.show_full_page_name:
			# Show top level pages with full contex
			if len(iter.treepath) == 1:
				return iter.name
			else:
				return iter.basename
		else:
			return PageTreeStore.on_get_value(self, iter, column)


class TagsPageTreeView(PageTreeView):

	def __init__(self, ui, model=None):
		PageTreeView.__init__(self, ui)
		self.set_name('zim-tags-pagelist')
		self._tag_filter = None

		if model:
			self.set_model(model)

	def set_model(self, model, filter=None):
		'''Set the model to be used'''
		# disconnect previous model
		oldmodel = self.get_model()
		if oldmodel:
			childmodel = oldmodel.get_model()
			childmodel.disconnect_index()

		# Filter is also provided here, just to make it more efficient to
		# set model and filter in one go without need for refilter
		self._set_tag_filter(filter)

		# set new model
		index = self.ui.notebook.index
		tagview = TagsView.new_from_index(index)
		def func(model, iter):
			if self._tag_filter is None:
				return True # no filtering
			else:
				iter = model.get_user_data(iter)
				if len(iter.treepath) > model.filter_depth:
					return True # deeper levels are not filtered at all
				else:
					if isinstance(iter, IndexTag):
						return iter in self._tag_filter[1] # show filtered tags
					else:
						tags = frozenset(tagview.list_tags(iter))
						return tags >= self._tag_filter[0] # match all selected tags

		filtermodel = model.filter_new(root = None)
		filtermodel.set_visible_func(func)

		# HACK add some methods and attributes
		# (can not subclass gtk.TreeModelFilter because it lacks a constructor)
		def get_indexpath(treeiter):
			childiter = filtermodel.convert_iter_to_child_iter(treeiter)
			if childiter:
				return model.get_indexpath(childiter)
			else:
				return None

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
		filtermodel.set_current_page = model.set_current_page

		PageTreeView.set_model(self, filtermodel)

	def set_tag_filter(self, filter):
		'''Sets the tags to filter on. The filter should be a tuple of
		two lists of tags, or None to not do any filtering.
		First list of tags are the tags that we filter on, so only pages
		matching all these tags should be selected.
		Second set is a superset of the first set and includes all tags
		that appear in one of the selected pages. So selecting one of these
		tags on top of the current selection should result in a subset
		of the current page selection.
		'''
		self._set_tag_filter(filter)
		model = self.get_model()
		if model:
			model.refilter()

	def _set_tag_filter(self, filter):
		if not filter:
			self._tag_filter = None
		else:
			self._tag_filter = (frozenset(filter[0]), frozenset(filter[1]))

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

	def set_current_page(self, path, vivificate=False):
		'''Set the current page in the treeview

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

		model.set_current_page(path) # highlight in model

		return treepath

# Need to register classes defining gobject signals
gobject.type_register(TagsPageTreeView)


class TagCloudItem(gtk.ToggleButton):
	'''Button item used on the tag cloud widget'''

	def __init__(self, indextag):
		gtk.ToggleButton.__init__(self, indextag.name, use_underline=False)
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


class TagCloudWidget(ConnectorMixin, gtk.TextView):
	'''Text-view based list of tags, where each tag is represented by a
	button inserted as a child in the textview.

	@signal: C{selection-changed ()}: emitted when tag selection changes
	@signal: C{sorting-changed ()}: emitted when tag sorting changes
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'selection-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		'sorting-changed': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self, index, sorting='score'):
		gtk.TextView.__init__(self, None) # Create TextBuffer implicitly
		self.set_name('zim-tags-tagcloud')
		self.index = None

		self.set_editable(False)
		self.set_cursor_visible(False)
		self.set_wrap_mode(gtk.WRAP_CHAR)

		self.set_sorting(sorting)
		self.set_index(index)

	def set_index(self, index):
		'''Connect to an Index object'''
		self.disconnect_index() # just to be sure
		self.index = index
		self.connectto_all(self.index, (
			('tag-created', self._update),
			('tag-deleted', self._update),
		))
		self._update()

	def set_sorting(self, sorting):
		self._alphabetically = (sorting == 'alpha')

	def disconnect_index(self):
		'''Stop the model from listening to the index. Used to unhook
		the model before reloading the index.
		'''
		self.disconnect_from(self.index)
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
		tagview = TagsView.new_from_index(self.index)
		selected = []
		for button in self.get_children():
			if button.get_active():
				try:
					selected.append(tagview.lookup_by_tagname(button.indextag))
				except IndexNotFoundError:
					pass
				# Need the lookup here in case the tag went missing in the
				# mean time e.g. due to editing of the page
		self._clear()

		if selected:
			tags = tagview.list_intersecting_tags(selected)
		else:
			tags = []

		if not tags:
			tags = tagview.list_all_tags_by_n_pages()
			# Can be we have a "selected", but the selected tags have
			# disappeared and thus list_intersecting returns empty

		if self._alphabetically:
			tags = sorted(tags, key=lambda t: t.name)
		# else leave sorted by score

		buffer = self.get_buffer()
		for tag in tags:
			iter = buffer.get_end_iter()
			anchor = buffer.create_child_anchor(iter)
			button = TagCloudItem(tag)
			button.set_active(tag in selected)
			button.connect("toggled", lambda b: self._update())
			self.add_child_at_anchor(button, anchor)

		self.show_all()
		self.emit('selection-changed')

	def do_populate_popup(self, menu):
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.CheckMenuItem(_('Sort alphabetically')) # T: Context menu item for tag cloud
		item.set_active(self._alphabetically)
		item.connect('toggled', self._switch_sorting)
		item.show_all()
		menu.prepend(item)

	def _switch_sorting(self, widget, *a):
		self._alphabetically = widget.get_active()
		self._update()
		if self._alphabetically:
			self.emit('sorting-changed', 'alpha')
		else:
			self.emit('sorting-changed', 'score')

# Need to register classes defining gobject signals
gobject.type_register(TagCloudWidget)



