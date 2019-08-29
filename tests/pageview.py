
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

import os

from zim.fs import File, Dir
from zim.newfs import LocalFile, LocalFolder
from zim.formats import wiki, ParseTree
from zim.notebook import Path
from zim.gui.pageview import *
from zim.gui.clipboard import Clipboard

from zim.newfs.mock import os_native_path


class FilterNoSuchImageWarning(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self, 'zim.gui.pageview', 'No such image:')


def new_parsetree_from_text(testcase, text):
	## FIXME had to wrap my own here, because of stupid resolve_images - get rid of that
	tree = tests.new_parsetree_from_text(text)
	notebook = testcase.setUpNotebook()
	page = notebook.get_page(Path('Foo'))
	tree.resolve_images(notebook, page)

	return tree


def setUpPageView(notebook, text=''):
	'''Some bootstrap code to get an isolated PageView object'''
	page = notebook.get_page(Path('Test'))
	page.parse('wiki', text)
	notebook.store_page(page)

	navigation = tests.MockObject()
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



class TestCaseMixin(object):
	# Mixin class with extra test methods

	def get_buffer(self, input=None):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		if input is not None:
			self.set_buffer(buffer, input)
		return buffer

	def set_buffer(self, buffer, input):
		if isinstance(input, str):
			if not input.startswith('<?xml'):
				input = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw="True">%s</zim-tree>''' % input
			tree = tests.new_parsetree_from_xml(input)
		elif isinstance(input, (list, tuple)):
			raise NotImplementedError('Support tokens')
		else:
			tree = input

		buffer.set_parsetree(tree)

	def assertBufferEquals(self, buffer, wanted):
		if isinstance(wanted, (tuple, list)):
			wanted = list(wanted)
			tree = buffer.get_parsetree()
			tokens = list(tree.iter_tokens())
			self.assertEqual(tokens, wanted)
		else:
			if isinstance(wanted, str):
				if not wanted.startswith('<?xml'):
					wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw="True">%s</zim-tree>''' % wanted
			else:
				wanted = tree.tostring()
			raw = '<zim-tree raw="True">' in wanted
			tree = buffer.get_parsetree(raw=raw)
			self.assertEqual(tree.tostring(), wanted)

	def assertSelection(self, buffer, line, offset, string):
		self.assertCursorPosition(buffer, offset, line)
		bound = buffer.get_selection_bounds()
		self.assertTrue(bound)
		selection = bound[0].get_slice(bound[1])
		self.assertEqual(selection, string)

	def assertCursorPosition(self, buffer, offset, line):
		#~ print('CHECK', line, offset, text)
		cursor = buffer.get_insert_iter()
		#~ print('  GOT', cursor.get_line(), cursor.get_line_offset())
		self.assertEqual(cursor.get_line(), line)
		self.assertEqual(cursor.get_line_offset(), offset)


class TestTextBuffer(tests.TestCase, TestCaseMixin):

	def testVarious(self):
		'''Test serialization and interaction of the page view textbuffer'''
		wikitext = tests.WikiTestData.get('roundtrip')
		tree = new_parsetree_from_text(self, wikitext)
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(tree)

		raw1 = buffer.get_parsetree(raw=True)
		result1 = buffer.get_parsetree()
		reftree = tree.copy()
		reftree.unresolve_images() # needed to make compare succeed
		self.assertEqual(result1.tostring(), reftree.tostring())

		# Compare we are stable when loading raw tree again
		raw = raw1.tostring()
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(raw1)
		self.assertEqual(raw1.tostring(), raw)
			# If this fails, set_parsetree is modifying the tree
		raw2 = buffer.get_parsetree(raw=True)
		self.assertEqual(raw2.tostring(), raw)
			# Actual cooked roundtrip test

		# Compare we are stable when loading cooked tree again
		#~ cooked = result1.tostring()
		#~ with FilterNoSuchImageWarning():
			#~ buffer.set_parsetree(result1)
		#~ self.assertEqual(result1.tostring(), cooked)
			#~ # If this fails, set_parsetree is modifying the tree
		#~ result2 = buffer.get_parsetree()
		#~ self.assertEqual(result2.tostring(), cooked)
			# Actual cooked roundtrip test

		# Test 'raw' really preserves "errors"
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
foo<h level="1">bar</h>baz

dus <pre>ja</pre> hmm

<h level="2">foo
</h>bar

dus <div indent="5">ja</div> <emphasis>hmm
dus ja
</emphasis>grrr

