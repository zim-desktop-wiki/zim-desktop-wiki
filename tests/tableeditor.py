


import tests

from zim.formats import ParseTree, StubLinker
from zim.formats.html import Dumper as HtmlDumper

from zim.plugins.tableeditor import *

from tests.mainwindow import setUpMainWindow
from tests.pageview import setUpPageView


class TestPageViewExtension(tests.TestCase):

	def setUp(self):
		self.plugin = TableEditorPlugin()

	def tearDown(self):
		self.plugin.destroy()

	def testWidget(self):
		pageview = setUpPageView(
			self.setUpNotebook(),
			text='''\

|        H1       <|         H2 h2 | H3                    <|
|:----------------:|--------------:|:-----------------------|
|    Column A1     |     Column A2 | a                      |
| a very long cell | **bold text** | b                      |
|    hyperlinks    |   [[wp?wiki]] | [[http://x.org\|Xorg]] |

'''	)
		# test widget loaded
		objects = list(pageview.textview._object_widgets) # XXX
		self.assertIsInstance(objects[0], TableViewWidget)

		# test modify
		#widget = objects[0]
		#self.assertFalse(pageview.textview.get_buffer().get_modified())
		# FIXME: change content via widget
		#self.assertTrue(pageview.textview.get_buffer().get_modified())

		# test modification ends up in page
		tree = pageview.get_parsetree()
		#print(tree.tostring())
		elt = tree.find('table')
		self.assertIsNotNone(elt)
		# FIXME: test content

	def testInsertDialog(self):
		window = setUpMainWindow(self.setUpNotebook(content={'Test': 'Test 123'}), path='Test')
		extension = TableEditorPageViewExtension(self.plugin, window.pageview)

		def insert_table(dialog):
			self.assertIsInstance(dialog, EditTableDialog)
			dialog.assert_response_ok()

		with tests.DialogContext(insert_table):
			extension.insert_table()

		tree = window.pageview.get_parsetree()
		elt = tree.find('table')
		self.assertIsNotNone(elt)

	def testInsertDialogCancelled(self):
		window = setUpMainWindow(self.setUpNotebook(content={'Test': 'Test 123'}), path='Test')
		extension = TableEditorPageViewExtension(self.plugin, window.pageview)

		def cancel_dialog(dialog):
			self.assertIsInstance(dialog, EditTableDialog)
			dialog.response(Gtk.ResponseType.CANCEL)

		with tests.DialogContext(cancel_dialog):
			extension.insert_table()

		tree = window.pageview.get_parsetree()
		elt = tree.find('table')
		self.assertIsNone(elt)



class TestEditTable(tests.TestCase):

	def checkUpdateTableDialog(self, dialog):
		self.assertIsInstance(dialog, EditTableDialog)
		dialog.assert_response_ok()

	def runTest(self):
		attrib = {'aligns': 'normal,normal', 'wraps': '0,0'}
		headers = ['h1', 'h2']
		rows = [['t1', 't2'], ]

		model = TableModel(attrib, headers, rows)
		widget = TableViewWidget(model)

		with tests.DialogContext(self.checkUpdateTableDialog):
			widget.on_change_columns(None)

		self.assertTrue(isinstance(widget.treeview, Gtk.TreeView))


class TestTableFunctions(tests.TestCase):

	def testCellFormater(self):
		self.assertEqual(CellFormatReplacer.input_to_cell('**hello**', with_pango=True), '<b>hello</b>')
		self.assertEqual(CellFormatReplacer.cell_to_input('<span background="yellow">highlight</span>', with_pango=True),
						 '__highlight__')
		self.assertEqual(CellFormatReplacer.zim_to_cell('<link href="./alink">hello</link>'),
						 '<span foreground="blue">hello<span size="0">./alink</span></span>')
		self.assertEqual(CellFormatReplacer.cell_to_zim('<tt>code-block</tt>'), '<code>code-block</code>')
