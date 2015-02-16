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
		logger.fatal("HI")
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

	def checkInsertTableDialog(self, dialog):
		self.assertIsInstance(dialog, EditTableDialog)
		dialog.assert_response_ok()


class TestTableObject(tests.TestCase):

	def testDumpHtml(self):
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<table aligns="right,center" wraps="0,1"><thead><th>Column 1</th><th>Column 2</th></thead>
<trow><td>text 1</td><td>text 2</td></trow></table>
</zim-tree>
'''
		tree = ParseTree().fromstring(xml)
		dumper = HtmlDumper(StubLinker())
		html = dumper.dump(tree)
		#~ print '>>', html
		print '>>', html
		self.assertIn('  <td align="right">text 1</td>\n', html)
		self.assertIn('  <td align="center">text 2</td>\n', html)