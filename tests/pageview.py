# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests


from zim.fs import File, Dir
from zim.formats import wiki, ParseTree
from zim.notebook import Path
from zim.gui.pageview import *
from zim.config import SectionedConfigDict, VirtualConfigManager, ConfigManager
from zim.gui.clipboard import Clipboard


class FilterNoSuchImageWarning(tests.LoggingFilter):

	logger = 'zim.gui.pageview'
	message = 'No such image:'


def new_parsetree_from_text(text):
	## FIXME had to wrap my own here becase of stupid
	## resolve_images - get rid of that
	tree = tests.new_parsetree_from_text(text)
	notebook = tests.new_notebook(fakedir='/foo')
	page = notebook.get_page(Path('Foo'))
	tree.resolve_images(notebook, page)

	return tree


def setUpPageView(fakedir=None, notebook=None):
	'''Some bootstrap code to get an isolated PageView object'''
	## TODO - should not be needed
	## we can get rid of this when we refactor the actiongroup stuff
	## to not register, by be called by the window
	PageView.actiongroup = tests.MockObject() # use class attribute to fake ui init
	PageView.actiongroup.mock_method('get_action', tests.MockObject())
	PageView.actiongroup.mock_method('list_actions', [])

	if notebook is None:
		notebook = tests.new_notebook(fakedir)

	ui = MockUI()
	ui.config = VirtualConfigManager()
	ui.notebook = notebook
	ui.page = None
	ui.uimanager = tests.MockObject()
	ui.uimanager.mock_method('get_accel_group', tests.MockObject())

	ui.mainwindow = tests.MockObject()
	ui.mainwindow.statusbar_style_label = tests.MockObject()

	return PageView(ui)


class TestCaseMixin(object):
	# Mixin class with extra test methods

	def assertBufferEquals(self, buffer, wanted):
		if not isinstance(wanted, basestring):
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
		#~ print 'CHECK', line, offset, text
		cursor = buffer.get_insert_iter()
		#~ print '  GOT', cursor.get_line(), cursor.get_line_offset()
		self.assertEqual(cursor.get_line(), line)
		self.assertEqual(cursor.get_line_offset(), offset)


class TestTextBuffer(tests.TestCase, TestCaseMixin):

	def testVarious(self):
		'''Test serialization and interaction of the page view textbuffer'''
		wikitext = tests.WikiTestData.get('roundtrip')
		tree = new_parsetree_from_text(wikitext)
		buffer = TextBuffer()
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(tree)

		raw1 = buffer.get_parsetree(raw=True)
		result1 = buffer.get_parsetree()
		#~ print tree.tostring()
		#~ print result1.tostring()
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
		buffer = TextBuffer()
		buffer.insert_at_cursor(u'foo \uFFFC bar')
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
		start = buffer.get_iter_at_line(3) # Bar 1
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

		buffer = TextBuffer()
		buffer.set_parsetree(tree)

		iter = buffer.get_iter_at_offset(7) # middle of "bbb"
		buffer.place_cursor(iter)
		buffer.select_word()

		with buffer.user_action:
			buffer.delete_selection(True, True)
			buffer.insert_interactive_at_cursor("eee", True)

		self.assertBufferEquals(buffer, wanted)

	def testSelectLink(self):
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
aaa <link href="xxx">bbb</link> ccc
</zim-tree>
'''
		tree = tests.new_parsetree_from_xml(input)

		buffer = TextBuffer()
		buffer.set_parsetree(tree)
		buffer.place_cursor(buffer.get_iter_at_offset(7)) # middle of link

		self.assertIsNone(buffer.get_has_link_selection())
		data = buffer.select_link()
		self.assertEqual(data['href'], 'xxx')
		self.assertEqual(buffer.get_has_link_selection(), data)


class TestUndoStackManager(tests.TestCase):

	def runTest(self):
		'''Test the undo/redo functionality'''
		buffer = TextBuffer()
		undomanager = UndoStackManager(buffer)
		wikitext = tests.WikiTestData.get('roundtrip')
		tree = new_parsetree_from_text(wikitext)

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

		start, end = map(buffer.get_iter_at_offset, (5, 10))
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
		buffer = TextBuffer()
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
		buffer = TextBuffer()
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

		buffer = TextBuffer()
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
		] )

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

	def testNumberedLists(self):
		buffer = TextBuffer()

		# The rules for renumbering are:
		#
		# 1. If this is top of the list, number down
		# 2. Otherwise look at bullet above and number down from there
		#    (this means whatever the user typed doesn't really matter)
		# 3. If above bullet is non-number bullet, replace the numbered
		#    item with that bullet (for checkboxes always an open
		#    checkbox is used.)
		#
		# Note that the bullet on the line we look also at does not have
		# to be a numbered bullet. The one above or below may still be
		# number. And vice versa

		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="3." indent="1"> B</li>
<li bullet="a." indent="2"> C</li>
<li bullet="b." indent="2"> D</li>
<li bullet="*" indent="1"> E</li>
</zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="a." indent="2"> C</li>
<li bullet="b." indent="2"> D</li>
<li bullet="C." indent="1"> E</li>
</zim-tree>'''
		buffer.set_parsetree(tests.new_parsetree_from_xml(input))
		buffer.renumber_list(1) # top of list: A.
		self.assertBufferEquals(buffer, wanted)

		buffer.set_parsetree(tests.new_parsetree_from_xml(input))
		buffer.renumber_list(2) # middle of list: 3.
		self.assertBufferEquals(buffer, wanted)

		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="1." indent="1"> A</li>
