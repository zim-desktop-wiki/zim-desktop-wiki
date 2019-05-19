
# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk

import tests

from tests.mainwindow import setUpMainWindow

from zim.plugins import PluginManager
from zim.plugins.tableofcontents import *
from zim.gui.widgets import RIGHT_PANE, LEFT_PANE


@tests.slowTest
class TestTableOfContents(tests.TestCase):

	def testPageViewExtensions(self):
		plugin = PluginManager.load_plugin('tableofcontents')

		notebook = self.setUpNotebook()
		mainwindow = setUpMainWindow(notebook)

		plugin.preferences['floating'] = True

		## floating
		ext = list(plugin.extensions)
		self.assertEqual(len(ext), 1)
		self.assertIsInstance(ext[0], ToCPageViewExtension)
		self.assertIsInstance(ext[0].tocwidget, FloatingToC)

		plugin.preferences.changed() # make sure no errors are triggered
		plugin.preferences['show_h1'] = True
		plugin.preferences['show_h1'] = False
		plugin.preferences['pane'] = RIGHT_PANE
		plugin.preferences['pane'] = LEFT_PANE

		### embedded
		plugin.preferences['floating'] = False
		self.assertIsInstance(ext[0].tocwidget, SidePaneToC)

		plugin.preferences.changed() # make sure no errors are triggered
		plugin.preferences['show_h1'] = True
		plugin.preferences['show_h1'] = False
		plugin.preferences['pane'] = RIGHT_PANE
		plugin.preferences['pane'] = LEFT_PANE

		plugin.preferences['floating'] = True  # switch back

	def testToCWidget(self):
		'''Test Tabel Of Contents plugin'''
		notebook = self.setUpNotebook()
		window = setUpMainWindow(notebook)
		pageview = window.pageview

		widget = ToCWidget(pageview, ellipsis=False)

		def get_tree():
			# Count number of rows in TreeModel
			model = widget.treeview.get_model()
			rows = []
			def c(model, path, iter):
				rows.append((len(path), model[iter][TEXT_COL]))
			model.foreach(c)
			return rows

		page = notebook.get_page(Path('Test'))
		page.parse('wiki', '''\
====== Foo ======

===== bar =====

line below could be mistaken for heading of the same name..

baz

sfsfsfsd

===== baz =====

sdfsdfsd

==== A ====

==== B ====

==== C ====

===== dus =====

sdfsdf

''')
		notebook.store_page(page)
		#~ print page.get_parsetree().tostring()

		with_h1 = [
			(1, 'Foo'),
			(2, 'bar'),
			(2, 'baz'),
			(3, 'A'),
			(3, 'B'),
			(3, 'C'),
			(2, 'dus'),
		]
		without_h1 = [
			(1, 'bar'),
			(1, 'baz'),
			(2, 'A'),
			(2, 'B'),
			(2, 'C'),
			(1, 'dus'),
		]

		# Test basic usage - click some headings
		window.open_page(page)
		widget.on_page_changed(window, page)
		self.assertEqual(get_tree(), without_h1)
		widget.on_store_page(notebook, page)
		self.assertEqual(get_tree(), without_h1)

		widget.set_show_h1(True)
		self.assertEqual(get_tree(), with_h1)
		widget.set_show_h1(False)
		self.assertEqual(get_tree(), without_h1)

		column = widget.treeview.get_column(0)
		model = widget.treeview.get_model()
		def activate_row(m, path, i):
			#~ print(">>>", path)
			widget.treeview.row_activated(path, column)
				# TODO assert something here

			widget.select_section(pageview.textview.get_buffer(), path)

			menu = Gtk.Menu()
			widget.treeview.get_selection().select_path(path)
			widget.on_populate_popup(widget.treeview, menu)
				# TODO assert something here
			widget.treeview.get_selection().unselect_path(path)

		model.foreach(activate_row)

		# Test promote / demote
		pageview.set_readonly(False)
		wanted = [
			(1, 'bar'),
			(2, 'baz'),
			(3, 'A'),
			(3, 'B'),
			(3, 'C'),
			(1, 'dus'),
		]

		widget.treeview.get_selection().unselect_all()
		widget.treeview.get_selection().select_path((1,)) # "baz"
		self.assertFalse(widget.on_promote())
		self.assertTrue(widget.on_demote())
		self.assertEqual(get_tree(), wanted)

		widget.treeview.expand_all()
		widget.treeview.get_selection().unselect_all()
		widget.treeview.get_selection().select_path((0, 0)) # "baz"
		self.assertFalse(widget.on_demote())
		self.assertTrue(widget.on_promote())
		self.assertEqual(get_tree(), without_h1)

		# Test promote / demote multiple selected
		wanted = [
			(1, 'bar'),
			(2, 'baz'),	# (1,)	demote 1 -> 2
			(3, 'A'),	# (1,0) demote 2 -> 3
			(3, 'B'),	# (1,1) demote 2 -> 3
			(3, 'C'),	# (1,2)	demote 2 -> 3
			(2, 'dus'),	# (2,)	demote 1 -> 2
		]

		widget.treeview.expand_all()
		widget.treeview.get_selection().unselect_all()
		for path in (
			(1,), (1, 0), (1, 1), (1, 2), (2,) # "baz" -> "dus"
		):
			widget.treeview.get_selection().select_path(path)
		self.assertFalse(widget.on_promote())
		self.assertTrue(widget.on_demote())
		self.assertEqual(get_tree(), wanted)

		widget.treeview.expand_all()
		widget.treeview.get_selection().unselect_all()
		for path in (
			(0, 0), (0, 0, 0), (0, 0, 1), (0, 0, 2), (0, 1) # "baz" -> "dus"
		):
			widget.treeview.get_selection().select_path(path)
		self.assertFalse(widget.on_demote())
		self.assertTrue(widget.on_promote())
		self.assertEqual(get_tree(), without_h1)

		# Test empty page
		emptypage = tests.MockObject()
		widget.on_page_changed(window, emptypage)
		self.assertEqual(get_tree(), [])
		widget.on_store_page(notebook, emptypage)
		self.assertEqual(get_tree(), [])


		# Test some more pages - any errors ?
		for path in notebook.pages.walk():
			page = notebook.get_page(path)
			widget.on_page_changed(window, page)
			widget.on_store_page(notebook, page)


