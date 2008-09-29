# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.formats module.'''

import unittest

from zim.fs import *
import zim.formats

class TestTextFormat(unittest.TestCase):

	def setUp(self):
		self.format = zim.formats.get_format('plain')

	def testRoundtrip(self):
		text='''\
====== Head1 ======

===== Head 2 =====

Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
aliquip ex ea commodo consequat. Duis aute irure dolor in
reprehenderit in voluptate velit esse cillum dolore eu fugiat
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.

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
		tree = self.format.Parser().parse_string(text)
		self.assertTrue( isinstance(tree, zim.formats.NodeTree) )
		#~ print '\n', tree
		output = self.format.Dumper().dump_string(tree)
		#~ print '\n', '='*10, '\n', self.format, '\n', '-'*10, '\n', output
		self.assertEqual(output, text)


class TestWikiFormat(TestTextFormat):

	def setUp(self):
		self.format = zim.formats.get_format('wiki')


#~ class TestHtmlFormat(TestTextFormat):

	#~ def SetUp(self):
		#~ self.format = zim.formats.get_format('html')