<li bullet="2." indent="1"> B</li>
<li bullet="a." indent="2"> C</li>
<li bullet="b." indent="2"> D</li>
<li bullet="*" indent="1"> E</li>
</zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="1." indent="1"> A</li>
<li bullet="2." indent="1"> B</li>
<li bullet="a." indent="2"> C</li>
<li bullet="b." indent="2"> D</li>
<li bullet="3." indent="1"> E</li>
</zim-tree>'''

		buffer.set_parsetree(tests.new_parsetree_from_xml(input))
		buffer.renumber_list(5) # after sub list: "*"
		self.assertBufferEquals(buffer, wanted)

		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="*" indent="1"> B</li>
<li bullet="C." indent="1"> C</li>
</zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="C." indent="1"> C</li>
</zim-tree>'''
		buffer.set_parsetree(tests.new_parsetree_from_xml(input))
		buffer.renumber_list(2) # middle of list: B.
		self.assertBufferEquals(buffer, wanted)

		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="*" indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="*" indent="1"> C</li>
</zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="*" indent="1"> A</li>
<li bullet="*" indent="1"> B</li>
<li bullet="*" indent="1"> C</li>
</zim-tree>'''
		buffer.set_parsetree(tests.new_parsetree_from_xml(input))
		buffer.renumber_list(2) # middle of list: B.
		self.assertBufferEquals(buffer, wanted)

		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="checked-box" indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="*" indent="1"> C</li>
</zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="checked-box" indent="1"> A</li>
<li bullet="unchecked-box" indent="1"> B</li>
<li bullet="*" indent="1"> C</li>
</zim-tree>'''
		buffer.set_parsetree(tests.new_parsetree_from_xml(input))
		buffer.renumber_list(2) # middle of list: B.
		self.assertBufferEquals(buffer, wanted)

		# Renumber behavior after changing indenting:
		#
		# 1. If this is now middle of a list (above item is same or
		#    more indenting) look above and renumber
		# 2. If this is now top of a sublist (above item is lower
		#    indent) look _below_ and copy bullet found there then
		#    number down
		# 3. If this is the top of a new sublist (no item below)
		#    switch bullet style (numbers vs letters) and reset count
		# 4. If this is the top of the list (no bullet above) don't
		#    need to do anything
		#
		# ALSO look at previous level where item went missing,
		# look at above item at that level and number downward

		def indent(buffer, line):
			row, list = TextBufferList.new_from_line(buffer, line)
			list.indent(row)

		def unindent(buffer, line):
			row, list = TextBufferList.new_from_line(buffer, line)
			list.unindent(row)

		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="C." indent="1"> C</li>
