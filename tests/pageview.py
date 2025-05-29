# Copyright 2009-2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests
from tests import os_native_path

import logging
import os


logger = logging.getLogger('tests.pageview')


from zim.plugins import PluginManager
from zim.newfs import LocalFile, LocalFolder
from zim.config import XDG_DATA_HOME
from zim.formats import get_format, ParseTree
from zim.notebook import Path
from zim.gui.clipboard import Clipboard

from zim.gui.pageview import *
from zim.gui.pageview.lists import TextBufferList
from zim.gui.pageview.textview import camelcase
from zim.gui.pageview.serialize import *
from zim.gui.pageview.undostack import UndoStackManager


class FilterNoSuchImageWarning(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self, 'zim.gui.pageview', 'No such image:')


def setUpPageView(notebook, text=''):
	'''Some bootstrap code to get an isolated PageView object'''
	page = notebook.get_page(Path('Test'))
	page.parse('wiki', text)
	notebook.store_page(page)

	navigation = tests.MockObject(methods=('open_page', 'open_notebook'))
	pageview = PageView(notebook, navigation)
	pageview.set_page(page)
	return pageview


def get_text(buffer):
	start, end = buffer.get_bounds()
	return start.get_slice(end)


LINE_TEXT = '-' * 20

class TestLines(tests.TestCase):

	def testLines(self):
		'''Test lines formatting.'''

		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()

		def check_text(input, result):
			buffer.set_text(input)
			tree = buffer.get_parsetree()
			dumper = get_format('wiki').Dumper()
			text = ''.join(dumper.dump(tree))
			self.assertEqual(text, result)

		# Check formatting.
		string = 'text... \n{}\n text... \n'
		input = string.format('-' * 4)
		check_text(input, input) # doesn't format
		for i in range(30):
			if i < 5:
				output = string.format('-' * i)
			else:
				output = string.format(LINE_TEXT)
			input = string.format('-' * i)
			check_text(input, output)

		# Check that any additional symbol other than '-' fails.
		input = 'text... {}\n text... \n'.format('-' * 10)
		check_text(input, input)
		input = 'text... \n{}text... \n'.format('-' * 10)
		check_text(input, input)
		input = 'text... \n{} \n text... \n'.format('-' * 10)
		check_text(input, input)
		input = 'text... \n {}\n text... \n'.format('-' * 10)
		check_text(input, input)

		# Check more complex text.
		string = 'text... \n\n{0}\n\n{0}\n\n text... \n'
		input = string.format('-' * 7)
		output = string.format(LINE_TEXT)
		check_text(input, output)

		string = '... \n{}\n{}\n{}\n ... \n{}\n{}0\n'
		input = string.format('-' * 8, '-' * 6, '-' * 4, '-' * 11, '-' * 10)
		output = string.format(LINE_TEXT, LINE_TEXT, '-' * 4, LINE_TEXT, '-' * 10)
		check_text(input, output)



class TextBufferTestCaseMixin(object):
	# Mixin class with extra test methods

	def get_buffer(self, content=None):
		'''Create a new L{TextBuffer}
		@param content: buffer contents, see L{set_buffer()} for supported formats
		'''
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		if content is not None:
			self.set_buffer(buffer, content)
			buffer.undostack.clear_undostack()
		return buffer

	def set_buffer(self, buffer, content):
		'''Set L{TextBuffer} contents
		If using xml contents, it can be treated as either L{ParseTree} xml or L{TextBufferInternalContents}
		xml. This depends on the xml tag `<zim-tree>` being present or not
		@param content: buffer content as xml, L{ParseTree}, tokens or L{TextBufferInternalContents}
		'''
		input = content
		if isinstance(content, (list, tuple)):
			raise NotImplementedError('Support tokens') # TODO convert to ParseTree
		elif isinstance(content, str):
			if '<zim-tree>' in content:
				if not content.startswith('<?xml'):
					content = '''<?xml version='1.0' encoding='utf-8'?>\n%s''' % content
				content = tests.new_parsetree_from_xml(content)
			else:
				# assume textbuffer internal
				if not content.startswith('<zim-textbuffer>'):
					content = '<zim-textbuffer>%s</zim-textbuffer>' % content
				content = TextBufferInternalContents.new_from_xml(content)

		if isinstance(content, ParseTree):
			with FilterNoSuchImageWarning():
				buffer.set_parsetree(content)
			self.assertParseTreeEqual(buffer, input, 'Set/get failed on `set_buffer()`') # Set/get test
		elif isinstance(content, TextBufferInternalContents):
			buffer.clear()
			with FilterNoSuchImageWarning():
				textbuffer_internal_insert_at_cursor(buffer, content)
			self.assertBufferEqual(buffer, input, 'Set/get failed on `set_buffer()`') # Set/get test
		else:
			raise TypeError('Unsupported input type: %s', content)

	def assertParseTreeEqual(self, parsetree, wanted, msg=None):
		'''Compare L{ParseTree} contents
		NOTE: This method compares the L{ParseTree} content, which is cleaned up to adhere to the formatting
		rules, if you are interrested in the internal state of a L{TextBuffer} use L{assertBufferEqual()} instead
		@param content: either a L{ParseTree}, xml or token representation, or any object supporting C{get_parsetree()}
		@param wanted: either a L{ParseTree}, xml or token representation, or any object supporting C{get_parsetree()}
		'''
		parsetree = self._parsetree_like_to_xml(parsetree)
		wanted = self._parsetree_like_to_xml(wanted)
		self.assertEqual(parsetree, wanted, msg)

	def _parsetree_like_to_xml(self, content):
		if hasattr(content, 'get_parsetree'):
			content = content.get_parsetree()

		if isinstance(content, (tuple, list)):
			raise NotImplementedError('Convert tokens to ParseTree')
			# return parsetree.tostring()
		elif isinstance(content, str):
			if not content.startswith('<?xml') and '<zim-tree' not in content:
				content = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>%s</zim-tree>''' % content
			elif not content.startswith('<?xml'):
				content = '''<?xml version='1.0' encoding='utf-8'?>\n%s''' % content
			return content
		elif isinstance(content, ParseTree):
			return content.tostring()
		else:
			raise TypeError('Unsupported input type: %s', content)

	def assertBufferEqual(self, buffer, wanted, msg=None):
		'''Compare L{TextBuffer} contents
		NOTE: this method compares the internal state of the L{TextBuffer}, if you are only interested in 
		the resulting L{ParseTree}, use L{assertParseTreeEqual()} instead
		@param buffer: a L{TextBuffer}, L{TextBufferInternalContents}, or xml representation
		@param wanted: a L{TextBuffer}, L{TextBufferInternalContents}, or xml representation
		'''
		buffer = self._buffer_like_to_xml(buffer)
		wanted = self._buffer_like_to_xml(wanted)
		self.assertEqual(buffer, wanted, msg)

	def _buffer_like_to_xml(self, buffer):
		if isinstance(buffer, TextBuffer):
			data = textbuffer_internal_serialize_range(buffer, *buffer.get_bounds())
			return data.to_xml()
		elif isinstance(buffer, TextBufferInternalContents):
			return buffer.to_xml()
		elif isinstance(buffer, str):
			assert '<zim-tree' not in buffer, 'Expected buffer contents, got parsetree'
			if not buffer.startswith('<zim-textbuffer>'):
				buffer = '<zim-textbuffer>%s</zim-textbuffer>' % buffer
			return buffer
		else:
			raise TypeError('Unsupported input type: %s', buffer)

	def assertSelection(self, buffer, line, offset, string):
		bound = buffer.get_selection_bounds()
		self.assertTrue(bound, msg="There is no selection")
		selection = bound[0].get_slice(bound[1])
		self.assertEqual(selection, string, msg="Selection matches >%s< instead of >%s<" % (selection, string))
		self.assertCursorPosition(buffer, line, offset, msg="Selection does not start at line %i pos %i" % (line, offset))
			# least informative check done last - will only hit if right string is matched in wrong location

	def assertCursorPosition(self, buffer, line, offset, msg=None):
		msg = msg or "Cursor is not a line %i pos %i" % (line, offset)
		#~ print('CHECK', line, offset, text)
		cursor = buffer.get_insert_iter()
		#~ print('  GOT', cursor.get_line(), cursor.get_line_offset())
		self.assertEqual(cursor.get_line(), line, msg=msg)
		self.assertEqual(cursor.get_line_offset(), offset, msg=msg)

	def print_buffer(self, buffer):
		print(self._buffer_like_to_xml(buffer))


class TestTextBuffer(tests.TestCase, TextBufferTestCaseMixin):

	def testFormatRoundTrip(self):
		tree = tests.new_parsetree() # uses tests/data/formats/wiki.txt
		dumper = get_format('wiki').Dumper()
		wikitext = ''.join(dumper.dump(tree))

		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(tree)

		newtree = buffer.get_parsetree()
		newwikitext = ''.join(dumper.dump(newtree))

		self.assertEqual(newwikitext, wikitext)

	def testFormatRoundTripSimple(self):
		# Added this one specifically to check newline handling around list
		# items and headings
		dumper = get_format('wiki').Dumper()
		parser = get_format('wiki').Parser()
		wikitext = '''\
=== A list ===

* item 1
* item 2
* item 3
	* item a
	* item b
* item 4

Text before heading
== Head ==
Some para with //italic// and **bold**

== Head with **bold** ==
More text

'''
		tree = parser.parse(wikitext)

		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(tree)

		newtree = buffer.get_parsetree()
		newwikitext = ''.join(dumper.dump(newtree))

		self.assertEqual(newwikitext, wikitext)

	def testGetPartialParseTree(self):
		# See issue #1895 for bug found here
		# Select list item until end of line, not including newline
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p><ul><li bullet="*">Item 1
</li><li bullet="*">Item 2
</li></ul></p>
</zim-tree>'''
		wanted_with_newline = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul><li bullet="*">Item 1
</li><li bullet="*">Item 2
</li></ul></p></zim-tree>'''
		wanted_without_newline = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul><li bullet="*">Item 1
</li><li bullet="*">Item 2</li></ul></p></zim-tree>'''

		buffer = self.get_buffer(input)

		start = buffer.get_iter_at_line(1)
		end = buffer.get_iter_at_line(2)
		end.forward_line()
		result = buffer.get_parsetree(bounds=(start, end))
		self.assertEqual(result.tostring(), wanted_with_newline)

		start = buffer.get_iter_at_line(1)
		end = buffer.get_iter_at_line(2)
		end.forward_to_line_end()
		result = buffer.get_parsetree(bounds=(start, end))
		self.assertEqual(result.tostring(), wanted_without_newline)

		newbuffer = self.get_buffer()
		newbuffer.insert_parsetree_at_cursor(result)
		result = newbuffer.get_parsetree()
		self.assertEqual(result.tostring(), wanted_without_newline)

	def testSetParseTreeDoesNotModify(self):
		# Ensure insert does not modify tree (e.g. attrib types)
		# comparing tokens to avoid xml flattening
		tree = tests.new_parsetree()
		tokens = list(tree.iter_tokens())
		buffer = self.get_buffer(tree)
		self.assertEqual(tokens, list(tree.iter_tokens()))

	def testPasteFormattedText(self):
		buffer = self.get_buffer('''\
<zim-tree><h level="2">foo
</h><p>bar
</p>
<p><ul><li bullet="*">Foo
</li><li bullet="*">Bar
</li></ul></p></zim-tree>''')
		pastetree = tests.new_parsetree_from_xml('''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><strong>Bold</strong></zim-tree>''')
		iter = buffer.get_iter_at_line(3)
		iter.forward_chars(5) # position after "* Foo"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		iter = buffer.get_iter_at_line(4) # position before bullet "* Bar"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		self.assertTrue(buffer.get_modified())
		self.assertParseTreeEqual(buffer, '''\
<zim-tree><h level="2">foo
</h><p>bar
</p>
<p><ul><li bullet="*">Foo<strong>Bold</strong>
</li><li bullet="*"><strong>Bold</strong>Bar
</li></ul></p></zim-tree>''')

	def testPasteList(self):
		# Paste list halfway and see result is OK
		# because of the bullets pasting should go to a new line
		# automatically
		buffer = self.get_buffer('''\
<zim-tree><h level="2">foo
</h><p>bar
</p>
<p><ul><li bullet="*">Foo
</li><li bullet="*">Bar
</li></ul></p></zim-tree>''')
		pastetree = tests.new_parsetree_from_xml('''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><li bullet="*">Foo
</li><li bullet="*">Bar
</li></zim-tree>''')
		iter = buffer.get_iter_at_line(1)
		iter.forward_chars(3) # position after "baz"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		self.assertTrue(buffer.get_modified())
		self.assertParseTreeEqual(buffer, '''\
<h level="2">foo
</h><p>bar
<ul><li bullet="*">Foo
</li><li bullet="*">Bar
</li></ul></p>

<p><ul><li bullet="*">Foo
</li><li bullet="*">Bar
</li></ul></p>''')

	def testRobustForUTF8PlaceholderCharacter(self):
		buffer = self.get_buffer('foo \uFFFC bar')
		self.assertBufferEqual(buffer, 'foo \uFFFC bar')
		self.assertParseTreeEqual(buffer, '<zim-tree><p>foo  bar</p></zim-tree>')

	def testStringEscapeDoesNotGetEvaluated(self):
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p>this is not a newline: \\name
This is not a tab: \\tab
</p></zim-tree>'''
		buffer = self.get_buffer(input)
		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), input)

	def testReplace(self):
		# Check replacing a formatted word
		# word is deleted, but formatting should stay
		input = 'aaa <strong>bbb</strong> ccc'
		wanted = 'aaa <strong>eee</strong> ccc'

		buffer = self.get_buffer(input)
		iter = buffer.get_iter_at_offset(6) # middle of "bbb"
		buffer.place_cursor(iter)
		buffer.select_word()

		with buffer.user_action:
			buffer.delete_selection(True, True)
			buffer.insert_interactive_at_cursor("eee", 3, True)

		self.assertBufferEqual(buffer, wanted)

	def testSelectLink(self):
		input = 'aaa <link href="xxx">bbb</link> ccc'
		buffer = self.get_buffer(input)
		buffer.place_cursor(buffer.get_iter_at_offset(6)) # middle of link

		self.assertIsNone(buffer.get_has_link_selection())
		data = buffer.select_link()
		self.assertEqual(data['href'], 'xxx')
		self.assertEqual(buffer.get_has_link_selection(), data)

	def testSelectWord(self):
		buffer = self.get_buffer('Test 123. foo\n')

		buffer.place_cursor(buffer.get_iter_at_offset(6))
		buffer.select_word()
		self.assertSelection(buffer, 0, 5, '123')

		buffer.select_word()
		self.assertSelection(buffer, 0, 5, '123') # no change

		buffer.place_cursor(buffer.get_iter_at_offset(33))
		buffer.select_word()
		self.assertFalse(buffer.get_has_selection()) # middle of whitespace

	def testStripSelection(self):
		buffer = self.get_buffer('Test 123. foo\n')

		# existing selection needs stripping
		start = buffer.get_iter_at_offset(4)
		end = buffer.get_iter_at_offset(10)
		buffer.select_range(start, end)
		self.assertSelection(buffer, 0, 4, ' 123. ')
		buffer.strip_selection()
		self.assertSelection(buffer, 0, 5, '123.')

	def testSelectLines(self):
		buffer = self.get_buffer('Test 123. foo\nline with spaces    \n\n')

		# select line (with / without previous selection)
		buffer.place_cursor(buffer.get_iter_at_offset(6))
		buffer.select_word()
		self.assertSelection(buffer, 0, 5, '123')
		buffer.select_lines_for_selection()
		self.assertSelection(buffer, 0, 0, 'Test 123. foo\n') # extended

		buffer.select_lines_for_selection()
		self.assertSelection(buffer, 0, 0, 'Test 123. foo\n') # no change

		buffer.place_cursor(buffer.get_iter_at_offset(6))
		self.assertFalse(buffer.get_has_selection())
		buffer.select_lines_for_selection()
		self.assertSelection(buffer, 0, 0, 'Test 123. foo\n')

		# empty line
		buffer.place_cursor(buffer.get_iter_at_line(3))
		self.assertFalse(buffer.get_has_selection())
		buffer.select_lines_for_selection()
		self.assertFalse(buffer.get_has_selection())

	def testToggleTextStylePre(self):
		buffer = self.get_buffer('''\
A
<div indent="1">B
</div>C
<div indent="1">D
</div>''')
		start, end = buffer.get_bounds()
		buffer.select_range(start, end)
		buffer.toggle_format_tag_by_name('pre')
		self.assertBufferEqual(buffer, '''\
<pre>A
	B
C
	D
