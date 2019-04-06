
# Copyright 2011-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from gi.repository import Gtk
from gi.repository import Pango

from zim.notebook import Path
from zim.notebook.index import Index
from zim.notebook.index.tags import MyTreeIter, IS_PAGE, IS_TAG
from zim.config import ConfigDict
from zim.plugins.tags import *

from tests.pageindex import init_model_validator_wrapper


class TestTaggedPageTreeStore(tests.TestCase):

	def setUp(self):
		self.storeclass = TaggedPageTreeStore
		self.viewclass = TagsPageTreeView
		self.toplevel = IS_PAGE
		self.tags = ('foo', 'bar')
		self.notebook = self.setUpNotebook(mock=tests.MOCK_ALWAYS_MOCK, content={
			'foobar': '@foo @bar',
			'foobar:child1:subfoobar': '@foo @bar',
			'bar:foobar': '@foo @bar',

			'bar': '@bar',
			'none': 'no tag here',
			'none:child': 'or here',
			'other': '@third tag, not used in test',
		})
		# select: (@foo, @bar), sort by (basename, len(name), name)
		#
		# TaggedPageTreeStore
		# - foobar
		#   - child1
		#     - subfoobar
		# - bar:foobar
		# - foobar:child1:subfoobar

	def testTreeStore(self):
		'''Test TaggedPageTreeStore index interface'''
		notebook = self.notebook

		# Check configuration
		treestore = self.storeclass(notebook.index, self.tags)
		init_model_validator_wrapper(self, treestore)
		self.assertEqual(treestore.get_flags(), 0)
		self.assertEqual(treestore.get_n_columns(), 7)
		for i in range(treestore.get_n_columns()):
			self.assertTrue(not treestore.get_column_type(i) is None)

		# Check top level
		n = treestore.on_iter_n_children(None) # iternal
		self.assertTrue(n > 0)
		n = treestore.iter_n_children(None) # external
		self.assertTrue(n > 0)

		# Quick check for basic methods
		myiter = treestore.on_get_iter((0,))
		self.assertIsInstance(myiter, MyTreeIter)
		self.assertEqual(myiter.hint, self.toplevel)
		self.assertEqual(myiter.treepath, Gtk.TreePath((0,)))
		self.assertEqual(treestore.on_get_path(myiter), Gtk.TreePath((0,)))

		treeiter = treestore.get_iter((0,))
		path = treestore.get_indexpath(treeiter)
		self.assertEqual(treestore.find(path), Gtk.TreePath((0,)))

		basename = treestore.on_get_value(myiter, 0)
		self.assertTrue(len(basename) > 0)

		iter2 = treestore.on_iter_children(None)
		self.assertEqual(iter2.treepath, Gtk.TreePath((0,)))

		self.assertTrue(treestore.on_get_iter((20, 20, 20, 20, 20)) is None)
		self.assertRaises(IndexNotFoundError, treestore.find, Path('nonexisting'))
		self.assertRaises(ValueError, treestore.find, Path(':'))

		# Now walk through the whole tree testing the API
		nitems = 0
		path = (0,)
		prevpath = None
		while path:
			#~ print('PATH', path)
			assert path != prevpath, 'Prevent infinite loop'
			nitems += 1
			prevpath = path

			iter = treestore.get_iter(path)
			self.assertEqual(treestore.get_path(iter), Gtk.TreePath(path))

			# Determine how to continue
			if treestore.iter_has_child(iter):
				path = path + (0,)
			else:
				path = path[:-1] + (path[-1] + 1,) # increase last member
				while path:
					try:
						treestore.get_iter(path)
					except ValueError:
						path = path[:-1]
						if len(path):
							path = path[:-1] + (path[-1] + 1,) # increase last member
					else:
						break


	def testTreeView(self):
		self.notebook.index.flush() # we want to index ourselves
		navigation = tests.MockObject()
		treestore = self.storeclass(self.notebook.index, self.tags)
		init_model_validator_wrapper(self, treestore)
		treeview = self.viewclass(self.notebook, navigation, treestore)

		# Process signals on by one
		self.assertEqual(self.notebook.pages.n_all_pages(), 0) # assert we start blank
		for p in self.notebook.index.update_iter():
			tests.gtk_process_events()
		tests.gtk_process_events()

		# Try some TreeView methods
		path = Path('foobar')
		treepath = treeview.get_model().find(path)
		self.assertEqual(treeview.set_current_page(path), treepath)
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

	def testSignals(self):
		PAGES = ('a', 'a:a', 'a:b', 'b', 'c')
		TAGS = ('@foo @bar', '', '@foo @bar', '@foo @bar', '@bar')

		#  - a
		#    - a:a
		#    - a:b
		#  - b
		#  - a:b

		notebook = self.setUpNotebook()
		navigation = tests.MockObject()
		model = self.storeclass(notebook.index, ('foo', 'bar'))
		init_model_validator_wrapper(self, model)
		treeview = PageTreeView(notebook, navigation, model=model)

		signals = []
		def signal_logger(o, *a):
			path = a[0].to_string()
			signal = a[-1]
			signals.append((signal, path))
			#print(">>>", signal, path)

		for signal in ('row-inserted', 'row-changed', 'row-deleted', 'row-has-child-toggled'):
			model.connect(signal, signal_logger, signal)

		for path, tags in zip(PAGES, TAGS):
			page = notebook.get_page(Path(path))
			page.parse('wiki', 'Test 123 %s\n' % tags)
			notebook.store_page(page)

		expect_add = [
			('row-inserted', '0'),
			('row-changed', '0'),

			('row-inserted', '0:0'),
			('row-has-child-toggled', '0'),
			('row-changed', '0'),
			('row-changed', '0:0'),

			('row-inserted', '0:1'),
			('row-changed', '0'),

			('row-inserted', '1'),
			('row-changed', '0:1'),
			('row-changed', '1'),

			('row-inserted', '1'),
			('row-changed', '1'),
		]
		self.assertEqual(signals, expect_add)
		signals[:] = []

		for path in reversed(PAGES):
			notebook.delete_page(Path(path))

		expect_del = [
			('row-deleted', '1'),

			('row-deleted', '1'),

			('row-deleted', '0:1'),
			('row-changed', '0'),

			('row-deleted', '0:0'),
			('row-has-child-toggled', '0'),
			('row-changed', '0'),

			('row-deleted', '0'),
		]
		self.assertEqual(signals, expect_del)


