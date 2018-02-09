# -*- coding: utf-8 -*-

# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from tests.mainwindow import setUpMainWindow

from zim.formats import ParseTree, StubLinker
from zim.formats.html import Dumper as HtmlDumper

from zim.plugins.sourceview import *


class TestMainWindowExtension(tests.TestCase):

	def runTest(self):
		window = setUpMainWindow(self.setUpNotebook())
		plugin = SourceViewPlugin()
		extension = SourceViewMainWindowExtension(plugin, window)

		with tests.DialogContext(self.checkInsertCodeBlockDialog):
			extension.insert_sourceview()

		tree = window.pageview.get_parsetree()
		#~ print tree.tostring()
		obj = tree.find('object')
		self.assertTrue(obj.attrib['type'] == 'code')

	def checkInsertCodeBlockDialog(self, dialog):
		self.assertIsInstance(dialog, InsertCodeBlockDialog)
		dialog.form['lang'] = list(LANGUAGES.keys())[0]
		dialog.assert_response_ok()


class TestSourceViewObject(tests.TestCase):

	def testDumpHtml(self):
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><object lang="python" linenumbers="false" type="code">
def foo(a, b):
	print "FOO", a >= b

</object></zim-tree>'''
		tree = ParseTree().fromstring(xml)
		dumper = HtmlDumper(StubLinker())
		html = dumper.dump(tree)
		#~ print '>>', html
		self.assertIn('\tprint "FOO", a &gt;= b\n', html)
