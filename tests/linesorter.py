
# Copyright 2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>




import tests

from tests.mainwindow import setUpMainWindow

from zim.plugins.linesorter import LineSorterPlugin, LineSorterPageViewExtension, NoSelectionError
from zim.gui.pageview import PageView


class TestLineSorterWindowExtension(tests.TestCase):

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
			template % '<li>B list item</li><li>C list item</li><li>A list item</li>'
		)
		self.buffer.set_parsetree(tree)
		self.select_range(0, 42)
		self.extension.sort_selected_lines()
		tree = self.buffer.get_parsetree()
		self.assertEqual(
			tree.tostring(),
			template % '<li bullet="*">A list item</li><li bullet="*">B list item</li><li bullet="*">C list item</li>'
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