<li bullet="*" indent="0"> Foo</li>
<li bullet="*" indent="0"> Bar</li>
</zim-tree>'''
		tree = tests.new_parsetree_from_xml(input)
		buffer.set_parsetree(tree)
		self.assertFalse(buffer.get_modified())

		rawtree = buffer.get_parsetree(raw=True)
		self.assertFalse(buffer.get_modified())
		self.assertEqual(rawtree.tostring(), input)

		# Test errors are cleaned up correctly
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p>foo
</p>
<h level="1">bar</h>
<p>baz
</p>
<p>dus <code>ja</code> hmm
</p>
<h level="2">foo</h>
<p>bar
</p>
<p>dus ja <emphasis>hmm</emphasis>
<emphasis>dus ja</emphasis>
grrr
</p>
<p><ul><li bullet="*">Foo</li><li bullet="*">Bar</li></ul></p></zim-tree>'''
		tree = buffer.get_parsetree()
		self.assertFalse(buffer.get_modified())
		self.assertEqual(tree.tostring(), wanted)

		# Test pasting some simple text
		buffer.set_parsetree(tree) # reset without errors
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><strong>Bold</strong></zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p>foo
</p>
<h level="1">bar</h>
<p>baz
</p>
<p>dus <code>ja</code> hmm
</p>
<h level="2">foo</h>
<p>bar
</p>
<p>dus ja <emphasis>hmm</emphasis>
<emphasis>dus ja</emphasis>
grrr
</p>
<p><ul><li bullet="*">Foo<strong>Bold</strong></li><li bullet="*"><strong>Bold</strong>Bar</li></ul></p></zim-tree>'''
		pastetree = tests.new_parsetree_from_xml(input)
		iter = buffer.get_iter_at_line(15)
		iter.forward_chars(5) # position after "* Foo"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		iter = buffer.get_iter_at_line(16) # position before bullet "* Bar"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		tree = buffer.get_parsetree()
		self.assertTrue(buffer.get_modified())
		self.assertEqual(tree.tostring(), wanted)

		# Now paste list halfway and see result is OK
		# because of the bullets pasting should go to a new line
		# automatically
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><li>Foo</li><li>Bar</li>
</zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p>foo
</p>
<h level="1">bar</h>
<p>baz
<ul><li bullet="*">Foo</li><li bullet="*">Bar</li></ul></p>


<p>dus <code>ja</code> hmm
</p>
<h level="2">foo</h>
<p>bar
</p>
<p>dus ja <emphasis>hmm</emphasis>
<emphasis>dus ja</emphasis>
grrr
</p>
<p><ul><li bullet="*">Foo<strong>Bold</strong></li><li bullet="*"><strong>Bold</strong>Bar</li></ul></p></zim-tree>'''
		pastetree = tests.new_parsetree_from_xml(input)
		iter = buffer.get_iter_at_line(4)
		iter.forward_chars(3) # position after "baz"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		tree = buffer.get_parsetree()
		self.assertTrue(buffer.get_modified())
		self.assertEqual(tree.tostring(), wanted)

		# Test sanity for editing "errors"
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<li bullet="unchecked-box" indent="0">Box 1</li><li bullet="unchecked-box" indent="0">Box 2</li><li bullet="unchecked-box" indent="0">Box 3</li>
</zim-tree>
'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p><ul><li bullet="unchecked-box">Box 1</li><li bullet="unchecked-box">foo Box 2</li><li bullet="unchecked-box">Box 3</li></ul></p>
</zim-tree>'''
		tree = tests.new_parsetree_from_xml(input)
		buffer.set_parsetree(tree)
		iter = buffer.get_iter_at_line(2) # iter *before* checkbox
		buffer.insert(iter, 'foo ')
		#print buffer.get_parsetree(raw=True).tostring()
		#print buffer.get_parsetree().tostring()
		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), wanted)

		# Strange bug let to second bullet disappearing in this case
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p><ul indent="1"><li bullet="*">Box 1</li><li bullet="*">Box 2</li><li bullet="*">Box 3</li></ul></p>
</zim-tree>'''
		tree = tests.new_parsetree_from_xml(input)
		buffer.set_parsetree(tree)
		iter = buffer.get_iter_at_line(2) # iter before checkbox
		bound = iter.copy()
		bound.forward_char()
		buffer.select_range(iter, bound)
		buffer.toggle_textstyle('strike')
		#~ print buffer.get_parsetree(raw=True).tostring()
		#~ print buffer.get_parsetree().tostring()
		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), input)

		# Check how robust we are for placeholder utf8 character
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		buffer.insert_at_cursor('foo \uFFFC bar')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>foo  bar
</p></zim-tree>'''
		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), wanted)

		# Test merge lines logic on delete
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><h level="1">Foo</h>

<h level="2">Bar</h>

<p><ul><li bullet="*">List item 0</li></ul></p>
<p><ul indent="1"><li bullet="*">List item 1</li></ul></p></zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><h level="1">FooBar</h>

<p>List item 0
</p>
<p><div indent="1">List item 1
</div></p></zim-tree>'''
		# Note: we don't insert extra newlines, but <li> assumes them
		tree = tests.new_parsetree_from_xml(input)
		buffer.set_parsetree(tree)
		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), input)

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

		#~ print buffer.get_parsetree().tostring()
		#~ print wanted
		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), wanted)



		# Exercize recursive checkbox lists
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="0"> Foo</li>
<li bullet="unchecked-box" indent="0"> Bar</li>
<li bullet="unchecked-box" indent="1"> Bar 1</li>
<li bullet="unchecked-box" indent="2"> Bar 1.1</li>
<li bullet="unchecked-box" indent="1"> Bar 2</li>
<li bullet="unchecked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = tests.new_parsetree_from_xml(input)
		buffer.set_parsetree(tree)
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), input) # just a sanity check

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="xchecked-box" indent="0"> Foo</li>
<li bullet="checked-box" indent="0"> Bar</li>
<li bullet="xchecked-box" indent="1"> Bar 1</li>
<li bullet="checked-box" indent="2"> Bar 1.1</li>
<li bullet="checked-box" indent="1"> Bar 2</li>
<li bullet="checked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		buffer.toggle_checkbox(2, recursive=True) # Bar
		buffer.toggle_checkbox(3, recursive=True) # Bar 1
			# After first click all children become checked
			# After second click one becomes xchecked
		buffer.place_cursor(buffer.get_iter_at_line(1)) # Foo
		buffer.toggle_checkbox_for_cursor_or_selection(XCHECKED_BOX)
			# Like <Shift><F12> on first list item line
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="xchecked-box" indent="0"> Foo</li>
<li bullet="unchecked-box" indent="0"> Bar</li>
<li bullet="unchecked-box" indent="1"> Bar 1</li>
<li bullet="unchecked-box" indent="2"> Bar 1.1</li>
<li bullet="unchecked-box" indent="1"> Bar 2</li>
<li bullet="unchecked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		start = buffer.get_iter_at_line(2) # Bar
		end = buffer.get_iter_at_line(6) # Bar 3
		end.forward_to_line_end()
		buffer.select_range(start, end)
		buffer.toggle_checkbox_for_cursor_or_selection(CHECKED_BOX, recursive=True)
			# Like keypress would trigger while selection present
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)


		# Test deleting checkbox and undo / redo does not mess up indenting etc
		undomanager = UndoStackManager(buffer)
		previous = wanted
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="xchecked-box" indent="0"> Foo</li>
<li bullet="unchecked-box" indent="0"> Bar</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		start = buffer.get_iter_at_line(3) # Bar
		end = buffer.get_iter_at_line(7) # Baz (before checkbox !)
		buffer.delete(start, end)
		tree = buffer.get_parsetree(raw=True)
		#~ print tree.tostring()
		#~ print wanted
		self.assertEqual(tree.tostring(), wanted)

		undomanager.undo()
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), previous)

		undomanager.redo()
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

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
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p>aaa <strong>bbb</strong> ccc
</p></zim-tree>
'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p>aaa <strong>eee</strong> ccc
</p></zim-tree>'''
		tree = tests.new_parsetree_from_xml(input)

		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		buffer.set_parsetree(tree)

		iter = buffer.get_iter_at_offset(7) # middle of "bbb"
		buffer.place_cursor(iter)
		buffer.select_word()

		with buffer.user_action:
			buffer.delete_selection(True, True)
			buffer.insert_interactive_at_cursor("eee", 3, True)

		self.assertBufferEquals(buffer, wanted)

	def testSelectLink(self):
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
aaa <link href="xxx">bbb</link> ccc
</zim-tree>
'''
		tree = tests.new_parsetree_from_xml(input)

		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		buffer.set_parsetree(tree)
		buffer.place_cursor(buffer.get_iter_at_offset(7)) # middle of link

		self.assertIsNone(buffer.get_has_link_selection())
		data = buffer.select_link()
		self.assertEqual(data['href'], 'xxx')
		self.assertEqual(buffer.get_has_link_selection(), data)

	def testToggleTextStylePre(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		buffer.set_parsetree(tests.new_parsetree_from_xml('''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>A
<div indent="1">B
</div>C
<div indent="1">D
</div></p></zim-tree>
'''))
		start, end = buffer.get_bounds()
		buffer.select_range(start, end)
		buffer.toggle_textstyle('code')

		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><pre>A
	B
C
	D
</pre></zim-tree>''')

	def testMergeLinesWithBullet(self):
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<ul><li>item 1</li><li>item 2</li></ul>
</zim-tree>
'''
		tree = tests.new_parsetree_from_xml(input)

		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		buffer.set_parsetree(tree)

		# Position at end of first lest item and delete end of line
		buffer.place_cursor(buffer.get_iter_at_offset(9))
		start = buffer.get_insert_iter()
		end = start.copy()
		end.forward_char()
		buffer.delete_interactive(start, end, True)

		tree = buffer.get_parsetree()
		self.assertEqual(tree.tostring(), '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<p><ul><li bullet="*">item 1item 2</li></ul></p>
</zim-tree>''')

	def testFormatHeading(self):
		buffer = self.get_buffer('foo bar\n')
		for lvl in range(1, 7):
			buffer.select_line(0)
			buffer.toggle_textstyle('h%i' % lvl)
			self.assertBufferEquals(buffer, '<h level="%i">foo bar</h>\n' % lvl)

	def testFormatHeadingWithFormatting(self):
		buffer = self.get_buffer('foo <strong>bar</strong> <link href="Foo">Foo</link>\n')
		buffer.select_line(0)
		buffer.toggle_textstyle('h2')
		self.assertBufferEquals(buffer, '<h level="2">foo bar Foo</h>\n')

	def testFormatHeadingOnIndent(self):
		buffer = self.get_buffer('<div indent="2">foo bar</div>\n')
		buffer.select_line(0)
		buffer.toggle_textstyle('h2')
		self.assertBufferEquals(buffer, '<h level="2">foo bar</h>\n')

	def testFormatHeadingOnList(self):
		buffer = self.get_buffer('<li bullet="1."> foo bar</li>\n')
		buffer.select_line(0)
		buffer.toggle_textstyle('h2')
		self.assertBufferEquals(buffer, '<h level="2" /><h level="2">1. foo bar</h>\n')
				# FIXME: first <h level="2" /> should not be there, but does not seem to affect user behavior
				#        maybe removed by refactoring serialization

	def testReNumberList(self):
		buffer = self.get_buffer(
			'<li bullet="2." indent="0"> foo bar</li>\n'
			'<li bullet="5." indent="0"> foo bar</li>\n'
			'<li bullet="7." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list(1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="2." indent="0"> foo bar</li>\n'
			'<li bullet="3." indent="0"> foo bar</li>\n'
			'<li bullet="4." indent="0"> foo bar</li>\n'
		)

	def testReNumberListWithBullet(self):
		# Must break at bullet
		buffer = self.get_buffer(
			'<li bullet="2." indent="0"> foo bar</li>\n'
			'<li bullet="*" indent="0"> foo bar</li>\n'
			'<li bullet="7." indent="0"> foo bar</li>\n'
		)
		for line in (0, 1, 2):
			buffer.renumber_list(line)
			self.assertBufferEquals(	# Raw content
				buffer,
				'<li bullet="2." indent="0"> foo bar</li>\n'
				'<li bullet="*" indent="0"> foo bar</li>\n'
				'<li bullet="7." indent="0"> foo bar</li>\n'
			)
			self.assertBufferEquals(	# Serialize towards formatter
				buffer,
				'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
				'<zim-tree><p>'
				'<ol start="2"><li>foo bar</li></ol>'
				'<ul><li bullet="*">foo bar</li></ul>'
				'<ol start="7"><li>foo bar</li></ol>'
				'</p></zim-tree>'
			)

	def testReNumberListWithCheckbox(self):
		# Must break at checkbox
		buffer = self.get_buffer(
			'<li bullet="2." indent="0"> foo bar</li>\n'
			'<li bullet="unchecked-box" indent="0"> foo bar</li>\n'
			'<li bullet="7." indent="0"> foo bar</li>\n'
		)
		for line in (0, 1, 2):
			buffer.renumber_list(line)
			self.assertBufferEquals(	# Raw content
				buffer,
				'<li bullet="2." indent="0"> foo bar</li>\n'
				'<li bullet="unchecked-box" indent="0"> foo bar</li>\n'
				'<li bullet="7." indent="0"> foo bar</li>\n'
			)
			self.assertBufferEquals(	# Serialize towards formatter
				buffer,
				'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
				'<zim-tree><p>'
				'<ol start="2"><li>foo bar</li></ol>'
				'<ul><li bullet="unchecked-box">foo bar</li></ul>'
				'<ol start="7"><li>foo bar</li></ol>'
				'</p></zim-tree>'
			)

	def testReNumberListAfterIndentTop(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="2." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 0)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="c." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)

	def testReNumberListAfterUnIndentTop(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="c." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)

	def testReNumberListAfterIndentMiddle(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(2, 0)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="c." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)

	def testReNumberListAfterUnIndentMiddle(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="c." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(2, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)

	def testReNumberListAfterIndentBottom(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(3, 0)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="c." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)

	def testReNumberListAfterUnIndentBottom(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="c." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(3, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)

	def assertRenumberListAfterIndentForNewNumberSublist1(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="2." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="a." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)

	def assertRenumberListAfterIndentForNewNumberSublist2(self):
		buffer = self.get_buffer(
			'<li bullet="a." indent="0"> foo bar</li>\n'
			'<li bullet="b." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="c." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="a." indent="0"> foo bar</li>\n'
			'<li bullet="1." indent="1"> foo bar</li>\n' # was indented
			'<li bullet="b." indent="0"> foo bar</li>\n'
		)

	def assertRenumberListAfterIndentForNewBulletSublist(self):
		buffer = self.get_buffer(
			'<li bullet="*" indent="0"> foo bar</li>\n'
			'<li bullet="*" indent="1"> foo bar</li>\n' # was indented
			'<li bullet="*" indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="*" indent="0"> foo bar</li>\n'
			'<li bullet="*" indent="1"> foo bar</li>\n' # was indented
			'<li bullet="*" indent="0"> foo bar</li>\n'
		)

	def assertRenumberListAfterUnindentCovertsBulletToNumber(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="*" indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="*" indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="*" indent="1"> foo bar</li>\n'
			'<li bullet="3." indent="0"> foo bar</li>\n'
		)

	def testReNumberListAfterUnIndentDoesNotTouchCheckbox(self):
		buffer = self.get_buffer(
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="unchecked-box" indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="unchecked-box" indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="1." indent="0"> foo bar</li>\n'
			'<li bullet="unchecked-box" indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="unchecked-box" indent="1"> foo bar</li>\n'
			'<li bullet="2." indent="0"> foo bar</li>\n'
		)

	def assertRenumberListAfterUnindentCovertsNumberToBullet(self):
		buffer = self.get_buffer(
			'<li bullet="*" indent="0"> foo bar</li>\n'
			'<li bullet="1." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="2." indent="1"> foo bar</li>\n'
			'<li bullet="*" indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="*" indent="0"> foo bar</li>\n'
			'<li bullet="*" indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="1." indent="1"> foo bar</li>\n'
			'<li bullet="*" indent="0"> foo bar</li>\n'
		)

	def assertRenumberListAfterUnindentCovertsNumberToCheckbox(self):
		buffer = self.get_buffer(
			'<li bullet="checked-box" indent="0"> foo bar</li>\n'
			'<li bullet="1." indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="2." indent="1"> foo bar</li>\n'
			'<li bullet="checked-box" indent="0"> foo bar</li>\n'
		)
		buffer.renumber_list_after_indent(1, 1)
		self.assertBufferEquals(
			buffer,
			'<li bullet="checked-box" indent="0"> foo bar</li>\n'
			'<li bullet="unchecked-box" indent="0"> foo bar</li>\n' # was unindented
			'<li bullet="1." indent="1"> foo bar</li>\n'
			'<li bullet="checked-box" indent="0"> foo bar</li>\n'
		)


class TestUndoStackManager(tests.TestCase):

	def runTest(self):
		'''Test the undo/redo functionality'''
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		undomanager = UndoStackManager(buffer)
		wikitext = tests.WikiTestData.get('roundtrip')
		tree = new_parsetree_from_text(self, wikitext)

		with FilterNoSuchImageWarning():
			buffer._insert_element_children(tree._etree.getroot())
				# Use private method to circumvent begin-insert-tree
				# signal etc. so we get undo stack for inserting

		# First test is to check we have a continuous undo stack after
		# inserting a parse tree. Nota bene, if this test fails, the
		# insert_parsetree() function is not strictly serial, which
		# probably breaks proper formatting e.g. when pasting a tree
		# half way in a line.
		#~ import pprint
		#~ undomanager.flush_insert()
		#~ def tostring(data):
			#~ if hasattr(data, 'tostring'):
				#~ return data.tostring()[39:]
			#~ else:
				#~ return data.get_property('name')
		i = 0
		for group in undomanager.stack + [undomanager.group]:
			#~ pprint.pprint(
				#~ [(a[0], a[1], a[2], tostring(a[3])) for a in group] )
			for action in group:
				self.assertEqual(action[1], i) # assert undo stack is continous
				i = action[2]
		self.assertTrue(len(undomanager.stack) > 10) # check we recorded something

		# Now we iterate through the tree to verify we get a proper
		# state at every step of the stack, then we redo to check we
		# get back what we had
		buffertree1 = buffer.get_parsetree(raw=True)

		while undomanager.undo():
			_ = buffer.get_parsetree() # just check for no warnings

		emptytree = buffer.get_parsetree(raw=True)
		self.assertEqual(emptytree.tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\" />")

		with FilterNoSuchImageWarning():
			while undomanager.redo():
				_ = buffer.get_parsetree() # just check for no warnings

		buffertree2 = buffer.get_parsetree(raw=True)
		self.assertEqual(buffertree2.tostring(), buffertree1.tostring())

		while undomanager.undo():
			continue

		emptytree = buffer.get_parsetree(raw=True)
		self.assertEqual(emptytree.tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\" />")

		buffer.clear()
		self.assertTrue(len(undomanager.stack) == 0)
		undomanager.unblock()

		# Test merging
		for c in 'fooo barr baz':
			with buffer.user_action:
				buffer.insert_at_cursor(c)
		#~ import pprint
		#~ undomanager.flush_insert()
		#~ pprint.pprint(undomanager.stack)
		self.assertTrue(len(undomanager.stack) == 5) # 3 words, 2 spaces
		for group in undomanager.stack:
			self.assertTrue(len(group) == 1) # merge was sucessfull
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo barr baz</zim-tree>")

		for wanted in (
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo barr </zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo barr</zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo </zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo</zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\" />"
		):
			undomanager.undo()
			self.assertEqual(buffer.get_parsetree(raw=True).tostring(), wanted)

		while undomanager.redo():
			continue
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo barr baz</zim-tree>")

		# test other actions
		iter = buffer.get_iter_at_offset(7)
		buffer.place_cursor(iter)
		buffer.select_word()
		buffer.toggle_textstyle('strong')
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo <strong>barr</strong> baz</zim-tree>")

		undomanager.undo()
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo barr baz</zim-tree>")

		undomanager.redo()
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo <strong>barr</strong> baz</zim-tree>")

		start, end = list(map(buffer.get_iter_at_offset, (5, 10)))
		with buffer.user_action:
			buffer.delete(start, end)
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo baz</zim-tree>")

		undomanager.undo()
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo <strong>barr</strong> baz</zim-tree>")

		undomanager.redo()
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo baz</zim-tree>")

		# test folding
		undomanager.undo()
		undomanager.undo()
		undomanager.undo()
		undomanager.undo()

		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo barr</zim-tree>")

		with buffer.user_action:
			buffer.insert_at_cursor(' ')

		undomanager.undo()
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo barr</zim-tree>")

		undomanager.undo() # here we undo fold of 4 undos above
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo baz</zim-tree>")
		undomanager.undo()
		self.assertEqual(buffer.get_parsetree(raw=True).tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\">fooo <strong>barr</strong> baz</zim-tree>")


class TestFind(tests.TestCase, TestCaseMixin):

	def testVarious(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		finder = buffer.finder
		buffer.set_text('''\
FOO FooBar FOOBAR
FooBaz Foo Bar
foo Bar Baz Foo
''')
		buffer.place_cursor(buffer.get_start_iter())

		# Check normal usage, case-insensitive
		for text in ('f', 'fo', 'foo', 'fo', 'f', 'F', 'Fo', 'Foo'):
			finder.find(text)
			self.assertSelection(buffer, 0, 0, text.upper())

		finder.find('Grr')
		self.assertCursorPosition(buffer, 0, 0)

		finder.find('Foob')
		self.assertSelection(buffer, 0, 4, 'FooB')

		for line, offset, text in (
			(0, 11, 'FOOB'),
			(1, 0, 'FooB'),
			(0, 4, 'FooB'),
		):
			finder.find_next()
			self.assertSelection(buffer, line, offset, text)

		for line, offset, text in (
			(1, 0, 'FooB'),
			(0, 11, 'FOOB'),
			(0, 4, 'FooB'),
		):
			finder.find_previous()
			self.assertSelection(buffer, line, offset, text)

		# Case sensitive
		finder.find('Foo', FIND_CASE_SENSITIVE)
		self.assertSelection(buffer, 0, 4, 'Foo')

		for line, offset, text in (
			(1, 0, 'Foo'),
			(1, 7, 'Foo'),
			(2, 12, 'Foo'),
			(0, 4, 'Foo'),
		):
			finder.find_next()
			self.assertSelection(buffer, line, offset, text)

		# Whole word
		finder.find('Foo', FIND_WHOLE_WORD)
		self.assertSelection(buffer, 1, 7, 'Foo')

		for line, offset, text in (
			(2, 0, 'foo'),
			(2, 12, 'Foo'),
			(0, 0, 'FOO'),
			(1, 7, 'Foo'),
		):
			finder.find_next()
			self.assertSelection(buffer, line, offset, text)

		# Regular expression
		finder.find(r'Foo\s*Bar', FIND_REGEX | FIND_CASE_SENSITIVE)
		self.assertSelection(buffer, 1, 7, 'Foo Bar')
		finder.find_next()
		self.assertSelection(buffer, 0, 4, 'FooBar')

		# Highlight - just check it doesn't crash
		finder.set_highlight(True)
		finder.set_highlight(False)

	def testReplace(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		finder = buffer.finder
		tree = tests.new_parsetree_from_xml('''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">FOO FooBar FOOBAR
FooBaz Foo Bar
<strong>foo</strong> Bar Baz Foo
</zim-tree>''')
		buffer.set_parsetree(tree)

		finder.find('Foo(\w*)', FIND_REGEX) # not case sensitive!
		finder.find_next()
		self.assertSelection(buffer, 0, 4, 'FooBar')

		finder.replace('Dus')
		self.assertSelection(buffer, 0, 4, 'Dus')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">FOO Dus FOOBAR
FooBaz Foo Bar
<strong>foo</strong> Bar Baz Foo
</zim-tree>'''
		self.assertBufferEquals(buffer, wanted)

		finder.replace_all('dus*\\1*')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">dus** Dus dus*BAR*
dus*Baz* dus** Bar
<strong>dus**</strong> Bar Baz dus**
</zim-tree>'''
		self.assertBufferEquals(buffer, wanted)


class TestLists(tests.TestCase, TestCaseMixin):

	def testBulletLists(self):
		'''Test interaction for lists'''

		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="*" indent="0"> Foo</li>
<li bullet="*" indent="0"> Bar</li>
<li bullet="*" indent="1"> Bar 1</li>
<li bullet="*" indent="2"> Bar 1.1</li>
<li bullet="*" indent="1"> Bar 2</li>
<li bullet="*" indent="1"> Bar 3</li>
<li bullet="*" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = tests.new_parsetree_from_xml(input)
		buffer.set_parsetree(tree)
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), input) # just a sanity check

		undomanager = UndoStackManager(buffer)

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
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="*" indent="0"> Foo</li>
<li bullet="*" indent="1"> Bar</li>
<li bullet="*" indent="2"> Bar 1</li>
<li bullet="*" indent="3"> Bar 1.1</li>
<li bullet="*" indent="2"> Bar 2</li>
<li bullet="*" indent="2"> Bar 3</li>
<li bullet="*" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		row, list = TextBufferList.new_from_line(buffer, 7) # Baz
		self.assertFalse(list.can_unindent(row))
		self.assertFalse(list.unindent(row))

		row, list = TextBufferList.new_from_line(buffer, 3) # Bar 1
		self.assertTrue(list.can_unindent(row))
		self.assertTrue(list.unindent(row))

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="*" indent="0"> Foo</li>
<li bullet="*" indent="1"> Bar</li>
<li bullet="*" indent="1"> Bar 1</li>
<li bullet="*" indent="2"> Bar 1.1</li>
<li bullet="*" indent="2"> Bar 2</li>
<li bullet="*" indent="2"> Bar 3</li>
<li bullet="*" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		for line in (2, 5, 6): # Bar, Bar 2 & Bar 3
			row, list = TextBufferList.new_from_line(buffer, line)
			self.assertTrue(list.can_unindent(row))
			self.assertTrue(list.unindent(row))

		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), input)

		# Test undo / redo for indenting and lists
		for i in range(3):
			self.assertTrue(undomanager.undo())
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		while undomanager.undo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), input)

		while undomanager.redo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), input)

		for i in range(3):
			self.assertTrue(undomanager.undo())
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)


		# Exercize recursive checkbox lists
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="0"> Foo</li>
<li bullet="unchecked-box" indent="0"> Bar</li>
<li bullet="unchecked-box" indent="1"> Bar 1</li>
<li bullet="unchecked-box" indent="2"> Bar 1.1</li>
<li bullet="unchecked-box" indent="1"> Bar 2</li>
<li bullet="unchecked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = tests.new_parsetree_from_xml(input)
		buffer.set_parsetree(tree)
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), input) # just a sanity check

		undomanager = UndoStackManager(buffer)


		row, list = TextBufferList.new_from_line(buffer, 2) # Bar
		list.set_bullet(row, CHECKED_BOX)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="0"> Foo</li>
<li bullet="checked-box" indent="0"> Bar</li>
<li bullet="checked-box" indent="1"> Bar 1</li>
<li bullet="checked-box" indent="2"> Bar 1.1</li>
<li bullet="checked-box" indent="1"> Bar 2</li>
<li bullet="checked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		list.set_bullet(row, UNCHECKED_BOX)
		row = list.get_row_at_line(3) # Bar 1
		list.set_bullet(row, XCHECKED_BOX)
		row = list.get_row_at_line(5) # Bar 2
		list.set_bullet(row, UNCHECKED_BOX)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="0"> Foo</li>
<li bullet="unchecked-box" indent="0"> Bar</li>
<li bullet="xchecked-box" indent="1"> Bar 1</li>
<li bullet="checked-box" indent="2"> Bar 1.1</li>
<li bullet="unchecked-box" indent="1"> Bar 2</li>
<li bullet="checked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		row = list.get_row_at_line(5) # Bar 2
		list.set_bullet(row, CHECKED_BOX)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="0"> Foo</li>
<li bullet="unchecked-box" indent="0"> Bar</li>
<li bullet="xchecked-box" indent="1"> Bar 1</li>
<li bullet="checked-box" indent="2"> Bar 1.1</li>
<li bullet="checked-box" indent="1"> Bar 2</li>
<li bullet="checked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		row = list.get_row_at_line(4) # Bar 1.1
		list.set_bullet(row, UNCHECKED_BOX)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="0"> Foo</li>
<li bullet="unchecked-box" indent="0"> Bar</li>
<li bullet="unchecked-box" indent="1"> Bar 1</li>
<li bullet="unchecked-box" indent="2"> Bar 1.1</li>
<li bullet="checked-box" indent="1"> Bar 2</li>
<li bullet="checked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		wantedpre1 = wanted
		row = list.get_row_at_line(4) # Bar 1.1
		list.set_bullet(row, CHECKED_BOX)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="0"> Foo</li>
<li bullet="checked-box" indent="0"> Bar</li>
<li bullet="checked-box" indent="1"> Bar 1</li>
<li bullet="checked-box" indent="2"> Bar 1.1</li>
<li bullet="checked-box" indent="1"> Bar 2</li>
<li bullet="checked-box" indent="1"> Bar 3</li>
<li bullet="unchecked-box" indent="0"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		# Test indenting / unindenting the whole list
		wantedpre = wanted
		row = list.get_row_at_line(1) # Foo
		list.indent(row)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">Dusss
<li bullet="unchecked-box" indent="1"> Foo</li>
<li bullet="checked-box" indent="1"> Bar</li>
<li bullet="checked-box" indent="2"> Bar 1</li>
<li bullet="checked-box" indent="3"> Bar 1.1</li>
<li bullet="checked-box" indent="2"> Bar 2</li>
<li bullet="checked-box" indent="2"> Bar 3</li>
<li bullet="unchecked-box" indent="1"> Baz</li>
Tja
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		list.unindent(row)
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wantedpre)

		# Test undo / redo for indenting and lists
		for xml in (wanted, wantedpre, wantedpre1):
			self.assertTrue(undomanager.undo())
			tree = buffer.get_parsetree(raw=True)
			self.assertEqual(tree.tostring(), xml)

		for xml in (wantedpre, wanted, wantedpre):
			self.assertTrue(undomanager.redo())
			tree = buffer.get_parsetree(raw=True)
			self.assertEqual(tree.tostring(), xml)

		while undomanager.undo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), input)

		while undomanager.redo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wantedpre)


def press(widget, sequence):
	#~ print('PRESS', sequence)
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


class TestTextView(tests.TestCase, TestCaseMixin):

	def setUp(self):
		# Initialize default preferences from module
		self.preferences = {}
		for pref in ui_preferences:
			self.preferences[pref[0]] = pref[4]

	def testTyping(self):
		## TODO: break apart this test case, see e.g. TestDoEndOfLine

		view = TextView(self.preferences)
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		view.set_buffer(buffer)
		undomanager = UndoStackManager(buffer)

		# Need a window to get the widget realized
		window = Gtk.Window()
		window.add(view)
		view.realize()
		#~ window.show_all()
		#~ view.grab_focus()

		press(view, 'aaa\n')
		start, end = buffer.get_bounds()
		self.assertEqual(buffer.get_text(start, end, True), 'aaa\n')
			# Just checking test routines work

		# Test bullet & indenting logic
		press(view, '* foo')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		press(view, '\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="0"> </li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		start, end = buffer.get_bounds()
		self.assertEqual(tree.tostring(), wanted)

		press(view, '\tduss')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		press(view, '\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> </li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		press(view, 'CamelCase\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>
<li bullet="*" indent="1"> </li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		press(view, '\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>

</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		# selection + * to toggle bullets
		start = buffer.get_iter_at_line(1) # before foo
		end = buffer.get_iter_at_line(4) # empty line !
		buffer.select_range(start, end)
		press(view, '*')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
foo
<div indent="1">duss
<link href="CamelCase">CamelCase</link>
</div>
</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		start = buffer.get_iter_at_line(1) # before foo
		end = buffer.get_iter_at_line(4) # empty line !
		buffer.select_range(start, end)
		press(view, '*')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>

</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		iter = buffer.get_iter_at_line(1)
		iter.forward_to_line_end() # behind "foo"
		buffer.place_cursor(iter)
		press(view, '\n') # because foo has children, insert indent 1 instead of 0
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> </li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>

</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)



		# Test unindenting and test backspace can remove line end
		press(view, (KEYVALS_BACKSPACE[0],)) # unindent
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="0"> </li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>

</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		press(view, (KEYVALS_LEFT_TAB[0],)) # Check <Shift><Tab> does not fall through to Tab when indent fails
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		press(view, (KEYVALS_BACKSPACE[0],)) # delete bullet at once
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>

<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>

</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqual(tree.tostring(), wanted)

		# TODO: this test case fails, even though it works when I try it interactively !?
		#~ press(view, (KEYVALS_BACKSPACE[0],)) # remove newline
		#~ wanted = '''\
#~ <?xml version='1.0' encoding='utf-8'?>
#~ <zim-tree raw="True">aaa
#~ <li bullet="*" indent="0"> foo</li>
#~ <li bullet="*" indent="1"> duss</li>
#~ <li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>
#~
#~ </zim-tree>'''
		#~ tree = buffer.get_parsetree(raw=True)
		#~ self.assertEqual(tree.tostring(), wanted)

		# TODO more unindenting ?
		# TODO checkboxes
		# TODO Auto formatting of various link types
		# TODO enter on link, before link, after link

	@tests.expectedFailure
	def testCopyPaste(self):
		notebook = self.setUpNotebook(
			content={'roundtrip': tests.FULL_NOTEBOOK['roundtrip']}
		)
		page = notebook.get_page(Path('roundtrip'))
		parsetree = page.get_parsetree()

		buffer = TextBuffer(notebook, page)
		textview = TextView(self.preferences)
		textview.set_buffer(buffer)

		print('** HACK for cleaning up parsetree')
		def cleanup(parsetree):
			# FIXME - HACK - dump and parse as wiki first to work
			# around glitches in pageview parsetree dumper
			# main visibility when copy pasting bullet lists
			# Same hack in gui clipboard code
			from zim.notebook import Path, Page
			from zim.formats import get_format
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
		wanted_tree = "<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial=\"True\"><p>try these <strong>bold</strong>, <emphasis>italic</emphasis></p></zim-tree>"
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
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree partial="True"><p>Foo <strong>Bar</strong> Baz\n</p></zim-tree>')

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


	def testUnkownObjectType(self):
		view = TextView(self.preferences)
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		view.set_buffer(buffer)

		tree = new_parsetree_from_text(self, '''\
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
		newtree = buffer.get_parsetree()
		self.assertEqual(newtree.tostring(), tree.tostring())

	def testPopup(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		buffer.set_text("TEst ABC\n")
		textview = TextView(self.preferences)
		textview.set_buffer(buffer)
		menu = textview.get_popup()
		self.assertIsInstance(menu, Gtk.Menu)


class TestDoEndOfLine(tests.TestCase, TestCaseMixin):

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

	def assertInsertNewLine(self, input, wanted, line=-1):
		self._assertInsertNewLine(input, wanted, line)
		if line == -1:
			# Ensure that end of buffer is not special
			self._assertInsertNewLine(input + '\n', wanted + '\n', line=-2)

	def _assertInsertNewLine(self, input, wanted, line=-1):
		input = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw="True">%s</zim-tree>''' % input
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw="True">%s</zim-tree>''' % wanted
		tree = tests.new_parsetree_from_xml(input)
		self.buffer.set_parsetree(tree)
		self.assertBufferEquals(self.buffer, input) # Ensure we got what we asked
		self.typeNewLine(line)
		#print("GOT:", self.buffer.get_parsetree(raw=True).tostring())
		self.assertBufferEquals(self.buffer, wanted)

	def testInsertNewLine(self):
		# Simple test to ensure inserting newline works unaffected
		self.assertInsertNewLine('aaa', 'aaa\n')
		self.assertInsertNewLine('aaa\n', 'aaa\n\n')
		self.assertInsertNewLine('aaa\nbbb', 'aaa\n\nbbb', line=0)

	def testFormatHeading(self):
		self.assertInsertNewLine('== Foo', '<h level="1">Foo</h>\n')
		self.assertInsertNewLine('=== Foo', '<h level="2">Foo</h>\n')

	def testFormatLine(self):
		self.assertInsertNewLine('aaa\n-----', 'aaa\n<line>--------------------</line>\n')

	def testAddBullet(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="0"> </li>'
		)

	def testRemoveEmptyBullet(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="0"> </li>',
			'<li bullet="*" indent="0"> foo</li>\n\n'
		)

	def testAddSubBullet(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> bar</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> bar</li>\n<li bullet="*" indent="1"> </li>',
		)

	def testRemoveEmptySubBullet(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> bar</li>\n<li bullet="*" indent="1"> </li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> bar</li>\n\n'
		)

	def testAddSubBulletAtTopOfSublist(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> bar</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> </li>\n<li bullet="*" indent="1"> bar</li>',
			line=0
		)

	def testAddSubBulletAtBottomOfSublist(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> bar</li>\n<li bullet="*" indent="0"> next</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="*" indent="1"> bar</li>\n<li bullet="*" indent="1"> </li>\n<li bullet="*" indent="0"> next</li>',
			line=1
		)

	def testAddNumberedBullet(self):
		self.assertInsertNewLine(
			'<li bullet="1." indent="0"> foo</li>',
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="2." indent="0"> </li>',
		)

	def testRemoveEmptyNumberedBullet(self):
		self.assertInsertNewLine(
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="2." indent="0"> </li>',
			'<li bullet="1." indent="0"> foo</li>\n\n',
		)

	def testAddNumberedSubBullet(self):
		self.assertInsertNewLine(
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="a." indent="1"> bar</li>',
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="a." indent="1"> bar</li>\n<li bullet="b." indent="1"> </li>',
		)

	def testRemoveEmptyNumberedSubBullet(self):
		self.assertInsertNewLine(
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="a." indent="1"> bar</li>\n<li bullet="b." indent="1"> </li>',
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="a." indent="1"> bar</li>\n\n',
		)

	def testAddNumberedSubBulletAtTopOfSublist(self):
		self.assertInsertNewLine(
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="a." indent="1"> bar</li>',
			'<li bullet="1." indent="0"> foo</li>\n<li bullet="a." indent="1"> </li>\n<li bullet="b." indent="1"> bar</li>',
			line=0
		)

	def testAddCheckbox(self):
		self.assertInsertNewLine(
			'<li bullet="unchecked-box" indent="0"> foo</li>',
			'<li bullet="unchecked-box" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="0"> </li>',
		)
		self.assertInsertNewLine(
			'<li bullet="checked-box" indent="0"> foo</li>',
			'<li bullet="checked-box" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="0"> </li>',
		)

	def testRemoveEmptyCheckbox(self):
		self.assertInsertNewLine(
			'<li bullet="unchecked-box" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="0"> </li>',
			'<li bullet="unchecked-box" indent="0"> foo</li>\n\n',
		)

	def testAddSubCheckbox(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="1"> bar</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="1"> bar</li>\n<li bullet="unchecked-box" indent="1"> </li>',
		)
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="checked-box" indent="1"> bar</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="checked-box" indent="1"> bar</li>\n<li bullet="unchecked-box" indent="1"> </li>',
		)

	def testRemoveEmptySubCheckbox(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="1"> bar</li>\n<li bullet="unchecked-box" indent="1"> </li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="1"> bar</li>\n\n',
		)

	def testAddSubCheckboxAtTopOfSublist(self):
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="1"> bar</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="1"> </li>\n<li bullet="unchecked-box" indent="1"> bar</li>',
			line=0
		)
		self.assertInsertNewLine(
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="checked-box" indent="1"> bar</li>',
			'<li bullet="*" indent="0"> foo</li>\n<li bullet="unchecked-box" indent="1"> </li>\n<li bullet="checked-box" indent="1"> bar</li>',
			line=0
		)


class TestPageView(tests.TestCase, TestCaseMixin):

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


	def testAutoSelect(self):
		# This test indirectly tests select_word, select_line and strip_selection

		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()
		buffer.set_text('''Test 123. foo\nline with spaces    \n\n''')

		# select word (with / without previous selection)
		buffer.place_cursor(buffer.get_iter_at_offset(6))
		pageview.autoselect()
		self.assertSelection(buffer, 0, 5, '123')

		pageview.autoselect()
		self.assertSelection(buffer, 0, 5, '123') # no change

		buffer.place_cursor(buffer.get_iter_at_offset(33))
		pageview.autoselect()
		self.assertFalse(buffer.get_has_selection()) # middle of whitespace

		# select line (with / without previous selection)
		buffer.place_cursor(buffer.get_iter_at_offset(6))
		pageview.autoselect()
		self.assertSelection(buffer, 0, 5, '123')
		pageview.autoselect(selectline=True)
		self.assertSelection(buffer, 0, 0, 'Test 123. foo') # extended

		pageview.autoselect(selectline=True)
		self.assertSelection(buffer, 0, 0, 'Test 123. foo') # no change

		buffer.place_cursor(buffer.get_iter_at_offset(6))
		self.assertFalse(buffer.get_has_selection())
		pageview.autoselect(selectline=True)
		self.assertSelection(buffer, 0, 0, 'Test 123. foo')

		# empty line
		buffer.place_cursor(buffer.get_iter_at_line(3))
		self.assertFalse(buffer.get_has_selection())
		pageview.autoselect(selectline=True)
		self.assertFalse(buffer.get_has_selection())

		# existing selection needs stripping
		start = buffer.get_iter_at_offset(4)
		end = buffer.get_iter_at_offset(10)
		buffer.select_range(start, end)
		self.assertSelection(buffer, 0, 4, ' 123. ')
		pageview.autoselect()
		self.assertSelection(buffer, 0, 5, '123.')

	def testInsertLinks(self):
		pageview = setUpPageView(self.setUpNotebook())
		buffer = pageview.textview.get_buffer()
		buffer.set_text('''Test 123\n''')

		buffer.place_cursor(buffer.get_end_iter())
		pageview.insert_links((Path("foo"), File("/foo.txt"), "~/bar.txt"))
		wantedtext = 'Test 123\nfoo\n%s\n%s\n' % (File('/foo.txt').uri, os_native_path('~/bar.txt'))
		text = get_text(buffer)
		self.assertEqual(text, wantedtext)

		buffer.place_cursor(buffer.get_iter_at_line(2))
		buffer.select_line()
		pageview.insert_links(('http://cpan.org',))
		wantedtext = 'Test 123\nfoo\n%s\n%s\n' % ('http://cpan.org ', os_native_path('~/bar.txt'))
		text = get_text(buffer)
		self.assertEqual(text, wantedtext)

	def testLinkClicked(self):
		pageview = setUpPageView(self.setUpNotebook('test'))
		pageview.page = Path('test')

		for href in ('foo', 'foo:bar', 'mailto:foo.com'):
			pageview.activate_link(href)
			self.assertEqual(
				pageview.navigation.mock_calls[-1],
				('open_page', Path(href), {'new_window': False})
			)

		def check_zim_cmd(cmd, args):
			self.assertEqual(args, ('--gui', 'file://foo/bar', 'dus.txt'))

		with tests.ZimApplicationContext(check_zim_cmd):
			pageview.activate_link('zim+file://foo/bar?dus.txt')

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

		def mock_default(*a):
			raise AssertionError('Default handler reached')

		pageview.do_activate_link = mock_default

		def myhandler(o, link, hints):
			if link.startswith('myurl://'):
				return True

		id = pageview.connect('activate-link', myhandler)

		with self.assertRaisesRegex(AssertionError, 'Default handler reached'):
			pageview.activate_link('foo')

		pageview.activate_link('myurl://foo') # No raise

		pageview.disconnect(id)


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
		with buffer.user_action:
			buffer.insert_at_cursor('test')
		with buffer.user_action:
			buffer.insert_at_cursor(' ')
		with buffer.user_action:
			buffer.insert_at_cursor('123')

		self.assertEqual(get_text(buffer), 'test 123\n')

		for text in ('test \n', 'test\n', '\n'):
			pageview.undo()
			self.assertEqual(get_text(buffer), text)

		for text in ('test\n', 'test \n', 'test 123\n'):
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
		self.assertEqual(get_text(buffer), 'test 123\n')
		pageview.delete()
		self.assertEqual(get_text(buffer), 'tst 123\n')
		pageview.delete()
		self.assertEqual(get_text(buffer), 'tt 123\n')

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

	def testEditObjectForLink(self):
		pageview = setUpPageView(self.setUpNotebook(), '[[link]]\n')

		def edit_link(dialog):
			dialog.set_input(href='test')
			dialog.assert_response_ok()

		with tests.DialogContext(edit_link):
			pageview.edit_object()

		self.assertEqual(pageview.page.dump('wiki'), ['[[test]]\n'])

	def testEditObjectForImage(self):
		file = File('./data/zim.png')
		pageview = setUpPageView(self.setUpNotebook(), '{{%s}}\n' % file.path)

		def edit_img(dialog):
			dialog.set_input(href='test')
			dialog.assert_response_ok()

		with tests.DialogContext(edit_img):
			pageview.edit_object()

		text = ''.join(pageview.page.dump('wiki')).strip()
		self.assertTrue(text.startswith('{{') and text.endswith('?href=test}}'), '%r does not match \{\{...?href=test\}\}' % text)
		self.assertEqual(File(text[2:-12]), file)

	def testEditObjectForObject(self):
		pageview = setUpPageView(self.setUpNotebook(), '{{{test:\nfoo\n}}}\n')

		buffer = pageview.textview.get_buffer()
		anchor = buffer.get_objectanchor(buffer.get_insert_iter())
		widget = anchor.get_widgets()[0]

		counter = tests.Counter()
		widget.edit_object = counter

		pageview.edit_object()

		self.assertEquals(counter.count, 1)

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
		file = File('./data/zim.png')

		def choose_file(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		with tests.DialogContext(choose_file):
			pageview.show_insert_image()

		text = ''.join(pageview.page.dump('wiki')).strip()
		self.assertTrue(text.startswith('{{') and text.endswith('}}'), '%r does not match \{\{...\}\}' % text)
		self.assertEqual(File(text[2:-2]), file)

	def testInsertBulletList(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.insert_bullet_list()
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		self.assertEqual(pageview.page.dump('wiki'), ['* test 123\n', '\n'])

	def testInsertNumberedList(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.insert_numbered_list()
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		self.assertEqual(pageview.page.dump('wiki'), ['1. test 123\n', '\n'])

	def testInsertCheckBoxList(self):
		pageview = setUpPageView(self.setUpNotebook())
		pageview.insert_checkbox_list()
		buffer = pageview.textview.get_buffer()
		buffer.insert_at_cursor('test 123')
		self.assertEqual(pageview.page.dump('wiki'), ['[ ] test 123\n', '\n'])

	def testApplyBulletList(self):
		pageview = setUpPageView(self.setUpNotebook(), 'test 123\n')
		buffer = pageview.textview.get_buffer()
		begin = buffer.get_iter_at_offset(0)
		end = buffer.get_iter_at_offset(8)
		buffer.select_range(begin, end)
		pageview.apply_format_bullet_list()
		self.assertEqual(pageview.page.dump('wiki'), ['* test 123\n'])

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

		self.assertEqual(pageview.page.dump('wiki'), ['my text\n', '\n'])

	def testInsertLink(self):
		pageview = setUpPageView(self.setUpNotebook())

		def select_link(dialog):
			dialog.set_input(href='mylink')
			dialog.assert_response_ok()

		with tests.DialogContext(select_link):
			pageview.insert_link()

		self.assertEqual(pageview.page.dump('wiki'), ['[[mylink]]\n'])

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


class TestPageviewDialogs(tests.TestCase):

	def testVarious(self):
		'''Test input/output of various pageview dialogs'''
		## Insert Date dialog
		buffer = tests.MockObject()
		notebook = tests.MockObject()
		notebook.mock_method('suggest_link', Path(':suggested_link'))
		page = Path('test')

		dialog = InsertDateDialog(None, buffer, notebook, page)
		dialog.linkbutton.set_active(False)
		dialog.view.get_selection().select_path((0,))
		dialog.assert_response_ok()
		self.assertEqual(buffer.mock_calls[-1][0], 'insert_at_cursor')

		dialog = InsertDateDialog(None, buffer, notebook, page)
		dialog.linkbutton.set_active(True)
		dialog.view.get_selection().select_path((0,))
		dialog.assert_response_ok()
		self.assertEqual(buffer.mock_calls[-1][0], 'insert_link_at_cursor')

		## Insert Image dialog
		buffer = tests.MockObject()
		file = File('data/zim.png')
		dialog = InsertImageDialog(None, buffer, notebook, Path(':some_page'), file)
		self.assertTrue(dialog.filechooser.get_preview_widget_active())
		#~ self.assertEqual(dialog.get_file(), file)
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(buffer.mock_calls[-1][0], 'insert_image_at_cursor')

		## Edit Image dialog
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		notebook = tests.MockObject()
		notebook.mock_method('resolve_file', file)
		notebook.mock_method('relative_filepath', './data/zim.png')
		file = File('data/zim.png')
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
			'_src_file': file,
			'height': 24,
		})
		self.assertEqual(type(imagedata['height']).__name__, 'int')

		## Insert text from file dialog
		buffer = tests.MockObject()
		dialog = InsertTextFromFileDialog(None, buffer, notebook, Path(':some_page'))
		#~ dialog.set_file()
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(buffer.mock_calls[-1][0], 'insert_parsetree_at_cursor')

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
		# Insert Link dialog
		pageview = setUpPageView(self.setUpNotebook())
		dialog = InsertLinkDialog(None, pageview)
		dialog.form.widgets['href'].set_text('Foo')
		dialog.assert_response_ok()
		buffer = pageview.textview.get_buffer()
		self.assertEqual(get_text(buffer), 'Foo\n')


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


class TestAutolink(tests.TestCase):

	def runTest(self):
		test = (
			'ВаняИванов',		# CamelCase
			'+ВаняИванов',		# page match
			'ВаняИванов:foo', 	# page match
		)
		view = TextView({'autolink_files': True, 'autolink_camelcase': True})
		buffer = view.get_buffer()
		for word in test:
			buffer.insert_at_cursor(word)
			iter = buffer.get_insert_iter()
			start = iter.copy()
			start.backward_chars(len(word))
			char = '\n'
			editmode = []
			view.emit('end-of-word', start, iter, word, char, editmode)
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


class TestDragAndDropFunctions(tests.TestCase):

	@tests.expectedFailure
	def testSerializeParseTree(self):
		tree = tests.new_parsetree()
		tree.resolve_images()
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		buffer = TextBuffer(notebook, page)
		with FilterNoSuchImageWarning():
			buffer.insert_parsetree_at_cursor(tree)

		start, end = buffer.get_bounds()
		xml = buffer.serialize(buffer, Gdk.Atom.intern('text/x-zim-parsetree', False), start, end)
		tree.unresolve_images()
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
		#folder = self.setUpFolder('imagedata', mock=tests.MOCK_NEVER)
		folder = Dir(self.create_tmp_dir('imagedata'))
		notebook = tests.MockObject()
		notebook.mock_method('get_attachments_dir', folder)
		notebook.resolve_file = lambda fpath, ppath: fpath
		path = Path('Mock')

		buffer = TextBuffer(notebook, path)
		image = File('./data/zim.png').raw()
		iter = buffer.get_insert_iter()
		buffer.deserialize(buffer, Gdk.Atom.intern('image/png', False), iter, image)

		tree = buffer.get_parsetree()
		xml = tree.tostring()
		self.assertIn("pasted_image.png", xml) # FIXME: should use tree api to get image
