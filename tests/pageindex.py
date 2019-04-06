
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from gi.repository import Gtk
from gi.repository import Pango

from zim.notebook import Path
from zim.notebook.index.pages import MyTreeIter, IndexNotFoundError
from zim.formats import ParseTree
from zim.gui.clipboard import Clipboard

from zim.plugins import find_extension, PluginManager
from zim.plugins.pageindex import *


from tests.mainwindow import setUpMainWindow


class TestPageIndexPlugin(tests.TestCase):

	def runTest(self):
		plugin = PluginManager.load_plugin('pageindex')
		window = setUpMainWindow(self.setUpNotebook())
		extension = find_extension(window.pageview, PageIndexPageViewExtension)
		self.assertIsNotNone(extension)


def init_model_validator_wrapper(test, model):

		def validate_path_iter(model, path, iter):
			assert isinstance(path, Gtk.TreePath)
			assert model.iter_is_valid(iter)

			test.assertEqual(model.get_path(iter).get_indices(), path.get_indices())

			if model.iter_has_child(iter):
				test.assertTrue(model.iter_n_children(iter) > 0)
				child = model.iter_children(iter)
				test.assertIsNotNone(child)
				childpath = model.get_path(child)
				test.assertEqual(childpath.get_indices(), path.get_indices() + [0])
			else:
				test.assertTrue(model.iter_n_children(iter) == 0)

		def validate_parent_path_iter(model, path):
			assert isinstance(path, Gtk.TreePath)
			if path.get_depth() > 1:
				parent = Gtk.TreePath(path.get_indices()[:-1])
				iter = model.get_iter(parent)
				validate_path_iter(model, parent, iter)

		for signal in ('row-inserted', 'row-changed', 'row-has-child-toggled'):
			model.connect(signal, validate_path_iter)

		for signal in ('row-deleted',):
			model.connect(signal, validate_parent_path_iter)


class TestPageTreeStore(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)

		treestore = PageTreeStore(notebook.index)
		init_model_validator_wrapper(self, treestore)
		self.assertEqual(treestore.get_flags(), 0)
		self.assertEqual(treestore.get_n_columns(), 7)
		for i in range(treestore.get_n_columns()):
			self.assertTrue(not treestore.get_column_type(i) is None)

		n = treestore.on_iter_n_children(None)
		self.assertTrue(n > 0)
		n = treestore.iter_n_children(None)
		self.assertTrue(n > 0)

		# Quick check for basic methods
		iter = treestore.on_get_iter((0,))
		self.assertTrue(isinstance(iter, MyTreeIter))
		self.assertFalse(iter.row['name'] == '')
		self.assertEqual(iter.treepath, Gtk.TreePath((0,)))
		self.assertEqual(treestore.on_get_path(iter), Gtk.TreePath((0,)))
		self.assertEqual(treestore.find(Path(iter.row['name'])), Gtk.TreePath((0,)))
		basename = treestore.on_get_value(iter, 0)
		self.assertTrue(len(basename) > 0)

		iter2 = treestore.on_iter_children(None)
		self.assertIs(iter2, iter)

		self.assertIsNone(treestore.on_get_iter((20, 20, 20, 20, 20)))
		self.assertRaises(IndexNotFoundError, treestore.find, Path('nonexisting'))
		self.assertRaises(ValueError, treestore.find, Path(':'))

		# Now walk through the whole notebook testing the API
		# with nested pages and stuff
		npages = 0
		path = []
		for page in notebook.pages.walk():
			#~ print('>>', page)
			npages += 1
			names = page.name.split(':')
			if len(names) > len(path):
				path.append(0) # always increment by one
			elif len(names) < len(path):
				while len(names) < len(path):
					path.pop()
				path[-1] += 1
			else:
				path[-1] += 1
			#~ print('>>', page, path)
			iter = treestore.get_iter(tuple(path))
			indexpath = treestore.get_indexpath(iter)
			#~ print('>>>', indexpath)
			self.assertEqual(indexpath, page)
			self.assertEqual(treestore.get_value(iter, NAME_COL), page.basename)
			self.assertEqual(treestore.get_value(iter, PATH_COL), page)
			if not treestore.get_value(iter, EXISTS_COL):
				self.assertEqual(treestore.get_value(iter, STYLE_COL), Pango.Style.ITALIC)
			else:
				self.assertEqual(treestore.get_value(iter, STYLE_COL), Pango.Style.NORMAL)
			self.assertEqual(treestore.get_path(iter), Gtk.TreePath(path))

			if indexpath.haschildren:
				self.assertTrue(treestore.iter_has_child(iter))
				child = treestore.iter_children(iter)
				self.assertTrue(not child is None)
				child = treestore.iter_nth_child(iter, 0)
				self.assertTrue(not child is None)
				parent = treestore.iter_parent(child)
				self.assertEqual(
					treestore.get_indexpath(parent), page)
				childpath = treestore.get_path(child)
				self.assertEqual(
					childpath, Gtk.TreePath(tuple(path) + (0,)))
				n = treestore.iter_n_children(iter)
				for i in range(1, n):
					child = treestore.iter_next(child)
					childpath = treestore.get_path(child)
					self.assertEqual(
						childpath, Gtk.TreePath(tuple(path) + (i,)))
				child = treestore.iter_next(child)
				self.assertIsNone(child) # children exhausted

			else:
				self.assertTrue(not treestore.iter_has_child(iter))
				child = treestore.iter_children(iter)
				self.assertTrue(child is None)
				child = treestore.iter_nth_child(iter, 0)
				self.assertTrue(child is None)

		self.assertTrue(npages > 10) # double check sanity of walk() method


