# Copyright 2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO: there are more tests for find functionality in tests.pageview that could be merged here

import tests

from tests.pageview import TextBufferTestCaseMixin, Path, TextBuffer

from zim.gui.pageview.find import FindQuery, TextBufferFindMixin, PluginInsertedObjectFindMixin, \
	FIND_CASE_SENSITIVE, FIND_REGEX, FIND_WHOLE_WORD, FIND_HAS_MATCH, FIND_HAS_HIGHLIGHT

import re

from gi.repository import Gtk


class TestGtkTextBuffer(TextBufferFindMixin, Gtk.TextBuffer):

	def __init__(self):
		Gtk.TextBuffer.__init__(self)
		TextBufferFindMixin.__init__(self)


class TestFindQuery(tests.TestCase):

	def runTest(self):
		#i = 0
		for (string, flags, regex) in (
			('test*', 0, re.compile('test\\*', re.I)),
			('test*', FIND_CASE_SENSITIVE, re.compile('test\\*')),
			('test*', FIND_CASE_SENSITIVE | FIND_REGEX, re.compile('test*')),
			('test*', FIND_CASE_SENSITIVE | FIND_REGEX | FIND_WHOLE_WORD, re.compile('\\btest*\\b')),
			('test*', FIND_REGEX, re.compile('test*', re.I)),
			('test*', FIND_REGEX | FIND_WHOLE_WORD, re.compile('\\btest*\\b', re.I)),
			('test*', FIND_WHOLE_WORD, re.compile('\\btest\\*\\b', re.I)),
			('test*', FIND_WHOLE_WORD | FIND_CASE_SENSITIVE, re.compile('\\btest\\*\\b')),
		):
			#i += 1
			#print(">>", i, string, flags, regex)
			query = FindQuery(string, flags)
			self.assertEqual(query.string, string)
			self.assertEqual(query.flags, flags)
			self.assertEqual(query.regex, regex)

			query1 = FindQuery(string, flags)
			self.assertEqual(query1, query)