</pre>''')

	def testToggleTextStyleCodeOverTag(self):
		buffer = self.get_buffer('foo <tag name="None">@test</tag> bar')
		buffer.select_line(0)
		buffer.toggle_format_tag_by_name('code')
		self.assertBufferEqual(buffer, '<code>foo @test bar</code>')

	def testMergeLinesVarious(self):
		# Test merge lines logic on delete
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><h level="1">Foo
</h>
<h level="2">Bar
</h>
<p><ul><li bullet="*">List item 0
</li></ul></p>
<p><ul indent="1"><li bullet="*">List item 1
</li></ul></p></zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><h level="1">FooBar
</h>
<p>List item 0
</p>
<p><div indent="1">List item 1
</div></p></zim-tree>'''
		# Note: we don't insert extra newlines, but <li> assumes them
		buffer = self.get_buffer(input)

		iter = buffer.get_iter_at_line(2) # before h2
		bound = iter.copy()
		iter.backward_chars(2) # after h1
		buffer.delete(iter, bound)

		iter = buffer.get_iter_at_line(2) # list item 0
		bound = iter.copy()
		bound.forward_chars(2) # Behind bullet
		buffer.delete(iter, bound)

		iter = buffer.get_iter_at_line(4) # list item 1
		bound = iter.copy()
		bound.forward_chars(2) # Behind bullet
		buffer.delete(iter, bound)

		self.assertParseTreeEqual(buffer, wanted)

	def assertMergeLines(self, input, output, line=0, offset=None):
		buffer = self.get_buffer(input)
		iter = buffer.get_iter_at_line(line)
		if offset is not None:
			iter.forward_chars(offset)
		else:
			iter.forward_to_line_end()
		end = iter.copy()
		end.forward_char()
		buffer.place_cursor(iter)

		with buffer.user_action:
			buffer.delete_interactive(iter, end, True)
		self.assertBufferEqual(buffer, output)

		# Check undo / redo of special handling of bullets at merge - see issue #1949
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, input)
		buffer.undostack.redo()
		self.assertBufferEqual(buffer, output)

	def testMergeLinesWithBullet(self):
		# Ensure that bullet of line 2 is removed, in raw tree also the space is gone
		self.assertMergeLines(
			'<li indent="0" style="bullet-list">\u2022 item 1\n\u2022 item 2\n</li>',
			'<li indent="0" style="bullet-list">\u2022 item 1item 2\n</li>'
		)

	def testMergeLinesWithNumberedBullet(self):
		# Ensure that bullet of line 2 is removed, in raw tree also the space is gone
		self.assertMergeLines(
			'<li indent="0" style="numbered-list">1. item 1\n2. item 2\n</li>',
			'<li indent="0" style="numbered-list">1. item 1item 2\n</li>'
		)

	def testMergeLinesWithBulletWithNotABullet(self):
		# Check numer at start of 2nd bullet is preserved - see issue #1949
		self.assertMergeLines(
			'<li indent="0" style="bullet-list">\u2022 item 1\n\u2022 1. item 2\n</li>',
			'<li indent="0" style="bullet-list">\u2022 item 11. item 2\n</li>'
		)

	def testMergeLinesWithNotABulletWithoutNewline(self):
		# See issue #1328, avoid accidental removal of something that looks
		# like a bullet
		self.assertMergeLines(
			'<li indent="0" style="bullet-list">\u2022 item 1 123. test\n</li>',
			'<li indent="0" style="bullet-list">\u2022 item 1123. test\n</li>',
			line=0, offset=8 # Position at after "item 1"
		)

	def testMergeLinesWithNotABulletAfterNewline(self):
		# See issue #1328, avoid accidental removal of something that looks
		# like a bullet
		self.assertMergeLines(
			'<li indent="0" style="bullet-list">\u2022 item 1\n</li>123. test\n',
			'<li indent="0" style="bullet-list">\u2022 item 1123. test\n</li>'
		)

	def testMergeLinesNewlineAfterListItem(self):
		# Ensure that trailing newline gets formatted as well
		self.assertMergeLines(
			'<li indent="0" style="bullet-list">\u2022 item 1\n</li>\ntext\n',
			'<li indent="0" style="bullet-list">\u2022 item 1\n</li>text\n',
		)

	def testMergeLinesNewlineAfterHeading(self):
		# Ensure that trailing newline gets formatted as well
		self.assertMergeLines(
			'<h level="1">head\n</h>\ntext\n',
			'<h level="1">head\n</h>text\n',
		)

	def testMergeLinesNewlineAfterPre(self):
		# Ensure that trailing newline gets formatted as well
		self.assertMergeLines(
			'<pre>pre formatted\n</pre>\ntext\n',
			'<pre>pre formatted\n</pre>text\n',
		)

	def testFormatHeading(self):
		buffer = self.get_buffer('foo bar\n')
		for lvl in range(1, 7):
			buffer.select_line(0)
			buffer.toggle_format_tag_by_name('h%i' % lvl)
			self.assertBufferEqual(buffer, '<h level="%i">foo bar\n</h>' % lvl)

	def testFormatHeadingWithFormatting(self):
		buffer = self.get_buffer('<code>foo</code> <strong>bar</strong> <link href="None">Foo</link>\n')
		buffer.select_line(0)
		buffer.toggle_format_tag_by_name('h2')
		self.assertBufferEqual(buffer, '<h level="2"><code>foo</code> <strong>bar</strong> <link href="None">Foo</link>\n</h>')

	def testFormatHeadingOnIndent(self):
		buffer = self.get_buffer('<div indent="2">foo bar\n</div>')
		buffer.select_line(0)
		buffer.toggle_format_tag_by_name('h2')
		self.assertBufferEqual(buffer, '<h level="2">foo bar\n</h>')

	def testFormatHeadingOnList(self):
		buffer = self.get_buffer('<li indent="0" style="numbered-list">1. foo bar\n</li>')
		buffer.select_line(0)
		buffer.toggle_format_tag_by_name('h2')
		self.assertBufferEqual(buffer, '<h level="2">1. foo bar\n</h>')

	def testFormatHeadingOnAnchor(self):
		buffer = self.get_buffer('Foo bar <anchor name="bar" />')
		buffer.select_line(0)
		buffer.toggle_format_tag_by_name('h2')
		self.assertBufferEqual(buffer, '<h level="2">Foo bar <anchor name="bar" /></h>')

	def testBreakHeadingOnNewline(self):
		buffer = self.get_buffer('<h level="1">Heading\n</h>')
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>')

		buffer.place_cursor(buffer.get_iter_at_offset(7))
		with buffer.user_action:
			buffer.insert_at_cursor('\n')
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>\n')
		with buffer.user_action:
			buffer.insert_at_cursor('test 123')
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>test 123\n')

		# Check undo stack since this is special case in do_insert_text()
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>\n')
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>')

		# Check for special case at end of buffer
		buffer = self.get_buffer('<h level="1">Heading</h>')
		buffer.place_cursor(buffer.get_iter_at_offset(7))
		buffer.insert_at_cursor('\n')
		buffer.insert_at_cursor('test 123')
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>test 123')

	def testMoveHeadingOnNewlineAtStart(self):
		# Newline at start of heading should not result in empty line
		# with heading tag, insetad move heading down and leave normal line
		buffer = self.get_buffer('<h level="1">Heading\n</h>')
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>')

		buffer.place_cursor(buffer.get_iter_at_offset(0))
		with buffer.user_action:
			buffer.insert_at_cursor('\n')
		self.assertBufferEqual(buffer, '\n<h level="1">Heading\n</h>')
		with buffer.user_action:
			buffer.insert_at_cursor('test 123')
		self.assertBufferEqual(buffer, '\n<h level="1">test 123Heading\n</h>')

		# Check undo stack since this is special case in do_insert_text()
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, '\n<h level="1">Heading\n</h>')
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, '<h level="1">Heading\n</h>')

	def testMoveIndentOnNewlineAtStart(self):
		buffer = self.get_buffer('<div indent="2">Test 123\n</div>')
		self.assertBufferEqual(buffer, '<div indent="2">Test 123\n</div>')

		buffer.place_cursor(buffer.get_iter_at_offset(0))
		with buffer.user_action:
			buffer.insert_at_cursor('\n')
		self.assertBufferEqual(buffer, '\n<div indent="2">Test 123\n</div>')

	def testMoveVerbatimBlockOnNewlineAtStart(self):
		buffer = self.get_buffer('<pre>Test 123\n</pre>')
		self.assertBufferEqual(buffer, '<pre>Test 123\n</pre>')

		buffer.place_cursor(buffer.get_iter_at_offset(0))
		with buffer.user_action:
			buffer.insert_at_cursor('\n')
		self.assertBufferEqual(buffer, '\n<pre>Test 123\n</pre>')

	def testFindAnchor(self):
		buffer = self.get_buffer()
		self.assertIsNone(buffer.find_anchor('test'))
		# explicit anchor
		buffer = self.get_buffer('Some text <anchor name="test" />\n')
		self.assertIsNotNone(buffer.find_anchor('test'))
		# explicit anchor with text
		buffer = self.get_buffer('Some text <anchor name="test" />\n')
		self.assertIsNotNone(buffer.find_anchor('test'))

	def testFindImageAnchor(self):
		file = tests.ZIM_DATA_FOLDER.file('zim.png')
		notebook = tests.MockObject(
			return_values={
				'resolve_file': file,
				'relative_filepath': './data/zim.png'
			}
		)
		buffer = TextBuffer(notebook, page=None)
		buffer.insert_image_at_cursor(file, "https://en.wikipedia.org/wiki/File:Zim_globe.svg", width="48", id="image:globe")
		self.assertIsNotNone(buffer.find_anchor('image:globe'))

	def testFindObjectAnchor(self):
		buffer = self.get_buffer(
			'<object id="code:1" lang="python3" linenumbers="True" type="code">import unittest\n'
			'\n'
			'class MyTests(unittest.TestCase):\n'
			'  def test_1():\n'
			'    pass\n'
			'</object>\n'
		)
		self.assertIsNotNone(buffer.find_anchor('code:1'))

	def testFindImplicitAnchor(self):
		# basic case
		buffer = self.get_buffer('<h level="1">Title\n</h>')
		self.assertIsNotNone(buffer.find_anchor('title'))
		# with blanks
		buffer = self.get_buffer('<h level="2">foo bar\n</h>')
		self.assertIsNotNone(buffer.find_anchor('foo-bar'))
		# with styled text
		buffer = self.get_buffer('<h level="2"><code>foo</code> bar\n</h>')
		self.assertIsNotNone(buffer.find_anchor('foo-bar'))

	def testGetAnchorAtSameIter(self):
		buffer = self.get_buffer('Some text <anchor name="test" />\n')
		iter = buffer.get_iter_at_offset(10)
		anchor = buffer.get_anchor_for_location(iter)
		self.assertEqual(anchor, 'test') # pick one at iter

	def testGetAnchorNearbyIter(self):
		buffer = self.get_buffer('Some <anchor name="anchor1" /> text <anchor name="test" />\n')
		iter = buffer.get_iter_at_offset(8)
		anchor = buffer.get_anchor_for_location(iter)
		self.assertEqual(anchor, 'anchor1') # pick closest one

	def testGetAnchorAtSameIterForImage(self):
		buffer = self.get_buffer('Some text <img id="anchor1" src="./foo.png" />\n')
		iter = buffer.get_iter_at_offset(10)
		anchor = buffer.get_anchor_for_location(iter)
		self.assertEqual(anchor, 'anchor1') # pick one at iter

	def testGetAnchorNearbyIterForImage(self):
		buffer = self.get_buffer('Some <img id="anchor1" src="./foo.png" /> text <anchor name="test" />\n')
		iter = buffer.get_iter_at_offset(8)
		anchor = buffer.get_anchor_for_location(iter)
		self.assertEqual(anchor, 'anchor1') # pick closest one

	def testGetAnchorForHeadingExplicit(self):
		buffer = self.get_buffer('<h level="2">Some heading <anchor name="test" />\n</h>')
		iter = buffer.get_iter_at_offset(2)
		anchor = buffer.get_anchor_for_location(iter)
		self.assertEqual(anchor, 'test') # prefer explicit over implicit

	def testGetAnchorForHeadingImplicit(self):
		buffer = self.get_buffer('<h level="2">Some heading\n</h>')
		iter = buffer.get_iter_at_offset(2)
		anchor = buffer.get_anchor_for_location(iter)
		self.assertEqual(anchor, 'some-heading') # implicit heading anchor

	def testReNumberList(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">2. foo bar\n'
			'5. foo bar\n'
			'7. foo bar\n</li>'
		)
		buffer.renumber_list(1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">2. foo bar\n'
			'3. foo bar\n'
			'4. foo bar\n</li>'
		)

	def testReNumberListWithBullet(self):
		# Must break at bullet
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
			'<li indent="0" style="numbered-list">7. foo bar\n</li>'
		)
		for line in (0, 1, 2):
			buffer.renumber_list(line)
			self.assertBufferEqual(	# Raw content
				buffer,
				'<li indent="0" style="numbered-list">2. foo bar\n</li>'
				'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
				'<li indent="0" style="numbered-list">7. foo bar\n</li>'
			)
			self.assertParseTreeEqual(	# Serialize towards formatter
				buffer,
				'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
				'<zim-tree><p>'
				'<ol start="2"><li>foo bar\n</li></ol>'
				'<ul><li bullet="*">foo bar\n</li></ul>'
				'<ol start="7"><li>foo bar\n</li></ol>'
				'</p></zim-tree>'
			)

	def testReNumberListWithCheckbox(self):
		# Must break at checkbox
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo bar\n</li>'
			'<li indent="0" style="numbered-list">7. foo bar\n</li>'
		)
		for line in (0, 1, 2):
			buffer.renumber_list(line)
			self.assertBufferEqual(	# Raw content
				buffer,
				'<li indent="0" style="numbered-list">2. foo bar\n</li>'
				'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo bar\n</li>'
				'<li indent="0" style="numbered-list">7. foo bar\n</li>'
			)
			self.assertParseTreeEqual(	# Serialize towards formatter
				buffer,
				'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
				'<zim-tree><p>'
				'<ol start="2"><li>foo bar\n</li></ol>'
				'<ul><li bullet="unchecked-box">foo bar\n</li></ul>'
				'<ol start="7"><li>foo bar\n</li></ol>'
				'</p></zim-tree>'
			)

	def testReNumberListAfterIndentTop(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">2. foo bar\n' # was indented
			'a. foo bar\n'
			'b. foo bar\n</li>'
			'<li indent="0" style="numbered-list">3. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 0)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n' # was indented
			'b. foo bar\n'
			'c. foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)

	def testReNumberListAfterUnIndentTop(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n'
			'a. foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">b. foo bar\n'
			'c. foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n'
			'2. foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">a. foo bar\n'
			'b. foo bar\n</li>'
			'<li indent="0" style="numbered-list">3. foo bar\n</li>'
		)

	def testReNumberListAfterIndentMiddle(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n'
			'2. foo bar\n' # was indented
			'a. foo bar\n</li>'
			'<li indent="0" style="numbered-list">3. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(2, 0)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n'
			'b. foo bar\n' # was indented
			'c. foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)

	def testReNumberListAfterUnIndentMiddle(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n</li>'
			'<li indent="0" style="numbered-list">b. foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">c. foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(2, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">a. foo bar\n</li>'
			'<li indent="0" style="numbered-list">3. foo bar\n</li>'
		)

	def testReNumberListAfterIndentBottom(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n'
			'b. foo bar\n'
			'2. foo bar\n</li>' # was indented
			'<li indent="0" style="numbered-list">3. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(3, 0)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n'
			'b. foo bar\n'
			'c. foo bar\n</li>' # was indented
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)

	def testReNumberListAfterUnIndentBottom(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n'
			'b. foo bar\n</li>'
			'<li indent="0" style="numbered-list">c. foo bar\n' # was unindented
			'2. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(3, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n'
			'b. foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n' # was unindented
			'3. foo bar\n</li>'
		)

	def assertRenumberListAfterIndentForNewNumberSublist1(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">2. foo bar\n</li>' # was indented
			'<li indent="0" style="numbered-list">3. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="1" style="numbered-list">a. foo bar\n</li>' # was indented
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)

	def assertRenumberListAfterIndentForNewNumberSublist2(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">a. foo bar\n</li>'
			'<li indent="1" style="numbered-list">b. foo bar\n</li>' # was indented
			'<li indent="0" style="numbered-list">c. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">a. foo bar\n</li>'
			'<li indent="1" style="numbered-list">1. foo bar\n</li>' # was indented
			'<li indent="0" style="numbered-list">b. foo bar\n</li>'
		)

	def assertRenumberListAfterIndentForNewBulletSublist(self):
		buffer = self.get_buffer(
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
			'<li indent="1" style="bullet-list">\u2022 foo bar\n</li>' # was indented
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
			'<li indent="1" style="bullet-list">\u2022 foo bar\n</li>' # was indented
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
		)

	def assertRenumberListAfterUnindentCovertsBulletToNumber(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>' # was unindented
			'<li indent="1" style="bullet-list">\u2022 foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n'
			'2. foo bar\n</li>' # was unindented
			'<li indent="1" style="bullet-list">\u2022 foo bar\n</li>'
			'<li indent="0" style="numbered-list">3. foo bar\n</li>'
		)

	def testReNumberListAfterUnIndentDoesNotTouchCheckbox(self):
		buffer = self.get_buffer(
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo bar\n</li>' # was unindented
			'<li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="numbered-list">1. foo bar\n</li>'
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo bar\n</li>' # was unindented
			'<li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo bar\n</li>'
			'<li indent="0" style="numbered-list">2. foo bar\n</li>'
		)

	def assertRenumberListAfterUnindentCovertsNumberToBullet(self):
		buffer = self.get_buffer(
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
			'<li indent="0" style="numbered-list">1. foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">2. foo bar\n</li>'
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="bullet-list">\u2022 foo bar\n'
			'\u2022 foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">1. foo bar\n</li>'
			'<li indent="0" style="bullet-list">\u2022 foo bar\n</li>'
		)

	def assertRenumberListAfterUnindentCovertsNumberToCheckbox(self):
		buffer = self.get_buffer(
			'<li indent="0" style="checked-box"><icon stock="zim-checked-box" /> foo bar\n</li>'
			'<li indent="0" style="numbered-list">1. foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">2. foo bar\n</li>'
			'<li indent="0" style="checked-box"><icon stock="zim-checked-box" /> foo bar\n</li>'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEqual(
			buffer,
			'<li indent="0" style="checked-box"><icon stock="zim-checked-box" /> foo bar\n</li>'
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo bar\n</li>' # was unindented
			'<li indent="1" style="numbered-list">1. foo bar\n</li>'
			'<li indent="0" style="checked-box"><icon stock="zim-checked-box" /> foo bar\n</li>'
		)

	def testNestedFormattingRoundtrip(self):
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>normal <strong>bold</strong> normal2
normal <strike>strike  <strong>nested bold</strong> strike2</strike> normal2
normal <strike>strike  <strong>nested bold</strong> strike2</strike> <emphasis>italic <link href="https://example.org">link</link></emphasis> normal2
normal <strike>strike  <strong>nested bold</strong> strike2 <emphasis>striked italic <strong>bold link coming: <link href="https://example.org">link</link></strong></emphasis></strike> normal2
</p></zim-tree>'''
		buffer = self.get_buffer(xml)
		self.assertParseTreeEqual(buffer, xml)

	def testLinkWithFormatting(self):
		#text = '[[http://example.com| //Example// ]]' # spaces are crucial in this example - see issue #1306
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><link href="http://example.com"> <emphasis>Example</emphasis> </link>
</p></zim-tree>'''
		buffer = self.get_buffer(xml)
		self.assertParseTreeEqual(buffer, xml)

	def testLinkWithoutTargetDirectEditable(self):
		buffer = self.get_buffer('<zim-tree><p><link href="Test">Test</link>\n</p></zim-tree>')
		buffer.place_cursor(buffer.get_iter_at_offset(4))
		buffer.insert_at_cursor('Link')
		self.assertParseTreeEqual(buffer, '<zim-tree><p><link href="TestLink">TestLink</link>\n</p></zim-tree>')

	def testLinkWithoutTargetDirectEditableWhileFormatted(self):
		buffer = self.get_buffer('<zim-tree><p><link href="TestFormatted">Test<strong>Formatted</strong></link>\n</p></zim-tree>')
		buffer.place_cursor(buffer.get_iter_at_offset(13))
		buffer.insert_at_cursor('Link')
		self.assertParseTreeEqual(buffer, '<zim-tree><p><link href="TestFormattedLink">Test<strong>FormattedLink</strong></link>\n</p></zim-tree>')

	def testFormatWithinCode(self):
		# No format nests within verbatim, so needs to break up in multiple parts
		buffer = self.get_buffer('test <strong>strong</strong> test')
		code_tag = buffer.get_tag_table().lookup('style-code')
		bounds = buffer.get_bounds()
		buffer.apply_tag(code_tag, *bounds)
		self.assertBufferEqual(buffer, '<code>test </code><strong><code>strong</code></strong><code> test</code>')

	def testIllegalNestedTagTag(self):
		# Code and @tag are incompatible formats. When applied to the same region, the code part is dropped
		buffer = self.get_buffer('test <tag name="None">@tag</tag> test')
		code_tag = buffer.get_tag_table().lookup('style-code')
		bounds = buffer.get_bounds()
		buffer.apply_tag(code_tag, *bounds)
		self.assertBufferEqual(buffer, '<code>test </code><tag name="None"><code>@tag</code></tag><code> test</code>')
		self.assertParseTreeEqual(buffer, '<p><code>test</code> <tag name="tag">@tag</tag> <code>test</code></p>')

	def testIllegalFormatWithinPre(self):
		# No format nests within verbatim, ignore
		buffer = self.get_buffer('test\n<strong>strong</strong>\ntest\n')
		code_tag = buffer.get_tag_table().lookup('style-pre')
		bounds = buffer.get_bounds()
		buffer.apply_tag(code_tag, *bounds)
		self.assertBufferEqual(buffer, '<pre>test\n</pre><strong><pre>strong</pre></strong><pre>\ntest\n</pre>')
		self.assertParseTreeEqual(buffer, '<pre>test\nstrong\ntest\n</pre>')

	def testIllegalDoubleIndentTag(self):
		# Highest prio tag should get precedence - this is what the user sees
		# prio in reverse order of tag creation
		buffer = self.get_buffer('test 123\n')
		indent1 = buffer._get_indent_tag(1)
		indent2 = buffer._get_indent_tag(2)
		bounds = buffer.get_bounds()
		buffer.apply_tag(indent1, *bounds)
		buffer.apply_tag(indent2, *bounds)
		self.assertBufferEqual(buffer, '<div indent="2"><div indent="1">test 123\n</div></div>')
		self.assertParseTreeEqual(buffer, '<p><div indent="1">test 123\n</div></p>')

	def testIllegalIndentedListItem(self):
		# Bullet item should get precedence - this is what the user sees
		# prio in reverse order of tag creation
		# bullet should get prio, even if created earlier
		buffer = self.get_buffer('<li indent="0" style="bullet-list">\u2022 test 123\n</li>')
		indent = buffer._get_indent_tag(2)
		bounds = buffer.get_bounds()
		buffer.apply_tag(indent, *bounds)
		self.assertBufferEqual(buffer, '<div indent="2"><li indent="0" style="bullet-list">\u2022 test 123\n</li></div>')
		self.assertParseTreeEqual(buffer, '<p><ul><li bullet="*">test 123\n</li></ul></p>')

	def testIllegalIndentedHeading(self):
		# Heading should get prio - this is what the users sees
		buffer = self.get_buffer('test 123\n')
		head1 = buffer.get_tag_table().lookup('style-h1')
		indent = buffer._get_indent_tag(1)
		bounds = buffer.get_bounds()
		buffer.apply_tag(head1, *bounds)
		buffer.apply_tag(indent, *bounds)
		self.assertBufferEqual(buffer, '<div indent="1"><h level="1">test 123\n</h></div>')
		self.assertParseTreeEqual(buffer, '<h level="1">test 123\n</h>')

	def testIllegalDoubleHeading(self):
		# Highest prio tag should get precedence - this is what the user sees
		buffer = self.get_buffer('test 123\n')
		head1 = buffer.get_tag_table().lookup('style-h1')
		head2 = buffer.get_tag_table().lookup('style-h2')
		bounds = buffer.get_bounds()
		buffer.apply_tag(head1, *bounds)
		buffer.apply_tag(head2, *bounds)
		self.assertBufferEqual(buffer, '<h level="1"><h level="2">test 123\n</h></h>')
		self.assertParseTreeEqual(buffer, '<h level="2">test 123\n</h>')

	def testIllegalHeadingWithListItem(self):
		# Heading should get prio - this is what the users sees
		buffer = self.get_buffer('<li indent="0" style="bullet-list">\u2022 test 123\n</li>')
		head1 = buffer.get_tag_table().lookup('style-h1')
		bounds = buffer.get_bounds()
		buffer.apply_tag(head1, *bounds)
		self.assertBufferEqual(buffer, '<li indent="0" style="bullet-list"><h level="1">\u2022 test 123\n</h></li>')
		self.assertParseTreeEqual(buffer, '<h level="1">\u2022 test 123\n</h>')

	def testIllegalDoubleLink(self):
		# Serialization should be consistent with get_link_data() to make
		# behavior for user consistent
		buffer = self.get_buffer('<link href="None">Test 123</link>')
		link = buffer._create_link_tag('Test 123', 'target')
		bounds = buffer.get_bounds()
		buffer.apply_tag(link, *bounds)
		self.assertBufferEqual(buffer, '<link href="target"><link href="None">Test 123</link></link>')
		linkdata = buffer.get_link_data(buffer.get_iter_at_offset(4))
		self.assertEqual(linkdata['href'], 'target')
		self.assertParseTreeEqual(buffer, '<p><link href="target">Test 123</link></p>')

	def testIllegalDoubleTag(self):
		buffer = self.get_buffer('<tag name="None">@test</tag>')
		tag = buffer._create_tag_tag('@test')
		bounds = buffer.get_bounds()
		buffer.apply_tag(tag, *bounds)
		self.assertBufferEqual(buffer, '<tag name="None"><tag name="None">@test</tag></tag>')
		self.assertParseTreeEqual(buffer, '<p><tag name="test">@test</tag></p>')

	def testInsertBeforeBulletEndUpAfterBullet(self):
		input = '''\
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" />Box 1
<icon stock="zim-unchecked-box" />Box 2
<icon stock="zim-unchecked-box" />Box 3
</li>
'''
		wanted = '''\
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" />Box 1
<icon stock="zim-unchecked-box" />foo Box 2
<icon stock="zim-unchecked-box" />Box 3
</li>
'''
		buffer = self.get_buffer(input)
		iter = buffer.get_iter_at_line(1) # iter *before* checkbox
		buffer.insert(iter, 'foo ')
		self.assertBufferEqual(buffer, wanted)

	def testFormattingOnBullet(self):
		# Strange bug let to second bullet disappearing in this case
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p><ul indent="1"><li bullet="*">Box 1
</li><li bullet="*">Box 2
</li><li bullet="*">Box 3
</li></ul></p>
</zim-tree>'''
		buffer = self.get_buffer(input)
		iter = buffer.get_iter_at_line(2) # iter before checkbox
		bound = iter.copy()
		bound.forward_char()
		buffer.select_range(iter, bound)
		buffer.toggle_format_tag_by_name('strike')
		self.assertParseTreeEqual(buffer, input) # no change

	def testInlineTagsBreakAtNewline(self):
		buffer = self.get_buffer('<emphasis>line1\nline2</emphasis>')
		self.assertParseTreeEqual(buffer, '<p><emphasis>line1</emphasis>\n<emphasis>line2</emphasis></p>')

	def testInlineTagsBreakAtNewline_MultipleTags(self):
		buffer = self.get_buffer('<emphasis>line1 <strong>foo\nline2</strong></emphasis>')
		self.assertParseTreeEqual(buffer, '<p><emphasis>line1 <strong>foo</strong></emphasis>\n<emphasis><strong>line2</strong></emphasis></p>')

	def testInlineTagsBreakAtNewline_LeaveNoEmptyTag(self):
		buffer = self.get_buffer('<emphasis>line1<strong>\nline2</strong></emphasis>')
		self.assertParseTreeEqual(buffer, '<p><emphasis>line1</emphasis>\n<emphasis><strong>line2</strong></emphasis></p>')

	def testInlineTagsBreakAtNewline_ExampleIssue1245(self):
		buffer = self.get_buffer(
			'<strike>Ut enim ad minim veniam,\n'
			'<link href="http://localhost/">quis nostrud exercitation ullamco laboris.</link></strike>',
		)
		self.assertParseTreeEqual(buffer,
			'<p><strike>Ut enim ad minim veniam,</strike>\n'
			'<strike><link href="http://localhost/">quis nostrud exercitation ullamco laboris.</link></strike></p>',
		)

	def testHighLightedEmail_ExampleIssue1377(self):
		# This could as well be a formatting test - and extend to other markup as well
		buffer = self.get_buffer('<mark><link href="None">mike@example.com</link></mark>')
		self.assertParseTreeEqual(buffer, '<p><mark><link href="mike@example.com">mike@example.com</link></mark></p>')

	def testHighLightedURL(self):
		# This could as well be a formatting test - and extend to other markup as well
		buffer = self.get_buffer('<mark><link href="None">http://example.com</link></mark>')
		self.assertParseTreeEqual(buffer, '<p><mark><link href="http://example.com">http://example.com</link></mark></p>')

	def testAppendTree(self):
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p>new text</p>
</zim-tree>
'''
		tree = tests.new_parsetree_from_xml(input)

		buffer = self.get_buffer('Existing page\n')
		self.assertBufferEqual(buffer, 'Existing page\n')
		buffer.append_parsetree(tree)
		self.assertBufferEqual(buffer, 'Existing page\n\nnew text\n')
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, 'Existing page\n')


class TestInternalSerialization(tests.TestCase):

	def setUp(self):
		self.notebook = self.setUpNotebook(content={'Test': tests.new_page_as_wiki_text()})
		self.page = self.notebook.get_page(Path('Test'))
		with tests.LoggingFilter('zim.gui.pageview'):
			self.buffer = TextBuffer(self.notebook, self.page, parsetree=self.page.get_parsetree())

	def testEmptyRange(self):
		start, end = self.buffer.get_bounds()
		data = textbuffer_internal_serialize_range(self.buffer, end, start) # switch bounds
		self.assertEqual(data._data, [])
		self.assertEqual(data.to_xml(), '<zim-textbuffer></zim-textbuffer>')

		buffer1 = TextBuffer(self.notebook, self.page)
		textbuffer_internal_insert_at_cursor(buffer1, data)
		start, end = buffer1.get_bounds()
		self.assertTrue(start.equal(end))

		data = textbuffer_internal_serialize_range(buffer1, start, end)
		self.assertEqual(data._data, [])

	def testInternalDataReproducesBuffer(self):
		import copy
		data = textbuffer_internal_serialize_range(self.buffer, *self.buffer.get_bounds())
		dataref = copy.deepcopy(data._data)
		#print(data.to_xml())

		buffer1 = TextBuffer(self.notebook, self.page)
		with tests.LoggingFilter('zim.gui.pageview'):
			textbuffer_internal_insert_at_cursor(buffer1, data)
			self.assertEqual(data._data, dataref) # Ensure data not changed in insertion

		data1 = textbuffer_internal_serialize_range(buffer1, *buffer1.get_bounds())
		self.assertEqual(data1._data, data._data)

	def testXMLReproducesInternalData(self):
		# It might be easier to just compare the xml representations, because the conversion
		# flattens some of the differences. However, for tests that create buffers from xml data
		# it is important the xml exactly reproduces to buffer internal contents
		import copy
		data = textbuffer_internal_serialize_range(self.buffer, *self.buffer.get_bounds())
		dataref = copy.deepcopy(data._data)

		xml = data.to_xml()
		self.assertEqual(data._data, dataref) # Ensure data not changed in conversion

		data1 = TextBufferInternalContents.new_from_xml(xml)
		self.assertEqual(data1._data, data._data)


class TestInternalSerializationWithTableObject(TestInternalSerialization):
	# Table object is special case with respect to serialization

	def setUp(self):
		PluginManager.load_plugin('tableeditor')
		TestInternalSerialization.setUp(self)


class TestUndoStackManager(tests.TestCase, TextBufferTestCaseMixin):

	def testInsertUndoRedo(self):
		# Test inserting a full tree, than undoing and redoing it

		buffer = self.get_buffer()
		tree = tests.new_parsetree()

		with FilterNoSuchImageWarning():
			buffer._insert_element_children(tree._etree.getroot())
				# Use private method to circumvent begin-insert-tree
				# signal etc. so we get undo stack for inserting

		# First test is to check we have a continuous undo stack after
		# inserting a parse tree. Nota bene, if this test fails, the
		# insert_parsetree() function is not strictly serial, which
		# probably breaks proper formatting e.g. when pasting a tree
		# half way in a line.
		i = 0
		for group in buffer.undostack.stack + [buffer.undostack.group]:
			for action in group:
				self.assertEqual(action[1], i) # assert undo stack is continous
				i = action[2]

		self.assertTrue(len(buffer.undostack.stack) > 10) # check we recorded something

		# Now we iterate through the tree to verify we get a proper
		# state at every step of the stack, then we redo to check we
		# get back what we had
		buffercontent1 = textbuffer_internal_serialize_range(buffer, *buffer.get_bounds())

		while buffer.undostack.undo():
			_ = buffer.get_parsetree() # just check for no warnings

		start, end = buffer.get_bounds()
		self.assertEqual(start.get_slice(end), '') # Ensure buffer empty

		with FilterNoSuchImageWarning():
			while buffer.undostack.redo():
				_ = buffer.get_parsetree() # just check for no warnings

		self.assertBufferEqual(buffer, buffercontent1) # Fully reconstructed

		while buffer.undostack.undo():
			continue

		start, end = buffer.get_bounds()
		self.assertEqual(start.get_slice(end), '') # Ensure buffer empty

	def testMore(self):
		buffer = self.get_buffer()

		# Test merging
		for c in 'fooo barr baz':
			with buffer.user_action:
				buffer.insert_at_cursor(c)
		#~ import pprint
		#~ buffer.undostack.flush_insert()
		#~ pprint.pprint(buffer.undostack.stack)
		self.assertTrue(len(buffer.undostack.stack) == 5) # 3 words, 2 spaces
		for group in buffer.undostack.stack:
			self.assertTrue(len(group) == 1) # merge was sucessfull
		self.assertBufferEqual(buffer, 'fooo barr baz')

		for wanted in (
			"fooo barr ",
			"fooo barr",
			"fooo ",
			"fooo",
			""
		):
			buffer.undostack.undo()
			self.assertBufferEqual(buffer, wanted)

		while buffer.undostack.redo():
			continue
		self.assertBufferEqual(buffer, 'fooo barr baz')

		# test format action
		iter = buffer.get_iter_at_offset(7)
		buffer.place_cursor(iter)
		buffer.select_word()
		buffer.toggle_format_tag_by_name('strong')
		self.assertBufferEqual(buffer, 'fooo <strong>barr</strong> baz')

		buffer.undostack.undo()
		self.assertBufferEqual(buffer, 'fooo barr baz')

		buffer.undostack.redo()
		self.assertBufferEqual(buffer, 'fooo <strong>barr</strong> baz')

		# test delete action
		start, end = list(map(buffer.get_iter_at_offset, (5, 10)))
		with buffer.user_action:
			buffer.delete(start, end)
		self.assertBufferEqual(buffer, 'fooo baz')

		buffer.undostack.undo()
		self.assertBufferEqual(buffer, 'fooo <strong>barr</strong> baz')

		buffer.undostack.redo()
		self.assertBufferEqual(buffer, 'fooo baz')

		# test folding
		buffer.undostack.undo()
		buffer.undostack.undo()
		buffer.undostack.undo()
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, 'fooo barr')

		with buffer.user_action:
			buffer.insert_at_cursor(' ')
		self.assertBufferEqual(buffer, 'fooo barr ')

		buffer.undostack.undo()
		self.assertBufferEqual(buffer, 'fooo barr')

		buffer.undostack.undo() # here we undo fold of 4 undos above
		self.assertBufferEqual(buffer, 'fooo baz')
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, 'fooo <strong>barr</strong> baz')

	def testBrokenLink(self):
		# Specific test for when "href == text"
		buffer = self.get_buffer('<zim-tree><p><link href="TestLink">TestLink</link>\n</p></zim-tree>')
		iter = buffer.get_iter_at_offset(4)
		end = buffer.get_iter_at_offset(8)
		buffer.delete(iter, end)
		self.assertParseTreeEqual(buffer, '<p><link href="Test">Test</link>\n</p>')
		buffer.undostack.undo()
		self.assertParseTreeEqual(buffer, '<p><link href="TestLink">TestLink</link>\n</p>')

	def testUndoPageReload(self):
		# page reload calls "set_parsetree", so by testing whether we can
		# undo "set_parsetree()" we test undo-ing a buffer reload using page.reload_textbuffer()
		buffer = self.get_buffer('test 123')
		tree = tests.new_parsetree_from_text('test ABC')
		buffer.set_parsetree(tree)
		self.assertBufferEqual(buffer, 'test ABC')
		buffer.undostack.undo()
		self.assertBufferEqual(buffer, 'test 123')