def get_headings(model, parent=None, level=1):
	headings = []
	iter = model.iter_children(parent)
	while iter:
		text = model[iter][0]
		children = get_headings(model, iter, level+1) if model.iter_has_child(iter) else []
		headings.append((level, text, children))
		iter = model.iter_next(iter)
	return headings


class TestToCModel(tests.TestCase):

	def testGetNthHeadingWithH1(self):
		headings = [
			(1, 'a', [
				(2, 'b1', []),
				(2, 'b2', [
					(3, 'c1', []),
					(3, 'c2', []),
					(3, 'c3', []),
				]),
				(2, 'b3', []),
			]),
		]

		model = ToCTreeModel()
		model.update(headings, show_h1=True)
		for path, n in (
			((0,),    1),
			((0,0),   2),
			((0,1),   3),
			((0,1,0), 4),
			((0,1,1), 5),
			((0,1,2), 6),
			((0,2),   7)
		):
			path = Gtk.TreePath(path)
			self.assertEqual(model.get_nth_heading(path), n)

		model.update(headings, show_h1=False)
		for path, n in (
			((0,),  2),
			((1,),  3),
			((1,0), 4),
			((1,1), 5),
			((1,2), 6),
			((2),   7)
		):
			path = Gtk.TreePath(path)
			self.assertEqual(model.get_nth_heading(path), n)

	def testGetNthHeadingWithoutH1(self):
		headings = [
			(1, 'b1', []),
			(1, 'b2', [
				(2, 'c1', []),
				(2, 'c2', []),
				(2, 'c3', []),
			]),
			(1, 'b3', []),
		]

		model = ToCTreeModel()
		model.update(headings, show_h1=True)
		for path, n in (
			((0,),  1),
			((1,),  2),
			((1,0), 3),
			((1,1), 4),
			((1,2), 5),
			((2),   6)
		):
			path = Gtk.TreePath(path)
			self.assertEqual(model.get_nth_heading(path), n)

		model.update(headings, show_h1=False)
		for path, n in (
			((0,),  1),
			((1,),  2),
			((1,0), 3),
			((1,1), 4),
			((1,2), 5),
			((2),   6)
		):
			path = Gtk.TreePath(path)
			self.assertEqual(model.get_nth_heading(path), n)

	def testSimpleUpdate(self):
		headings = [
			(1, 'a', []),
			(1, 'b', []),
			(1, 'c', []),
		]
		model = ToCTreeModel()
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)
		headings = [
			(1, 'a', []),
			(1, 'bbb', []),
			(1, 'c', []),
		]
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)

	def testUpdateShorter(self):
		headings = [
			(1, 'a', []),
			(1, 'b', []),
			(1, 'c', []),
		]
		model = ToCTreeModel()
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)
		headings = [
			(1, 'a', []),
		]
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)

	def testUpdateLonger(self):
		headings = [
			(1, 'a', []),
			(1, 'b', []),
			(1, 'c', []),
		]
		model = ToCTreeModel()
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)
		headings = [
			(1, 'a', []),
			(1, 'b', []),
			(1, 'c', []),
			(1, 'd', []),
			(1, 'e', []),
		]
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)

	def testUpdateWithChildren(self):
		headings = [
			(1, 'a', [
				(2, 'a1', []),
				(2, 'a2', []),
				(2, 'a3', []),
			]),
			(1, 'b', [
				(2, 'b1', []),
				(2, 'b2', []),
				(2, 'b3', []),
			]),
			(1, 'c', []),
		]
		model = ToCTreeModel()
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)
		headings = [
			(1, 'a', []),	# remove
			(1, 'b', [		# change
				(2, 'b1', []),
				(2, 'bbbb', []),
				(2, 'b3', []),
			]),
			(1, 'c', [		# insert
				(2, 'c1', []),
				(2, 'c2', []),
			]),
		]
		model.update(headings, show_h1=True)
		self.assertEqual(get_headings(model), headings)
