# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.formats module.'''

from tests import TestCase

from zim.fs import *
from zim.formats import *

wikitext = u"""\
====== Head1 ======

===== Head 2 =====

Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
aliquip ex ea commodo consequat. Duis aute irure dolor in
reprehenderit in voluptate velit esse cillum dolore eu fugiat
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.

'''
Some Verbatim here

	Indented and all: //foo//
'''

IMAGE: {{../my-image.png|Foo Bar}}
LINKS: [[:foo:bar]] [[./file.png]] [[file:///etc/passwd]]

	Some indented
	paragraphs go here ...

Let's try these **bold**, //italic//, __underline__ and ~~strike~~
And don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_

And some utf8 bullet items
• foo
• bar

• baz

That's all ...
"""

class TestTextFormat(TestCase):

	def setUp(self):
		self.format = get_format('plain')

	def testRoundtrip(self):
		tree = self.format.Parser().parse( Buffer(wikitext) )
		self.assertTrue(isinstance(tree, NodeTree))
		#~ print '\n', tree
		output = Buffer()
		self.format.Dumper().dump(tree, output)
		#~ print '\n', '='*10, '\n', self.format, '\n', '-'*10, '\n', output
		self.assertEqualDiff(output.getvalue(), wikitext)


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
			TextNode('''\
Some Verbatim here

	Indented and all: //foo//
''', style='Verbatim' ),
			TextNode('\n'),
			NodeList( [
				TextNode('IMAGE: '),
				ImageNode('../my-image.png', text='Foo Bar'),
				TextNode('\nLINKS: '),
				LinkNode(':foo:bar', link=':foo:bar'),
				TextNode(' '),
				LinkNode('./file.png', link='./file.png'),
				TextNode(' '),
				LinkNode('file:///etc/passwd', link='file:///etc/passwd'),
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
		self.assertEqualDiff(t.__str__(), tree.__str__())


class TestHtmlFormat(TestCase):

	def setUp(self):
		self.format = get_format('html')

	def testEncoding(self):
		'''Test HTML encoding'''
		text = '<foo>"foo" & "bar"</foo>'
		encode = '&lt;foo&gt;&quot;foo&quot; &amp; &quot;bar&quot;&lt;/foo&gt;'
		tree = NodeTree([ TextNode(text) ])
		html = Buffer()
		self.format.Dumper().dump(tree, html)
		self.assertEqual(html.getvalue(), encode)

	def testExport(self):
		'''Test exporting wiki format to Html'''
		wiki = Buffer(wikitext)
		output = Buffer()
		tree = get_format('wiki').Parser().parse(wiki)
		self.format.Dumper().dump(tree, output)
		html = u'''\
<h1>Head1</h1>
<h2>Head 2</h2>
<p>
Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
aliquip ex ea commodo consequat. Duis aute irure dolor in
reprehenderit in voluptate velit esse cillum dolore eu fugiat
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.
</p>

<pre>
Some Verbatim here

	Indented and all: //foo//
</pre>

<p>
IMAGE: <img src="../my-image.png" alt="Foo Bar">
LINKS: <a href=":foo:bar">:foo:bar</a> <a href="./file.png">./file.png</a> <a href="file:///etc/passwd">file:///etc/passwd</a>
</p>

<p>
	Some indented
	paragraphs go here ...
</p>

<p>
Let's try these <b>bold</b>, <i>italic</i>, <u>underline</u> and <strike>strike</strike>
And don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_
</p>

<p>
And some utf8 bullet items
• foo
• bar
</p>

<p>
• baz
</p>

<p>
That's all ...
</p>
'''
		self.assertEqualDiff(output.getvalue(), html)
