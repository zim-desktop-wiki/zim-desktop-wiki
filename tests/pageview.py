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

<li bullet="*" indent="0">Foo</li>
<li bullet="*" indent="0">Bar</li>
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


#~ def press(widget, char):
	#~ event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)
	#~ event.keyval = int( gtk.gdk.unicode_to_keyval(ord(char)) )
	#~ event.string = char
	#~ widget.event(event)
#~
#~ class TestTextView(TestCase):
#~
	#~ preferences = {
	#~ }
#~
	#~ def runTest(self):
		#~ view = TextView(self.preferences)
		#~ buffer = TextBuffer()
		#~ view.set_buffer(buffer)
		#~ undomanager = UndoStackManager(buffer)
#~
		#~ # Need a window to get the widget realized
		#~ window = gtk.Window()
		#~ window.add(view)
		#~ window.show_all()
#~
		#~ press(view, '*')
		#~ press(view, '\n')
		#~ start, end = buffer.get_bounds()
		#~ self.assertEqual(buffer.get_text(start, end), '*\n')