class TestLists(tests.TestCase, TextBufferTestCaseMixin):

	def testBulletLists(self):
		input = '''\
Dusss
<li indent="0" style="bullet-list">\u2022 Foo
\u2022 Bar
</li><li indent="1" style="bullet-list">\u2022 Bar 1
</li><li indent="2" style="bullet-list">\u2022 Bar 1.1
</li><li indent="1" style="bullet-list">\u2022 Bar 2
\u2022 Bar 3
</li><li indent="0" style="bullet-list">\u2022 Baz
</li>Tja
'''
		buffer = self.get_buffer(input)

		# check list initializes properly
		row, list = TextBufferList.new_from_line(buffer, 3) # Bar 1
		self.assertEqual(list.firstline, 1)
		self.assertEqual(list.lastline, 7)
		self.assertEqual(row, 2)
		self.assertEqual(list, [
			(1, 0, '*'),
			(2, 0, '*'),
			(3, 1, '*'),
			(4, 2, '*'),
			(5, 1, '*'),
			(6, 1, '*'),
			(7, 0, '*'),
		])

		# Exercise indenting
		row, list = TextBufferList.new_from_line(buffer, 3) # Bar 1
		self.assertFalse(list.can_indent(row))
		self.assertFalse(list.indent(row))

		row, list = TextBufferList.new_from_line(buffer, 2) # Bar
		self.assertTrue(list.can_indent(row))
		self.assertTrue(list.indent(row))
		self.assertFalse(list.can_indent(row))

		wanted = '''\
Dusss
<li indent="0" style="bullet-list">\u2022 Foo
</li><li indent="1" style="bullet-list">\u2022 Bar
</li><li indent="2" style="bullet-list">\u2022 Bar 1
</li><li indent="3" style="bullet-list">\u2022 Bar 1.1
</li><li indent="2" style="bullet-list">\u2022 Bar 2
\u2022 Bar 3
</li><li indent="0" style="bullet-list">\u2022 Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		row, list = TextBufferList.new_from_line(buffer, 7) # Baz
		self.assertFalse(list.can_unindent(row))
		self.assertFalse(list.unindent(row))

		row, list = TextBufferList.new_from_line(buffer, 3) # Bar 1
		self.assertTrue(list.can_unindent(row))
		self.assertTrue(list.unindent(row))

		wanted = '''\