class TestFindWithGtkTextBuffer(tests.TestCase):

	TEXT ='''\
Some text here
Word words words

Some more text in this textbuffer

TEXT test text
'''

	FORWARD_MATCHES_FROM_LINE_TWO = (
			(3, 10, 'text'),
			# Ignore partial match "textbuffer"
			(5, 0, 'TEXT'), # Case insensitive match
			(5, 10, 'text'),
			# Wrap around
			(0, 5, 'text'),
			(3, 10, 'text') # back to start
		)

	BACKWARD_MATCHES_FROM_LINE_TWO = (
			(0, 5, 'text'),
			# Wrap around
			(5, 10, 'text'),
			(5, 0, 'TEXT'), # Case insensitive match
			# Ignore partial match "textbuffer"
			(3, 10, 'text'),
			(0, 5, 'text') # back to start
		)

	ALL_MATCHES_FOR_HIGHLIGHT = [(0, 5), (3, 10), (5, 0), (5, 10)]

	TEXT_REPLACE_ONE = '''\
Some text here
Word words words

Some more mytext in this textbuffer

TEXT test text
'''

	TEXT_REPLACE_ALL = '''\
Some mytext here
Word words words

Some more mytext in this textbuffer

myTEXT test mytext
'''

	def setUp(self):
		self.buffer = TestGtkTextBuffer()
		self.buffer.set_text(self.TEXT)

	def testFindNext(self):
		query = FindQuery('text', FIND_WHOLE_WORD)
		self.buffer.place_cursor(self.buffer.get_iter_at_line(2))
		for line, offset, text in self.FORWARD_MATCHES_FROM_LINE_TWO:
			self.assertTrue(self.buffer.find_next(query))
			self.assertMatchPosition(line, offset, text)

	def testFindNextMatchesAtCursor(self):
		# Behavior for match at cursor depends on whether it was highlighted already or not
		query = FindQuery('text', FIND_WHOLE_WORD)
		self.buffer.place_cursor(self.buffer.get_iter_at_line(2))
		match_pos_one = self.FORWARD_MATCHES_FROM_LINE_TWO[0]
		match_pos_two = self.FORWARD_MATCHES_FROM_LINE_TWO[1]

		self.assertTrue(self.buffer.find_next(query))
		self.assertMatchPosition(*match_pos_one)
		self.buffer.find_clear() # Reset matching state
		self.assertTrue(self.buffer.find_next(query))
		self.assertMatchPosition(*match_pos_one) # stay at cursor
		# no reset
		self.assertTrue(self.buffer.find_next(query))
		self.assertMatchPosition(*match_pos_two) # move forward

	def testFindPrevious(self):
		query = FindQuery('text', FIND_WHOLE_WORD)
		self.buffer.place_cursor(self.buffer.get_iter_at_line(2))
		for line, offset, text in self.BACKWARD_MATCHES_FROM_LINE_TWO:
			self.assertTrue(self.buffer.find_previous(query))
			self.assertMatchPosition(line, offset, text)

	def assertMatchPosition(self, line, offset, text):
		# Check cursor position
		cursor_iter = self.buffer.get_iter_at_mark(self.buffer.get_insert())
		cursor_pos = (cursor_iter.get_line(), cursor_iter.get_line_offset())
		self.assertEqual(cursor_pos, (line, offset))

		if text is None:
			return # Skip checks below for object matches

		# Check selection applied
		end_iter = cursor_iter.copy()
		start, end = self.buffer.get_selection_bounds()
		self.assertTrue(start.equal(cursor_iter))
		self.assertEqual(start.get_text(end), text)

		# Check match tag applied
		start = self.buffer.get_start_iter()
		start.forward_to_tag_toggle(self.buffer._find_match_tag)
		end = start.copy()
		end.forward_to_tag_toggle(self.buffer._find_match_tag)
		self.assertEqual(start.get_text(end), text)
		self.assertTrue(start.equal(cursor_iter))
		self.assertEqual(start.get_text(end), text)
		end.forward_to_tag_toggle(self.buffer._find_match_tag)
		self.assertFalse(end.forward_to_tag_toggle(self.buffer._find_match_tag)) # no other tag found before end of buffer

	def testHighlightAll(self):
		query = FindQuery('text', FIND_WHOLE_WORD)
		self.assertHighlightPositions([], 'text')
		self.buffer.find_highlight_all(query)
		self.assertHighlightPositions(self.ALL_MATCHES_FOR_HIGHLIGHT, 'text')
		self.buffer.find_clear()
		self.assertHighlightPositions([], 'text')

	def testFindNextPreviousClearHighlight(self):
		# Test the implied statefull behavior
		query = FindQuery('text', FIND_WHOLE_WORD)
		self.buffer.find_highlight_all(query)
		self.assertHighlightPositions(self.ALL_MATCHES_FOR_HIGHLIGHT, 'text')
		self.buffer.find_next(query)
		self.assertHighlightPositions(self.ALL_MATCHES_FOR_HIGHLIGHT, 'text')
		self.buffer.find_previous(query)
		self.assertHighlightPositions(self.ALL_MATCHES_FOR_HIGHLIGHT, 'text')

		new_query = FindQuery('word')
		self.buffer.find_next(new_query)
		self.assertHighlightPositions([], 'text')

		self.buffer.find_highlight_all(query)
		self.assertHighlightPositions(self.ALL_MATCHES_FOR_HIGHLIGHT, 'text')
		self.buffer.find_previous(new_query)
		self.assertHighlightPositions([], 'text')

	def assertHighlightPositions(self, wanted, text):
		iter = self.buffer.get_start_iter()
		matches = []
		while iter.forward_to_tag_toggle(self.buffer._find_highlight_tag):
			matches.append((iter.get_line(), iter.get_line_offset()))
			start = iter.copy()
			iter.forward_to_tag_toggle(self.buffer._find_highlight_tag)
			self.assertEqual(start.get_text(iter).lower(), text)
		self.assertEqual(matches, wanted)

	def testReplaceAtCursor(self):
		query = FindQuery('text', FIND_WHOLE_WORD)
		self.buffer.place_cursor(self.buffer.get_iter_at_line(2))
		self.buffer.find_replace_at_cursor(query, 'mytext')
		start, end = self.buffer.get_bounds()
		self.assertEqual(start.get_text(end), self.TEXT) # no change, since no match at cursor
		self.assertTrue(self.buffer.find_next(query))
		self.assertTrue(self.buffer.find_replace_at_cursor(query, 'mytext'))
		start, end = self.buffer.get_bounds()
		self.assertEqual(start.get_text(end), self.TEXT_REPLACE_ONE)

	def testReplaceAll(self):
		# Added FIND_REGEX to test regex replacement
		query = FindQuery('(text)', FIND_WHOLE_WORD | FIND_REGEX)
		self.assertTrue(self.buffer.find_replace_all(query, 'my\\1'))
		start, end = self.buffer.get_bounds()
		self.assertEqual(start.get_text(end), self.TEXT_REPLACE_ALL)


def _get_text_matches(text, query):
	matches = []
	for i, line in enumerate(text.splitlines()):
		for m in query.regex.finditer(line):
			j = m.start()
			matches.append((i, j, m.group()))
	return matches


