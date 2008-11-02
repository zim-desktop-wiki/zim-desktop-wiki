# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.formats module.'''

from tests import TestCase, get_test_page

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
And some ''//verbatim//''
And don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_

And some utf8 bullet items
• foo
• bar

• baz

----

====

That's all ...
"""

class TestTextFormat(TestCase):

	def setUp(self):
		self.format = get_format('plain')
		self.page = get_test_page()

	def testRoundtrip(self):
		tree = self.format.Parser(self.page).parse( Buffer(wikitext) )
		self.assertTrue(isinstance(tree, ElementTree))
		self.assertTrue(tree.getroot().tag == 'page')
		#~ print '>>>\n'+serialize_tree(tree)+'\n<<<\n'
		output = Buffer()
		self.format.Dumper(self.page).dump(tree, output)
		self.assertEqualDiff(output.getvalue(), wikitext)


class TestWikiFormat(TestTextFormat):

	def setUp(self):
		#~ TestTextFormat.setUp(self)
		self.format = get_format('wiki')
		self.page = get_test_page()

	def testParsing(self):
		'''Test wiki parse tree generation.'''
		tree = u'''\
<?xml version='1.0' encoding='utf8'?>
<page><h level="1">Head1</h>
<h level="2">Head 2</h>
<p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut
aliquip ex ea commodo consequat. Duis aute irure dolor in
reprehenderit in voluptate velit esse cillum dolore eu fugiat
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.
</p>
<pre>Some Verbatim here

	Indented and all: //foo//
</pre>
<p>IMAGE: <img src="../my-image.png">Foo Bar</img>
LINKS: <a href=":foo:bar">:foo:bar</a> <a href="./file.png">./file.png</a> <a href="file:///etc/passwd">file:///etc/passwd</a>
</p>
<p>	Some indented
	paragraphs go here ...
</p>
<p>Let's try these <strong>bold</strong>, <em>italic</em>, <mark>underline</mark> and <strike>strike</strike>
And some <code>//verbatim//</code>
And don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_
</p>
<p>And some utf8 bullet items
• foo
• bar
</p>
<p>• baz
</p>
<p>----
</p>
<p>====
</p>
<p>That's all ...
</p></page>'''
		t = self.format.Parser(self.page).parse( Buffer(wikitext) )
		self.assertEqualDiff(serialize_tree(t), tree)


class TestHtmlFormat(TestCase):

	def setUp(self):
		self.format = get_format('html')
		self.page = get_test_page()

	def testEncoding(self):
		'''Test HTML encoding'''
		page = Element('page')
		para = SubElement(page, 'p')
		para.text = '<foo>"foo" & "bar"</foo>'
		tree = ElementTree(page)
		html = Buffer()
		self.format.Dumper(self.page).dump(tree, html)
		self.assertEqual(html.getvalue(),
			'<p>\n&lt;foo&gt;"foo" &amp; "bar"&lt;/foo&gt;</p>\n' )

	def testExport(self):
		'''Test exporting wiki format to Html'''
		wiki = Buffer(wikitext)
		output = Buffer()
		tree = get_format('wiki').Parser(self.page).parse(wiki)
		self.format.Dumper(self.page).dump(tree, output)
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
Let's try these <strong>bold</strong>, <em>italic</em>, <u>underline</u> and <strike>strike</strike>
And some <code>//verbatim//</code>
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
----
</p>

<p>
====
</p>

<p>
That's all ...
</p>
'''
		self.assertEqualDiff(output.getvalue(), html)
