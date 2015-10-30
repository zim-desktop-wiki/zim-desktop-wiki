# -*- coding: utf-8 -*-

from __future__ import with_statement

import tests

from tests.pageview import setUpPageView

from zim.config import ConfigDict
from zim.formats import ParseTree, StubLinker
from zim.formats.html import Dumper as HtmlDumper

from zim.plugins.tableeditor import *


from tests.pageview import setUpPageView


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
		attrib = {'aligns': 'normal,normal', 'wraps': '0,0'}
		header = ['h1', 'h2']
		rows = [['t1', 't2'],]
		obj = TableViewObject(attrib, header, rows, {})
		widget = obj.get_widget()

		with tests.DialogContext(self.checkUpdateTableDialog):
			widget.on_change_columns(None)

		self.assertTrue(isinstance(widget.treeview, gtk.TreeView))


class TestTableFunctions(tests.TestCase):

	def testCellFormater(self):
		self.assertEqual(CellFormatReplacer.input_to_cell('**hello**', with_pango=True), '<b>hello</b>')
		self.assertEqual(CellFormatReplacer.cell_to_input('<span background="yellow">highlight</span>', with_pango=True),
						 '__highlight__')
		self.assertEqual(CellFormatReplacer.zim_to_cell('<link href="./alink">hello</link>'),
						 '<span foreground="blue">hello<span size="0">./alink</span></span>')
		self.assertEqual(CellFormatReplacer.cell_to_zim('<tt>code-block</tt>'), '<code>code-block</code>')


class TestTableViewObject(tests.TestCase):

	def runTest(self):
		attrib = {'aligns': 'left,left', 'wraps': '0,0'}
		preferences = {}

		for headers, rows in (
			( # Two simple rows
				['C1', 'C2'],
				[ ['a', 'b'], ['q', 'x'] ]
			),
			( # Some empty fields
				['C1', 'C2'],
				[ ['a', ' '], ['q', ' '], [' ', ' '] ]
			),
		):
			obj = TableViewObject(attrib, headers, rows, preferences)
			data = obj.get_data()
			self.assertEqual(data, (headers, rows, attrib))

			widget = obj.get_widget()
			data = obj.get_data()
			self.assertEqual(data, (headers, rows, attrib))

			# put object in pageview and serialize
			pageview = setUpPageView()
			pageview.insert_object(obj)
			tree = pageview.get_parsetree()
			#~ print tree.tostring()

			# re-construct from serialized version
			newpageview = setUpPageView()
			newpageview.set_parsetree(tree)
			buffer = newpageview.view.get_buffer()
			buffer.place_cursor(buffer.get_iter_at_offset(1))
			newobj = buffer.get_object_at_cursor()
			self.assertIsInstance(newobj, TableViewObject)

			data = newobj.get_data()
			self.assertEqual(data, (headers, rows, attrib))