<li bullet="D." indent="1"> D</li>
</zim-tree>'''
		buffer.set_parsetree(tests.new_parsetree_from_xml(input))

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="1." indent="2"> C</li>
<li bullet="C." indent="1"> D</li>
</zim-tree>'''
		indent(buffer, 3) # new sub-list -- reset style and numbering
		self.assertBufferEquals(buffer, wanted)

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="1." indent="2"> C</li>
<li bullet="2." indent="2"> D</li>
</zim-tree>'''
		indent(buffer, 4) # add to existing sub list
		self.assertBufferEquals(buffer, wanted)

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="1." indent="2"> B</li>
<li bullet="1." indent="3"> C</li>
<li bullet="2." indent="3"> D</li>
</zim-tree>'''
		indent(buffer, 2) # top of existing sub list
		self.assertBufferEquals(buffer, wanted)

		prev = wanted
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="1." indent="2"> B</li>
<li bullet="1." indent="3"> C</li>
<li bullet="a." indent="4"> D</li>
</zim-tree>'''
		indent(buffer, 4) # yet another new sub level
		self.assertBufferEquals(buffer, wanted)

		unindent(buffer, 4)
		self.assertBufferEquals(buffer, prev)

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="1." indent="2"> C</li>
<li bullet="2." indent="2"> D</li>
</zim-tree>'''
		unindent(buffer, 2) # renumber both levels
		self.assertBufferEquals(buffer, wanted)

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="A." indent="1"> A</li>
<li bullet="B." indent="1"> B</li>
<li bullet="1." indent="2"> C</li>
<li bullet="C." indent="1"> D</li>
</zim-tree>'''
		unindent(buffer, 4)
		self.assertBufferEquals(buffer, wanted)

		buffer.set_bullet(4, NUMBER_BULLET)
		self.assertBufferEquals(buffer, wanted)


		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="1." indent="1"> A</li>
<li bullet="2." indent="1"> B</li>
<li bullet="3." indent="1"> C</li>
</zim-tree>'''
		buffer.set_parsetree(tests.new_parsetree_from_xml(input))

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="1." indent="1"> A</li>
<li bullet="2." indent="1"> B</li>
<li bullet="a." indent="2"> C</li>
</zim-tree>'''
		indent(buffer, 3)
		self.assertBufferEquals(buffer, wanted)


		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="*" indent="1"> A</li>
<li bullet="1." indent="2"> B</li>
<li bullet="2." indent="2"> C</li>
<li bullet="*" indent="1"> D</li>
</zim-tree>'''
		buffer.set_parsetree(tests.new_parsetree_from_xml(input))

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="*" indent="1"> A</li>
<li bullet="1." indent="2"> B</li>
<li bullet="2." indent="2"> C</li>
<li bullet="3." indent="2"> D</li>
</zim-tree>'''
		indent(buffer, 4)
		self.assertBufferEquals(buffer, wanted)

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
<li bullet="*" indent="1"> A</li>
<li bullet="*" indent="1"> B</li>
<li bullet="1." indent="2"> C</li>
<li bullet="2." indent="2"> D</li>
</zim-tree>'''
		unindent(buffer, 2)
		self.assertBufferEquals(buffer, wanted)


def press(widget, sequence):
	#~ print 'PRESS', sequence
	for key in sequence:
		event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)
		if isinstance(key, (int, long)):
			event.keyval = int(key)
		elif key == '\n':
			event.keyval = int( gtk.gdk.keyval_from_name('Return') )
		elif key == '\t':
			event.keyval = int( gtk.gdk.keyval_from_name('Tab') )
		else:
			event.keyval = int( gtk.gdk.unicode_to_keyval(ord(key)) )

		if not isinstance(key, (int, long)):
			event.string = key

		#gtk.main_do_event(event)
		#assert widget.event(event) # Returns True if event was handled
		#while gtk.events_pending():
		#	gtk.main_iteration()
		widget.emit('key-press-event', event)


