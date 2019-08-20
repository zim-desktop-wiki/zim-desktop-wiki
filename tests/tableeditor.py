
# Copyright 2015 Tobias Haupenthal
# Copyright 2016-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests

from zim.formats import ParseTree, StubLinker, OldParseTreeBuilder
from zim.formats.wiki import Parser as WikiParser
from zim.formats.wiki import Dumper as WikiDumper
from zim.formats.html import Dumper as HtmlDumper
from zim.notebook import Path

from zim.plugins import PluginManager
from zim.plugins.tableeditor import *

from zim.gui.insertedobjects import UnknownInsertedObject

from tests.mainwindow import setUpMainWindow
from tests.pageview import setUpPageView


def get_gtk_action(uimanager, name):
	for group in uimanager.get_action_groups():
		action = group.get_action(name)
		if action is not None:
			return action
	else:
		raise ValueError


TABLE_WIKI_TEXT = '''\

|        H1       <|         H2 h2 | H3                    <|
|:----------------:|--------------:|:-----------------------|
|    Column A1     |     Column A2 | a \\\\name               |
| a very long cell | **bold text** | two\\nlines             |
|    hyperlinks    |   [[wp?wiki]] | [[http://x.org\|Xorg]] |

'''

TABLE_OBJECT_TEXT = '''\

{{{table:
%s
}}}

''' % TABLE_WIKI_TEXT.strip()

TABLE_TOKENS = [
	('zim-tree', {}),
		('T', '\n'),
		('table', {'aligns': 'center,right,left', 'wraps': '1,0,1'}),
			('thead', {}),
				('th', {}), ('T', 'H1'), ('/', 'th'),
				('th', {}), ('T', 'H2 h2'), ('/', 'th'),
				('th', {}), ('T', 'H3'), ('/', 'th'),
			('/', 'thead'),
			('trow', {}),
				('td', {}), ('T', 'Column A1'), ('/', 'td'),
				('td', {}), ('T', 'Column A2'), ('/', 'td'),
				('td', {}), ('T', 'a \\name'), ('/', 'td'),
			('/', 'trow'),
			('trow', {}),
				('td', {}), ('T', 'a very long cell'), ('/', 'td'),
				('td', {}), ('strong', {}), ('T', 'bold text'), ('/', 'strong'), ('/', 'td'),
				('td', {}), ('T', 'two\n'), ('T', 'lines'), ('/', 'td'),
			('/', 'trow'),
			('trow', {}),
				('td', {}), ('T', 'hyperlinks'), ('/', 'td'),
				('td', {}), ('link', {'href': 'wp?wiki'}), ('T', 'wp?wiki'), ('/', 'link'), ('/', 'td'),
				('td', {}), ('link', {'href': 'http://x.org'}), ('T', 'Xorg'), ('/', 'link'), ('/', 'td'),
			('/', 'trow'),
		('/', 'table'),
		('T', '\n'),
	('/', 'zim-tree')
]


class TestWikiSyntaxNoPlugin(tests.TestCase):

	def parseAndDump(self, text):
		tree = WikiParser().parse(text)
		self.assertEquals(list(tree.iter_tokens()), TABLE_TOKENS)

	def testWikiText(self):
		self.parseAndDump(TABLE_WIKI_TEXT)

	def testObectText(self):
		# This test is important to ensure backward compatibility with previous
		# versions that would write out an object when the table plugin wasn't
		# loaded
		self.parseAndDump(TABLE_OBJECT_TEXT)


class TestWikiSyntaxWithPlugin(TestWikiSyntaxNoPlugin):

	def setUp(self):
		PluginManager.load_plugin('tableeditor')


class TestTableObjectType(tests.TestCase):

	def setUp(self):
		PluginManager.load_plugin('tableeditor')
		self.otype = PluginManager.insertedobjects['table']

	def testModelFromElement(self):
		tree = WikiParser().parse(TABLE_WIKI_TEXT)
		element = tree._etree.getroot().find('table')
		self.assertIsNotNone(element)
		model = self.otype.model_from_element(element.attrib, element)

		builder = OldParseTreeBuilder() # XXX
		builder.start('zim-tree')
		self.otype.dump(builder, model)
		builder.end('zim-tree')
		tree = ParseTree(builder.close())

		#self.assertEquals(list(tree.iter_tokens()), TABLE_TOKENS) -- XXX should work but doesn;t :(
		self.assertEquals(''.join(WikiDumper().dump(tree)), TABLE_WIKI_TEXT[1:-1])

	def testModelFromData(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		model = self.otype.model_from_data(notebook, page, {}, TABLE_WIKI_TEXT)

		builder = OldParseTreeBuilder() # XXX
		builder.start('zim-tree')
		self.otype.dump(builder, model)
		builder.end('zim-tree')
		tree = ParseTree(builder.close())

		#self.assertEquals(list(tree.iter_tokens()), TABLE_TOKENS) -- XXX should work but doesn;t :(
		self.assertEquals(''.join(WikiDumper().dump(tree)), TABLE_WIKI_TEXT[1:-1])


class TestPageViewNoPlugin(tests.TestCase):

	def setUp(self):
		self.assertNotIn('table', PluginManager.insertedobjects)

	def testLoadAndDump(self):
		pageview = setUpPageView(
			self.setUpNotebook(),
			text=TABLE_WIKI_TEXT,
		)
		pageview.textview.get_buffer().set_modified(True) # Force re-interpretation of the buffer
		tree = pageview.get_parsetree()
		self.assertEquals(list(tree.iter_tokens()), TABLE_TOKENS)


class TestPageViewWithPlugin(TestPageViewNoPlugin):

	def setUp(self):
		PluginManager.load_plugin('tableeditor')
		self.assertIn('table', PluginManager.insertedobjects)

	def testWidget(self):
		pageview = setUpPageView(
			self.setUpNotebook(),
			text=TABLE_WIKI_TEXT,
		)
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
		action = get_gtk_action(window.uimanager, 'insert_table')

		def insert_table(dialog):
			self.assertIsInstance(dialog, EditTableDialog)
			dialog.assert_response_ok()

		with tests.DialogContext(insert_table):
			action.activate()

		tree = window.pageview.get_parsetree()
		elt = tree.find('table')
		self.assertIsNotNone(elt)

	def testInsertDialogCancelled(self):
		window = setUpMainWindow(self.setUpNotebook(content={'Test': 'Test 123'}), path='Test')
		action = get_gtk_action(window.uimanager, 'insert_table')

		def cancel_dialog(dialog):
			self.assertIsInstance(dialog, EditTableDialog)
			dialog.response(Gtk.ResponseType.CANCEL)

		with tests.DialogContext(cancel_dialog):
			action.activate()

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