def _find_object_matches(buffer, query):
	for iter, anchor in buffer.list_objectanchors():
		if hasattr(anchor, 'objecttype'):
			attrib, data = anchor.objecttype.data_from_model(anchor.objectmodel)
			if data and query.regex.search(data):
				yield iter.get_line(), iter.get_line_offset(), None


class TestFindWithFormattedTextBuffer(TestFindWithGtkTextBuffer):
	# Extension of test case above testing in a buffer with formatting applied and some objects

	# These values are generated in setup below
	TEXT = None
	FORWARD_MATCHES_FROM_LINE_TWO = None
	BACKWARD_MATCHES_FROM_LINE_TWO = None
	ALL_MATCHES_FOR_HIGHLIGHT = None
	TEXT_REPLACE_ONE = None
	TEXT_REPLACE_ALL = None

	def setUp(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		self.buffer = TextBuffer(notebook, page)
		tree = tests.new_parsetree()
		with tests.LoggingFilter('zim.gui.pageview'):
			self.buffer.set_parsetree(tree)

		start, end = self.buffer.get_bounds()
		self.TEXT = start.get_text(end)
		query = FindQuery('text', FIND_WHOLE_WORD)
		text_matches = _get_text_matches(self.TEXT, query)
		assert len(text_matches) == 3, 'Should be 3 text matches'
		self.ALL_MATCHES_FOR_HIGHLIGHT = [m[0:2] for m in text_matches] # Text matches only

		object_matches = list(_find_object_matches(self.buffer, query))
		assert len(object_matches) == 1, 'Should be 1 object match'
		self.FORWARD_MATCHES_FROM_LINE_TWO = tuple(sorted(text_matches + object_matches))
		rev_object_matches = [(l, c+1, m) for l, c, m in object_matches] # cursor *behind* object
		self.BACKWARD_MATCHES_FROM_LINE_TWO = tuple(reversed(sorted(text_matches + rev_object_matches)))

		self.TEXT_REPLACE_ONE = re.sub('\\btext\\b', 'mytext', self.TEXT, count=1)
		self.TEXT_REPLACE_ALL = re.sub('\\btext\\b', 'mytext', self.TEXT)


class MockSimplePluginObjectType():

	is_inline = True

	def data_from_model(self, model):
		return {}, model.data


class MockSimplePluginObjectModel():

	def __init__(self, data):
		self.data = data


class TestFindWithSimplePluginObject(tests.TestCase):

	DATA = 'Foo bar baz'

	def setUp(self):
		from zim.gui.pageview.objectanchors import PluginInsertedObjectAnchor

		self.anchor = PluginInsertedObjectAnchor(MockSimplePluginObjectType(), MockSimplePluginObjectModel(self.DATA))
		self.query = FindQuery('bar')

	def testFindNext(self):
		self._test_next_prev(self.anchor.find_next)

	def testFindPrevious(self):
		self._test_next_prev(self.anchor.find_previous)

	def _test_next_prev(self, method):
		self.assertTrue(method(self.query))
		self.assertTrue(self.anchor._find_match_highlight_state == FIND_HAS_MATCH)
		self.assertFalse(method(self.query)) # no "next" match if already highlighting current match
		self.assertTrue(self.anchor._find_match_highlight_state == 0)
		self.assertTrue(method(self.query))
		self.assertFalse(method(self.query)) # no "next" match if already highlighting current match

		self.assertTrue(method(self.query))
		self.assertTrue(self.anchor._find_match_highlight_state == FIND_HAS_MATCH)
		self.anchor.find_clear()
		self.assertTrue(self.anchor._find_match_highlight_state == 0)

		fail_query = FindQuery('No match!')
		self.assertFalse(method(fail_query))
		self.assertFalse(method(fail_query))

	def testHighlightAll(self):
		self.anchor.find_highlight_all(self.query)
		self.assertTrue(self.anchor._find_match_highlight_state == FIND_HAS_HIGHLIGHT)
		self.anchor.find_clear()
		self.assertTrue(self.anchor._find_match_highlight_state == 0)

	def testFindNextPreviousClearHighlight(self):
		# Test the implied statefull behavior
		self.anchor.find_highlight_all(self.query)
		self.assertTrue(self.anchor._find_match_highlight_state == FIND_HAS_HIGHLIGHT)
		self.assertTrue(self.anchor.find_next(self.query))
		self.assertTrue(self.anchor._find_match_highlight_state == FIND_HAS_HIGHLIGHT | FIND_HAS_MATCH)
		self.assertFalse(self.anchor.find_next(self.query))
		self.assertTrue(self.anchor._find_match_highlight_state == FIND_HAS_HIGHLIGHT)

		new_query = FindQuery('baz')
		self.assertTrue(self.anchor.find_next(new_query))
		self.assertTrue(self.anchor._find_match_highlight_state == FIND_HAS_MATCH)

	def testReplaceAtCursor(self):
		self.assertFalse(self.anchor.find_replace_at_cursor(self.query, 'foo')) # not supported

	def testReplaceAll(self):
		self.assertFalse(self.anchor.find_replace_all(self.query, 'foo')) # not supported


class MockPluginObjectModelWithOverload():

	def __init__(self, data):
		self.data = data

	def find_simple_match(self, query):
		return query.regex.search(self.data) is not None


class TestFindWithBackwardImageGeneratorPluginObject(TestFindWithSimplePluginObject):

	# Testing overload interface used for image generators

	def setUp(self):
		from zim.gui.pageview.objectanchors import PluginInsertedObjectAnchor

		self.anchor = PluginInsertedObjectAnchor(MockSimplePluginObjectType(), MockPluginObjectModelWithOverload(self.DATA))
		self.query = FindQuery('bar')


#class TestFindWithNestedTextBufferPluginObject(tests.TestCase):

#	def setUp(self):
#		pass

#	def testFindNext(self):
#		pass

#	def testFindPrevious(self):
#		pass

#	def testHighlightAll(self):
#		pass # include clear

#	def testFindNextPreviousClearHighlight(self):
#		# Test the implied statefull behavior
#		pass

#	def testReplaceAtCursor(self):
#		pass

#	def testReplaceAll(self):
#		pass


class TestFindOptionsWithTextBuffer(tests.TestCase, TextBufferTestCaseMixin):
		# Older set of tests, kept as "monkey testing" of the interface

	def runTest(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		buffer.set_text('''\
FOO FooBar FOOBAR
FooBaz Foo Bar
foo Bar Baz Foo
''')
		buffer.place_cursor(buffer.get_start_iter())

		# Check normal usage, case-insensitive
		for text in ('f', 'fo', 'foo', 'fo', 'f', 'F', 'Fo', 'Foo'):
			buffer.find_next(FindQuery(text))
			self.assertSelection(buffer, 0, 0, text.upper())
			buffer.find_clear() # prevent skip to next occurence

		buffer.find_next(FindQuery('Grr'))
		self.assertCursorPosition(buffer, 0, 0)

		buffer.find_next(FindQuery('Foob'))
		self.assertSelection(buffer, 0, 4, 'FooB')

		for line, offset, text in (
			(0, 11, 'FOOB'),
			(1, 0, 'FooB'),
			(0, 4, 'FooB'),
		):
			buffer.find_next(FindQuery('Foob'))
			self.assertSelection(buffer, line, offset, text)

		for line, offset, text in (
			(1, 0, 'FooB'),
			(0, 11, 'FOOB'),
			(0, 4, 'FooB'),
		):
			buffer.find_previous(FindQuery('Foob'))
			self.assertSelection(buffer, line, offset, text)

		# Case sensitive
		buffer.find_clear() # reset state
		buffer.find_next(FindQuery('Foo', FIND_CASE_SENSITIVE))
		self.assertSelection(buffer, 0, 4, 'Foo')

		for line, offset, text in (
			(1, 0, 'Foo'),
			(1, 7, 'Foo'),
			(2, 12, 'Foo'),
			(0, 4, 'Foo'),
		):
			buffer.find_next(FindQuery('Foo', FIND_CASE_SENSITIVE))
			self.assertSelection(buffer, line, offset, text)

		# Whole word
		buffer.find_clear() # reset state
		buffer.find_next(FindQuery('Foo', FIND_WHOLE_WORD))
		self.assertSelection(buffer, 1, 7, 'Foo')

		for line, offset, text in (
			(2, 0, 'foo'),
			(2, 12, 'Foo'),
			(0, 0, 'FOO'),
			(1, 7, 'Foo'),
		):
			buffer.find_next(FindQuery('Foo', FIND_WHOLE_WORD))
			self.assertSelection(buffer, line, offset, text)

		# Regular expression
		buffer.find_clear() # reset state
		query = FindQuery(r'Foo\s*Bar', FIND_REGEX | FIND_CASE_SENSITIVE)
		buffer.find_next(query)
		self.assertSelection(buffer, 1, 7, 'Foo Bar')
		buffer.find_next(query)
		self.assertSelection(buffer, 0, 4, 'FooBar')
