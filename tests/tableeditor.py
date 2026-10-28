
# Copyright 2015 Tobias Haupenthal
# Copyright 2016-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests

from zim.formats import ParseTree, StubLinker, BackwardParseTreeBuilderWithCleanup
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
|    hyperlinks    |   [[wp?wiki]] | [[http://x.org\\|Xorg]] |

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


TABLE_WIKI_TEXT_SPECIAL_CHARS = '''\

| Name & Type <b> | Value               |
|:----------------|:--------------------|
| a & b <i>x</i>  | [[http://x.org?a=1&b=2]] |

'''


class TestWikiSyntaxNoPlugin(tests.TestCase):

	def parseAndDump(self, text):
		tree = WikiParser().parse(text)
		self.assertEqual(list(tree.iter_tokens()), TABLE_TOKENS)

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

		builder = BackwardParseTreeBuilderWithCleanup() # XXX
		builder.start('zim-tree')
		self.otype.dump(builder, model)
		builder.end('zim-tree')
		tree = ParseTree(builder.close())

		#self.assertEqual(list(tree.iter_tokens()), TABLE_TOKENS) -- XXX should work but doesn;t :(
		self.assertEqual(''.join(WikiDumper().dump(tree)), TABLE_WIKI_TEXT[1:-1])

	def testModelFromData(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		model = self.otype.model_from_data(notebook, page, {}, TABLE_WIKI_TEXT)

		builder = BackwardParseTreeBuilderWithCleanup() # XXX
		builder.start('zim-tree')
		self.otype.dump(builder, model)
		builder.end('zim-tree')
		tree = ParseTree(builder.close())

		#self.assertEqual(list(tree.iter_tokens()), TABLE_TOKENS) -- XXX should work but doesn;t :(
		self.assertEqual(''.join(WikiDumper().dump(tree)), TABLE_WIKI_TEXT[1:-1])


	def testSuperscriptAndSubscriptRoundTrip(self):
		# Superscript and subscript in a cell should survive loading and
		# dumping the table again, see issue #3038
		text = '''\
| Name   | Formula |
|:-------|:--------|
| quetta | 10^{30} |
| water  | H_{2}O  |
'''
		tree = WikiParser().parse(text)
		element = tree._etree.getroot().find('table')
		model = self.otype.model_from_element(element.attrib, element)

		builder = BackwardParseTreeBuilderWithCleanup()
		builder.start('zim-tree')
		self.otype.dump(builder, model)
		builder.end('zim-tree')
		tree = ParseTree(builder.close())

		dumped = ''.join(WikiDumper().dump(tree))
		self.assertEqual(dumped, text)

		# Export of the re-loaded page should render real tags, not escaped ones
		html = ''.join(HtmlDumper(linker=StubLinker()).dump(WikiParser().parse(dumped)))
		self.assertIn('10<sup>30</sup>', html)
		self.assertIn('H<sub>2</sub>O', html)
		self.assertNotIn('&lt;sup&gt;', html)


class TestPageViewNoPlugin(tests.TestCase):

	def setUp(self):
		self.assertNotIn('table', PluginManager.insertedobjects)

	def testLoadAndDump(self):
		pageview = setUpPageView(
			self.setUpNotebook(),
			text=TABLE_WIKI_TEXT,
		)
		pageview.textview.get_buffer().set_modified(True) # Force re-interpretation of the buffer
		tree = pageview.page.get_parsetree()
		self.assertEqual(list(tree.iter_tokens()), TABLE_TOKENS)


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
		objects = list(pageview.textview.get_inserted_object_widgets())
		self.assertIsInstance(objects[0], TableViewWidget)

		# test modify
		#widget = objects[0]
		#self.assertFalse(pageview.textview.get_buffer().get_modified())
		# FIXME: change content via widget
		#self.assertTrue(pageview.textview.get_buffer().get_modified())

		# test modification ends up in page
		tree = pageview.page.get_parsetree()
		#print(tree.tostring())
		elt = tree.find_element('table')
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

		tree = window.pageview.page.get_parsetree()
		elt = tree.find_element('table')
		self.assertIsNotNone(elt)

	def testInsertDialogCancelled(self):
		window = setUpMainWindow(self.setUpNotebook(content={'Test': 'Test 123'}), path='Test')
		action = get_gtk_action(window.uimanager, 'insert_table')

		def cancel_dialog(dialog):
			self.assertIsInstance(dialog, EditTableDialog)
			dialog.response(Gtk.ResponseType.CANCEL)

		with tests.DialogContext(cancel_dialog):
			action.activate()

		tree = window.pageview.page.get_parsetree()
		elt = tree.find_element('table')
		self.assertIsNone(elt)



	def testSpecialCharacters(self):
		# Characters like "&" and "<" in headers and cells are plain text
		# and should not be interpreted as markup - see issue #3035
		pageview = setUpPageView(
			self.setUpNotebook(),
			text=TABLE_WIKI_TEXT_SPECIAL_CHARS,
		)
		widget = list(pageview.textview.get_inserted_object_widgets())[0]
		self.assertIsInstance(widget, TableViewWidget)

		labels = [
			col.get_widget().get_children()[0].get_text()
				for col in widget.treeview.get_columns()
		]
		self.assertEqual(labels, ['Name & Type <b>', 'Value'])

		cell = Gtk.CellRendererText()
		cell.set_property('markup', widget.model.liststore[0][0])
		self.assertEqual(cell.get_property('text'), 'a & b <i>x</i>')

		pageview.textview.get_buffer().set_modified(True) # Force re-interpretation of the buffer
		tree = pageview.page.get_parsetree()
		self.assertEqual(
			list(tree.iter_tokens()),
			list(WikiParser().parse(TABLE_WIKI_TEXT_SPECIAL_CHARS).iter_tokens())
		)


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


class TestToolbarTimer(tests.TestCase):

	def runTest(self):
		model = TableModel({'aligns': 'normal,normal', 'wraps': '0,0'}, ['h1', 'h2'], [['t1', 't2']])
		widget = TableViewWidget(model)

		# Losing focus starts the timer that hides the toolbar
		widget.on_focus_out(widget.treeview, None, widget.toolbar)
		self.assertIsNotNone(widget._timer)

		# Destroying the treeview must cancel it, or it fails on the destroyed treeview's selection
		widget.treeview.destroy()
		self.assertIsNone(widget._timer)


class TableWidgetInWindowTestCase(tests.TestCase):
	'''Shows a table in a window, as GTK only starts editing a cell in a realized treeview'''

	def setUp(self):
		self.model = TableModel(
			{'aligns': 'normal,normal', 'wraps': '0,0'}, ['h1', 'h2'],
			[['a1', 'a2'], ['b1', 'b2'], ['c1', 'c2']]
		)
		self.widget = TableViewWidget(self.model)
		self.window = Gtk.Window()
		self.window.add(self.widget)
		self.window.show_all()
		tests.gtk_process_events()

	def tearDown(self):
		self.window.destroy()
		tests.gtk_process_events()

	def start_editing(self, row, col):
		treeview = self.widget.treeview
		treeview.set_cursor(Gtk.TreePath.new_from_indices([row]), treeview.get_column(col), True)
		tests.gtk_process_events()
		return self.get_editor()

	def get_editor(self):
		entries = [c for c in self.widget.treeview.get_children() if isinstance(c, Gtk.Entry)]
		return entries[0] if entries else None

	def rows(self):
		return [list(row) for row in self.model.liststore]


class TestSaveCellBeforeToolbarActions(TableWidgetInWindowTestCase):

	def testMoveRowKeepsEdit(self):
		self.start_editing(0, 0).set_text('edited')
		self.widget.on_move_row(None, 1)
		tests.gtk_process_events()
		self.assertEqual(self.rows(), [['b1', 'b2'], ['edited', 'a2'], ['c1', 'c2']])

	def testAddRowKeepsEdit(self):
		self.start_editing(0, 1).set_text('edited')
		self.widget.on_add_row(None)
		tests.gtk_process_events()
		self.assertEqual(self.rows(), [['a1', 'edited'], ['', ''], ['b1', 'b2'], ['c1', 'c2']])

	def testAutosaveSavesOnce(self):
		writes = []
		self.model.liststore.connect('row-changed', lambda *a: writes.append(a))
		self.start_editing(1, 0).set_text('edited')
		self.widget.autosave_current_cell()
		tests.gtk_process_events()
		self.assertEqual(self.rows()[1], ['edited', 'b2'])
		self.assertEqual(len(writes), 1)
		self.assertIsNone(self.get_editor())

	def testCancelledEditNotSaved(self):
		# What the editor does when Escape is pressed
		editor = self.start_editing(1, 1)
		editor.set_text('cancelled')
		editor.props.editing_canceled = True
		editor.editing_done()
		editor.remove_widget()
		tests.gtk_process_events()

		self.widget.treeview.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
		self.widget.on_add_row(None)
		tests.gtk_process_events()
		self.assertEqual(self.rows(), [['a1', 'a2'], ['', ''], ['b1', 'b2'], ['c1', 'c2']])


class TestTabNavigation(TableWidgetInWindowTestCase):

	def press(self, keyval, state=0):
		event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
		event.key.keyval = keyval
		event.key.state = state
		return self.widget.on_treeview_key_press_event(self.widget.treeview, event.key)

	def wait_for_move(self):
		# The next edit doesn't start until a frame's been drawn, so wait for its editor to appear
		import time
		deadline = time.time() + 2
		while self.get_editor() is None and time.time() < deadline:
			tests.gtk_process_events()
			time.sleep(0.01)
		tests.gtk_process_events()

	def cursor(self):
		path, col = self.widget.treeview.get_cursor()
		return path.get_indices()[0], self.widget.treeview.get_columns().index(col)

	def testTabSavesAndEditsNextCell(self):
		self.start_editing(0, 1).set_text('edited')
		self.assertTrue(self.press(Gdk.KEY_Tab))
		self.wait_for_move()
		self.assertEqual(self.rows()[0], ['a1', 'edited'])
		self.assertEqual(self.cursor(), (1, 0))
		self.assertIsNotNone(self.get_editor())

	def testShiftTabGoesBack(self):
		self.start_editing(1, 0)
		self.assertTrue(self.press(Gdk.KEY_ISO_Left_Tab, Gdk.ModifierType.SHIFT_MASK))
		self.wait_for_move()
		self.assertEqual(self.cursor(), (0, 1))

	def testFastTabsAreNotLost(self):
		self.start_editing(0, 0)
		for i in range(3):
			self.press(Gdk.KEY_Tab)  # no main loop iterations in between
		self.wait_for_move()
		self.assertEqual(self.cursor(), (1, 1))

	def testCtrlTabIsLeftToGtk(self):
		self.start_editing(0, 0)
		self.assertFalse(self.press(Gdk.KEY_Tab, Gdk.ModifierType.CONTROL_MASK))


class TestProcessColRowMove(tests.TestCase):

	def move(self, col, row, num_cols, num_rows, col_direction, row_direction=0):
		path = Gtk.TreePath.new_from_indices([row])
		next_col, next_path = TableViewWidget.process_col_row_move(
			col, path, num_cols, num_rows, col_direction, row_direction)
		return next_col, next_path.get_indices()[0]

	def testForward(self):
		self.assertEqual(self.move(0, 0, 3, 2, 1), (1, 0))
		self.assertEqual(self.move(2, 0, 3, 2, 1), (0, 1))  # end of a row goes onto the next
		self.assertEqual(self.move(2, 1, 3, 2, 1), (0, 0))  # last cell goes back to the first

	def testBackward(self):
		self.assertEqual(self.move(1, 1, 3, 2, -1), (0, 1))
		self.assertEqual(self.move(0, 1, 3, 2, -1), (2, 0))  # start of a row goes onto the previous
		self.assertEqual(self.move(0, 0, 3, 2, -1), (2, 1))  # first cell goes round to the last

	def testSingleRowAndColumn(self):
		self.assertEqual(self.move(2, 0, 3, 1, 1), (0, 0))
		self.assertEqual(self.move(0, 0, 3, 1, -1), (2, 0))
		self.assertEqual(self.move(0, 1, 1, 3, 1), (0, 2))
		self.assertEqual(self.move(0, 0, 1, 3, -1), (0, 2))


class TestTableFunctions(tests.TestCase):

	def testCellFormater(self):
		self.assertEqual(CellFormatReplacer.input_to_cell('**hello**', with_pango=True), '<b>hello</b>')
		self.assertEqual(CellFormatReplacer.cell_to_input('<span background="yellow">highlight</span>', with_pango=True),
						 '__highlight__')
		self.assertEqual(CellFormatReplacer.zim_to_cell('<link href="./alink">hello</link>'),
						 '<span foreground="blue"><span size="1">./alink</span>hello</span>')
		self.assertEqual(CellFormatReplacer.cell_to_zim('<tt>code-block</tt>'), '<code>code-block</code>')
		self.assertEqual(CellFormatReplacer.input_to_cell('10^{30}', with_pango=True), '10<sup>30</sup>')
		self.assertEqual(CellFormatReplacer.input_to_cell('H_{2}O', with_pango=True), 'H<sub>2</sub>O')
		self.assertEqual(CellFormatReplacer.cell_to_input('10<sup>30</sup>', with_pango=True), '10^{30}')
		self.assertEqual(CellFormatReplacer.cell_to_input('H<sub>2</sub>O', with_pango=True), 'H_{2}O')
		self.assertEqual(CellFormatReplacer.input_to_cell('__mark__ H_{2}O', with_pango=True),
						 '<span background="yellow">mark</span> H<sub>2</sub>O')
