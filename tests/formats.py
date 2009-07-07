# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.formats module.'''

from tests import TestCase, get_test_page, get_test_data

from zim.formats import *
from zim.notebook import Link
from zim.parsing import link_type

if not ElementTreeModule.__name__.endswith('cElementTree'):
	print 'WARNING: using ElementTree instead of cElementTree'

wikitext = get_test_data('notebook-wiki/roundtrip.txt')

class TestParseTree(TestCase):

	def setUp(self):
		self.xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<page>
<h level="1">Head 1</h>
<h level="2">Head 2</h>
<h level="3">Head 3</h>
<h level="2">Head 4</h>
<h level="5">Head 5</h>
<h level="4">Head 6</h>
<h level="5">Head 7</h>
<h level="6">Head 8</h>
</page>'''

	def teststring(self):
		'''Test ParseTree.fromstring() and .tostring()'''
		tree = ParseTree()
		r = tree.fromstring(self.xml)
		self.assertEqual(id(r), id(tree)) # check return value
		e = tree.getroot()
		self.assertEqual(e.tag, 'page') # check content
		text = tree.tostring()
		self.assertEqualDiff(text, self.xml)

	def testcleanup_headings(self):
		'''Test ParseTree.cleanup_headings()'''
		tree = ParseTree().fromstring(self.xml)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<page>
<h level="2">Head 1</h>
<h level="3">Head 2</h>
<h level="4">Head 3</h>
<h level="3">Head 4</h>
<h level="4">Head 5</h>
<h level="4">Head 6</h>
<h level="4">Head 7</h>
<h level="4">Head 8</h>
</page>'''
		tree.cleanup_headings(offset=1, max=4)
		text = tree.tostring()
		self.assertEqualDiff(text, wanted)

	def testSetHeading(self):
		'''Test ParseTree.set_heading()'''
		tree = ParseTree().fromstring(self.xml)
		tree.set_heading('Foo')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<page>
<h level="1">Foo</h>
<h level="2">Head 2</h>
<h level="3">Head 3</h>
<h level="2">Head 4</h>
<h level="5">Head 5</h>
<h level="4">Head 6</h>
<h level="5">Head 7</h>
<h level="6">Head 8</h>
</page>'''
		text = tree.tostring()
		self.assertEqualDiff(text, wanted)

class TestTextFormat(TestCase):

	def setUp(self):
		self.format = get_format('plain')
		notebook, self.page = get_test_page()

	def testRoundtrip(self):
		# First using file interface
		tree = self.format.Parser().parse(wikitext)
		self.assertTrue(isinstance(tree, ParseTree))
		self.assertTrue(tree.getroot().tag == 'page')
		#~ print '>>>\n'+tree.tostring()+'\n<<<\n'
		output = self.format.Dumper().dump(tree)
		self.assertEqualDiff(output, wikitext.splitlines(True))

		# Next the same test usiing string interface
		tree = self.format.Parser().parse(wikitext)
		self.assertTrue(isinstance(tree, ParseTree))
		self.assertTrue(tree.getroot().tag == 'page')
		#~ print '>>>\n'+tree.tostring()+'\n<<<\n'
		output = self.format.Dumper().dump(tree)
		self.assertEqualDiff(output, wikitext.splitlines(True))


class TestWikiFormat(TestTextFormat):

	def setUp(self):
		#~ TestTextFormat.setUp(self)
		self.format = get_format('wiki')
		notebook, self.page = get_test_page()

	#~ def testHeaders(self):
		#~ text = '''\
#~ Content-Type: text/x-zim-wiki
#~ Wiki-Format: zim 0.26
#~ Creation-Date: Unkown
#~ Modification-Date: Wed, 06 Aug 2008 22:17:29 +0200
#~
#~ foo bar
#~ '''
		#~ tree = self.format.Parser().parse(text)
		#~ print '>>>\n'+tostring(tree)+'\n<<<\n'
		#~ self.assertEquals(tree.getroot().attrib['Content-Type'], 'text/x-zim-wiki')
		#~ output = self.format.Dumper().dump(tree)
		#~ self.assertEqualDiff(output, text.splitlines(True))

	def testParsing(self):
		'''Test wiki parse tree generation.'''
		tree = '''\
<?xml version='1.0' encoding='utf-8'?>
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
<p>IMAGE: <img src="../my-image.png" width="600">Foo Bar</img>
LINKS: <link href=":foo:bar">:foo:bar</link> <link href="./file.png">./file.png</link> <link href="file:///etc/passwd">file:///etc/passwd</link>
LINKS: <link href="Foo">Foo</link><link href="Bar">Bar</link>
</p>
<p>	Some indented
	paragraphs go here ...
</p>


<p>Let's try these <strong>bold</strong>, <emphasis>italic</emphasis>, <mark>underline</mark> and <strike>strike</strike>
And some <code>//verbatim//</code>
And don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_
</p>
<p>A list
<ul><li bullet="*">foo</li><ul><li bullet="*">bar</li><li bullet="*">baz</li></ul></ul></p>
<p>And a checkbox list
<ul><li bullet="unchecked-box">item 1</li><ul><li bullet="checked-box">sub item 1</li><ul><li bullet="*">Some normal bullet</li></ul><li bullet="xchecked-box">sub item 2</li><li bullet="unchecked-box">sub item 3</li></ul><li bullet="unchecked-box">item 2</li><li bullet="unchecked-box">item 3</li><ul><li bullet="xchecked-box">item FOOOOOO !</li></ul></ul></p>
<p>----
</p>
<p>====
This is not a header
</p>
<p>That's all ...
</p></page>'''
		t = self.format.Parser().parse(wikitext)
		self.assertEqualDiff(t.tostring(), tree)


	def testUnicodeBullet(self):
		input = u'''\
A list
• foo
	• bar
	• baz
'''
		text = u'''\
A list
* foo
	* bar
	* baz
'''
		tree = self.format.Parser().parse(input)
		output = self.format.Dumper().dump(tree)
		self.assertEqualDiff(output, text.splitlines(True))

	def testLink(self):
		text = '[[FooBar]]' # FIXME add link type
		tree = self.format.Parser().parse(text)
		done = False
		for tag in tree.getiterator('link'):
			link = Link(self.page, **tag.attrib)
			self.assertEqual(tag.attrib['href'], link.href)
			done = True
		self.assertTrue(done)

	def testBackward(self):
		input = u'''\
test 1 2 3

	Some Verbatim block
	here ....

test 4 5 6
'''
		wanted = u'''\
test 1 2 3

\'''
	Some Verbatim block
	here ....
\'''

test 4 5 6
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<page><p>test 1 2 3
</p>
<pre>	Some Verbatim block
	here ....
</pre>
<p>test 4 5 6
</p></page>'''
		t = self.format.Parser(version='Unknown').parse(input)
		self.assertEqualDiff(t.tostring(), xml)
		output = self.format.Dumper().dump(t)
		self.assertEqualDiff(output, wanted.splitlines(True))

