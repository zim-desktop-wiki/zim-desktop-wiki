# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from __future__ import with_statement

from tests import TestCase, get_test_data_page, get_test_page

import logging

from zim.fs import *
from zim.formats import wiki, ParseTree
from zim.gui.pageview import *


logger = logging.getLogger('zim.gui.pageview')


class FilterNoSuchImageWarning(object):

	def __enter__(self):
		logger.addFilter(self)

	def __exit__(self, *a):
		logger.removeFilter(self)

	def filter(self, record):
		return not record.getMessage().startswith('No such image:')


def get_tree(wikitext):
	tree = wiki.Parser().parse(wikitext)
	notebook, page = get_test_page()
	notebook.get_store(page).dir = Dir('/foo') # HACK
	tree.resolve_images(notebook, page)
	return tree


def get_tree_from_xml(xml):
	# For some reason this does not work with cElementTree.XMLBuilder ...
	from xml.etree.ElementTree import XMLTreeBuilder
	builder = XMLTreeBuilder()
	builder.feed(xml)
	root = builder.close()
	return ParseTree(root)


class TestTextBuffer(TestCase):

	def runTest(self):
		'''Test serialization of the page view textbuffer'''
		wikitext = get_test_data_page('wiki', 'roundtrip')
		tree = get_tree(wikitext)
		buffer = TextBuffer()
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(tree)

		raw1 = buffer.get_parsetree(raw=True)
		result1 = buffer.get_parsetree()
		#~ print result1.tostring()
		#~ self.assertEqualDiff(result1.tostring(), tree.tostring())

		# Compare cooked tree after dumping back
		resulttext = u''.join(wiki.Dumper().dump(result1))
		self.assertEqualDiff(resulttext, wikitext)

		# Compare we are stable when loading raw tree again
		raw = raw1.tostring()
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(raw1)
		self.assertEqualDiff(raw1.tostring(), raw)
			# If this fails, set_parsetree is modifying the tree
		raw2 = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(raw2.tostring(), raw)
			# Actual cooked roundtrip test

		# Compare we are stable when loading cooked tree again
		cooked = result1.tostring()
		with FilterNoSuchImageWarning():
			buffer.set_parsetree(result1)
		self.assertEqualDiff(result1.tostring(), cooked)
			# If this fails, set_parsetree is modifying the tree
		result2 = buffer.get_parsetree()
		self.assertEqualDiff(result2.tostring(), cooked)
			# Actual cooked roundtrip test

		# Test 'raw' really preserves "errors"
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">
foo<h level="1">bar</h>baz

dus <pre>ja</pre> hmm

<h level="2">foo
</h>bar

dus <p indent="5">ja</p> <emphasis>hmm
dus ja
</emphasis>grrr

<li bullet="*" indent="0"> Foo</li>
<li bullet="*" indent="0"> Bar</li>
</zim-tree>'''
		tree = get_tree_from_xml(input)
		buffer.set_parsetree(tree)
		self.assertFalse(buffer.get_modified())

		rawtree = buffer.get_parsetree(raw=True)
		self.assertFalse(buffer.get_modified())
		self.assertEqualDiff(rawtree.tostring(), input)

		# Test errors are cleaned up correctly
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
foo

<h level="1">bar</h>
baz

dus <code>ja</code> hmm

<h level="2">foo</h>
bar

dus ja <emphasis>hmm</emphasis>
<emphasis>dus ja</emphasis>
grrr

<li bullet="*" indent="0">Foo</li><li bullet="*" indent="0">Bar</li></zim-tree>'''
		tree = buffer.get_parsetree()
		self.assertFalse(buffer.get_modified())
		self.assertEqualDiff(tree.tostring(), wanted)

		# Test pasteing some simple text
		buffer.set_parsetree(tree) # reset without errors
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><strong>Bold</strong></zim-tree>'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
foo

<h level="1">bar</h>
baz

dus <code>ja</code> hmm

<h level="2">foo</h>
bar

dus ja <emphasis>hmm</emphasis>
<emphasis>dus ja</emphasis>
grrr

