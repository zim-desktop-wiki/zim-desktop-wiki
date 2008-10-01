# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.formats module.'''

import unittest

from zim.fs import *
from zim.formats import *

wikitext = u'''\
====== Head1 ======

===== Head 2 =====

Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
aliquip ex ea commodo consequat. Duis aute irure dolor in
reprehenderit in voluptate velit esse cillum dolore eu fugiat
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.

IMAGE: {{../my-image.png}}

	Some indented
	paragraphs go here ...

Let's try these **bold**, //italic//, __underline__ and ~~strike~~
And don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_

And some utf8 bullet items
• foo
• bar

• baz

That's all ...
'''

class TestTextFormat(unittest.TestCase):

	def setUp(self):
		self.format = get_format('plain')

	def testRoundtrip(self):
		tree = self.format.Parser().parse( Buffer(wikitext) )
		self.assertTrue(isinstance(tree, NodeTree))
		#~ print '\n', tree
		output = Buffer()
		self.format.Dumper().dump(tree, output)
		#~ print '\n', '='*10, '\n', self.format, '\n', '-'*10, '\n', output
		self.assertEqual(output.getvalue(), wikitext)


class TestWikiFormat(TestTextFormat):

	def setUp(self):
		#~ TestTextFormat.setUp(self)
		self.format = get_format('wiki')

	def testParsing(self):
		'''Test wiki parse tree generation.'''
		tree = NodeTree( [
			HeadingNode(1, 'Head1'),
			TextNode('\n'),
			HeadingNode(2, 'Head 2'),
			TextNode('\n'),
			NodeList( [TextNode('''\
Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
aliquip ex ea commodo consequat. Duis aute irure dolor in
reprehenderit in voluptate velit esse cillum dolore eu fugiat
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.
''' )] ),
			TextNode('\n'),
			NodeList( [
				TextNode('IMAGE: '),
				ImageNode(link='../my-image.png'),
				TextNode('\n'),
			] ),
			TextNode('\n'),
			NodeList( [TextNode('''\
	Some indented
	paragraphs go here ...
''' )] ),
			TextNode('\n'),
			NodeList( [
				TextNode('''Let's try these '''),
				TextNode('bold', style='bold'),
				TextNode(', '),
				TextNode('italic', style='italic'),
				TextNode(', '),
				TextNode('underline', style='underline'),
				TextNode(' and '),
				TextNode('strike', style='strike'),
				TextNode('''\nAnd don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_\n'''),
			] ),
			TextNode('\n'),
			NodeList( [
				TextNode(u'''\
And some utf8 bullet items
• foo
• bar
''' ) ] ),
			TextNode('\n'),
			NodeList([ TextNode(u'• baz\n') ]),
			TextNode('\n'),
			NodeList([ TextNode('''That's all ...\n''') ])
		] )
		t = self.format.Parser().parse( Buffer(wikitext) )
		#~ self.diff(t.__str__(), tree.__str__())
		self.assertEqual(t.__str__(), tree.__str__())

	def diff(self, text1, text2):
		'''FIXME'''
		from difflib import Differ
		text1 = text1.splitlines()
		text2 = text2.splitlines()
		for line in Differ().compare(text1, text2):
			print line


class TestHtmlFormat(unittest.TestCase):

	def setUp(self):
		self.format = get_format('html')

	def testHtml(self):
		'''Test HTML encoding'''
		text = '<foo>"foo" & "bar"</foo>'
		encode = '&lt;foo&gt;&quot;foo&quot; &amp; &quot;bar&quot;&lt;/foo&gt;'
		tree = NodeTree([ TextNode(text) ])
		html = Buffer()
		self.format.Dumper().dump(tree, html)
		self.assertEqual(html.getvalue(), encode)

