
# Copyright 2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>




import tests

from tests.mainwindow import setUpMainWindow
from tests.pageview import TextBufferTestCaseMixin

from zim.plugins.linesorter import LineSorterPlugin, LineSorterPageViewExtension, NoSelectionError
from zim.gui.pageview import PageView


class TestLineSorterWindowExtension(tests.TestCase, TextBufferTestCaseMixin):

	def setUp(self):
		plugin = LineSorterPlugin()
		window = setUpMainWindow(self.setUpNotebook())
		self.extension = LineSorterPageViewExtension(plugin, window.pageview)
		self.buffer = window.pageview.textview.get_buffer()

	def set_text(self, text):
		self.buffer.set_text(text)

	def place_cursor(self, offset):
		iter = self.buffer.get_iter_at_offset(offset)
		self.buffer.place_cursor(iter)

	def select_range(self, startoffset, endoffset):
		start = self.buffer.get_iter_at_offset(startoffset)
		end = self.buffer.get_iter_at_offset(endoffset)
		self.buffer.select_range(start, end)

	def get_text(self):
		start, end = self.buffer.get_bounds()
		return start.get_text(end)

	def testSortLines(self):
		self.set_text('A line\nB line\nC line\nB line\n0 trailing text\n')
		self.select_range(0, 28)
		self.extension.sort_selected_lines()
		self.assertEqual(self.get_text(), 'A line\nB line\nB line\nC line\n0 trailing text\n')

	def testPartialLineSelected(self):
		self.set_text('A line\nC line\nB line\ntrailing text\n')
		self.select_range(3, 18)
		self.extension.sort_selected_lines()
		self.assertEqual(self.get_text(), 'A line\nB line\nC line\ntrailing text\n')

	def testSortSortedLinesReverses(self):
		self.set_text('A line\nB line\nC line\nZ trailing text\n')
		self.select_range(0, 21)
		self.extension.sort_selected_lines()
		self.assertEqual(self.get_text(), 'C line\nB line\nA line\nZ trailing text\n')

	def testSortListItems(self):
		from zim.formats import ParseTree
		template = '<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><p><ul>%s</ul></p></zim-tree>'
		tree = ParseTree().fromstring(
			template % '<li>B list item\n</li><li>C list item\n</li><li>A list item\n</li>'
		)
		self.buffer.set_parsetree(tree)
		self.select_range(0, 42)
		self.extension.sort_selected_lines()
		tree = self.buffer.get_parsetree()
		self.assertEqual(
			tree.tostring(),
			template % '<li bullet="*">A list item\n</li><li bullet="*">B list item\n</li><li bullet="*">C list item\n</li>'
		)

	def testErrorForSortLinesIfNoSelection(self):
		self.set_text('A line\nB line\nC line\ntrailing text\n')
		with self.assertRaises(NoSelectionError):
			self.extension.sort_selected_lines()

	def testErrorForSortLinesIfSingleLineSelected(self):
		self.set_text('A line\nB line\nC line\ntrailing text\n')
		with self.assertRaises(NoSelectionError):
			self.select_range(0, 7)
			self.extension.sort_selected_lines()

	def testMoveUpNoSelection(self):
		self.set_text('A line\nB line\nC line\n')
		self.place_cursor(10)
		self.extension.move_line_up()
		self.assertEqual(self.get_text(), 'B line\nA line\nC line\n')

	def testMoveUpStyledTextIntoCheckboxList(self):
		self.set_buffer(self.buffer,
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Checkbox #1\n'
			'<icon stock="zim-unchecked-box" /> Checkbox #2\n</li>'
			'Line with <strong>bold</strong> text\n'
		)
		self.place_cursor(32)
		self.extension.move_line_up()
		self.assertBufferEqual(self.buffer,
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Checkbox #1\n</li>'
			'Line with <strong>bold</strong> text\n'
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Checkbox #2\n</li>'
		)

	def testMoveUpLineWithPageLinkIntoList(self):
		self.set_buffer(self.buffer,
			'<li indent="0" style="bullet-list">\u2022 List item #1\n'
			'\u2022 List item #2\n</li>'
			'Line containing a <link href="None">page link</link>\n'
		)
		self.place_cursor(32)
		self.extension.move_line_up()
		self.assertBufferEqual(self.buffer,
			'<li indent="0" style="bullet-list">\u2022 List item #1\n</li>'
			'Line containing a <link href="None">page link</link>\n'
			'<li indent="0" style="bullet-list">\u2022 List item #2\n</li>'
		)

	def testMoveDownNoSelection(self):
		self.set_text('A line\nB line\nC line\n')
		self.place_cursor(10)
		self.extension.move_line_down()
		self.assertEqual(self.get_text(), 'A line\nC line\nB line\n')

	def testMoveUpWordSelection(self):
		self.set_text('A line\nB line\nC line\n')
		self.select_range(9, 13)
		self.extension.move_line_up()
		self.assertEqual(self.get_text(), 'B line\nA line\nC line\n')

	def testMoveDownWordSelection(self):
		self.set_text('A line\nB line\nC line\n')
		self.select_range(9, 13)
		self.extension.move_line_down()
		self.assertEqual(self.get_text(), 'A line\nC line\nB line\n')

	def testMoveUpLineSelection(self):
		self.set_text('A line\nB line\nC line\ntrailing text\n')
		self.select_range(7, 21)
		self.extension.move_line_up()
		self.assertEqual(self.get_text(), 'B line\nC line\nA line\ntrailing text\n')

	def testMoveDownLinesSelection(self):
		self.set_text('A line\nB line\nC line\ntrailing text\n')
		self.select_range(0, 14)
		self.extension.move_line_down()
		self.assertEqual(self.get_text(), 'C line\nA line\nB line\ntrailing text\n')

	def testMoveUpPartialLinesSelection(self):
		self.set_text('A line\nB line\nC line\ntrailing text\n')
		self.select_range(10, 18)
		self.extension.move_line_up()
		self.assertEqual(self.get_text(), 'B line\nC line\nA line\ntrailing text\n')

	def testMoveDownPartialLinesSelection(self):
		self.set_text('A line\nB line\nC line\ntrailing text\n')
		self.select_range(3, 11)
		self.extension.move_line_down()
		self.assertEqual(self.get_text(), 'C line\nA line\nB line\ntrailing text\n')

	# In a numbered list the bullet belongs to the position, not to the line,
	# so moving a line must not take its number along

	NUMBERED_LIST = (
		'<li indent="0" style="numbered-list">'
		'1. foo\n2. bar\n3. baz\n4. x\n</li>'
	)

	def testMoveDownInNumberedList(self):
		self.set_buffer(self.buffer, self.NUMBERED_LIST)
		self.place_cursor(16) # on "baz"
		self.extension.move_line_down()
		self.assertBufferEqual(self.buffer,
			'<li indent="0" style="numbered-list">'
			'1. foo\n2. bar\n3. x\n4. baz\n</li>'
		)

	def testMoveUpInNumberedList(self):
		self.set_buffer(self.buffer, self.NUMBERED_LIST)
		self.place_cursor(16) # on "baz"
		self.extension.move_line_up()
		self.assertBufferEqual(self.buffer,
			'<li indent="0" style="numbered-list">'
			'1. foo\n2. baz\n3. bar\n4. x\n</li>'
		)

	def testMoveFirstItemOfNumberedListKeepsListStart(self):
		# Moving the first item used to leave the list starting at "2.",
		# which survives saving because the first bullet defines the start
		self.set_buffer(self.buffer, self.NUMBERED_LIST)
		self.place_cursor(3) # on "foo"
		self.extension.move_line_down()
		self.assertBufferEqual(self.buffer,
			'<li indent="0" style="numbered-list">'
			'1. bar\n2. foo\n3. baz\n4. x\n</li>'
		)

	NESTED_NUMBERED_LIST = (
		'<li indent="0" style="numbered-list">1. foo\n2. bazooka\n</li>'
		'<li indent="1" style="numbered-list">a. abc\nb. def\nc. hij\n</li>'
		'<li indent="0" style="numbered-list">3. bar\n</li>'
	)

	def testMoveUpOutOfNestedNumberedList(self):
		# The line ends up on the position of a list item one level up - its
		# own bullet style and indent must survive that
		self.set_buffer(self.buffer, self.NESTED_NUMBERED_LIST)
		self.place_cursor(22) # on "abc"
		self.extension.move_line_up()
		self.assertEqual(self.get_text().splitlines()[:3], ['1. foo', 'a. abc', '2. bazooka'])
		self.assertEqual(self.buffer.get_bullet(1), 'a.')
		self.assertEqual(self.buffer.get_indent(1), 1)

	def testMoveUpWithinNestedNumberedList(self):
		self.set_buffer(self.buffer, self.NESTED_NUMBERED_LIST)
		self.place_cursor(29) # on "def"
		self.extension.move_line_up()
		self.assertEqual(self.get_text().splitlines()[2:5], ['a. def', 'b. abc', 'c. hij'])

	def testMoveInNumberedListIsSingleUndoStep(self):
		# Renumbering used to add an undo group per corrected bullet
		self.set_buffer(self.buffer, self.NUMBERED_LIST)
		self.buffer.undostack.clear_undostack()
		self.place_cursor(16) # on "baz"
		self.extension.move_line_up()
		self.buffer.undostack.undo()
		self.assertBufferEqual(self.buffer, self.NUMBERED_LIST)

	def testNothingHappensMoveUpAtStart(self):
		self.set_text('A line\nB line\nC line\n')
		self.select_range(3, 11)
		self.extension.move_line_up()
		self.assertEqual(self.get_text(), 'A line\nB line\nC line\n')

	def testNothingHappensMoveDownAtEnd(self):
		self.set_text('A line\nB line\nC line\n')
		self.select_range(10, 18)
		self.extension.move_line_down()
		self.assertEqual(self.get_text(), 'A line\nB line\nC line\n')

	def testHandleMissingNewlineAtEndForMoveUp(self):
		self.set_text('A line\nB line\nC line')
		self.place_cursor(18)
		self.extension.move_line_up()
		self.assertEqual(self.get_text(), 'A line\nC line\nB line\n')

	def testHandleMissingNewlineAtEndForMoveDown(self):
		self.set_text('A line\nB line\nC line')
		self.place_cursor(10)
		self.extension.move_line_down()
		self.assertEqual(self.get_text(), 'A line\nC line\nB line\n')

	def testDuplicateLine(self):
		self.set_text('Line A\nLine B\nLine C\n')
		self.place_cursor(10)
		self.extension.duplicate_line()
		self.assertEqual(self.get_text(), 'Line A\nLine B\nLine B\nLine C\n')

	def testDuplicateLineWithSelection(self):
		self.set_text('Line A\nLine B\nLine C\n')
		self.select_range(0, 10)
		self.extension.duplicate_line()
		self.assertEqual(self.get_text(), 'Line A\nLine B\nLine A\nLine B\nLine C\n')

	def testDuplicateLastLine(self):
		self.set_text('Line A\nLine B\nLast Line')
		self.place_cursor(20)
		self.extension.duplicate_line()
		self.assertEqual(self.get_text(), 'Line A\nLine B\nLast Line\nLast Line')

	def testDuplicateLineAvoidResetHeaderForBullet(self):
		# Test case for specific issue seen #1457
		# Effective testing pageview behavior, so might be in the wrong place
		# in the test suite.
		# Doubles as test for content other than pure text
		self.set_buffer(self.buffer, '''\
<li indent="0" style="bullet-list">\u2022 line A
\u2022 line B
</li><h level="2">Heading</h>
''')
		self.place_cursor(10)
		self.extension.duplicate_line()
		self.assertBufferEqual(self.buffer, '''\
<li indent="0" style="bullet-list">\u2022 line A
\u2022 line B
\u2022 line B
</li><h level="2">Heading</h>
'''
)

	def testRemoveLine(self):
		self.set_text('Line A\nLine B\nLine C\n')
		self.place_cursor(10)
		self.extension.remove_line()
		self.assertEqual(self.get_text(), 'Line A\nLine C\n')

	def testRemoveLineWithSelection(self):
		self.set_text('Line A\nLine B\nLine C\n')
		self.select_range(0, 10)
		self.extension.remove_line()
		self.assertEqual(self.get_text(), 'Line C\n')
