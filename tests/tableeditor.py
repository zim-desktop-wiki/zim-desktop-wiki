# -*- coding: utf-8 -*-

from __future__ import with_statement

import tests

from tests.pageview import setUpPageView

from zim.config import ConfigDict
from zim.formats import ParseTree, StubLinker
from zim.formats.html import Dumper as HtmlDumper

from zim.plugins.tableeditor import *

class TestMainWindowExtension(tests.TestCase):

	def runTest(self):
		window = tests.MockObject()
		window.pageview = setUpPageView()
		window.ui = tests.MockObject()
		window.ui.uimanager = tests.MockObject()
		window.ui.uistate = ConfigDict()
		window.ui.mainwindow = window # XXX

		plugin = TableEditorPlugin()
		extension = MainWindowExtension(plugin, window)

		with tests.DialogContext(self.checkInsertTableDialog):
			extension.insert_table()

		tree = window.pageview.get_parsetree()
		#~ print tree.tostring()
		obj = tree.find('table')
		
		self.assertTrue(obj.attrib['aligns'] == 'left')
		self.assertTrue(obj.attrib['wraps'] == '0')

		# Parses tree to a table object
		tabledata = tree.tostring().replace("<?xml version='1.0' encoding='utf-8'?>", '')\
			.replace('<zim-tree>', '').replace('</zim-tree>', '')\
			.replace('<td> </td>', '<td>text</td>')

		table = plugin.create_table({'type': 'table'}, ElementTree.fromstring(tabledata))

		self.assertTrue(isinstance(table, TableViewObject))

	def checkInsertTableDialog(self, dialog):
		self.assertIsInstance(dialog, EditTableDialog)
		dialog.assert_response_ok()

class TestEditTableExtension(tests.TestCase):
	def checkUpdateTableDialog(self, dialog):
		self.assertIsInstance(dialog, EditTableDialog)
		dialog.assert_response_ok()

	def testChangeTable(self):
		window = tests.MockObject()
		window.pageview = setUpPageView()
		window.ui = tests.MockObject()
		window.ui.uimanager = tests.MockObject()
		window.ui.uistate = ConfigDict()
		window.ui.mainwindow = window # XXX
		plugin = TableEditorPlugin()
		extension = MainWindowExtension(plugin, window)
		obj = plugin.create_table({'aligns': 'normal,normal', 'wraps': '0,0'}, (('h1', 'h2'),('t1', 't2')))
		obj.get_widget()

		with tests.DialogContext(self.checkUpdateTableDialog):
			extension.do_edit_object(obj)

		self.assertTrue(isinstance(obj.get_widget().treeview, gtk.TreeView))

class TestTableFunctions(tests.TestCase):
	def testCellFormater(self):
		self.assertEqual(CellFormatReplacer.input_to_cell('**hello**', with_pango=True), '<b>hello</b>')
		self.assertEqual(CellFormatReplacer.cell_to_input('<span background="yellow">highlight</span>', with_pango=True),
						 '__highlight__')
		self.assertEqual(CellFormatReplacer.zim_to_cell('<link href="./alink">hello</link>'),
						 '<span foreground="blue">hello<span size="0">./alink</span></span>')
		self.assertEqual(CellFormatReplacer.cell_to_zim('<tt>code-block</tt>'), '<code>code-block</code>')

class TestColumnSorting(tests.TestCase):
	def testSorting(self):
		pass