@tests.slowTest
class TestTagsPageTreeStore(TestTaggedPageTreeStore):

	def setUp(self):
		self.storeclass = TagsPageTreeStore
		self.viewclass = TagsPageTreeView
		self.toplevel = IS_TAG
		self.tags = ('foo', 'bar')
		self.notebook = self.setUpNotebook(mock=tests.MOCK_ALWAYS_MOCK, content={
			'foo': '@foo',
			'bar': '@bar',
			'foobar': '@foo @bar',
			'foo:child1:subfoo': '@foo',

			'none': 'no tag here',
			'none:child': 'or here',
			'other': '@third tag, not used in test',
		})
		# select: (@foo, @bar)
		#
		# TagsPageTreeStore
		# @bar
		#   - bar
		#   - foobar
		# @foo
		#   - foo
		#     - child1
		#       - subfoo
		#   - foobar
		#   - foo:child1:subfoo


	def testSignals(self):
		PAGES = ('a', 'a:a', 'a:b', 'b', 'c')
		TAGS = ('@foo', '', '@foo @bar', '@foo', '@bar')
		#
		# @bar
		#  - a:b
		#  - c
		# @foo
		#  - a
		#    - a:a
		#    - a:b
		#  - b
		#  - a:b

		notebook = self.setUpNotebook()
		navigation = tests.MockObject()
		model = self.storeclass(notebook.index, ('foo', 'bar'))
		init_model_validator_wrapper(self, model)
		treeview = PageTreeView(notebook, navigation, model=model)

		signals = []
		def signal_logger(o, *a):
			path = a[0].to_string()
			signal = a[-1]
			signals.append((signal, path))
			#print(">>>", signal, path)

		for signal in ('row-inserted', 'row-changed', 'row-deleted', 'row-has-child-toggled'):
			model.connect(signal, signal_logger, signal)

		for path, tags in zip(PAGES, TAGS):
			page = notebook.get_page(Path(path))
			page.parse('wiki', 'Test 123 %s\n' % tags)
			notebook.store_page(page)

		expect_add = [
			('row-inserted', '0'), # @foo

			('row-inserted', '0:0'), # @foo a
			('row-has-child-toggled', '0'),
			('row-changed', '0'),
			('row-changed', '0:0'),

			('row-inserted', '0:0:0'), # @foo a:a
			('row-has-child-toggled', '0:0'),
			('row-changed', '0:0'),
			('row-changed', '0:0:0'),

			('row-inserted', '0:0:1'), # @foo a:b
			('row-changed', '0:0'),
			('row-inserted', '0:1'), # @foo a:b
			('row-changed', '0'),
			('row-inserted', '0'), # @bar
			('row-inserted', '0:0'), # @bar a:b
			('row-has-child-toggled', '0'),
			('row-changed', '0'),
			('row-changed', '0:0'),
			('row-changed', '1:0:1'),
			('row-changed', '1:1'),

			('row-inserted', '1:1'), # @foo b
			('row-changed', '1'),
			('row-changed', '1:1'),

			('row-inserted', '0:1'), # @bar c
			('row-changed', '0'),
			('row-changed', '0:1'),
		]
		self.assertEqual(signals, expect_add)
		signals[:] = []

		for path in reversed(PAGES):
			notebook.delete_page(Path(path))

		expect_del = [
			('row-deleted', '0:1'), # @bar c
			('row-changed', '0'),

			('row-deleted', '1:1'), # @foo b
			('row-changed', '1'),

			('row-deleted', '0:0'), # @bar a:b --> @bar
			('row-changed', '0'),
			('row-deleted', '0'),

			('row-deleted', '0:1'), # @foo a:b
			('row-changed', '0'),

			('row-deleted', '0:0:1'), # @foo a:b
			('row-changed', '0:0'),

			('row-deleted', '0:0:0'), # @foo a:a
			('row-has-child-toggled', '0:0'),
			('row-changed', '0:0'),

			('row-deleted', '0:0'), # @foo a --> @foo
			('row-changed', '0'),
			('row-deleted', '0'),

		]
		self.assertEqual(signals, expect_del)