<li bullet="*" indent="0">Foo<strong>Bold</strong></li><li bullet="*" indent="0">Bar</li></zim-tree>'''
		pastetree = get_tree_from_xml(input)
		iter = buffer.get_iter_at_line(15)
		iter.forward_chars(5) # position after "* Foo"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		tree = buffer.get_parsetree()
		self.assertTrue(buffer.get_modified())
		self.assertEqualDiff(tree.tostring(), wanted)

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
foo

<h level="1">bar</h>
baz
<li bullet="*" indent="0">Foo</li><li bullet="*" indent="0">Bar</li>


dus <code>ja</code> hmm

<h level="2">foo</h>
bar

dus ja <emphasis>hmm</emphasis>
<emphasis>dus ja</emphasis>
grrr

<li bullet="*" indent="0">Foo<strong>Bold</strong></li><li bullet="*" indent="0">Bar</li></zim-tree>'''
		pastetree = get_tree_from_xml(input)
		iter = buffer.get_iter_at_line(4)
		iter.forward_chars(3) # position after "baz"
		buffer.insert_parsetree(iter, pastetree, interactive=True)
		tree = buffer.get_parsetree()
		self.assertTrue(buffer.get_modified())
		self.assertEqualDiff(tree.tostring(), wanted)

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
<li bullet="unchecked-box" indent="0">Box 1</li>foo <li bullet="unchecked-box" indent="0">Box 2</li><li bullet="unchecked-box" indent="0">Box 3</li>
</zim-tree>'''
		tree = get_tree_from_xml(input)
		buffer.set_parsetree(tree)
		iter = buffer.get_iter_at_line(2) # iter before checkbox
		buffer.insert(iter, 'foo ')
		#print buffer.get_parsetree(raw=True).tostring()
		#print buffer.get_parsetree().tostring()
		tree = buffer.get_parsetree()
		self.assertEqualDiff(tree.tostring(), wanted)


class TestUndoStackManager(TestCase):

	def runTest(self):
		'''Test the undo/redo functionality'''
		buffer = TextBuffer()
		undomanager = UndoStackManager(buffer)
		wikitext = get_test_data_page('wiki', 'roundtrip')
		tree = get_tree(wikitext)

		with FilterNoSuchImageWarning():
			buffer._insert_element_children(tree.getroot())
				# Use private method to circumvent begin-insert-tree signal etc.

		#~ import pprint
		#~ undomanager.flush_insert()
		i = 0
		for group in undomanager.stack + [undomanager.group]:
			#~ pprint.pprint(
				#~ [(a[0], a[1], a[2], a[3].tostring()[39:]) for a in group] )
			for action in group:
				self.assertEqual(action[1], i) # assert undo stack is continous
				i = action[2]
		self.assertTrue(len(undomanager.stack) > 10) # check we recorded something

		buffertree1 = buffer.get_parsetree(raw=True)

		while undomanager.undo():
			continue

		emptytree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(emptytree.tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\" />")

		with FilterNoSuchImageWarning():
			while undomanager.redo():
				continue

		buffertree2 = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(buffertree2.tostring(), buffertree1.tostring())

		while undomanager.undo():
			continue

		emptytree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(emptytree.tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree raw=\"True\" />")

		buffer.clear()
		self.assertTrue(len(undomanager.stack) == 0)
		undomanager.unblock()

		# test merging
		for c in 'fooo barr baz':
			with buffer.user_action:
				buffer.insert_at_cursor(c)
		#~ import pprint
		#~ undomanager.flush_insert()
		#~ pprint.pprint(undomanager.stack)
		self.assertTrue(len(undomanager.stack) == 5) # 3 words, 2 spaces
		for group in undomanager.stack:
			self.assertTrue(len(group) == 1) # merge was sucessfull
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo barr baz</zim-tree>")

		for wanted in (
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo barr </zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo barr</zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo </zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo</zim-tree>",
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree />"
		):
			undomanager.undo()
			self.assertEqualDiff(buffer.get_parsetree().tostring(), wanted)

		while undomanager.redo():
			continue
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo barr baz</zim-tree>")

		# test other actions
		iter = buffer.get_iter_at_offset(7)
		buffer.place_cursor(iter)
		buffer.select_word()
		buffer.toggle_textstyle('strong', interactive=True)
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo <strong>barr</strong> baz</zim-tree>")

		undomanager.undo()
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo barr baz</zim-tree>")

		undomanager.redo()
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo <strong>barr</strong> baz</zim-tree>")

		start, end = map(buffer.get_iter_at_offset, (5, 10))
		with buffer.user_action:
			buffer.delete(start, end)
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo baz</zim-tree>")

		undomanager.undo()
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo <strong>barr</strong> baz</zim-tree>")

		undomanager.redo()
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo baz</zim-tree>")

		# test folding
		undomanager.undo()
		undomanager.undo()
		undomanager.undo()
		undomanager.undo()

		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo barr</zim-tree>")

		with buffer.user_action:
			buffer.insert_at_cursor(' ')

		undomanager.undo()
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo barr</zim-tree>")

		undomanager.undo() # here we undo fold of 4 undos above
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo baz</zim-tree>")
		undomanager.undo()
		self.assertEqualDiff(buffer.get_parsetree().tostring(),
			"<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>fooo <strong>barr</strong> baz</zim-tree>")


class TestFind(TestCase):

	def runTest(self):
		buffer = TextBuffer()
		finder = buffer.finder
		buffer.set_text('''\
