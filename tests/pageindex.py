# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import gtk
import pango

import os

from zim.fs import Dir
from zim.notebook import Path
from zim.notebook.index import IndexPath
from zim.formats import ParseTree
from zim.gui.clipboard import Clipboard
from zim.gui.pageindex import *


class TestPageTreeStore(tests.TestCase):

	def testAPI(self):
		'''Test PageTreeStore index interface'''
		# This is one big test instead of seperate sub tests because in the
		# subclass we generate a file based notebook in setUp, and we do not
		# want to do that many times.
		# Hooking up the treeview as well just to see if we get any errors
		# From the order the signals are generated.

		notebook = tests.new_notebook()

		ui = MockUI()
		ui.notebook = notebook
		ui.page = Path('Test:foo')
		self.assertTrue(notebook.get_page(ui.page).exists())

		treestore = PageTreeStore(notebook.index)
		self.assertEqual(treestore.get_flags(), 0)
		self.assertEqual(treestore.get_n_columns(), 8)

		treeview = PageTreeView(ui) # just run hidden to check errors
		treeview.set_model(treestore)

		# Now start from scratch and fill the view
		notebook.index.flush()
		try:
			for i in notebook.index.update_iter():
				tests.gtk_process_events()
		finally:
			tests.gtk_process_events()

		n = treestore.on_iter_n_children(None)
		self.assertTrue(n > 0)
		n = treestore.iter_n_children(None)
		self.assertTrue(n > 0)

		for i in range(treestore.get_n_columns()):
			self.assertTrue(not treestore.get_column_type(i) is None)

		# TODO - do this again with thread

		# Quick check for basic methods
		iter = treestore.on_get_iter((0,))
		self.assertTrue(isinstance(iter, IndexPath))
		self.assertFalse(iter.isroot)
		self.assertEqual(iter.treepath, (0,))
		self.assertEqual(treestore.on_get_path(iter), (0,))
		self.assertEqual(treestore.get_treepath(iter), (0,))
		self.assertEqual(treestore.get_treepath(Path(iter.name)), (0,))
		basename = treestore.on_get_value(iter, 0)
		self.assertTrue(len(basename) > 0)

		iter2 = treestore.on_iter_children(None)
		self.assertEqual(iter2, iter)

		self.assertTrue(treestore.on_get_iter((20,20,20,20,20)) is None)
		self.assertTrue(treestore.get_treepath(Path('nonexisting')) is None)
		self.assertRaises(ValueError, treestore.get_treepath, Path(':'))

		# Now walk through the whole notebook testing the API
		# with nested pages and stuff
		npages = 0
		path = []
		for page in notebook.pages.walk():
			#~ print '>>', page
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
			#~ print '>>', page, path
			iter = treestore.get_iter(tuple(path))
			indexpath = treestore.get_indexpath(iter)
			#~ print '>>>', indexpath
			self.assertEqual(indexpath, page)
			self.assertEqual(treestore.get_value(iter, NAME_COL), page.basename)
			self.assertEqual(treestore.get_value(iter, PATH_COL), page)
			if page.hascontent or page.haschildren:
				self.assertEqual(treestore.get_value(iter, EMPTY_COL), False)
				self.assertEqual(treestore.get_value(iter, STYLE_COL), pango.STYLE_NORMAL)
				self.assertEqual(treestore.get_value(iter, FGCOLOR_COL), treestore.NORMAL_COLOR)
			else:
				self.assertEqual(treestore.get_value(iter, EMPTY_COL), True)
				self.assertEqual(treestore.get_value(iter, STYLE_COL), pango.STYLE_ITALIC)
				self.assertEqual(treestore.get_value(iter, FGCOLOR_COL), treestore.EMPTY_COLOR)
			self.assertEqual(treestore.get_path(iter), tuple(path))
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

		self.assertTrue(npages > 10) # double check sanity of walk() method

		# Try some TreeView methods
		path = Path('Test:foo')
		treeview.set_current_page(path)
		# TODO assert something
		treepath = treeview.get_model().get_treepath(path)
		self.assertTrue(not treepath is None)
		col = treeview.get_column(0)
		treeview.row_activated(treepath, col)

		#~ treeview.emit('popup-menu')
		treeview.emit('insert-link', path)
		treeview.emit('copy')

		# Check if all the signals go OK in delete
		try:
			for page in reversed(list(notebook.pages.walk())): # delete bottom up
				notebook.delete_page(page)
				tests.gtk_process_events()
		finally:
			tests.gtk_process_events()

	def testThreading(self):
		notebook = tests.new_notebook()

		notebook.index.flush()
		treestore = PageTreeStore(notebook.index)
		notebook.index.start_update()
		while notebook.index.wait_for_update(timeout=0.01):
			tests.gtk_process_events()
		else:
			tests.gtk_process_events()


class TestPageTreeView(tests.TestCase):

	# This class is intended for testing the widget user interaction,
	# interaction with the store is already tested by having the
	# view attached in TestPageTreeStore

	def setUp(self):
		self.ui = tests.MockObject()
		self.ui.page = Path('Test')
		self.notebook = tests.new_notebook()
		self.ui.notebook = self.notebook
		self.model = PageTreeStore(self.notebook.index)
		self.treeview = PageTreeView(self.ui, self.model)
		treepath = self.treeview.set_current_page(Path('Test'))
		assert treepath is not None
		self.treeview.select_treepath(treepath)

	def testContextMenu(self):
		menu = self.treeview.get_popup()

		# Check these do not cause errors - how to verify state ?
		tests.gtk_activate_menu_item(menu, _("Expand _All"))
		tests.gtk_activate_menu_item(menu, _("_Collapse All"))

		# Copy item
		tests.gtk_activate_menu_item(menu, 'gtk-copy')
		self.assertEqual(Clipboard.get_text(), 'Test')

	# Single click navigation, ... ?


class MockUI(tests.MockObject):

	page = None
	notebook = None
