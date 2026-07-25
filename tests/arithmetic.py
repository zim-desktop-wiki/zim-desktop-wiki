
# Copyright 2016 Joachim Trouverie <joachim.trouverie@linoame.fr>
# This is the test for Arithmetic plugin.
# Arithmetic is a plugin for Zim program
# by Patricio Paez <pp@pp.com.mx>

import tests
from zim.inc.arithmetic import ParserGTK, feed


class ArithmeticTest(tests.TestCase):

	def runTest(self):
		'''Test Arithmetic plugin'''
		# operations tests
		data = [
			('3 + 7=', '3 + 7=10'),
			('3 + 7=11', '3 + 7=10'),
			('-3 + 7=', '-3 + 7=4'),
			('-3 + 7=10', '-3 + 7=4'),
			('3 - 7=', '3 - 7=-4'),
			('3 - 7=-5', '3 - 7=-4'),
			('-3 - 7=', '-3 - 7=-10'),
			('-3 - 7=-5', '-3 - 7=-10'),
			('3 * 7=', '3 * 7=21'),
			('3 * 7=22', '3 * 7=21'),
			('3 * -7=', '3 * -7=-21'),
			('3 * -7=-22', '3 * -7=-21'),
			('3 x 7=', '3 x 7=21'),
			('3 x 7=22', '3 x 7=21'),
			('3 x -7=', '3 x -7=-21'),
			('3 x -7=-22', '3 x -7=-21'),
			('8 / 4=', '8 / 4=2'),
			('8 / 4=3', '8 / 4=2'),
			('-8 / 4=', '-8 / 4=-2'),
			('-8 / 4=-3', '-8 / 4=-2'),
			('2 ** 2=', '2 ** 2=4'),
			('2 ** 2=8', '2 ** 2=4'),
			('-2 ** 3=', '-2 ** 3=-8'),
			('-2 ** 3=-6', '-2 ** 3=-8'),
			('2 ^ 2=', '2 ^ 2=4'),
			('2 ^ 2=8', '2 ^ 2=4'),
			('-2 ^ 3=', '-2 ^ 3=-8'),
			('-2 ^ 3=-6', '-2 ^ 3=-8'),
		]

		for text, wanted in data:
			result = feed(text).strip()
			self.assertEqual(result, wanted)

		text = '''
		a=5
		b=6
		a + b=
		a + b=12
		a - b=
		a - b=-2
		b - a=
		b - a=2
		a * b=
		a * b=31
		b / a=
		b / a=1
		a ** b=
		a ** b=15626
		'''
		wanted = '''
		a=5
		b=6
		a + b=11
		a + b=11
		a - b=-1
		a - b=-1
		b - a=1
		b - a=1
		a * b=30
		a * b=30
		b / a=1.2
		b / a=1.2
		a ** b=15,625
		a ** b=15,625
		'''
		self.assertEqual(feed(text), wanted)

		text = '''
		W=5
		Höhe=3
		W * Höhe=
		'''
		wanted = '''
		W=5
		Höhe=3
		W * Höhe=15
		'''
		self.assertEqual(feed(text), wanted)


class MockTextBuffer:
	'''Minimal stand-in for the parts of Gtk.TextBuffer used by writeResult()'''

	def __init__(self):
		self.inserted = None

	def get_iter_at_line_offset(self, line, offset):
		return (line, offset)

	def insert(self, iter, text):
		self.inserted = text


class ArithmeticGtkGroupedResultTest(tests.TestCase):

	def runTest(self):
		'''Grouped results must not break the GTK result formatting'''
		# AddCommas() groups thousands, so writeResult() must not feed
		# the separators straight into float() - see issue #2994
		for text, wanted in (
			('1,000', '1,000'),
			('-1,000', '-1,000'),
			('15,625', '15,625'),
			('1,501.5', '1,501.5'),
			('10', '10'),
		):
			buffer = MockTextBuffer()
			ParserGTK().writeResult(0, buffer, 0, 0, text)
			self.assertEqual(buffer.inserted, wanted)
