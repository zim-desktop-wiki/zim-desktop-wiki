# -*- coding: utf-8 -*-

# Copyright 2011-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import gtk
import pango

from zim.notebook.index import Index, IndexPath, IndexTag
from zim.notebook import Path
from zim.gui.pageindex import FGCOLOR_COL, \
	EMPTY_COL, NAME_COL, PATH_COL, STYLE_COL
	# Explicitly don't import * from pageindex, make clear what we re-use
from zim.config import ConfigDict
from zim.plugins.tags import *


class TestTaggedPageTreeStore(tests.TestCase):

	def setUp(self):
		self.storeclass = TaggedPageTreeStore
		self.viewclass = TagsPageTreeView
		self.notebook = tests.new_notebook()
		self.index = self.notebook.index

	def testTreeStore(self):
		'''Test TaggedPageTreeStore index interface'''

		# Check configuration
		treestore = self.storeclass(self.index)
		self.assertEqual(treestore.get_flags(), 0)
		self.assertEqual(treestore.get_n_columns(), 8)
		for i in range(treestore.get_n_columns()):
			self.assertTrue(not treestore.get_column_type(i) is None)

		# Check top level
		n = treestore.on_iter_n_children(None) # iternal
		self.assertTrue(n > 0)
		n = treestore.iter_n_children(None) # external
		self.assertTrue(n > 0)

		# Quick check for basic methods
		iter = treestore.on_get_iter((0,))
		if self.storeclass is TaggedPageTreeStore:
			self.assertIsInstance(iter, IndexPath)
			self.assertFalse(iter.isroot)
		else:
			self.assertIsInstance(iter, IndexTag)

		self.assertEqual(iter.treepath, (0,))
		self.assertEqual(treestore.on_get_path(iter), (0,))
		self.assertEqual(treestore.get_treepath(iter), (0,))

		basename = treestore.on_get_value(iter, 0)
		self.assertTrue(len(basename) > 0)

		iter2 = treestore.on_iter_children(None)
		if self.storeclass is TaggedPageTreeStore:
			self.assertIsInstance(iter, IndexPath)
		else:
			self.assertIsInstance(iter, IndexTag)

		self.assertTrue(treestore.on_get_iter((20,20,20,20,20)) is None)
		self.assertTrue(treestore.get_treepath(Path('nonexisting')) is None)
		self.assertRaises(ValueError, treestore.get_treepath, Path(':'))

		# Now walk through the whole tree testing the API
		nitems = 0
		path = (0,)
		prevpath = None
		while path:
			#~ print 'PATH', path
			assert path != prevpath, 'Prevent infinite loop'
			nitems += 1
			prevpath = path

			iter = treestore.get_iter(path)
			self.assertEqual(treestore.get_path(iter), tuple(path))

			rawiter = treestore.on_get_iter(path)
			if isinstance(rawiter, IndexPath):
				self._check_indexpath_iter(treestore, iter, path)
			elif isinstance(rawiter, IndexTag):
				self._check_indextag_iter(treestore, iter, path)
			else:
				assert False, 'Huh!?'

			# Determine how to continue
			if treestore.iter_has_child(iter):
				path = path + (0,)
			else:
				path = path[:-1] + (path[-1]+1,) # increase last member
				while path:
					try:
						treestore.get_iter(path)
					except ValueError:
						path = path[:-1]
						if len(path):
							path = path[:-1] + (path[-1]+1,) # increase last member
					else:
						break

		self.assertTrue(nitems > 10) # double check sanity of loop

	def testTreeView(self):
		ui = MockUI()
		ui.notebook = self.notebook
		ui.page = Path('roundtrip')
		self.assertTrue(self.notebook.get_page(ui.page).exists())

		self.index.flush() # we want to index ourselves
		treestore = self.storeclass(self.index)
		treeview = self.viewclass(ui, treestore)

		# Process signals on by one
		self.assertEqual(self.notebook.pages.n_all_pages(), 0) # assert we start blank
		for p in self.index.update_iter():
			tests.gtk_process_events()
		tests.gtk_process_events()

		# Try some TreeView methods
		path = Path('roundtrip')
		self.assertTrue(treeview.set_current_page(path))
		# TODO assert something
		treepath = treeview.get_model().get_treepath(path)
		self.assertTrue(not treepath is None)
		col = treeview.get_column(0)
		treeview.row_activated(treepath, col)

		#~ treeview.emit('popup-menu')
		treeview.emit('insert-link', path)
		treeview.emit('copy')

		# Check signals for page change
		page = self.notebook.get_page(Path('Foo'))

		page.parse('wiki', 'Fooo @tag1 @tag2\n')
		self.notebook.store_page(page)
		tests.gtk_process_events()

		page.parse('wiki', 'Fooo @foo @bar @tag2\n')
		self.notebook.store_page(page)
		tests.gtk_process_events()

		# Check if all the signals go OK in delete
		for page in reversed(list(self.notebook.pages.walk())): # delete bottom up
			self.notebook.delete_page(page)
			tests.gtk_process_events()

	def _check_indexpath_iter(self, treestore, iter, path):
		# checks specific for nodes that map to IndexPath object
		indexpath = treestore.get_indexpath(iter)
		self.assertTrue(path in treestore.get_treepaths(indexpath))

		page = self.notebook.get_page(indexpath)
		self.assertIn(treestore.get_value(iter, NAME_COL), (page.basename, page.name))
		self.assertEqual(treestore.get_value(iter, PATH_COL), page)
		if page.hascontent or page.haschildren:
			self.assertEqual(treestore.get_value(iter, EMPTY_COL), False)
			self.assertEqual(treestore.get_value(iter, STYLE_COL), pango.STYLE_NORMAL)
			self.assertEqual(treestore.get_value(iter, FGCOLOR_COL), treestore.NORMAL_COLOR)
		else:
			self.assertEqual(treestore.get_value(iter, EMPTY_COL), True)
			self.assertEqual(treestore.get_value(iter, STYLE_COL), pango.STYLE_ITALIC)
			self.assertEqual(treestore.get_value(iter, FGCOLOR_COL), treestore.EMPTY_COLOR)

		self._check_iter_children(treestore, iter, path, indexpath.haschildren)

	def _check_indextag_iter(self, treestore, iter, path):
		# checks specific for nodes that map to IndexTag object
		self.assertTrue(treestore.get_indexpath(iter) is None)

		indextag = treestore.get_indextag(iter)
		self.assertTrue(path in treestore.get_treepaths(indextag))

		self.assertEqual(treestore.get_value(iter, NAME_COL), indextag.name)
		self.assertEqual(treestore.get_value(iter, PATH_COL), indextag)
		self.assertEqual(treestore.get_value(iter, EMPTY_COL), False)
		self.assertEqual(treestore.get_value(iter, STYLE_COL), pango.STYLE_NORMAL)
		self.assertEqual(treestore.get_value(iter, FGCOLOR_COL), treestore.NORMAL_COLOR)

		tags = TagsView.new_from_index(self.index)
		haschildren = tags.n_list_pages(indextag) > 0
		self._check_iter_children(treestore, iter, path, haschildren)

	def _check_iter_children(self, treestore, iter, path, haschildren):
		# Check API for children is consistent
		if haschildren:
			self.assertTrue(treestore.iter_has_child(iter))
			child = treestore.iter_children(iter)
			self.assertTrue(not child is None)
			child = treestore.iter_nth_child(iter, 0)
			self.assertTrue(not child is None)
			parent = treestore.iter_parent(child)
			self.assertEqual(treestore.get_path(parent), path)
			childpath = treestore.get_path(child)
			self.assertEqual(
				childpath, tuple(path) + (0,))
			n = treestore.iter_n_children(iter)
			for i in range(1, n):
				child = treestore.iter_next(child)
				childpath = treestore.get_path(child)
				self.assertEqual(
					childpath, tuple(path) + (i,))
			child = treestore.iter_next(child)
			self.assertTrue(child is None)
		else:
			self.assertTrue(not treestore.iter_has_child(iter))
			child = treestore.iter_children(iter)
			self.assertTrue(child is None)
			child = treestore.iter_nth_child(iter, 0)
			self.assertTrue(child is None)