class TestTextView(tests.TestCase, TestCaseMixin):

	def setUp(self):
		# Initialize default preferences from module
		self.preferences = {}
		for pref in ui_preferences:
			self.preferences[pref[0]] = pref[4]

	def testTyping(self):
		print '\n!! Two GtkWarnings expected here for gdk display !!'
		view = TextView(self.preferences)
		buffer = TextBuffer()
		view.set_buffer(buffer)
		undomanager = UndoStackManager(buffer)

		# Need a window to get the widget realized
		window = gtk.Window()
		window.add(view)
		view.realize()
		#~ window.show_all()
		#~ view.grab_focus()

		press(view, 'aaa\n')
		start, end = buffer.get_bounds()
		self.assertEqual(buffer.get_text(start, end), 'aaa\n')
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

	def testCopyPaste(self):
		dir = self.get_tmp_name('testCopyPaste')
		notebook = tests.new_notebook(fakedir=dir)
		page = notebook.get_page(Path('roundtrip'))
		parsetree = page.get_parsetree()

		buffer = TextBuffer(notebook, page)
		textview = TextView(self.preferences)
		textview.set_buffer(buffer)

		print '** HACK for cleaning up parsetree'
		def cleanup(parsetree):
			# FIXME - HACK - dump and parse as wiki first to work
			# around glitches in pageview parsetree dumper
			# main visibility when copy pasting bullet lists
			# Same hack in gui clipboard code
			from zim.notebook import Path, Page
			from zim.formats import get_format
			dumper = get_format('wiki').Dumper()
			text = ''.join( dumper.dump(parsetree) ).encode('utf-8')
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
		self.assertEqual(buffer.get_text(*buffer.get_bounds()), '')

		# popup menu
		page = tests.new_page_from_text('Foo **Bar** Baz\n')
		dir = self.get_tmp_name('testCopyPaste')
		pageview = setUpPageView(fakedir=dir)
		pageview.set_page(page)

		def get_context_menu():
			buffer = pageview.view.get_buffer()
			buffer.select_range(*buffer.get_bounds()) # select all
			return pageview.view.get_popup()

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
		tree = Clipboard.get_parsetree(pageview.ui.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree partial="True"><p>Foo <strong>Bar</strong> Baz\n</p></zim-tree>')

		page = tests.new_page_from_text('[[bar]]')
		pageview.set_page(page)
		click(_('Copy _Link'))
		self.assertEqual(Clipboard.get_text(), 'Bar')
		tree = Clipboard.get_parsetree(pageview.ui.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="Bar">Bar</link></zim-tree>')

		page = tests.new_page_from_text('[[wp?foobar]]')
		pageview.set_page(page)
		click(_('Copy _Link'))
		self.assertEqual(Clipboard.get_text(), 'http://en.wikipedia.org/wiki/foobar')
		tree = Clipboard.get_parsetree(pageview.ui.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="wp?foobar">wp?foobar</link></zim-tree>')

		page = tests.new_page_from_text('[[~//bar.txt]]')
			# Extra '/' is in there to verify path gets parsed as File object
		pageview.set_page(page)
		click(_('Copy _Link'))
		self.assertEqual(Clipboard.get_text(), '~/bar.txt')
		tree = Clipboard.get_parsetree(pageview.ui.notebook, page)
		self.assertEqual(tree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="~/bar.txt">~/bar.txt</link></zim-tree>')



# TODO: More popup stuff



class TestPageView(tests.TestCase, TestCaseMixin):

	def testGetSelection(self):
		pageview = setUpPageView()
		buffer = pageview.view.get_buffer()
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

		pageview = setUpPageView()
		buffer = pageview.view.get_buffer()
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
		pageview = setUpPageView()
		buffer = pageview.view.get_buffer()
		buffer.set_text('''Test 123\n''')

		buffer.place_cursor(buffer.get_end_iter())
		pageview.insert_links((Path("foo"), File("/foo.txt"), "~/bar.txt"))
		wantedtext = 'Test 123\nfoo\n%s\n~/bar.txt\n' % File('/foo.txt').uri
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, wantedtext)

		buffer.place_cursor(buffer.get_iter_at_line(2))
		buffer.select_line()
		pageview.insert_links(('http://cpan.org',))
		wantedtext = 'Test 123\nfoo\n%s\n~/bar.txt\n' % 'http://cpan.org '
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, wantedtext)


class TestPageviewDialogs(tests.TestCase):

	def testVarious(self):
		'''Test input/output of various pageview dialogs'''
		## Insert Date dialog
		ui = MockUI()
		buffer = MockBuffer()
		ui.notebook.mock_method('suggest_link', Path(':suggested_link'))
		ui.config = ConfigManager() # need dates.list

		dialog = InsertDateDialog(ui, buffer)
		dialog.linkbutton.set_active(False)
		dialog.view.get_selection().select_path((0,))
		dialog.assert_response_ok()
		self.assertEqual(buffer.mock_calls[-1][0], 'insert_at_cursor')

		dialog = InsertDateDialog(ui, buffer)
		dialog.linkbutton.set_active(True)
		dialog.view.get_selection().select_path((0,))
		dialog.assert_response_ok()
		self.assertEqual(buffer.mock_calls[-1][0], 'insert_link_at_cursor')

		## Insert Image dialog
		ui = MockUI()
		buffer = MockBuffer()
		file = File('data/zim.png')
		dialog = InsertImageDialog(ui, buffer, Path(':some_page'), file)
		self.assertTrue(dialog.filechooser.get_preview_widget_active())
		#~ self.assertEqual(dialog.get_file(), file)
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(buffer.mock_calls[-1][0], 'insert_image_at_cursor')

		## Edit Image dialog
		ui = MockUI()
		file = File('data/zim.png')
		ui.notebook.mock_method('resolve_file', file)
		ui.notebook.mock_method('relative_filepath', './data/zim.png')
		buffer = TextBuffer()
		buffer.insert_image_at_cursor(file, '../MYPATH/./data/zim.png')
		dialog = EditImageDialog(ui, buffer, Path(':some_page'))
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
		ui = MockUI()
		buffer = MockBuffer()
		dialog = InsertTextFromFileDialog(ui, buffer)
		#~ dialog.set_file()
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(buffer.mock_calls[-1][0], 'insert_parsetree_at_cursor')

		## Find And Replace dialog
		ui = MockUI()
		textview = TextView({})
		buffer = textview.get_buffer()
		buffer.set_text('''\
foo bar foooobar
foo bar bazzz baz
''')
		dialog = FindAndReplaceDialog(ui, textview)
		dialog.find_entry.set_text('foo')
		dialog.replace_entry.set_text('dus')
		dialog.word_option_checkbox.set_active(True)
		dialog.replace()
		dialog.replace_all()
		self.assertEqual(buffer.get_text(*buffer.get_bounds()), '''\
dus bar foooobar
dus bar bazzz baz
''')

		## Word Count dialog
		pageview = tests.MockObject()
		pageview.view = textview
		pageview.ui = MockUI()
		dialog = WordCountDialog(pageview)
		dialog.destroy() # nothing to test really

	def testInsertLinkDialog(self):
		# Insert Link dialog
		ui = MockUI()
		ui.notebook.index = tests.MockObject()
		ui.notebook.index.mock_method('list_pages', [])
		ui.notebook.index.mock_method('walk', [])
		pageview = tests.MockObject()
		pageview.page = Path('Test:foo:bar')
		textview = TextView({})
		pageview.view = textview
		dialog = InsertLinkDialog(ui, pageview)
		dialog.form.widgets['href'].set_text('Foo')
		dialog.assert_response_ok()
		buffer = textview.get_buffer()
		self.assertEqual(buffer.get_text(*buffer.get_bounds()), 'Foo')



class MockUI(tests.MockObject):

	def __init__(self):
		tests.MockObject.__init__(self)
		self.mainwindow = None
		self.notebook = tests.MockObject()
		self.preferences = SectionedConfigDict()
		self.page = Path('Test')

	def register_preferences(self, section, preferences):
		for p in preferences:
			if len(p) == 5:
				key, type, category, label, default = p
				self.preferences[section].setdefault(key, default)
			else:
				key, type, category, label, default, check = p
				self.preferences[section].setdefault(key, default, check=check)


class MockBuffer(tests.MockObject):
	pass


class TestCamelCase(tests.TestCase):

	def testLatin(self):
		for text in (
			'CamelCase', 'AbbA',
			u'ĚěščřžýáíéúůŮěščřžýáíéúů'
		):
			self.assertTrue(
				camelcase(unicode(text)),
				msg='"%s" should be CamelCase' % text
			)

		for text in (
			'A', 'AAAA', 'aaaa', 'Aaaaa', 'AAAAaaa', 'aAAAAA', 'aaaAAA',
			'123', 'A123A123',
			u'ĚŠČŘŽÝÁÍÉÚŮ', u'ěščřžýáíéúů',
		):
			self.assertFalse(
				camelcase(unicode(text)),
				msg='"%s" should NOT be CamelCase' % text
			)

	def testArabic(self):
		# Arabic text should never be CamelCase,
		# letters test as neither upper not lower case
		for text in (
			u'سلام',
			u'کهکشان',
			u'روزانه',
			u'ذائقه',
			u'آبادی',
			u'انشاء',
			u'محَبّت',
			u'اَعْداد',
			u'حتماً',
			u'ماوراء‌الطبیعه',
			u'پشتک‌وارو',
			u'راه‌راه',
			u' یاپ کارزنبرگ',
		):
			assert isinstance(text, unicode)
			self.assertFalse(
				camelcase(unicode(text)),
				msg='"%s" should NOT be CamelCase' % text
			)