Dusss
<li indent="0" style="bullet-list">\u2022 Foo
</li><li indent="1" style="bullet-list">\u2022 Bar
\u2022 Bar 1
</li><li indent="2" style="bullet-list">\u2022 Bar 1.1
\u2022 Bar 2
\u2022 Bar 3
</li><li indent="0" style="bullet-list">\u2022 Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		for line in (2, 5, 6): # Bar, Bar 2 & Bar 3
			row, list = TextBufferList.new_from_line(buffer, line)
			self.assertTrue(list.can_unindent(row))
			self.assertTrue(list.unindent(row))

		self.assertBufferEqual(buffer, input)

		# Test undo / redo for indenting and lists
		for i in range(3):
			self.assertTrue(buffer.undostack.undo())
		self.assertBufferEqual(buffer, wanted)

		while buffer.undostack.undo():
			pass
		self.assertBufferEqual(buffer, input)

		while buffer.undostack.redo():
			pass
		self.assertBufferEqual(buffer, input)

		for i in range(3):
			self.assertTrue(buffer.undostack.undo())
		self.assertBufferEqual(buffer, wanted)

	def testCheckBoxLists(self):
		# Exercize recursive checkbox lists
		input = '''\
Dusss
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Foo
<icon stock="zim-unchecked-box" /> Bar
</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> Bar 1
</li><li indent="2" style="unchecked-box"><icon stock="zim-unchecked-box" /> Bar 1.1
</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> Bar 2
<icon stock="zim-unchecked-box" /> Bar 3
</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Baz
</li>Tja
'''
		buffer = self.get_buffer(input)

		row, list = TextBufferList.new_from_line(buffer, 2) # Bar
		list.set_bullet(row, CHECKED_BOX)
		wanted = '''\
Dusss
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Foo
</li><li indent="0" style="checked-box"><icon stock="zim-checked-box" /> Bar
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar 1
</li><li indent="2" style="checked-box"><icon stock="zim-checked-box" /> Bar 1.1
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar 2
<icon stock="zim-checked-box" /> Bar 3
</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		list.set_bullet(row, UNCHECKED_BOX)
		row = list.get_row_at_line(3) # Bar 1
		list.set_bullet(row, XCHECKED_BOX)
		row = list.get_row_at_line(5) # Bar 2
		list.set_bullet(row, UNCHECKED_BOX)
		wanted = '''\
Dusss
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Foo
<icon stock="zim-unchecked-box" /> Bar
</li><li indent="1" style="xchecked-box"><icon stock="zim-xchecked-box" /> Bar 1
</li><li indent="2" style="checked-box"><icon stock="zim-checked-box" /> Bar 1.1
</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> Bar 2
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar 3
</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		row = list.get_row_at_line(5) # Bar 2
		list.set_bullet(row, CHECKED_BOX)
		wanted = '''\
Dusss
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Foo
<icon stock="zim-unchecked-box" /> Bar
</li><li indent="1" style="xchecked-box"><icon stock="zim-xchecked-box" /> Bar 1
</li><li indent="2" style="checked-box"><icon stock="zim-checked-box" /> Bar 1.1
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar 2
<icon stock="zim-checked-box" /> Bar 3
</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		row = list.get_row_at_line(4) # Bar 1.1
		list.set_bullet(row, UNCHECKED_BOX)
		wanted = '''\
Dusss
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Foo
<icon stock="zim-unchecked-box" /> Bar
</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> Bar 1
</li><li indent="2" style="unchecked-box"><icon stock="zim-unchecked-box" /> Bar 1.1
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar 2
<icon stock="zim-checked-box" /> Bar 3
</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		wantedpre1 = wanted
		row = list.get_row_at_line(4) # Bar 1.1
		list.set_bullet(row, CHECKED_BOX)
		wanted = '''\
Dusss
<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Foo
</li><li indent="0" style="checked-box"><icon stock="zim-checked-box" /> Bar
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar 1
</li><li indent="2" style="checked-box"><icon stock="zim-checked-box" /> Bar 1.1
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar 2
<icon stock="zim-checked-box" /> Bar 3
</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		# Test indenting / unindenting the whole list
		wantedpre = wanted
		row = list.get_row_at_line(1) # Foo
		list.indent(row)
		wanted = '''\
Dusss
<li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> Foo
</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> Bar
</li><li indent="2" style="checked-box"><icon stock="zim-checked-box" /> Bar 1
</li><li indent="3" style="checked-box"><icon stock="zim-checked-box" /> Bar 1.1
</li><li indent="2" style="checked-box"><icon stock="zim-checked-box" /> Bar 2
<icon stock="zim-checked-box" /> Bar 3
</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> Baz
</li>Tja
'''
		self.assertBufferEqual(buffer, wanted)

		list.unindent(row)
		self.assertBufferEqual(buffer, wantedpre)

		# Test undo / redo for indenting and lists
		for xml in (wanted, wantedpre, wantedpre1):
			self.assertTrue(buffer.undostack.undo())
			self.assertBufferEqual(buffer, xml)

		for xml in (wantedpre, wanted, wantedpre):
			self.assertTrue(buffer.undostack.redo())
			self.assertBufferEqual(buffer, xml)

		while buffer.undostack.undo():
			pass
		self.assertBufferEqual(buffer, input)

		while buffer.undostack.redo():
			pass
		self.assertBufferEqual(buffer, wantedpre)


class TestTextView(tests.TestCase, TextBufferTestCaseMixin):

	# See also:
	#  - TestKeyPresses
	#  - TestDoEndOfLine
	#  - TestDoEndOfWord

	def get_view(self):
		# Initialize default preferences from module
		preferences = {}
		for pref in ui_preferences:
			preferences[pref[0]] = pref[4]

		# Initialize view
		view = TextView(preferences)
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		view.set_buffer(buffer)
		return view

	@tests.expectedFailure
	def testCopyPaste(self):
		assert False # FIXME

		notebook = self.setUpNotebook(
			content={'roundtrip': tests.new_page_as_wiki_text()}
		)
		page = notebook.get_page(Path('roundtrip'))
		parsetree = page.get_parsetree()
		view = self.get_view(notebook, page)

		print('** HACK for cleaning up parsetree')
		def cleanup(parsetree):
			# FIXME - HACK - dump and parse as wiki first to work
			# around glitches in pageview parsetree dumper
			# main visibility when copy pasting bullet lists
			# Same hack in gui clipboard code
			from zim.notebook import Path, Page
			dumper = get_format('wiki').Dumper()
			text = ''.join(dumper.dump(parsetree))
			parser = get_format('wiki').Parser()
			parsetree = parser.parse(text)
			return parsetree
			#--

		# paste
		Clipboard.set_parsetree(notebook, page, parsetree)
		with FilterNoSuchImageWarning():
			textview.emit('paste-clipboard')
		result = buffer.get_parsetree()
		result = cleanup(result)
		self.assertEqual(result.tostring(), parsetree.tostring())

		# paste replacing selection
		buffer.set_text('foo bar baz')
		buffer.select_range(*buffer.get_bounds()) # select all
		with FilterNoSuchImageWarning():
			textview.emit('paste-clipboard')
		result = buffer.get_parsetree()
		result = cleanup(result)
		self.assertEqual(result.tostring(), parsetree.tostring())

		# copy
		Clipboard.clear()
		self.assertIsNone(Clipboard.get_parsetree())
		buffer.select_range(*buffer.get_bounds()) # select all
		textview.emit('copy-clipboard')
		result = Clipboard.get_parsetree(notebook, page)
		self.assertIsNotNone(result)
		result = cleanup(result)
		self.assertEqual(result.tostring(), parsetree.tostring())

		# copy partial
		# line 33, offset 6 to 28 "try these **bold**, //italic//" in roundtrip page
		wanted_tree = "<?xml version='1.0' encoding='utf-8'?>\n<zim-tree><p>try these <strong>bold</strong>, <emphasis>italic</emphasis></p></zim-tree>"
		wanted_text = "try these bold, italic" # no newline !
		Clipboard.clear()
		self.assertIsNone(Clipboard.get_parsetree())
		start = buffer.get_iter_at_line_offset(33, 6)
		end = buffer.get_iter_at_line_offset(33, 28)
		buffer.select_range(start, end)
		textview.emit('copy-clipboard')
		result = Clipboard.get_parsetree(notebook, page)
		self.assertIsNotNone(result)
		self.assertEqual(result.tostring(), wanted_tree)
		self.assertEqual(Clipboard.get_text(), wanted_text)

		# cut
		Clipboard.clear()
		self.assertIsNone(Clipboard.get_parsetree())
		buffer.select_range(*buffer.get_bounds()) # select all
		textview.emit('cut-clipboard')
		result = Clipboard.get_parsetree(notebook, page)
		self.assertIsNotNone(result)
		result = cleanup(result)
		self.assertEqual(result.tostring(), parsetree.tostring())
		self.assertEqual(get_text(buffer), '')

		# popup menu
		page = tests.new_page_from_text('Foo **Bar** Baz\n')
		pageview = setUpPageView(self.setUpNotebook())
		pageview.set_page(page)

		def get_context_menu():
			buffer = pageview.textview.get_buffer()
			buffer.select_range(*buffer.get_bounds()) # select all
			return pageview.textview.get_popup()

		def click(id):
			menu = get_context_menu()
			tests.gtk_activate_menu_item(menu, id)

		#~ tests.gtk_activate_menu_item(menu, 'gtk-copy')
		#~ self.assertEqual(Clipboard.get_text(), 'Test')
		#~ ## Looks like this item not initialized yet

		menu = get_context_menu()
		item = tests.gtk_get_menu_item(menu, _('Copy _As...'))
		copy_as_menu = item.get_submenu()
		tests.gtk_activate_menu_item(copy_as_menu, 'Wiki')
		self.assertEqual(Clipboard.get_text(), 'Foo **Bar** Baz\n')
		tree = Clipboard.get_parsetree(pageview.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><p>Foo <strong>Bar</strong> Baz\n</p></zim-tree>')

		page = tests.new_page_from_text('[[Bar]]')
		pageview.set_page(page)
		click(_('Copy _Link'))
		self.assertEqual(Clipboard.get_text(), 'Bar')
		tree = Clipboard.get_parsetree(pageview.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="Bar">Bar</link></zim-tree>')

		page = tests.new_page_from_text('[[wp?foobar]]')
		pageview.set_page(page)
		click(_('Copy _Link'))
		self.assertEqual(Clipboard.get_text(), 'https://en.wikipedia.org/wiki/foobar')
		tree = Clipboard.get_parsetree(pageview.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="wp?foobar">wp?foobar</link></zim-tree>')

		page = tests.new_page_from_text('[[~//bar.txt]]')
			# Extra '/' is in there to verify path gets parsed as File object
		pageview.set_page(page)
		wanted = '~/bar.txt' if os.name != 'nt' else '~\\bar.txt'
		click(_('Copy _Link'))
		self.assertEqual(Clipboard.get_text(), '~/bar.txt')
		tree = Clipboard.get_parsetree(pageview.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="%s">%s</link></zim-tree>' % (wanted, wanted))

	def testPasteWikiAndVerbatim(self):
		view = self.get_view()
		buffer = view.get_buffer()

		Clipboard.set_text('foo [[link]] ')
		view.emit('paste-clipboard')
		self.assertBufferEqual(buffer, 'foo <link href="None">link</link> ')

		Clipboard.set_text('foo [[no link]]')
		buffer.toggle_format_tag_by_name('code')
		view.emit('paste-clipboard')
		self.assertBufferEqual(buffer, 'foo <link href="None">link</link> <code>foo [[no link]]</code>')

	def testPasteTextAtIndent(self):
		# Test indenting is preserved on past
		view = self.get_view()
		buffer = view.get_buffer()

		Clipboard.set_text('foo')
		iter = buffer.get_insert_iter()
		buffer.indent(iter.get_line(), interactive=True)
		view.emit('paste-clipboard')
		self.assertBufferEqual(buffer, '<div indent="1">foo\n</div>')

	def testPasteTextAtBullet(self):
		# Test indenting is preserved on past
		view = self.get_view()
		buffer = view.get_buffer()

		Clipboard.set_text('foo')
		iter = buffer.get_insert_iter()
		buffer.set_bullet(iter.get_line(), BULLET)
		view.emit('paste-clipboard')
		self.assertBufferEqual(buffer, '<li indent="0" style="bullet-list">\u2022 foo</li>')

	def testUnkownObjectType(self):
		view = self.get_view()
		buffer = view.get_buffer()

		tree = tests.new_parsetree_from_text('''\