FOO FooBar FOOBAR
FooBaz Foo Bar
foo Bar Baz Foo
''')
		buffer.place_cursor(buffer.get_start_iter())

		def check(line, offset, string):
			#~ print 'CHECK', line, offset, text
			cursor = buffer.get_insert_iter()
			#~ print '  GOT', cursor.get_line(), cursor.get_line_offset()
			self.assertEqual(cursor.get_line(), line)
			self.assertEqual(cursor.get_line_offset(), offset)

			if string:
				bound = buffer.get_selection_bounds()
				self.assertTrue(bound)
				selection = bound[0].get_slice(bound[1])
				self.assertEqual(selection, string)

		# Check normal usage, case-insensitive
		for text in ('f', 'fo', 'foo', 'fo', 'f', 'F', 'Fo', 'Foo'):
			finder.find(text)
			check(0, 0, text.upper())

		finder.find('Grr')
		check(0, 0, '')

		finder.find('Foob')
		check(0, 4, 'FooB')

		for line, offset, text in (
			(0, 11, 'FOOB'),
			(1, 0, 'FooB'),
			(0, 4, 'FooB'),
		):
			finder.find_next()
			check(line, offset, text)

		for line, offset, text in (
			(1, 0, 'FooB'),
			(0, 11, 'FOOB'),
			(0, 4, 'FooB'),
		):
			finder.find_previous()
			check(line, offset, text)

		# Case sensitive
		finder.find('Foo', FIND_CASE_SENSITIVE)
		check(0, 4, 'Foo')

		for line, offset, text in (
			(1, 0, 'Foo'),
			(1, 7, 'Foo'),
			(2, 12, 'Foo'),
			(0, 4, 'Foo'),
		):
			finder.find_next()
			check(line, offset, text)

		# Whole word
		finder.find('Foo', FIND_WHOLE_WORD)
		check(1, 7, 'Foo')

		for line, offset, text in (
			(2, 0, 'foo'),
			(2, 12, 'Foo'),
			(0, 0, 'FOO'),
			(1, 7, 'Foo'),
		):
			finder.find_next()
			check(line, offset, text)

		# Regular expression
		finder.find(r'Foo\s*Bar', FIND_REGEX | FIND_CASE_SENSITIVE)
		check(1, 7, 'Foo Bar')
		finder.find_next()
		check(0, 4, 'FooBar')

		# Highlight - just check it doesn't crash
		finder.set_highlight(True)
		finder.set_highlight(False)

		# Now check replace
		finder.find('Foo(\w*)', FIND_REGEX) # not case sensitive!
		check(0, 4, 'FooBar')

		finder.replace('Dus')
		check(0, 4, 'Dus')
		bounds = buffer.get_bounds()
		text = buffer.get_slice(*bounds)
		wanted = '''\
FOO Dus FOOBAR
FooBaz Foo Bar
foo Bar Baz Foo
'''
		self.assertEqualDiff(text, wanted)

		finder.replace_all('dus*\\1*')
		bounds = buffer.get_bounds()
		text = buffer.get_slice(*bounds)
		wanted = '''\