class TestHtmlFormat(TestCase):

	def setUp(self):
		self.format = get_format('html')
		notebook, self.page = get_test_page()

	def testEncoding(self):
		'''Test HTML encoding'''
		page = Element('page')
		para = SubElement(page, 'p')
		para.text = '<foo>"foo" & "bar"</foo>'
		tree = ParseTree(page)
		html = self.format.Dumper(linker=StubLinker()).dump(tree)
		self.assertEqual(html,
			['<p>\n', '&lt;foo&gt;"foo" &amp; "bar"&lt;/foo&gt;</p>\n'] )

	def testExport(self):
		'''Test exporting wiki format to Html'''

		from zim.config import data_file
		tree = get_format('wiki').Parser().parse(wikitext)
		output = self.format.Dumper(linker=StubLinker()).dump(tree)

		# Note '%' is doubled to '%%' because of format substitution being used
		html = u'''\
<h1>Head1</h1>

<h2>Head 2</h2>

<p>
Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do<br>
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim<br>
ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut<br>
aliquip ex ea commodo consequat. Duis aute irure dolor in<br>
reprehenderit in voluptate velit esse cillum dolore eu fugiat<br>
nulla pariatur.  Excepteur sint occaecat cupidatat non proident,<br>
sunt in culpa qui officia deserunt mollit anim id est laborum.<br>
</p>

<pre>
Some Verbatim here

	Indented and all: //foo//
</pre>

<p>
IMAGE: <img src="img://../my-image.png" alt="Foo Bar" width="600"><br>
LINKS: <a href="page://:foo:bar">:foo:bar</a> <a href="file://./file.png">./file.png</a> <a href="file://file:///etc/passwd">file:///etc/passwd</a><br>
LINKS: <a href="page://Foo">Foo</a><a href="page://Bar">Bar</a><br>
</p>

<p>
&nbsp;&nbsp;&nbsp;&nbsp;Some indented<br>
&nbsp;&nbsp;&nbsp;&nbsp;paragraphs go here ...<br>
</p>



<p>
Let's try these <strong>bold</strong>, <em>italic</em>, <u>underline</u> and <strike>strike</strike><br>
And some <code>//verbatim//</code><br>
And don't forget these: *bold*, /italic/ / * *^%#@#$#!@)_!)_<br>
</p>

<p>
A list<br>
<ul>
<li>foo</li>
<ul>
<li>bar</li>
<li>baz</li>
</ul>
</ul>
</p>

<p>
And a checkbox list<br>
<ul>
<li style="list-style-image: url(icon://unchecked-box)">item 1</li>
<ul>
<li style="list-style-image: url(icon://checked-box)">sub item 1</li>
<ul>
<li>Some normal bullet</li>
</ul>
<li style="list-style-image: url(icon://xchecked-box)">sub item 2</li>
<li style="list-style-image: url(icon://unchecked-box)">sub item 3</li>
</ul>
<li style="list-style-image: url(icon://unchecked-box)">item 2</li>
<li style="list-style-image: url(icon://unchecked-box)">item 3</li>
<ul>
<li style="list-style-image: url(icon://xchecked-box)">item FOOOOOO !</li>
</ul>
</ul>
</p>

<p>
----<br>
</p>

<p>
====<br>
This is not a header<br>
</p>

<p>
That's all ...<br>
</p>
'''
		self.assertEqualDiff(output, html.splitlines(True))


class StubLinker(object):

	def link(self, link): return '%s://%s' % (link_type(link), link)

	def img(self, src): return 'img://' + src

	def icon(self, name): return 'icon://' + name