@tests.slowTest
class TestTagPluginWidget(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		navigation = tests.MockObject()
		uistate = ConfigDict()
		widget = TagsPluginWidget(notebook, navigation, uistate)

		# Excersize all model switches and check we still have a sane state
		widget.toggle_treeview()
		widget.toggle_treeview()

		path = Path('Test:tags')
		notebook.pages.lookup_by_pagename(path)
		treepath = widget.treeview.get_model().find(path)

		widget.disconnect_model()
		widget.reconnect_model()

		path = Path('Test:tags')
		treepath = widget.treeview.get_model().find(path)

		# Check signals
		widget.treeview.emit('populate-popup', Gtk.Menu())
		widget.treeview.emit('insert-link', path)

		# Toggles in popup
		widget.toggle_show_full_page_name()
		widget.toggle_show_full_page_name()

		# Check tag filtering
		cloud = widget.tagcloud
		self.assertFalse(cloud.get_tag_filter())
		tag = None
		for button in cloud.get_children():
			if button.indextag.name == 'tags':
				tag = button.indextag
				button.clicked()
				break
		else:
			raise AssertionError('No button for @tags ?')

		selected = cloud.get_tag_filter()
		self.assertEqual(selected, [tag])
		model = widget.treeview.get_model()
		self.assertIsInstance(model, TaggedPageTreeStore)
		self.assertEqual(model.tags, (tag.name,))

		# check menu and sorting of tag cloud
		cloud.emit('populate-popup', Gtk.Menu())
		mockaction = tests.MockObject()
		mockaction.get_active = lambda: True
		cloud._switch_sorting(mockaction)
		mockaction.get_active = lambda: False
		cloud._switch_sorting(mockaction)