======= Test

{{{somenewtype: foo=123
Foo 123
}}}

''')
		for token in tree.iter_tokens(): # assert object in tree
			if token[0] == OBJECT:
				break
		else:
			self.fail('No object in tree')

		buffer.set_parsetree(tree)
		self.assertEqual(len(list(view._object_widgets)), 1) # assert there is an object in the view
		self.assertParseTreeEqual(buffer, tree) # assert stable over roundtrip

	def testPopup(self):
		view = self.get_view()
		buffer = view.get_buffer()
		buffer.set_text("TEst ABC\n")
		menu = view.get_popup()
		self.assertIsInstance(menu, Gtk.Menu)

	def testStyleConfig(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')

		# font

		# TODO

		# tabs

		# linespacing

		# wrapped-line-linespacing

		# font

		# justify - constant for FILL is 3
		pageview.text_style['TextView']['justify'] = 'FILL'
		self.assertEqual(pageview.textview.get_justification(), 3)

		# indent

		# bullet_icon_size

		# tag_styles


def press(widget, sequence):
	logger.debug('PRESS %s', sequence)
	for key in sequence:
		if isinstance(key, int):
			keyval = int(key)
		elif key == '\n':
			keyval = int(Gdk.keyval_from_name('Return'))
		elif key == '\t':
			keyval = int(Gdk.keyval_from_name('Tab'))
		else:
			keyval = int(Gdk.unicode_to_keyval(ord(key)))

		widget.test_key_press_event(keyval)


class TestKeyPresses(tests.TestCase, TextBufferTestCaseMixin):

	# TODO check key press routines with/without selection
	# for all keybindings that are not handled by end-of-word or end-of-line

	def get_view(self):
		# Initialize default preferences from module
		preferences = {}
		for pref in ui_preferences:
			preferences[pref[0]] = pref[4]

		# Initialize view
		view = TextView(preferences)
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		view.set_buffer(buffer)
		return view

	def testToggleSelectionToList(self):
		# selection + * to toggle bullets
		as_list = '''\
<li indent="0" style="bullet-list">\u2022 Item 1
</li><li indent="1" style="bullet-list">\u2022 Item 1.1
\u2022 Item 1.2
</li>
'''
		not_as_list = '''\
Item 1
<div indent="1">Item 1.1
Item 1.2
</div>
'''

		view = self.get_view()
		buffer = view.get_buffer()
		self.set_buffer(buffer, as_list)

		# Toggle off
		start = buffer.get_iter_at_line(0)
		end = buffer.get_iter_at_line(3) # empty line !
		buffer.select_range(start, end)
		press(view, '*')
		self.assertBufferEqual(buffer, not_as_list)

		# Toggle on
		start = buffer.get_iter_at_line(0)
		end = buffer.get_iter_at_line(3) # empty line !
		buffer.select_range(start, end)
		press(view, '*')
		self.assertBufferEqual(buffer, as_list)

	def testBackSpaceListUnindentAndDeleteBullet(self):
		view = self.get_view()
		buffer = view.get_buffer()
		self.set_buffer(buffer, '''\
<li indent="0" style="bullet-list">\u2022 Item 1
</li><li indent="1" style="bullet-list">\u2022 Item 1.1
\u2022 Item 1.2
</li>
''')

		# Un-indent item 1.1
		iter = buffer.get_iter_at_line(1)
		buffer.place_cursor(iter)
		press(view, (KEYVALS_BACKSPACE[0],))
		self.assertBufferEqual(buffer, '''\
<li indent="0" style="bullet-list">\u2022 Item 1
\u2022 Item 1.1
</li><li indent="1" style="bullet-list">\u2022 Item 1.2
</li>
''')

		# Delete bullet item 1.1 (including bullet whitespace)
		press(view, (KEYVALS_BACKSPACE[0],))
		self.assertBufferEqual(buffer, '''\
<li indent="0" style="bullet-list">\u2022 Item 1
</li>Item 1.1
<li indent="1" style="bullet-list">\u2022 Item 1.2
</li>
''')


class TestDoEndOfLine(tests.TestCase, TextBufferTestCaseMixin):

	@classmethod
	def setUpClass(cls):
		tests.TestCase.setUpClass()

		preferences = dict((p[0], p[4]) for p in ui_preferences)
		cls.view = TextView(preferences)
		cls.buffer = TextBuffer(None, None)
		cls.view.set_buffer(cls.buffer)

		press(cls.view, 'aaa\n')
		start, end = cls.buffer.get_bounds()
		assert cls.buffer.get_text(start, end, True) == 'aaa\n', 'Just checking test routines work'

	def typeNewLine(self, line):
		if line >= 0:
			iter = self.buffer.get_iter_at_line(line)
			if not iter.ends_line():
				iter.forward_to_line_end()
			self.buffer.place_cursor(iter)
		elif line < 0:
			iter = self.buffer.get_end_iter()
			for i in range(line, -1):
				iter.backward_line()
			iter.forward_to_line_end()
			self.buffer.place_cursor(iter)
		press(self.view, '\n')

	def assertInsertNewLine(self, input, wanted, wanted_alt=None, line=-1):
		self._assertInsertNewLine(input, wanted, line)
		if line == -1:
			# Ensure that end of buffer is not special
			mywanted = wanted_alt or wanted + '\n'
			self._assertInsertNewLine(input + '\n', mywanted, line=-2)

	def _assertInsertNewLine(self, input, wanted, line=-1):
		self.set_buffer(self.buffer, input)
		self.assertBufferEqual(self.buffer, input) # Ensure we got what we asked
		self.typeNewLine(line)
		self.assertBufferEqual(self.buffer, wanted)

	def testInsertNewLine(self):
		# Simple test to ensure inserting newline works unaffected
		self.assertInsertNewLine('aaa', 'aaa\n')
		self.assertInsertNewLine('aaa\n', 'aaa\n\n')
		self.assertInsertNewLine('aaa\nbbb', 'aaa\n\nbbb', line=0)

	def testFormatHeading(self):
		self.assertInsertNewLine('== Foo', '<h level="1">Foo\n</h>')
		self.assertInsertNewLine('=== Foo', '<h level="2">Foo\n</h>')
		self.assertInsertNewLine('=== Foo ===', '<h level="2">Foo\n</h>')

	def testNoFormattingInsideCode(self):
		# Make sure text inside code is not being formatted
		self.assertInsertNewLine('<code>== Foo ==</code>', '<code>== Foo ==</code>\n')
		self.assertInsertNewLine('<code>---</code>', '<code>---</code>\n')

	def testFormatLine(self):
		self.assertInsertNewLine('aaa\n-----', 'aaa\n<line />\n')

	def testAddBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n\u2022 </li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n\u2022 \n</li>'
		)

	def testRemoveEmptyBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n\u2022 </li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li>\n'
		)

	def testAddSubBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar\n\u2022 </li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar\n\u2022 \n</li>'
		)

	def testRemoveEmptySubBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar\n\u2022 </li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar\n</li>\n'
		)

	def testAddSubBulletAtTopOfSublist(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 \n\u2022 bar</li>',
			line=0
		)

	def testAddSubBulletAtBottomOfSublist(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar\n</li><li indent="0" style="bullet-list">\u2022 next</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="bullet-list">\u2022 bar\n\u2022 \n</li><li indent="0" style="bullet-list">\u2022 next</li>',
			line=1
		)

	def testAddNumberedBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="numbered-list">1. foo</li>',
			'<li indent="0" style="numbered-list">1. foo\n2. </li>',
			'<li indent="0" style="numbered-list">1. foo\n2. \n</li>'
		)

	def testRemoveEmptyNumberedBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="numbered-list">1. foo\n2. </li>',
			'<li indent="0" style="numbered-list">1. foo\n</li>\n',
		)

	def testAddNumberedSubBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="numbered-list">1. foo\n</li><li indent="1" style="numbered-list">a. bar</li>',
			'<li indent="0" style="numbered-list">1. foo\n</li><li indent="1" style="numbered-list">a. bar\nb. </li>',
			'<li indent="0" style="numbered-list">1. foo\n</li><li indent="1" style="numbered-list">a. bar\nb. \n</li>'
		)

	def testRemoveEmptyNumberedSubBullet(self):
		self.assertInsertNewLine(
			'<li indent="0" style="numbered-list">1. foo\n</li><li indent="1" style="numbered-list">a. bar\nb. </li>',
			'<li indent="0" style="numbered-list">1. foo\n</li><li indent="1" style="numbered-list">a. bar\n</li>\n',
		)

	def testAddNumberedSubBulletAtTopOfSublist(self):
		self.assertInsertNewLine(
			'<li indent="0" style="numbered-list">1. foo\n</li><li indent="1" style="numbered-list">a. bar</li>',
			'<li indent="0" style="numbered-list">1. foo\n</li><li indent="1" style="numbered-list">a. \nb. bar</li>',
			line=0
		)

	def testAddCheckbox(self):
		self.assertInsertNewLine(
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo</li>',
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo\n<icon stock="zim-unchecked-box" /> </li>',
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo\n<icon stock="zim-unchecked-box" /> \n</li>'
		)
		self.assertInsertNewLine(
			'<li indent="0" style="checked-box"><icon stock="zim-checked-box" /> foo</li>',
			'<li indent="0" style="checked-box"><icon stock="zim-checked-box" /> foo\n</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> </li>',
			'<li indent="0" style="checked-box"><icon stock="zim-checked-box" /> foo\n</li><li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> \n</li>'
		)

	def testRemoveEmptyCheckbox(self):
		self.assertInsertNewLine(
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo\n<icon stock="zim-unchecked-box" /> </li>',
			'<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> foo\n</li>\n',
		)

	def testAddSubCheckbox(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> bar</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> bar\n<icon stock="zim-unchecked-box" /> </li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> bar\n<icon stock="zim-unchecked-box" /> \n</li>'
		)
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> bar</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> bar\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> </li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> bar\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> \n</li>'
		)

	def testRemoveEmptySubCheckbox(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> bar\n<icon stock="zim-unchecked-box" /> </li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> bar\n</li>\n',
		)

	def testAddSubCheckboxAtTopOfSublist(self):
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> bar</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> \n<icon stock="zim-unchecked-box" /> bar</li>',
			line=0
		)
		self.assertInsertNewLine(
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> bar</li>',
			'<li indent="0" style="bullet-list">\u2022 foo\n</li><li indent="1" style="unchecked-box"><icon stock="zim-unchecked-box" /> \n</li><li indent="1" style="checked-box"><icon stock="zim-checked-box" /> bar</li>',
			line=0
		)


class TestDoEndOfWord(tests.TestCase, TextBufferTestCaseMixin):

	@classmethod
	def setUpClass(cls):
		tests.TestCase.setUpClass()

		preferences = dict((p[0], p[4]) for p in ui_preferences)
		cls.view = TextView(preferences)
		cls.buffer = TextBuffer(None, None)
		cls.view.set_buffer(cls.buffer)

		cls.view.preferences['auto_reformat'] = True

		press(cls.view, 'aaa\n')
		start, end = cls.buffer.get_bounds()
		assert cls.buffer.get_text(start, end, True) == 'aaa\n', 'Just checking test routines work'

	def setUp(self):
		self.buffer.clear()

	def assertTyping(self, text, wanted):
		press(self.view, text)
		self.assertBufferEqual(self.buffer, wanted)

	def set_textview_preference(self, key, value):
		orig = self.view.preferences[key]
		self.view.preferences[key] = value
		self.addCleanup(lambda: self.view.preferences.__setitem__(key, orig))

	def testAutoFormatTag(self):
		self.assertTyping('@test ', '<tag name="None">@test</tag> ')

	def testAutoFormatAnchor(self):
		self.assertTyping('##test ', '<anchor name="test" /> ')

	def testAutoFormatAnchor2(self):
		self.assertTyping('##case-1 ', '<anchor name="case-1" /> ')

	def testAutoFormatAnchor3(self):
		self.assertTyping('##case_2 ', '<anchor name="case_2" /> ')

	def testNoAutoFormatAnchorPref(self):
		self.set_textview_preference('autolink_anchor', False)
		self.assertTyping('##test ', '##test ')

	def testAutoFormatAnchorLink(self):
		self.assertTyping('#test ', '<link href="None">#test</link> ')

	def testAutoFormatAnchorLink1(self):
		self.assertTyping('#test-1 ', '<link href="None">#test-1</link> ')

	def testAutoFormatAnchorLink2(self):
		self.assertTyping('#test_2 ', '<link href="None">#test_2</link> ')

	def testNoAutoFormatAnchorLinkPref(self):
		self.set_textview_preference('autolink_anchor', False)
		self.assertTyping('#test ', '#test ')

	def testAutoFormatPageWithAnchorLink(self):
		self.assertTyping('foo#test ', '<link href="None">foo#test</link> ')

	def testAutoFormatPageWithAnchorLinkWithoutAnchorPref(self):
		# With page prefix, this is switched by 'autolink_page' preference
		self.set_textview_preference('autolink_anchor', False)
		self.assertTyping('foo#test ', '<link href="None">foo#test</link> ')

	def testNoAutoFormatPageWithAnchorLinkPref(self):
		self.set_textview_preference('autolink_page', False)
		self.assertTyping('foo#test ', 'foo#test ')

	def testAutoFormatURL(self):
		self.assertTyping('http://test.com ', '<link href="None">http://test.com</link> ')

	def testAutoFormatURLLocalHost(self):
		self.assertTyping('http://localhost ', '<link href="None">http://localhost</link> ')

	def testAutoFormatURLTrailingPunctuation(self):
		self.assertTyping('www.commonmark.org/a.b. ', '<link href="None">www.commonmark.org/a.b</link>. ')

	def testAutoFormatURLMatchingBracket(self):
		self.assertTyping('(www.google.com/search?q=Markup+(business)) ', '(<link href="None">www.google.com/search?q=Markup+(business)</link>) ')

	def testAutoFormatURLQuotes(self):
		self.assertTyping('"http://test.com" ', '"<link href="None">http://test.com</link>" ')

	def testAutoStripURLQuotes(self):
		# If the link already exists and we type trailing punctuation, it should
		# be stripped from the link
		self.set_buffer(self.buffer, '"<link href="None">http://test.com</link>')
		self.assertTyping('" ', '"<link href="None">http://test.com</link>" ')

	def testAutoFormatURLPunctuation(self):
		self.assertTyping('http://test.com. ', '<link href="None">http://test.com</link>. ')

	def testAutoStripURLPunctuation(self):
		# If the link already exists and we type trailing punctuation, it should
		# be stripped from the link
		self.set_buffer(self.buffer, '<link href="None">http://test.com</link>')
		self.assertTyping('. ', '<link href="None">http://test.com</link>. ')

	def testAutoFormatEmail(self):
		self.assertTyping('hello+xyz@mail.example ', '<link href="None">hello+xyz@mail.example</link> ')

	def testAutoFormatPageLink(self):
		self.assertTyping('Foo:Bar ', '<link href="None">Foo:Bar</link> ')

	def testNoAutoFormatPageLinkPref(self):
		self.set_textview_preference('autolink_page', False)
		self.assertTyping('Foo:Bar ', 'Foo:Bar ')

	def testAutoFormatPageLinkWithAnchor(self):
		self.assertTyping('Foo:Bar#anchor ', '<link href="None">Foo:Bar#anchor</link> ')

	def testAutoFormatSubPageLink(self):
		self.assertTyping('+Foo ', '<link href="None">+Foo</link> ')

	def testAutoFormatSubPageLinkWithAnchor(self):
		self.assertTyping('+Foo#anchor ', '<link href="None">+Foo#anchor</link> ')

	def testAutoFormatTopLevelPageLink(self):
		# edge case for time detection - see #2469
		self.assertTyping(':Foo ', '<link href="None">:Foo</link> ')

	def testNoAutoFormatTimeAsPageLink1(self):
		self.assertTyping('10:20 ', '10:20 ')

	def testNoAutoFormatTimeAsPageLink2(self):
		self.assertTyping('10:20PM ', '10:20PM ')

	def testNoAutoFormatTimeAsPageLink3(self):
		self.assertTyping('10:20 +0200 ', '10:20 +0200 ')

	def testEndOfWordBreaksLink(self):
		self.set_buffer(self.buffer, '<link href="None">Foo</link>')
		self.assertTyping(' http://test.com ', '<link href="None">Foo</link> <link href="None">http://test.com</link> ')

	def testNoAutoFormatLinkInLink(self):
		self.set_buffer(self.buffer, '<link href="None">Foo Bar</link>')
		self.buffer.place_cursor(self.buffer.get_iter_at_offset(4))
		self.assertTyping('http://test.com ', '<link href="None">Foo http://test.com Bar</link>')

	def testAutoFormatInterWikiLink(self):
		self.assertTyping('wp?Test ', '<link href="None">wp?Test</link> ')

	def testNoAutoFormatInterWikiLinkPref(self):
		self.set_textview_preference('autolink_interwiki', False)
		self.assertTyping('wp?Test ', 'wp?Test ')

	def testAutoFormatCamelCaseLink(self):
		self.assertTyping('FooBar ', '<link href="None">FooBar</link> ')

	def testNoAutoFormatCamelCaseLinkPref(self):
		self.set_textview_preference('autolink_camelcase', False)
		self.assertTyping('FooBar ', 'FooBar ')

	def testAutoFormatFileLinkWithAutolinkFilesPrefEnabled(self):
		self.assertTyping('./test.pdf ', '<link href="None">./test.pdf</link> ')

	def testAutoFormatFileLinkWithAutolinkFilesPrefDisabled(self):
		self.set_textview_preference('autolink_files', False)
		self.assertTyping('./test.pdf ', './test.pdf ')

	def testAutoFormatWikiStrong(self):
		self.assertTyping('Foo**Bar** ', 'Foo<strong>Bar</strong> ')

	def testAutoFormatWikiEmphasis(self):
		self.assertTyping('Foo //Bar // ', 'Foo <emphasis>Bar </emphasis> ')

	def testAutoFormatWikiMark(self):
		self.assertTyping('__Foo Bar__ ', '<mark>Foo Bar</mark> ')

	def testAutoFormatWikiCode(self):
		self.assertTyping("Type ''$ test.py'' ", 'Type <code>$ test.py</code> ')

	def testAutoFormatWikiStrike(self):
		self.assertTyping('~~Foo Bar~~ ', '<strike>Foo Bar</strike> ')

	def testAutoFormatWikiSup1(self):
		self.assertTyping('x^2 ', 'x<sup>2</sup> ')

	def testAutoFormatWikiNotSup1(self):
		self.assertTyping('^2 ^2 ', '^2 ^2 ')

	def testAutoFormatWikiSup2(self):
		self.assertTyping('x^{2} ', 'x<sup>2</sup> ')

	def testAutoFormatWikiNotSup2(self):
		self.assertTyping('^{2} ^{2} ', '^{2} ^{2} ')

	def testAutoFormatWikiSub(self):
		self.assertTyping('x_{2} ', 'x<sub>2</sub> ')

	def testAutoFormatWikiNotSub(self):
		self.assertTyping('_{2} _{2} ', '_{2} _{2} ')

	def testNoAutoFormatStyleInLink(self):
		self.set_buffer(self.buffer, '<link href="None">Foo</link>')
		self.assertTyping('__Bar__ ', '<link href="None">Foo__Bar__</link> ')

	def testAutoFormatStyleInLinkWithText(self):
		self.set_buffer(self.buffer, '<link href="Test">Foo</link>')
		self.assertTyping('__Bar__ ', '<link href="Test">Foo<mark>Bar</mark></link> ')

	def testNAutoFormatCode(self):
		self.set_buffer(self.buffer, '\'\'test foo')
		self.assertTyping(' dus\'\' ', '<code>test foo dus</code> ')

	def testNoAutoFormatCodeOverTag(self):
		self.set_buffer(self.buffer, '\'\'test <tag name="None">@foo</tag>')
		self.assertTyping(' dus\'\' ', '\'\'test <tag name="None">@foo</tag> dus\'\' ')

	def testNoAutoFormatInPre(self):
		self.set_buffer(self.buffer, '<pre>test\n</pre>')
		self.buffer.place_cursor(self.buffer.get_iter_at_offset(4))
		self.assertTyping(' @test ', '<pre>test @test \n</pre>')

	def testNoAutoFormatInCode(self):
		self.set_buffer(self.buffer, '<code>test</code>')
		self.buffer.place_cursor(self.buffer.get_iter_at_offset(4))
		self.assertTyping(' @test ', '<code>test @test </code>')

	def testAutoFormatBullet(self):
		self.assertTyping('* Test', '<li indent="0" style="bullet-list">\u2022 Test</li>')

	def testAutoFormatCheckbox(self):
		self.assertTyping('[] Test', '<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Test</li>')

	def testAutoFormatNumbered(self):
		self.assertTyping('3. Test', '<li indent="0" style="numbered-list">3. Test</li>')

	def testAutoFormatBulletWithinList(self):
		self.set_buffer(self.buffer, '<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Test</li>')
		iter = self.buffer.get_start_iter()
		iter.forward_chars(2) # put it behind the checkbox
		self.buffer.place_cursor(iter)
		self.assertTyping('* ', '<li indent="0" style="bullet-list">\u2022 Test</li>')

	def testNoAutoFormatNumberedWithinList(self):
		self.set_buffer(self.buffer, '<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> Test</li>')
		iter = self.buffer.get_start_iter()
		iter.forward_chars(2) # put it behind the checkbox
		self.buffer.place_cursor(iter)
		self.assertTyping('1. ', '<li indent="0" style="unchecked-box"><icon stock="zim-unchecked-box" /> 1. Test</li>')

	def testNoAutoFormatBulletInHeading(self):
		self.set_buffer(self.buffer, '<h level="1">test\n</h>')
		self.buffer.place_cursor(self.buffer.get_iter_at_offset(0))
		self.assertTyping('* Test ', '<h level="1">* Test test\n</h>')

	def testNoAutoFormatBullerInVerbatim(self):
		self.buffer.toggle_format_tag_by_name('code')
		self.assertTyping('* Test ', '<code>* Test </code>')

	#def testUnicodeCamelCase(self):
	#	self.assertTyping('ВаняИванов', '<link href="None">ВаняИванов</link>')

	def testUnicodeLinks(self):
		# Different style test framework, probably needs locale settings to
		# work with "assertTyping()"
		test = (
			'ВаняИванов',		# CamelCase
			'+ВаняИванов',		# page match
			'ВаняИванов:foo', 	# page match
		)

		buffer = self.view.get_buffer()
		for word in test:
			buffer.insert_at_cursor(word)
			iter = buffer.get_insert_iter()
			start = iter.copy()
			start.backward_chars(len(word))
			char = '\n'
			editmode = []
			self.view.emit('end-of-word', start, iter, word, char, editmode)
			buffer.insert_at_cursor('\n')

		xml = buffer.get_parsetree().tostring()
		self.assertEqual(xml,
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="ВаняИванов">ВаняИванов</link>\n'
			'<link href="+ВаняИванов">+ВаняИванов</link>\n'
			'<link href="ВаняИванов:foo">ВаняИванов:foo</link>\n'
			'</p></zim-tree>'
		)


class TestCamelCase(tests.TestCase):

	def testLatin(self):
		for text in (
			'CamelCase', 'AbbA',
			'ĚěščřžýáíéúůŮěščřžýáíéúů'
		):
			self.assertTrue(
				camelcase(str(text)),
				msg='"%s" should be CamelCase' % text
			)

		for text in (
			'A', 'AAAA', 'aaaa', 'Aaaaa', 'AAAAaaa', 'aAAAAA', 'aaaAAA',
			'123', 'A123A123',
			'ĚŠČŘŽÝÁÍÉÚŮ', 'ěščřžýáíéúů',
		):
			self.assertFalse(
				camelcase(str(text)),
				msg='"%s" should NOT be CamelCase' % text
			)

	def testArabic(self):
		# Arabic text should never be CamelCase,
		# letters test as neither upper not lower case
		for text in (
			'سلام',
			'کهکشان',
			'روزانه',
			'ذائقه',
			'آبادی',
			'انشاء',
			'محَبّت',
			'اَعْداد',
			'حتماً',
			'ماوراء‌الطبیعه',
			'پشتک‌وارو',
			'راه‌راه',
			' یاپ کارزنبرگ',
		):
			assert isinstance(text, str)
			self.assertFalse(
				camelcase(str(text)),
				msg='"%s" should NOT be CamelCase' % text
			)


class TestPageView(tests.TestCase, TextBufferTestCaseMixin):

	def testInitPageTemplateWithoutPlaceCursor(self):
		file = XDG_DATA_HOME.file('zim/templates/wiki/Default.txt')
		file.write(
			'======= [% page.basename %] =======\n'
			'[% gettext("Created") %] [% strftime("%A %d %B %Y") %]\n'
		)

		buffer = self._test_init_page_template()
		start, end = buffer.get_bounds()
		iter = buffer.get_insert_iter()
		self.assertTrue(iter.equal(end))

	def testInitPageTemplateWithPlaceCursor(self):
		file = XDG_DATA_HOME.file('zim/templates/wiki/Default.txt')
		file.write(
			'======= [% page.basename %] =======\n'
			'[% place_cursor() %]\n'
			'\n'
			'[% gettext("Created") %] [% strftime("%A %d %B %Y") %]\n'
		)

		CURSOR_CHAR = '\ufffe' # unicode "non-character"
		buffer = self._test_init_page_template()
		start, end = buffer.get_bounds()
		iter = buffer.get_insert_iter()
		self.assertFalse(iter.equal(end))
		self.assertNotIn(CURSOR_CHAR, start.get_text(end))

	def _test_init_page_template(self):
		# test we have text for a new page, but it does not get saved unless modified
		notebook = self.setUpNotebook()
		pageview = setUpPageView(notebook)
		page = notebook.get_page(Path('nonexistingpage'))
		self.assertFalse(page.exists())
		pageview.set_page(page)

		buffer = pageview.textview.get_buffer()
		start, end = buffer.get_bounds()
		self.assertTrue(len(start.get_text(end)) > 10)
		parsetree = buffer.get_parsetree()
		self.assertIsNone(parsetree)

		buffer.insert_at_cursor('test')
		parsetree = buffer.get_parsetree()
		self.assertIsNotNone(parsetree)

		return buffer

	def testGetSelection(self):
		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()
		buffer.set_text('''\