class TestSignals(tests.TestCase):

	PAGES = ('a', 'a:a', 'a:b', 'b', 'c')

	def runTest(self):
		notebook = self.setUpNotebook()
		navigation = tests.MockObject()
		model = PageTreeStore(notebook.index)
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

		for path in map(Path, self.PAGES):
			page = notebook.get_page(path)
			page.parse('plain', 'Test 123\n')
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
			('row-changed', '0:1'),
			('row-inserted', '1'),
			('row-changed', '1'),
			('row-inserted', '2'),
			('row-changed', '2')
		]
		self.assertEqual(signals, expect_add)
		signals[:] = []

		for path in reversed(self.PAGES):
			notebook.delete_page(Path(path))

		expect_del = [
			('row-deleted', '2'),
			('row-deleted', '1'),
			('row-deleted', '0:1'),
			('row-changed', '0'),
			('row-deleted', '0:0'),
			('row-has-child-toggled', '0'),
			('row-changed', '0'),
			('row-deleted', '0')
		]
		self.assertEqual(signals, expect_del)


class TestPageTreeView(tests.TestCase):

	def setUp(self):
		self.notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		navigation = tests.MockObject()
		self.model = PageTreeStore(self.notebook.index)
		init_model_validator_wrapper(self, self.model)
		self.treeview = PageTreeView(self.notebook, navigation, model=self.model)
		treepath = self.treeview.set_current_page(Path('Test'))
		assert treepath is not None
		self.treeview.select_treepath(treepath)

	def testView(self):
		path = Path('Test:foo')
		self.treeview.set_current_page(path)
		# TODO assert something
		treepath = self.treeview.get_model().find(path)
		self.assertTrue(not treepath is None)
		col = self.treeview.get_column(0)
		self.treeview.row_activated(treepath, col)

		#~ self.treeview.emit('popup-menu')
		self.treeview.emit('insert-link', path)
		#self.treeview.emit('copy')

	def testContextMenuExpandCollapse(self):
		menu = self.treeview.get_popup()

		# Check these do not cause errors - how to verify state ?
		tests.gtk_activate_menu_item(menu, _("Expand _All"))
		tests.gtk_activate_menu_item(menu, _("_Collapse All"))

	#@tests.expectedFailure
	#def testContextMenuCopyLocation(self):
	#	menu = self.treeview.get_popup()
	#
	#	# Copy item
	#	tests.gtk_activate_menu_item(menu, 'gtk-copy')
	#	self.assertEqual(Clipboard.get_text(), 'Test')

	def testSignals(self):
		pages = []

		self.assertGreater(self.model.on_iter_n_children(None), 0)

		# delete all pages
		for path in list(self.notebook.pages.walk_bottomup()):
			page = self.notebook.get_page(path)
			pages.append((page.name, page.dump('wiki')))
			self.notebook.delete_page(page)

		self.assertEqual(self.notebook.pages.n_list_pages(), 0)
		self.assertEqual(self.model.on_iter_n_children(None), 0)
		# TODO: assert something on the view ?

		# and add them again
		for name, content in reversed(pages):
			page = self.notebook.get_page(Path(name))
			page.parse('wiki', content)
			self.notebook.store_page(page)

		self.assertGreater(self.model.on_iter_n_children(None), 0)
		# TODO: assert something on the view ?