dus** Dus dus*BAR*
dus*Baz* dus** Bar
dus** Bar Baz dus**
'''
		self.assertEqualDiff(text, wanted)
		self.assertEqual(buffer.get_insert_iter().get_offset(), 6)


class TestLists(TestCase):

	def runTest(self):
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
		tree = get_tree_from_xml(input)
		buffer.set_parsetree(tree)
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), input) # just a sanity check

		undomanager = UndoStackManager(buffer)

		# check list initializes properly
		iter = buffer.get_iter_at_line(3) # Bar 1
		row, list = TextBufferList.new_from_iter(buffer, iter)
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
		iter = buffer.get_iter_at_line(3) # Bar 1
		row, list = TextBufferList.new_from_iter(buffer, iter)
		self.assertFalse(list.can_indent(row))
		self.assertFalse(list.indent(row))

		iter = buffer.get_iter_at_line(2) # Bar
		row, list = TextBufferList.new_from_iter(buffer, iter)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		iter = buffer.get_iter_at_line(7) # Baz
		row, list = TextBufferList.new_from_iter(buffer, iter)
		self.assertFalse(list.can_unindent(row))
		self.assertFalse(list.unindent(row))

		iter = buffer.get_iter_at_line(3) # Bar 1
		row, list = TextBufferList.new_from_iter(buffer, iter)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		for line in (2, 5, 6): # Bar, Bar 2 & Bar 3
			iter = buffer.get_iter_at_line(line)
			row, list = TextBufferList.new_from_iter(buffer, iter)
			self.assertTrue(list.can_unindent(row))
			self.assertTrue(list.unindent(row))

		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), input)

		# Test undo / redo for indenting and lists
		for i in range(3):
			self.assertTrue(undomanager.undo())
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wanted)

		while undomanager.undo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), input)

		while undomanager.redo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), input)

		for i in range(3):
			self.assertTrue(undomanager.undo())
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wanted)


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
		tree = get_tree_from_xml(input)
		buffer.set_parsetree(tree)
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), input) # just a sanity check

		undomanager = UndoStackManager(buffer)


		iter = buffer.get_iter_at_line(2) # Bar
		row, list = TextBufferList.new_from_iter(buffer, iter)
		list.update_checkbox(row, CHECKED_BOX)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		list.update_checkbox(row, UNCHECKED_BOX)
		iter = buffer.get_iter_at_line(3) # Bar 1
		row = list.get_row_from_iter(iter)
		list.update_checkbox(row, XCHECKED_BOX)
		iter = buffer.get_iter_at_line(5) # Bar 2
		row = list.get_row_from_iter(iter)
		list.update_checkbox(row, UNCHECKED_BOX)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		iter = buffer.get_iter_at_line(5) # Bar 2
		row = list.get_row_from_iter(iter)
		list.update_checkbox(row, CHECKED_BOX)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		iter = buffer.get_iter_at_line(4) # Bar 1.1
		row = list.get_row_from_iter(iter)
		list.update_checkbox(row, UNCHECKED_BOX)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		wantedpre1 = wanted
		iter = buffer.get_iter_at_line(4) # Bar 1.1
		row = list.get_row_from_iter(iter)
		list.update_checkbox(row, CHECKED_BOX)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		# Test indenting / unindenting the whole list
		wantedpre = wanted
		iter = buffer.get_iter_at_line(1) # Foo
		row = list.get_row_from_iter(iter)
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
		self.assertEqualDiff(tree.tostring(), wanted)

		list.unindent(row)
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wantedpre)

		# Test undo / redo for indenting and lists
		for xml in (wanted, wantedpre, wantedpre1):
			self.assertTrue(undomanager.undo())
			tree = buffer.get_parsetree(raw=True)
			self.assertEqualDiff(tree.tostring(), xml)

		for xml in (wantedpre, wanted, wantedpre):
			self.assertTrue(undomanager.redo())
			tree = buffer.get_parsetree(raw=True)
			self.assertEqualDiff(tree.tostring(), xml)

		while undomanager.undo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), input)

		while undomanager.redo():
			pass
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wantedpre)


def press(widget, string):
	for char in string:
		event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)
		if char == '\n':
			event.keyval = int( gtk.gdk.keyval_from_name('Return') )
		elif char == '\t':
			event.keyval = int( gtk.gdk.keyval_from_name('Tab') )
		else:
			event.keyval = int( gtk.gdk.unicode_to_keyval(ord(char)) )
		event.string = char
		#gtk.main_do_event(event)
		#assert widget.event(event) # Returns True if event was handled
		#while gtk.events_pending():
		#	gtk.main_iteration()
		widget.emit('key-press-event', event)


class TestTextView(TestCase):

	def setUp(self):
		# Initialize default preferences from module
		self.preferences = {}
		for pref in ui_preferences:
			self.preferences[pref[0]] = pref[-1]

	def runTest(self):
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
		self.assertEqualDiff(tree.tostring(), wanted)

		press(view, '\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="0"> </li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		start, end = buffer.get_bounds()
		self.assertEqualDiff(tree.tostring(), wanted)

		press(view, '\tduss')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wanted)

		press(view, '\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> </li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wanted)

		press(view, 'CamelCase\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>
<li bullet="*" indent="1"> </li></zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wanted)

		press(view, '\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>

</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wanted)

		iter = buffer.get_iter_at_line(1)
		iter.forward_to_line_end() # behind "foo"
		buffer.place_cursor(iter)
		press(view, '\n')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree raw="True">aaa
<li bullet="*" indent="0"> foo</li>
<li bullet="*" indent="1"> </li>
<li bullet="*" indent="1"> duss</li>
<li bullet="*" indent="1"> <link href="CamelCase">CamelCase</link></li>

</zim-tree>'''
		tree = buffer.get_parsetree(raw=True)
		self.assertEqualDiff(tree.tostring(), wanted)


		# TODO unindenting
		# TODO checkboxes
		# TODO Auto formatting of various link types
		# TODO enter on link, before link, after link