@tests.slowTest
class TestTagsPageTreeStore(TestTaggedPageTreeStore):

	def setUp(self):
		TestTaggedPageTreeStore.setUp(self)
		self.storeclass = TagsPageTreeStore
		self.viewclass = TagsPageTreeView


@tests.slowTest
class TestTagPluginWidget(tests.TestCase):

	def runTest(self):
		ui = MockUI()
		ui.notebook = tests.new_notebook()
		uistate = ConfigDict()
		widget = TagsPluginWidget(ui.notebook.index, uistate, ui)

		# Excersize all model switches and check we still have a sane state
		widget.toggle_treeview()
		widget.toggle_treeview()

		path = Path('Test:foo')
		treepath = widget.treeview.get_model().get_treepath(path)
		self.assertTrue(not treepath is None)

		widget.disconnect_model()
		widget.reload_model()

		path = Path('Test:foo')
		treepath = widget.treeview.get_model().get_treepath(path)
		self.assertTrue(not treepath is None)

		# Check signals
		widget.treeview.emit('populate-popup', gtk.Menu())
		widget.treeview.emit('insert-link', path)

		# Toggles in popup
		widget.toggle_show_full_page_name()
		widget.toggle_show_full_page_name()

		# Check tag filtering
		cloud = widget.tagcloud
		self.assertEqual(cloud.get_tag_filter(), None)
		tag = None
		for button in cloud.get_children():
			if button.indextag.name == 'tags':
				tag = button.indextag
				button.clicked()
				break
		else:
			raise AssertionError, 'No button for @tags ?'

		selected, filtered = cloud.get_tag_filter()
		self.assertEqual(selected, [tag])
		self.assertTrue(len(filtered) > 3)
		self.assertTrue(tag in filtered)

		self.assertTrue(not widget.treeview._tag_filter is None)

		# check menu and sorting of tag cloud
		cloud.emit('populate-popup', gtk.Menu())
		mockaction = tests.MockObject()
		mockaction.get_active = lambda : True
		cloud._switch_sorting(mockaction)
		mockaction.get_active = lambda : False
		cloud._switch_sorting(mockaction)

		# check filtering in treestore
		tagfilter = (selected, filtered)
		selected = frozenset(selected)
		filtered = frozenset(filtered)

		def toplevel(model):
			iter = model.get_iter_first()
			assert not iter is None
			while not iter is None:
				yield iter
				iter = model.iter_next(iter)

		def childiter(model, iter):
			iter = model.iter_children(iter)
			assert not iter is None
			while not iter is None:
				yield iter
				iter = model.iter_next(iter)

		self.assertEqual(uistate['treeview'], 'tagged')
		filteredmodel = widget.treeview.get_model()
		for iter in toplevel(filteredmodel):
			path = filteredmodel.get_indexpath(iter)
			self.assertTrue(not path is None)
			tags = list(ui.notebook.tags.list_tags(path))
			tags = frozenset(tags)
			self.assertTrue(selected.issubset(tags)) # Needs to contains selected tags
			self.assertTrue(tags.issubset(filtered)) # All other tags should be in the filter selection
			treepaths = filteredmodel.get_treepaths(path)
			self.assertTrue(filteredmodel.get_path(iter) in treepaths)

		widget.toggle_treeview()
		self.assertEqual(uistate['treeview'], 'tags')
		filteredmodel = widget.treeview.get_model()
		for iter in toplevel(filteredmodel):
			self.assertEqual(filteredmodel.get_indexpath(iter), None)
				# toplevel has tags, not pages
			tag = filteredmodel[iter][PATH_COL]
			self.assertTrue(tag in filtered)
			for iter in childiter(filteredmodel, iter):
				path = filteredmodel.get_indexpath(iter)
				self.assertTrue(not path is None)
				tags = list(ui.notebook.tags.list_tags(path))
				tags = frozenset(tags)
				self.assertTrue(selected.issubset(tags)) # Needs to contains selected tags
				self.assertTrue(tags.issubset(filtered)) # All other tags should be in the filter selection
				treepaths = filteredmodel.get_treepaths(path)
				self.assertTrue(filteredmodel.get_path(iter) in treepaths)


class MockUI(tests.MockObject):

	page = None
	notebook = None