Foo bar
Baz
''')
		iter = buffer.get_iter_at_offset(5)
		buffer.place_cursor(iter)
		self.assertEqual(pageview.get_word(), 'bar')
		self.assertEqual(pageview.get_selection(), 'bar')
		self.assertEqual(pageview.get_selection(format='wiki'), 'bar')

	def testInsertLinks(self):
		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()
		buffer.set_text('''Test 123\n''')

		buffer.place_cursor(buffer.get_end_iter())
		file1 = LocalFile(os_native_path('/foo.txt'))
		pageview.insert_links((Path("foo"), file1, "~/bar.txt"))
		wantedtext = 'Test 123\nfoo\n%s\n%s\n' % (file1.uri, os_native_path('~/bar.txt'))
		text = get_text(buffer)
		self.assertEqual(text, wantedtext)

		buffer.place_cursor(buffer.get_iter_at_line(2))
		buffer.select_line()
		pageview.insert_links(('http://cpan.org',))
		wantedtext = 'Test 123\nfoo\n%s%s\n' % ('http://cpan.org ', os_native_path('~/bar.txt'))
		text = get_text(buffer)
		self.assertEqual(text, wantedtext)

	def testLinkClicked(self):
		pageview = setUpPageView(self.setUpNotebook('test'))
		pageview.page = Path('test')

		for href in ('foo', 'foo:bar', 'mailto:foo.com'):
			pageview.activate_link(href)
			self.assertEqual(
				pageview.navigation.lastMethodCall,
				('open_page', Path(href), {'new_window': False, 'anchor': None})
			)
		for href, anchor in [('foo', 'sub-heading')]:
			pageview.activate_link('%s#%s' % (href, anchor))
			self.assertEqual(
				pageview.navigation.lastMethodCall,
				('open_page', Path(href), {'new_window': False, 'anchor': anchor})
			)

		pageview.activate_link('zim+file://foo/bar?dus.txt')
		self.assertEqual(pageview.navigation.lastMethodCall, ('open_notebook', 'file://foo/bar', 'dus.txt'))

		file = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL).file('test.txt')
		file.touch()
		def check_file(args):
			self.assertEqual(LocalFile(args[-1]), file)

		with tests.ApplicationContext(check_file):
			pageview.activate_link(file.uri)

		for href, want in (
			('http://foo/bar', None),
			('http://192.168.168.100', None),
			('file+ssh://foo/bar', None),
			('mailto:foo@bar.com', None),
			('foo@bar.com', 'mailto:foo@bar.com'),
			('mailto:foo//bar@bar.com', None),
			('mid:foo@bar.org', None),
			('cid:foo@bar.org', None),
			('wp?foo', 'https://en.wikipedia.org/wiki/foo'),
			('http://foo?bar', None),
			# ('\\\\host\\foo\\bar', None), FIXME os dependent parsing
		):
			def check_url(args):
				self.assertEqual(args[-1], want or href)

			with tests.ApplicationContext(check_url):
				pageview.activate_link(href)

	def testPluginCanHandleURL(self):
		pageview = setUpPageView(self.setUpNotebook())

		def myhandler(o, link, hints):
			if link.startswith('myurl://'):
				return True

		id = pageview.connect('activate-link', myhandler)

		pageview.do_activate_link = tests.CallBackLogger()
		pageview.activate_link('foo')
		self.assertTrue(pageview.do_activate_link.hasBeenCalled) # pass through to default

		pageview.do_activate_link = tests.CallBackLogger()
		pageview.activate_link('myurl://foo') # No raise
		self.assertFalse(pageview.do_activate_link.hasBeenCalled) # no pass through to default

		pageview.disconnect(id)

	def testEditBarHiddenWhenFindBarShown(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.preferences['show_edit_bar'] = True
		self.assertTrue(pageview.edit_bar.get_property('visible'))
		self.assertFalse(pageview.find_bar.get_property('visible'))

		pageview.show_find()
		self.assertFalse(pageview.edit_bar.get_property('visible'))
		self.assertTrue(pageview.find_bar.get_property('visible'))

		pageview.hide_find()
		self.assertTrue(pageview.edit_bar.get_property('visible'))
		self.assertFalse(pageview.find_bar.get_property('visible'))

	def testEditBarHiddenForReadOnly(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.set_readonly(True)
		self.assertFalse(pageview.edit_bar.get_property('visible'))
		self.assertFalse(pageview.find_bar.get_property('visible'))

		pageview.show_find()
		self.assertFalse(pageview.edit_bar.get_property('visible'))
		self.assertTrue(pageview.find_bar.get_property('visible'))

		pageview.hide_find()
		self.assertFalse(pageview.edit_bar.get_property('visible'))
		self.assertFalse(pageview.find_bar.get_property('visible'))


class TestFormatActions(tests.TestCase, TextBufferTestCaseMixin):

	def setUp(self):
		self.pageview = setUpPageView(self.setUpNotebook())
		self.buffer = self.pageview.textview.get_buffer()
		self.buffer.set_text("Test 123\n")

	def activate(self, name):
		# TODO: directly use action methods instead of actiongroup
		self.pageview.actiongroup.get_action(name).activate()

	def testApplyFormatHeadingWithSelection(self):
		self.buffer.select_line(0)
		self.activate('apply_format_h3')
		self.assertBufferEqual(self.buffer, '<h level="3">Test 123\n</h>')

	def testApplyFormatHeadingNoSelection(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.activate('apply_format_h3')
		self.assertBufferEqual(self.buffer, '<h level="3">Test 123\n</h>')
		self.assertFalse(self.buffer.get_has_selection())
		cursor = self.buffer.get_insert_iter().get_offset()
		self.assertEqual(cursor, 0)

	def testApplyFormatHeadingOnHeading(self):
		self.buffer.select_line(0)
		self.activate('apply_format_h3')
		self.buffer.select_line(0)
		self.activate('apply_format_h4')
		self.assertBufferEqual(self.buffer, '<h level="4">Test 123\n</h>')

	def testApplyFormatHeadingNoSelection(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.activate('apply_format_h3')
		self.assertBufferEqual(self.buffer, '<h level="3">Test 123\n</h>')

	def testApplyFormatHeadingWithFormatting(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_strong')
		self.buffer.select_line(0)
		self.activate('apply_format_h3')
		self.assertBufferEqual(self.buffer, '<h level="3"><strong>Test</strong> 123\n</h>')

	def testApplyFormattingOnHeading(self):
		self.buffer.select_line(0)
		self.activate('apply_format_h3')
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<h level="3"><strong>Test</strong> 123\n</h>')

	def testApplyFormatStrong(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')

	def testApplyFormatStrongNoSelectionBeginOfWord(self):
		# Only one-way toggle of word, no auto-select for un-toggling
		# because cursor is at boundary of formatting
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')

	def testApplyFormatStrongNoSelectionMiddleOfWord(self):
		# Both ways the word is auto-selected and toggles
		iter = self.buffer.get_start_iter()
		iter.forward_cursor_positions(2)
		self.buffer.place_cursor(iter)
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, 'Test 123\n')

	def testApplyFormatStrongNoSelectionEndOfWord(self):
		# No auto-select at end of word - so test nothing happens both ways
		iter = self.buffer.get_start_iter()
		iter.forward_cursor_positions(4)
		self.buffer.place_cursor(iter)
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, 'Test 123\n')
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')
		self.buffer.place_cursor(iter)
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')

	def testApplyFormatEmphasis(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_emphasis')
		self.assertBufferEqual(self.buffer, '<emphasis>Test</emphasis> 123\n')

	def testApplyFormatMark(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_mark')
		self.assertBufferEqual(self.buffer, '<mark>Test</mark> 123\n')

	def testApplyFormatStrike(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_strike')
		self.assertBufferEqual(self.buffer, '<strike>Test</strike> 123\n')

	def testApplyFormatCode(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_code')
		self.assertBufferEqual(self.buffer, '<code>Test</code> 123\n')

	def testApplyFormatVerbatimForLines(self):
		# Automatic conversion of "code" to "verbatim"
		self.buffer.set_text('line1\nline2\nline3\n')
		start = self.buffer.get_iter_at_line(1)
		end = self.buffer.get_iter_at_line(2)
		self.buffer.select_range(start, end)
		self.activate('apply_format_code')
		self.assertBufferEqual(self.buffer, 'line1\n<pre>line2\n</pre>line3\n')

	def testNotApplyFormatVerbatimForHalfLines(self):
		# No conversion if not selected up to and *including* line end
		# this is crucial to allow both behaviors and not block code formatting
		# of a whole line
		self.buffer.set_text('line1\nline2\nline3\n')
		start = self.buffer.get_iter_at_line(1)
		end = self.buffer.get_iter_at_line(2)
		end.backward_chars(1)
		self.buffer.select_range(start, end)
		self.activate('apply_format_code')
		self.assertBufferEqual(self.buffer, 'line1\n<code>line2</code>\nline3\n')

	def testApplyFormatVerbatimForLinesPreservesWhitespaceIndent(self):
		self.buffer.set_text('line1\n    line2\nline3\n')
		start = self.buffer.get_iter_at_line(1)
		end = self.buffer.get_iter_at_line(2)
		self.buffer.select_range(start, end)
		self.activate('apply_format_code')
		self.assertBufferEqual(self.buffer, 'line1\n<pre>    line2\n</pre>line3\n')
		self.assertEqual(''.join(self.pageview.page.dump('wiki')), "line1\n'''\n    line2\n'''\nline3\n")

	def testApplyFormatVerbatimOnStyle(self):
		self.buffer.set_text('line1\nline2\nline3\n')
		self.buffer.place_cursor(self.buffer.get_iter_at_line(1))
		self.buffer.select_word()
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, 'line1\n<strong>line2</strong>\nline3\n')
		bounds = self.buffer.get_bounds()
		self.buffer.select_range(*bounds)
		self.activate('apply_format_code')
		self.assertBufferEqual(self.buffer, '<pre>line1\nline2\nline3\n</pre>')

	def testApplyStyleOnFormatVerbatim(self):
		self.buffer.set_text('line1\nline2\nline3\n')
		bounds = self.buffer.get_bounds()
		self.buffer.select_range(*bounds)
		self.activate('apply_format_code')
		self.assertBufferEqual(self.buffer, '<pre>line1\nline2\nline3\n</pre>')
		self.buffer.place_cursor(self.buffer.get_iter_at_line(1))
		self.buffer.select_word()
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<pre>line1\nline2\nline3\n</pre>')

	def testApplyFormatSup(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_sup')
		self.assertBufferEqual(self.buffer, '<sup>Test</sup> 123\n')

	def testApplyFormatSub(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('apply_format_sub')
		self.assertBufferEqual(self.buffer, '<sub>Test</sub> 123\n')

	def testApplyFormatMultiple(self):
		self.buffer.select_line(0)
		self.activate('apply_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test 123</strong>\n')
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.activate('apply_format_strike')
		self.assertBufferEqual(self.buffer, '<strong><strike>Test</strike> 123</strong>\n')

	def testToggleFormatStrongSelection(self):
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.activate('toggle_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')
		self.assertFalse(self.buffer.get_has_selection())
		cursor = self.buffer.get_insert_iter().get_offset()
		self.assertEqual(cursor, 0)
		self.activate('toggle_format_strong')
		self.assertBufferEqual(self.buffer, '<strong>Test</strong> 123\n')
			# no selection, no change
		self.buffer.place_cursor(self.buffer.get_start_iter())
		self.buffer.select_word()
		self.activate('toggle_format_strong')
		self.assertBufferEqual(self.buffer, 'Test 123\n')

	def testToggleFormatStrongInsertMode(self):
		self.buffer.set_text('')
		self.buffer.insert_at_cursor('Test ')
		self.activate('toggle_format_strong')
		self.buffer.insert_at_cursor('bold')
		self.activate('toggle_format_strong')
		self.buffer.insert_at_cursor(' text')
		self.assertBufferEqual(self.buffer, 'Test <strong>bold</strong> text')

	def testMultiFormatInsertMode(self):
		self.buffer.set_text('')
		self.buffer.insert_at_cursor('Test ')
		self.activate('toggle_format_strong')
		self.activate('toggle_format_emphasis')
		self.buffer.insert_at_cursor('bolditalic')
		self.activate('toggle_format_strong')
		self.activate('toggle_format_emphasis')
		self.buffer.insert_at_cursor(' text')
		self.assertBufferEqual(self.buffer, 'Test <emphasis><strong>bolditalic</strong></emphasis> text')


class TestPageViewActions(tests.TestCase):

	def testSavePage(self):
		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		pageview.save_page()
		lines = pageview.page.source_file.readlines()
		self.assertEqual(lines[-1], 'test 123\n') # Other lines are source headers

	def testSavePageWithHeaderMixup(self):
		# This is a test for specific error condition where first line of
		# pageview got interpreted as page header, resulting in crash
		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()
		buffer.set_text('a: b\n')
		pageview.save_page()
		lines = pageview.page.source_file.readlines()
		self.assertEqual(lines[-1], 'a: b\n') # Other lines are real source headers

	def testUndoRedo(self):
		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()

		for text in ('test', ' ', '123'):
			with buffer.user_action:
				buffer.insert_at_cursor(text)

		self.assertEqual(get_text(buffer), 'test 123')

		for text in ('test ', 'test', ''):
			pageview.undo()
			self.assertEqual(get_text(buffer), text)

		for text in ('test', 'test ', 'test 123'):
			pageview.redo()
			self.assertEqual(get_text(buffer), text)

	@tests.expectedFailure
	def testCopyAndPaste(self):
		pageview1 = setUpPageView(self.setUpNotebook(), 'test 123\n')
		pageview2 = setUpPageView(self.setUpNotebook())

		buffer1 = pageview1.view.get_buffer()
		begin = buffer1.get_iter_at_offset(5)
		end = buffer1.get_iter_at_offset(8)
		buffer1.select_range(begin, end)

		buffer2 = pageview2.view.get_buffer()

		pageview1.copy()
		pageview2.paste()

		self.assertEqual(get_text(buffer1), 'test 123\n')
		self.assertEqual(get_text(buffer2), '123\n')

	@tests.expectedFailure
	def testCutAndPaste(self):
		pageview1 = setUpPageView(self.setUpNotebook(), 'test 123\n')
		pageview2 = setUpPageView(self.setUpNotebook())

		buffer1 = pageview1.view.get_buffer()
		begin = buffer1.get_iter_at_offset(5)
		end = buffer1.get_iter_at_offset(8)
		buffer1.select_range(begin, end)

		buffer2 = pageview2.view.get_buffer()

		pageview1.cut()
		pageview2.paste()

		self.assertEqual(get_text(buffer1), 'test \n')
		self.assertEqual(get_text(buffer2), '123\n')

	def testDelete(self):
		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		buffer.place_cursor(buffer.get_iter_at_offset(1))
		self.assertEqual(get_text(buffer), 'test 123')
		pageview.delete()
		self.assertEqual(get_text(buffer), 'tst 123')
		pageview.delete()
		self.assertEqual(get_text(buffer), 'tt 123')

	def testUnCheckCheckBox(self):
		pageview = setUpPageView(self.setUpNotebook(), '[*] my task\n')
		pageview.uncheck_checkbox()
		self.assertEqual(pageview.page.dump('wiki'), ['[ ] my task\n'])

	def testToggleCheckBox(self):
		pageview = setUpPageView(self.setUpNotebook(), '[ ] my task\n')
		pageview.toggle_checkbox()
		self.assertEqual(pageview.page.dump('wiki'), ['[*] my task\n'])

	def testXToggleCheckBox(self):
		pageview = setUpPageView(self.setUpNotebook(), '[*] my task\n')
		pageview.xtoggle_checkbox()
		self.assertEqual(pageview.page.dump('wiki'), ['[x] my task\n'])

	def testMigrateCheckBox(self):
		pageview = setUpPageView(self.setUpNotebook(), '[*] my task\n')
		pageview.migrate_checkbox()
		self.assertEqual(pageview.page.dump('wiki'), ['[>] my task\n'])

	def testTransmigrateCheckBox(self):
		pageview = setUpPageView(self.setUpNotebook(), '[*] my task\n')
		pageview.transmigrate_checkbox()
		self.assertEqual(pageview.page.dump('wiki'), ['[<] my task\n'])

	def testEditObjectForLink(self):
		pageview = setUpPageView(self.setUpNotebook(), '[[link]]\n')

		def edit_link(dialog):
			dialog.set_input(href='test')
			dialog.assert_response_ok()

		with tests.DialogContext(edit_link):
			pageview.edit_object()

		self.assertEqual(pageview.page.dump('wiki'), ['[[test]]\n'])

	def testEditObjectForImage(self):
		file = tests.ZIM_DATA_FOLDER.file('zim.png')
		pageview = setUpPageView(self.setUpNotebook(), '{{%s}}\n' % file.path)

		def edit_img(dialog):
			dialog.set_input(href='test')
			dialog.assert_response_ok()

		with tests.DialogContext(edit_img):
			pageview.edit_object()

		text = ''.join(pageview.page.dump('wiki')).strip()
		self.assertTrue(text.startswith('{{') and text.endswith('?href=test}}'), '%r does not match \\{\\{...?href=test\\}\\}' % text)
		self.assertEqual(LocalFile(text[2:-12]), file)

	def testEditObjectForObject(self):
		pageview = setUpPageView(self.setUpNotebook(), '{{{test:\nfoo\n}}}\n')

		buffer = pageview.textview.get_buffer()
		anchor = buffer.get_objectanchor(buffer.get_insert_iter())
		widget = anchor.get_widgets()[0]

		widget.edit_object = tests.CallBackLogger()

		pageview.edit_object()

		self.assertTrue(widget.edit_object.hasBeenCalled)

	def testRemoveLink(self):
		pageview = setUpPageView(self.setUpNotebook(), '[[link]]\n')
		buffer = pageview.textview.get_buffer()
		buffer.place_cursor(buffer.get_iter_at_offset(2))
		pageview.remove_link()
		self.assertEqual(pageview.page.dump('wiki'), ['link\n'])

	def testRemoveLinkWithIter(self):
		pageview = setUpPageView(self.setUpNotebook(), '[[link]] foo\n')
		buffer = pageview.textview.get_buffer()
		buffer.place_cursor(buffer.get_iter_at_offset(8))
		iter = buffer.get_iter_at_offset(2)
		pageview.remove_link(iter)
		self.assertEqual(pageview.page.dump('wiki'), ['link foo\n'])

	def testRemoveLinkWithSelection(self):
		pageview = setUpPageView(self.setUpNotebook(), '[[link]]\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(2)
		end = buffer.get_iter_at_offset(4)
		buffer.select_range(begin, end)
		pageview.remove_link()
		self.assertEqual(pageview.page.dump('wiki'), ['[[li]]nk\n'])

	def testReplaceSelection(self):
		pageview = setUpPageView(self.setUpNotebook(), 'this_has_a_bug\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(5)
		end = buffer.get_iter_at_offset(8)
		buffer.select_range(begin, end)
		pageview.replace_selection('does_not_have')
		self.assertEqual(pageview.page.dump('wiki'), ['this_does_not_have_a_bug\n'])

	def testInsertDate(self):
		pageview = setUpPageView(self.setUpNotebook())

		with tests.DialogContext(InsertDateDialog):
			pageview.insert_date()

		self.assertFalse(pageview.page.dump('wiki')[0].isspace())

	def testInsertLine(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		buffer = pageview.textview.get_buffer()
		buffer.place_cursor(buffer.get_iter_at_offset(9))
		pageview.insert_line()
		self.assertEqual(pageview.page.dump('wiki'), ['test 123\n', '--------------------\n'])

	def testInsertImage(self):
		pageview = setUpPageView(self.setUpNotebook())
		file = tests.ZIM_DATA_FOLDER.file('zim.png')

		def choose_file(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		with tests.DialogContext(choose_file):
			pageview.show_insert_image()

		text = ''.join(pageview.page.dump('wiki')).strip()
		self.assertTrue(text.startswith('{{') and text.endswith('}}'), '%r does not match \\{\\{...\\}\\}' % text)
		self.assertEqual(LocalFile(text[2:-2]), file)

	def testAttachFile(self):
		pageview = setUpPageView(self.setUpNotebook())
		notebook = pageview.notebook
		page = pageview.page

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('Attachment.abc')
		file.write('Test ABC\n')

		def attach_file(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		with tests.DialogContext(attach_file):
			pageview.attach_file()

		attach_folder = notebook.get_attachments_dir(page)
		attach_file = attach_folder.file('Attachment.abc')
		self.assertTrue(attach_file.exists())
		self.assertEqual(attach_file.read(), file.read())

	def testAttachFileResolveExistingFile(self):
		pageview = setUpPageView(self.setUpNotebook())
		notebook = pageview.notebook
		page = pageview.page

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('Attachment.abc')
		file.write('Test ABC\n')

		attach_folder = notebook.get_attachments_dir(page)
		conflict_file = attach_folder.file('Attachment.abc')
		conflict_file.write('Conflict\n')

		def attach_file(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		def resolve_conflict(dialog):
			dialog.set_input(name='NewName.abc')
			dialog.assert_response_ok()

		with tests.DialogContext(attach_file, resolve_conflict):
			pageview.attach_file()

		attach_file = attach_folder.file('NewName.abc')
		self.assertTrue(attach_file.exists())
		self.assertEqual(attach_file.read(), file.read())

		self.assertEqual(conflict_file.read(), 'Conflict\n')

	def testAttachFileOverwriteExistingFile(self):
		pageview = setUpPageView(self.setUpNotebook())
		notebook = pageview.notebook
		page = pageview.page

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('Attachment.abc')
		file.write('Test ABC\n')

		attach_folder = notebook.get_attachments_dir(page)
		conflict_file = attach_folder.file('Attachment.abc')
		conflict_file.write('Conflict\n')

		def attach_file(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		def resolve_conflict(dialog):
			dialog.do_response_overwrite()

		with tests.DialogContext(attach_file, resolve_conflict):
			pageview.attach_file()

		self.assertEqual(conflict_file.read(), file.read())

	def testInsertBulletList(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.insert_bullet_list()
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		self.assertEqual(pageview.page.dump('wiki'), ['* test 123\n'])

	def testInsertNumberedList(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.insert_numbered_list()
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		self.assertEqual(pageview.page.dump('wiki'), ['1. test 123\n'])

	def testInsertCheckBoxList(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.insert_checkbox_list()
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		self.assertEqual(pageview.page.dump('wiki'), ['[ ] test 123\n'])

	def testApplyBulletList(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(0)
		end = buffer.get_iter_at_offset(8)
		buffer.select_range(begin, end)
		pageview.apply_format_bullet_list()
		self.assertEqual(pageview.page.dump('wiki'), ['* test 123\n'])

	def testApplyBulletListWithoutSelection(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		buffer = pageview.textview.get_buffer()
		buffer.place_cursor(buffer.get_start_iter())
		pageview.apply_format_bullet_list()
		self.assertEqual(pageview.page.dump('wiki'), ['* test 123\n'])

	def testApplyBulletListOnHeadingRemovesHeading(self):
		pageview = setUpPageView(self.setUpNotebook(), '== test 123\n')
		self.assertEqual(pageview.page.dump('wiki'), ['== test 123 ==\n'])
		buffer = pageview.textview.get_buffer()
		buffer.place_cursor(buffer.get_start_iter())
		pageview.apply_format_bullet_list()
		self.assertEqual(pageview.page.dump('wiki'), ['* test 123\n'])

	def testApplyBulletSkipsEmptyLines(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n\nabc\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(0)
		end = buffer.get_iter_at_offset(14)
		buffer.select_range(begin, end)
		pageview.apply_format_bullet_list()
		self.assertEqual(pageview.page.dump('wiki'), ['* test 123\n', '\n', '* abc\n'])

	def testApplyNumberedList(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(0)
		end = buffer.get_iter_at_offset(8)
		buffer.select_range(begin, end)
		pageview.apply_format_numbered_list()
		self.assertEqual(pageview.page.dump('wiki'), ['1. test 123\n'])

	def testApplyCheckBoxList(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(0)
		end = buffer.get_iter_at_offset(8)
		buffer.select_range(begin, end)
		pageview.apply_format_checkbox_list()
		self.assertEqual(pageview.page.dump('wiki'), ['[ ] test 123\n'])

	def testInsertTextFromFile(self):
		pageview = setUpPageView(self.setUpNotebook())
		file = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL).file('test.txt')
		file.write('my text\n')

		def select_file(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		with tests.DialogContext(select_file):
			pageview.insert_text_from_file()

		self.assertEqual(pageview.page.dump('wiki'), ['my text\n'])

	def testInsertLink(self):
		pageview = setUpPageView(self.setUpNotebook())

		def select_link(dialog):
			dialog.set_input(href='mylink')
			dialog.assert_response_ok()

		with tests.DialogContext(select_link):
			pageview.insert_link()

		self.assertEqual(pageview.page.dump('wiki'), ['[[mylink]]'])

		def update_link(dialog):
			dialog.set_input(href='mylink', text="foo")
			dialog.assert_response_ok()

		buffer = pageview.textview.get_buffer()
		buffer.place_cursor(buffer.get_iter_at_offset(3))
		with tests.DialogContext(update_link):
			pageview.insert_link()

		self.assertEqual(pageview.page.dump('wiki'), ['[[mylink|foo]]'])

	def testOpenFileTemplatesFolder(self):
		pageview = setUpPageView(self.setUpNotebook())
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		pageview.preferences['file_templates_folder'] = folder.path

		def create_folder(dialog):
			dialog.answer_yes()

		def open_folder(args):
			self.assertEqual(LocalFolder(args[-1]), folder)

		with tests.DialogContext(create_folder):
			with tests.ApplicationContext(open_folder):
				pageview.open_file_templates_folder()

		# no create_folder here
		with tests.ApplicationContext(open_folder):
			pageview.open_file_templates_folder()

	def testClearFormatting(self):
		pageview = setUpPageView(self.setUpNotebook(), '**test 123**\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(0)
		end = buffer.get_iter_at_offset(8)
		buffer.select_range(begin, end)
		pageview.clear_formatting()
		self.assertEqual(pageview.page.dump('wiki'), ['test 123\n'])

	def testShowFind(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		self.assertFalse(pageview.find_bar.get_property('visible'))
		pageview.show_find()
		self.assertTrue(pageview.find_bar.get_property('visible'))

	def testShowFindWithQuery_FindNext_FindPrevious(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		self.assertFalse(pageview.find_bar.get_property('visible'))
		pageview.show_find('test')
		self.assertTrue(pageview.find_bar.get_property('visible'))

		pageview.find_next()
		pageview.find_previous()
		# TODO: what to assert here ?

	def testShowFindAndReplace(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')

		def replace(dialog):
			dialog.set_input(query='test', replacement='TEST')
			dialog.replace_all()

		with tests.DialogContext(replace):
			pageview.show_find_and_replace()

		self.assertEqual(pageview.page.dump('wiki'), ['TEST 123\n'])

	def testShowWordCount(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		with tests.DialogContext(WordCountDialog):
			pageview.show_word_count()

	def testZoom(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		pageview.text_style['TextView']['font'] = 'Arial 10'

		pageview.zoom_in()
		self.assertEqual(pageview.text_style['TextView']['font'], 'Arial 11')
		pageview.zoom_in()
		self.assertEqual(pageview.text_style['TextView']['font'], 'Arial 12')
		pageview.zoom_out()
		self.assertEqual(pageview.text_style['TextView']['font'], 'Arial 11')
		pageview.zoom_reset()
		#self.assertEqual(pageview.text_style['TextView']['font'], 'Arial 10') # FIXME

	def testCopyCurrentLine(self):
		# Check that the current line, where the cursor is located, can be
		# copied from one page to another via the copy current line feature.
		pageView1Text = 'test 123\ntest 456\ntest 789\n'
		pageview1 = setUpPageView(self.setUpNotebook(), pageView1Text)
		pageview2 = setUpPageView(self.setUpNotebook())

		buffer1 = pageview1.textview.get_buffer()
		buffer2 = pageview2.textview.get_buffer()
		self.assertEqual(get_text(buffer2), '')

		buffer1.place_cursor(buffer1.get_iter_at_offset(12))
		pageview1.copy_current_line()
		pageview2.paste()

		self.assertEqual(get_text(buffer1), pageView1Text)
		self.assertEqual(get_text(buffer2), 'test 456\n')

		# Ensure copying a line with no text does not add anything
		# to the clipboard.
		Clipboard.clear()
		buffer1.place_cursor(buffer1.get_bounds()[-1]) # after final "\n"
		pageview1.copy_current_line()
		with tests.LoggingFilter('zim.gui.clipboard'):
			self.assertIsNone(Clipboard.get_parsetree())

	def testCutCurrentLine(self):
		# Check that the current line, where the cursor is located, is cut and
		# can be copied from one page to another via the cut current line feature.
		pageView1Text = 'test 123\ntest 456\ntest 789\n'
		pageview1 = setUpPageView(self.setUpNotebook(), pageView1Text)
		pageview2 = setUpPageView(self.setUpNotebook())

		buffer1 = pageview1.textview.get_buffer()
		buffer2 = pageview2.textview.get_buffer()
		self.assertEqual(get_text(buffer2), '')

		buffer1.place_cursor(buffer1.get_iter_at_offset(12))
		pageview1.cut_current_line()
		pageview2.paste()

		self.assertEqual(get_text(buffer1), 'test 123\ntest 789\n')
		self.assertEqual(get_text(buffer2), 'test 456\n')

	def testCutCurrentLines(self):
		# Check that the multiple lines within the selection bounds are cut and
		# can be copied from one page to another via the cut current line feature.
		pageView1Text = 'test 123\ntest 456\ntest 789\n'
		pageview1 = setUpPageView(self.setUpNotebook(), pageView1Text)
		pageview2 = setUpPageView(self.setUpNotebook())

		buffer1 = pageview1.textview.get_buffer()
		buffer2 = pageview2.textview.get_buffer()
		self.assertEqual(get_text(buffer2), '')

		buffer1.select_range(buffer1.get_iter_at_offset(3), buffer1.get_iter_at_offset(12))
		pageview1.cut_current_line()
		pageview2.paste()

		self.assertEqual(get_text(buffer1), 'test 789\n')
		self.assertEqual(get_text(buffer2), 'test 123\ntest 456\n')

class TestPageviewDialogs(tests.TestCase):

	def testVarious(self):
		'''Test input/output of various pageview dialogs'''
		## Insert Date dialog
		buffer = tests.MockObject(methods=('insert_at_cursor', 'insert_link_at_cursor'))
		notebook = tests.MockObject(
			return_values={
				'get_page': None,
				'suggest_link': Path(':suggested_link')
			}
		)
		page = Path('test')

		dialog = InsertDateDialog(None, buffer, notebook, page)
		dialog.linkbutton.set_active(False)
		dialog.view.get_selection().select_path((0,))
		dialog.assert_response_ok()
		self.assertEqual(buffer.lastMethodCall[0], 'insert_at_cursor')

		dialog = InsertDateDialog(None, buffer, notebook, page)
		dialog.linkbutton.set_active(True)
		dialog.view.get_selection().select_path((0,))
		dialog.assert_response_ok()
		self.assertEqual(buffer.lastMethodCall[0], 'insert_link_at_cursor')

		## Insert Image dialog
		buffer = tests.MockObject()
		file = tests.ZIM_DATA_FOLDER.file('zim.png')
		dialog = InsertImageDialog(None, buffer, notebook, Path(':some_page'), file)
		self.assertTrue(dialog.filechooser.get_preview_widget_active())
		#~ self.assertEqual(dialog.get_file(), file)
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(buffer.lastMethodCall[0], 'insert_image_at_cursor')

		## Edit Image dialog
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		notebook = tests.MockObject(
			return_values={
				'get_page': None,
				'resolve_file': file,
				'relative_filepath': './data/zim.png'
			}
		)
		file = tests.ZIM_DATA_FOLDER.file('zim.png')
		buffer.insert_image_at_cursor(file, '../MYPATH/./data/zim.png')
		dialog = EditImageDialog(None, buffer, notebook, Path(':some_page'))
		self.assertEqual(dialog.form['width'], 48)
		self.assertEqual(dialog.form['height'], 48)
		dialog.form['width'] = 100
		self.assertEqual(dialog.form['width'], 100)
		self.assertEqual(dialog.form['height'], 100)
		dialog.reset_dimensions()
		self.assertEqual(dialog.form['width'], 48)
		self.assertEqual(dialog.form['height'], 48)
		dialog.form['height'] = 24
		self.assertEqual(dialog.form['width'], 24)
		self.assertEqual(dialog.form['height'], 24)
		dialog.assert_response_ok()
		iter = buffer.get_iter_at_offset(0)
		imagedata = buffer.get_image_data(iter)
		self.assertEqual(imagedata, {
			'src': './data/zim.png', # preserve relative path
			'height': 24,
		})
		self.assertEqual(type(imagedata['height']).__name__, 'int')

		## Insert text from file dialog
		buffer = tests.MockObject()
		dialog = InsertTextFromFileDialog(None, buffer, notebook, Path(':some_page'))
		#~ dialog.set_file()
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(buffer.lastMethodCall[0], 'insert_parsetree_at_cursor')

		## Find And Replace dialog
		textview = TextView({})
		buffer = textview.get_buffer()
		buffer.set_text('''\
