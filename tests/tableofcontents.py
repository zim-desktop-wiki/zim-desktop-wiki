# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import gtk

from tests.gui import setupGtkInterface

from zim.plugins.tableofcontents import *
from zim.gui.widgets import RIGHT_PANE, LEFT_PANE


@tests.slowTest
class TestTableOfContents(tests.TestCase):

	def testMainWindowExtensions(self):
		plugin = ToCPlugin()

		notebook = tests.new_notebook(self.get_tmp_name())
		ui = setupGtkInterface(self, notebook=notebook)

		plugin.preferences['floating'] = True
		self.assertEqual(plugin.extension_classes['MainWindow'], MainWindowExtensionFloating)
		plugin.extend(ui.mainwindow)

		ext = list(plugin.extensions)
		self.assertEqual(len(ext), 1)
		self.assertIsInstance(ext[0], MainWindowExtensionFloating)

		plugin.preferences.changed() # make sure no errors are triggered
		plugin.preferences['show_h1'] = True
		plugin.preferences['show_h1'] = False
		plugin.preferences['pane'] = RIGHT_PANE
		plugin.preferences['pane'] = LEFT_PANE


		plugin.preferences['floating'] = False
		self.assertEqual(plugin.extension_classes['MainWindow'], MainWindowExtensionEmbedded)
		plugin.extend(ui.mainwindow) # plugin does not remember objects, manager does that

		ext = list(plugin.extensions)
		self.assertEqual(len(ext), 1)
		self.assertIsInstance(ext[0], MainWindowExtensionEmbedded)

		plugin.preferences.changed() # make sure no errors are triggered
		plugin.preferences['show_h1'] = True
		plugin.preferences['show_h1'] = False
		plugin.preferences['pane'] = RIGHT_PANE
		plugin.preferences['pane'] = LEFT_PANE

		plugin.preferences['floating'] = True  # switch back

	def testToCWidget(self):
		'''Test Tabel Of Contents plugin'''
		notebook = tests.new_notebook(self.get_tmp_name())
		ui = setupGtkInterface(self, notebook=notebook)
		pageview = ui.mainwindow.pageview

		widget = ToCWidget(ui, pageview, ellipsis=False)

		def get_tree():
			# Count number of rows in TreeModel
			model = widget.treeview.get_model()
			rows = []
			def c(model, path, iter):
				rows.append((len(path), model[iter][TEXT_COL]))
			model.foreach(c)
			return rows

		page = ui.notebook.get_page(Path('Test'))
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
		ui.notebook.store_page(page)
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
		ui.open_page(page)
		widget.on_open_page(ui, page, page)
		self.assertEqual(get_tree(), without_h1)
		widget.on_stored_page(ui.notebook, page)
		self.assertEqual(get_tree(), without_h1)

		widget.set_show_h1(True)
		self.assertEqual(get_tree(), with_h1)
		widget.set_show_h1(False)
		self.assertEqual(get_tree(), without_h1)

		column = widget.treeview.get_column(0)
		model = widget.treeview.get_model()
		def activate_row(m, path, i):
			#~ print ">>>", path
			widget.treeview.row_activated(path, column)
				# TODO assert something here

			widget.select_section(pageview.view.get_buffer(), path)

			menu = gtk.Menu()
			widget.treeview.get_selection().select_path(path)
			widget.on_populate_popup(widget.treeview, menu)
				# TODO assert something here
			widget.treeview.get_selection().unselect_path(path)

		model.foreach(activate_row)

		# Test promote / demote
		ui.set_readonly(False)
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

		widget.treeview.get_selection().unselect_all()
		widget.treeview.get_selection().select_path((0, 0)) # "baz"
		self.assertFalse(widget.on_demote())
		self.assertTrue(widget.on_promote())
		self.assertEqual(get_tree(), without_h1)

		# Test promote / demote multiple selected
		wanted = [
			(1, 'bar'),
			(2, 'baz'),
			(3, 'A'),
			(3, 'B'),
			(3, 'C'),
			(2, 'dus'),
		]

		widget.treeview.get_selection().unselect_all()
		for path in (
			(1,), (1,0), (1,1), (1,2), (2,) # "baz" -> "dus"
		):
			widget.treeview.get_selection().select_path(path)
		self.assertFalse(widget.on_promote())
		self.assertTrue(widget.on_demote())
		self.assertEqual(get_tree(), wanted)

		widget.treeview.get_selection().unselect_all()
		for path in (
			(0,0), (0,0,0), (0,0,1), (0,0,2), (0,1) # "baz" -> "dus"
		):
			widget.treeview.get_selection().select_path(path)
		self.assertFalse(widget.on_demote())
		self.assertTrue(widget.on_promote())
		self.assertEqual(get_tree(), without_h1)

		# Test empty page
		emptypage = tests.MockObject()
		widget.on_open_page(ui, emptypage, emptypage)
		self.assertEqual(get_tree(), [])
		widget.on_stored_page(ui.notebook, emptypage)
		self.assertEqual(get_tree(), [])


		# Test some more pages - any errors ?
		for page in ui.notebook.walk():
			widget.on_open_page(ui, page, page)
			widget.on_stored_page(ui.notebook, page)

# TODO check selecting heading in actual PageView
# especially test selecting a non-existing item to check we don't get infinite loop