foo bar foooobar
foo bar bazzz baz
''')
		dialog = FindAndReplaceDialog(None, textview)
		dialog.find_entry.set_text('foo')
		dialog.replace_entry.set_text('dus')
		dialog.word_option_checkbox.set_active(True)
		dialog.replace()
		dialog.replace_all()
		self.assertEqual(get_text(buffer), '''\
dus bar foooobar
dus bar bazzz baz
''')

		## Word Count dialog
		pageview = tests.MockObject()
		pageview.textview = textview
		dialog = WordCountDialog(pageview)
		dialog.destroy() # nothing to test really

	def testInsertLinkDialog(self):
		pageview = setUpPageView(self.setUpNotebook())
		dialog = InsertLinkDialog(None, pageview)
		dialog.form.widgets['href'].set_text('Foo:Bar')
		dialog.assert_response_ok()
		buffer = pageview.textview.get_buffer()
		self.assertEqual(
			buffer.get_parsetree().tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p><link href="Foo:Bar">Foo:Bar</link></p></zim-tree>'
		)

	def testInsertLinkDialogShortLinkName(self):
		pageview = setUpPageView(self.setUpNotebook())
		dialog = InsertLinkDialog(None, pageview)
		dialog.form.widgets['href'].set_text('Foo:Bar')
		dialog.form.widgets['short_links'].set_active(True)
		dialog.assert_response_ok()
		buffer = pageview.textview.get_buffer()
		self.assertEqual(
			buffer.get_parsetree().tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p><link href="Foo:Bar">Bar</link></p></zim-tree>'
		)

	def testInsertLinkDialogUpdateText(self):
		pageview = setUpPageView(self.setUpNotebook())
		dialog = InsertLinkDialog(None, pageview)
		dialog.form.widgets['href'].set_text('Foo:Bar')
		self.assertEqual(dialog.form.widgets['text'].get_text(), 'Foo:Bar') # Updated automatically

		dialog.form.widgets['text'].set_text('Some text') # Text no longer matches
		dialog.form.widgets['href'].set_text('Foo:Bar:Baz')
		self.assertEqual(dialog.form.widgets['text'].get_text(), 'Some text') # Did *not* change

		dialog.form.widgets['text'].set_text('Foo:Bar:Baz') # Now they match again
		dialog.form.widgets['href'].set_text('Foo:Bar')
		self.assertEqual(dialog.form.widgets['text'].get_text(), 'Foo:Bar') # Updated automatically

	def testInsertLinkDialogUpdateTextShortLinkName(self):
		pageview = setUpPageView(self.setUpNotebook())
		dialog = InsertLinkDialog(None, pageview)
		dialog.form.widgets['short_links'].set_active(True)
		dialog.form.widgets['href'].set_text('Foo:Bar')
		self.assertEqual(dialog.form.widgets['text'].get_text(), 'Bar') # Updated automatically

		dialog.form.widgets['text'].set_text('Some text') # Text no longer matches
		dialog.form.widgets['href'].set_text('Foo:Bar:Baz')
		self.assertEqual(dialog.form.widgets['text'].get_text(), 'Some text') # Did *not* change

		dialog.form.widgets['text'].set_text('Baz') # Now they match again
		dialog.form.widgets['href'].set_text('Foo:Bar')
		self.assertEqual(dialog.form.widgets['text'].get_text(), 'Bar') # Updated automatically


class TestDragAndDropFunctions(tests.TestCase):

	@tests.expectedFailure
	def testSerializeParseTree(self):
		tree = tests.new_parsetree()
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		with FilterNoSuchImageWarning():
			buffer.insert_parsetree_at_cursor(tree)

		start, end = buffer.get_bounds()
		xml = buffer.serialize(buffer, Gdk.Atom.intern('text/x-zim-parsetree', False), start, end)
		tree._etree.getroot().attrib['partial'] = True # HACK
		self.assertEqual(xml, tree.tostring())

	@tests.expectedFailure
	def testDeserializeParseTree(self):
		notebook = tests.MockObject()
		path = Path('Mock')
		buffer = TextBuffer(notebook, path)
		iter = buffer.get_insert_iter()
		xml = tests.new_parsetree().tostring()
		with FilterNoSuchImageWarning():
			atom = Gdk.Atom.intern('text/x-zim-parsetree', False)
			buffer.deserialize(buffer, atom, iter, xml)

	@tests.expectedFailure
	def testDeserializeUriList(self):
		notebook = self.setUpNotebook()
		path = Path('Mock')
		buffer = TextBuffer(notebook, path)

		# external uris
		iter = buffer.get_insert_iter()
		data = "http://wikipedia.com\r\n"
		buffer.deserialize(buffer, Gdk.Atom.intern('text/uri-list', False), iter, data)

		tree = buffer.get_parsetree()
		xml = tree.tostring()
		self.assertIn('http://wikipedia.com', xml) # FIXME: should use tree api

		# internal uris
		iter = buffer.get_insert_iter()
		data = "Foo:Bar\r\n"
		buffer.deserialize(buffer, Gdk.Atom.intern('text/x-zim-page-list-internal', False), iter, data)

		tree = buffer.get_parsetree()
		xml = tree.tostring()
		self.assertIn('Foo:Bar', xml) # FIXME: should use tree api

	def testDeserializeImageData(self):
		import zim.datetimetz as datetime

		notebook = self.setUpNotebook(name='imagedata', mock=tests.MOCK_ALWAYS_REAL)
		notebook.config['Notebook']['paste_image_template'] = 'paste_image_test_%y%m%d'
		wanted = datetime.strftime('paste_image_test_%y%m%d', datetime.now())
		path = Path('Mock')

		buffer = TextBuffer(notebook, path)
		image = tests.ZIM_DATA_FOLDER.file('zim.png').read_binary()
		iter = buffer.get_insert_iter()
		buffer.deserialize(buffer, Gdk.Atom.intern('image/png', False), iter, image)

		tree = buffer.get_parsetree()
		xml = tree.tostring()
		self.assertIn(wanted, xml) # FIXME: should use tree api to get image

try:
	import PIL
except ImportError:
	PIL = None

@tests.slowTest
@tests.skipUnless(PIL, 'PIL library not available')
class TestWebPImageSupport(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(mock=tests.MOCK_ALWAYS_REAL)
		page = notebook.get_page(Path('Test'))
		file = page.attachments_folder.file('image_webp_test.webp')
		self.assertTrue(file.mimetype().startswith('image/'))
		self.assertTrue(file.isimage())
		src = tests.TEST_DATA_FOLDER.file('image_webp_test/image_webp_test.webp')
		src.copyto(file)

		pageview = setUpPageView(notebook, text='''\
====== test webp ======

If the Pillow fallback works, images should be displayed below, with the right one being 2x smaller.

{{./image_webp_test.webp}} {{./image_webp_test.webp?width=240}}
		''')
		# No assert, just test it runs without errors / warnings


@tests.slowTest
class TestMoveTextDialog(tests.TestCase):
	# Testing of all the premutations of resolving links & images is already
	# covered in test suite of the clipboard. Essentially we are re-using
	# the copy-paste logic.

	def runTest(self):
		notebook = self.setUpNotebook(mock=tests.MOCK_ALWAYS_REAL)
		page = notebook.get_page(Path('Test'))
		file = page.attachments_folder.file('zim.png')
		src = tests.ZIM_DATA_FOLDER.file('zim.png')
		src.copyto(file)

		pageview = setUpPageView(notebook, text='''\
Some **bold** test

An image {{./zim.png}}
And a link [[+Foo]]

All in one page
''')

		buffer = pageview.textview.get_buffer()
		buffer.select_lines(2, 3)
		self.assertEqual(pageview.get_selection(), 'An image \nAnd a link +Foo\n')

		newpath = Path('Bar')
		def move_text_dialog(dialog):
			self.assertIsInstance(dialog, MoveTextDialog)
			dialog.form['page'] = newpath
			dialog.form['link'] = True
			dialog.assert_response_ok()

		navigation = tests.MockObject()
		with tests.DialogContext(move_text_dialog):
			MoveTextDialog(pageview, notebook, page, buffer, navigation).run()

		newpage = notebook.get_page(newpath)
		self.assertEqual(newpage.dump('wiki')[-2:], [
			'An image {{%s}}\n' % tests.os_native_path('./zim.png'),
			'And a link [[Test:Foo]]\n'
		]) 	# Link updated - using last two lines to exclude template
		file = newpage.attachments_folder.file('zim.png')
		self.assertTrue(file.exists()) # File copied

		self.assertEqual(page.dump('wiki'), [
			'Some **bold** test\n', '\n', '[[:Bar]]\n', 'All in one page\n'
		]) 	# text replaced by link
