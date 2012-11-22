# -*- coding: utf-8 -*-

# Copyright 2008-2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.formats module.'''

from __future__ import with_statement


import tests

from zim.formats import *
from zim.fs import File
from zim.notebook import Path, Link
from zim.parsing import link_type
from zim.templates import Template


if not ElementTreeModule.__name__.endswith('cElementTree'):
	print 'WARNING: using ElementTree instead of cElementTree'

wikitext = tests.WikiTestData.get('roundtrip')



class TestFormatMixin(object):
	'''Mixin for testing formats, uses data in C{tests/data/formats/}'''

	reference_xml = File('tests/data/formats/parsetree.xml').read().rstrip('\n')

	reference_data = {
		'wiki': 'wiki.txt',
		'plain': 'plain.txt',
		'html': 'export.html',
		'latex': 'export.tex',
		'markdown': 'export.markdown',
		'reST': 'export.rst',
	}

	def testFormatInfo(self):
		for key in ('name', 'desc', 'mimetype', 'extension'):
			self.assertIsInstance(self.format.info[key], basestring,
				msg='Invalid key "%s" in format info' % key)

		for key in ('native', 'import', 'export'):
			self.assertIsInstance(self.format.info[key], bool,
				msg='Invalid key "%s" in format info' % key)

		if self.format.info['native'] or self.format.info['import']:
			self.assertTrue(hasattr(self.format, 'Parser'))

		if self.format.info['native'] or self.format.info['export']:
			self.assertTrue(hasattr(self.format, 'Dumper'))

	def getReferenceData(self):
		'''Returns reference data from C{tests/data/formats/} for the
		format being tested.
		'''
		name = self.format.info['name']
		assert name in self.reference_data, 'No reference data for format "%s"' % name
		path = 'tests/data/formats/' + self.reference_data[name]
		text = File(path).read()

		# No absolute paths ended up in reference
		pwd = Dir('.')
		self.assertFalse(pwd.path in text, 'Absolute path ended up in reference')
		self.assertFalse(pwd.user_path in text, 'Absolute path ended up in reference')

		return text

	def testFormat(self):
		'''Test if formats supports full syntax
		Uses data in C{tests/data/formats} as reference data.
		'''
		# Dumper
		wanted = self.getReferenceData()
		reftree = tests.new_parsetree_from_xml(self.reference_xml)
		linker = StubLinker()
		linker.set_base(Dir('tests/data/formats'))
		dumper = self.format.Dumper(linker=linker)
		result = ''.join(dumper.dump(reftree))
		#~ print '\n' + '>'*80 + '\n' + result + '\n' + '<'*80 + '\n'
		self.assertMultiLineEqual(result, wanted)
		self.assertNoTextMissing(result, reftree)

		# partial dumper
		parttree = tests.new_parsetree_from_xml("<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial=\"True\">try these <strong>bold</strong>, <emphasis>italic</emphasis></zim-tree>")
		result = ''.join(dumper.dump(parttree))
		#~ print ">>>%s<<<" % result
		self.assertFalse(result.endswith('\n')) # partial should not end with "\n"

		# Parser
		if not hasattr(self.format, 'Parser'):
			return
		input = wanted
		parser = self.format.Parser()
		result = parser.parse(input)
		if self.format.info['native']:
			self.assertMultiLineEqual(result.tostring(), self.reference_xml)
		else:
			self.assertTrue(len(result.tostring().splitlines()) > 10)
				# Quick check that we got back *something*
			string = ''.join(dumper.dump(result))
				# now we may have loss of formatting, but text should all be there
				#~ print '\n' + '>'*80 + '\n' + string + '\n' + '<'*80 + '\n'
			self.assertNoTextMissing(string, reftree)

	_nonalpha_re = re.compile('\W')

	def assertNoTextMissing(self, text, tree):
		'''Assert that no plain text from C{tree} is missing in C{text}
		intended to make sure that even for lossy formats all information
		is preserved.
		'''
		# TODO how to handle objects ??
		assert isinstance(text, basestring)
		offset = 0
		for elt in tree.iter():
			if elt.tag == 'img':
				elttext = (elt.tail) # img text is optional
			else:
				elttext = (elt.text, elt.tail)

			for wanted in elttext:
				if not wanted:
					continue

				wanted = self._nonalpha_re.sub(' ', wanted)
					# Non-alpha chars may be replaced with escapes
					# so no way to hard test them

				if wanted.isspace():
					continue

				for piece in wanted.strip().split():
					#~ print "| >>%s<< @ offset %i" % (piece, offset)
					try:
						start = text.index(piece, offset)
					except ValueError:
						self.fail('Could not find text piece "%s" in text after offset %i\n>>>%s<<<' % (piece, offset, text[offset:offset+100]))
					else:
						offset = start + len(piece)



class TestListFormats(tests.TestCase):

	def runTest(self):
		for desc in list_formats(EXPORT_FORMAT):
			name = canonical_name(desc)
			format = get_format(name)
			self.assertTrue(format.info['export'])

		for desc in list_formats(TEXT_FORMAT):
			name = canonical_name(desc)
			format = get_format(name)
			self.assertTrue(format.info['export'])
			self.assertTrue(format.info['mimetype'].startswith('text/'))


class TestParseTree(tests.TestCase):

	def setUp(self):
		self.xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<h level="1">Head 1</h>
<h level="2">Head 2</h>
<h level="3">Head 3</h>
<h level="2">Head 4</h>
<h level="5">Head 5</h>
<h level="4">Head 6</h>
<h level="5">Head 7</h>
<h level="6">Head 8</h>
</zim-tree>'''

	def teststring(self):
		'''Test ParseTree.fromstring() and .tostring()'''
		tree = ParseTree()
		r = tree.fromstring(self.xml)
		self.assertEqual(id(r), id(tree)) # check return value
		e = tree.getroot()
		self.assertEqual(e.tag, 'zim-tree') # check content
		text = tree.tostring()
		self.assertEqual(text, self.xml)

	def testcleanup_headings(self):
		'''Test ParseTree.cleanup_headings()'''
		tree = ParseTree().fromstring(self.xml)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<h level="2">Head 1</h>
<h level="3">Head 2</h>
<h level="4">Head 3</h>
<h level="3">Head 4</h>
<h level="4">Head 5</h>
<h level="4">Head 6</h>
<h level="4">Head 7</h>
<h level="4">Head 8</h>
</zim-tree>'''
		tree.cleanup_headings(offset=1, max=4)
		text = tree.tostring()
		self.assertEqual(text, wanted)

	def testGetHeading(self):
		'''Test that ParseTree.get_heading() returns the first header's text.
		'''
		tree = ParseTree().fromstring(self.xml)
		self.assertEqual(tree.get_heading(), "Head 1")

	def testSetHeading(self):
		'''Test ParseTree.set_heading()'''
		tree = ParseTree().fromstring(self.xml)
		tree.set_heading('Foo')
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<h level="1">Foo</h>
<h level="2">Head 2</h>
<h level="3">Head 3</h>
<h level="2">Head 4</h>
<h level="5">Head 5</h>
<h level="4">Head 6</h>
<h level="5">Head 7</h>
<h level="6">Head 8</h>
</zim-tree>'''
		text = tree.tostring()
		self.assertEqual(text, wanted)

	def testExtend(self):
		tree1 = ParseTree().fromstring(self.xml)
		tree2 = ParseTree().fromstring(self.xml)
		tree = tree1 + tree2
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<h level="1">Head 1</h>
<h level="2">Head 2</h>
<h level="3">Head 3</h>
<h level="2">Head 4</h>
<h level="5">Head 5</h>
<h level="4">Head 6</h>
<h level="5">Head 7</h>
<h level="6">Head 8</h>

<h level="1">Head 1</h>
<h level="2">Head 2</h>
<h level="3">Head 3</h>
<h level="2">Head 4</h>
<h level="5">Head 5</h>
<h level="4">Head 6</h>
<h level="5">Head 7</h>
<h level="6">Head 8</h>
</zim-tree>'''
		text = tree.tostring()
		self.assertEqual(text, wanted)


	def testGetEndsWithNewline(self):
		for xml, newline in (
			('<zim-tree partial="True">foo</zim-tree>', False),
			('<zim-tree partial="True"><strong>foo</strong></zim-tree>', False),
			('<zim-tree partial="True"><strong>foo</strong>\n</zim-tree>', True),
			('<zim-tree partial="True"><strong>foo\n</strong></zim-tree>', True),
			('<zim-tree partial="True"><strong>foo</strong>\n<img src="foo"></img></zim-tree>', False),
			('<zim-tree partial="True"><li bullet="unchecked-box" indent="0">foo</li></zim-tree>', True),
			('<zim-tree partial="True"><li bullet="unchecked-box" indent="0"><strong>foo</strong></li></zim-tree>', True),
			('<zim-tree partial="True"><li bullet="unchecked-box" indent="0"><strong>foo</strong></li></zim-tree>', True),
		):
			tree = ParseTree().fromstring(xml)
			self.assertEqual(tree.get_ends_with_newline(), newline)


class TestTextFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('plain')


class TestWikiFormat(TestTextFormat):

	def setUp(self):
		self.format = get_format('wiki')
		notebook = tests.new_notebook()
		self.page = notebook.get_page(Path('Foo'))

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
		#~ self.assertEqual(output, text.splitlines(True))

	def testUnicodeBullet(self):
		'''Test support for unicode bullets in source'''
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
		self.assertEqual(output, text.splitlines(True))

	def testLink(self):
		'''Test iterator function for link'''
		# + check for bugs in link encoding
		text = '[[FooBar]] [[Foo|]] [[|Foo]]'
		tree = self.format.Parser().parse(text)
		for i, tag in enumerate(tree.getiterator('link')):
			self.assertTrue(tag.text)
			self.assertTrue(tag.attrib.get('href'))
			link = Link(self.page, **tag.attrib)
			self.assertEqual(tag.attrib['href'], link.href)
			done = True
		self.assertEqual(i, 2)

	def testBackward(self):
		'''Test backward compatibility for wiki format'''
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
<zim-tree><p>test 1 2 3
</p>
<pre>	Some Verbatim block
	here ....
</pre>
<p>test 4 5 6
</p></zim-tree>'''
		t = self.format.Parser(version='Unknown').parse(input)
		self.assertEqual(t.tostring(), xml)
		output = self.format.Dumper().dump(t)
		self.assertEqual(output, wanted.splitlines(True))

	def testList(self):
		def check(text, xml, wanted=None):
			if wanted is None:
				wanted = text

			tree = self.format.Parser().parse(text)
			#~ print '>>>\n' + tree.tostring() + '\n<<<'
			self.assertEqual(tree.tostring(), xml)

			lines = self.format.Dumper().dump(tree)
			result = ''.join(lines)
			#~ print '>>>\n' + result + '<<<'
			self.assertEqual(result, wanted)


		# Bullet list (unordered list)
		text = '''\
* foo
* bar
	* sub list
	* here
* hmmm
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul><li bullet="*">foo</li><li bullet="*">bar</li><ul><li bullet="*">sub list</li><li bullet="*">here</li></ul><li bullet="*">hmmm</li></ul></p></zim-tree>'''
		check(text, xml)

		# Numbered list (ordered list)
		text = '''\
1. foo
2. bar
	a. sub list
	b. here
3. hmmm
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ol start="1"><li>foo</li><li>bar</li><ol start="a"><li>sub list</li><li>here</li></ol><li>hmmm</li></ol></p></zim-tree>'''
		check(text, xml)

		text = '''\
A. foo
B. bar
C. hmmm
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ol start="A"><li>foo</li><li>bar</li><li>hmmm</li></ol></p></zim-tree>'''
		check(text, xml)

		text = '''\
10. foo
11. bar
12. hmmm
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ol start="10"><li>foo</li><li>bar</li><li>hmmm</li></ol></p></zim-tree>'''
		check(text, xml)


		# Inconsistent lists
		# ( If first item is number, make all items numbered in sequence
		#   Otherwise numers will be turned into bullets )
		text = '''\
1. foo
4. bar
* hmmm
a. dus
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ol start="1"><li>foo</li><li>bar</li><li>hmmm</li><li>dus</li></ol></p></zim-tree>'''
		wanted = '''\
1. foo
2. bar
3. hmmm
4. dus
'''
		check(text, xml, wanted)

		text = '''\
* foo
4. bar
a. hmmm
* dus
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul><li bullet="*">foo</li><li bullet="*">bar</li><li bullet="*">hmmm</li><li bullet="*">dus</li></ul></p></zim-tree>'''
		wanted = '''\
* foo
* bar
* hmmm
* dus
'''
		check(text, xml, wanted)

		# Mixed sub-list
		text = '''\
* foo
* bar
	1. sub list
	2. here
* hmmm
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul><li bullet="*">foo</li><li bullet="*">bar</li><ol start="1"><li>sub list</li><li>here</li></ol><li bullet="*">hmmm</li></ul></p></zim-tree>'''
		check(text, xml)

		# Indented list
		text = '''\
	* foo
	* bar
		1. sub list
		2. here
	* hmmm
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul indent="1"><li bullet="*">foo</li><li bullet="*">bar</li><ol start="1"><li>sub list</li><li>here</li></ol><li bullet="*">hmmm</li></ul></p></zim-tree>'''
		check(text, xml)

		# Double indent sub-list ?
		text = '''\
* foo
* bar
		1. sub list
		2. here
* hmmm
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul><li bullet="*">foo</li><li bullet="*">bar</li><ol start="1"><ol start="1"><li>sub list</li><li>here</li></ol></ol><li bullet="*">hmmm</li></ul></p></zim-tree>'''
		check(text, xml)

		# This is not a list
		text = '''\
foo.
dus ja.
1.3
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>foo.
dus ja.
1.3
</p></zim-tree>'''
		check(text, xml)


	def testIndent(self):
		# Test some odditied pageview can give us
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><div indent="0">foo</div>
<div indent="0">bar</div>
<div indent="1">sub list</div>
<div indent="1">here</div>
<div indent="0">hmmm</div>
</zim-tree>'''
		wanted = '''\
foo
bar
	sub list
	here
hmmm
'''
		tree = ParseTree()
		tree.fromstring(xml)
		text = ''.join( self.format.Dumper().dump(tree) )
		self.assertEqual(text, wanted)


class TestHtmlFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('html')
		notebook = tests.new_notebook()
		self.page = notebook.get_page(Path('Foo'))

	def testEncoding(self):
		'''Test HTML encoding'''
		page = Element('zim-tree')
		para = SubElement(page, 'p')
		para.text = '<foo>"foo" & "bar"</foo>'
		tree = ParseTree(page)
		html = self.format.Dumper(linker=StubLinker()).dump(tree)
		self.assertEqual(html,
			['<p>\n', '&lt;foo&gt;"foo" &amp; "bar"&lt;/foo&gt;</p>\n'] )

	# TODO add test using http://validator.w3.org

class TestMarkdownFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('markdown')


class TestRstFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('rst')


class LatexLoggingFilter(tests.LoggingFilter):

	logger = 'zim.formats.latex'
	message = ('No document type set in template', 'Could not find latex equation')


class TestLatexFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('latex')

	def testFormat(self):
		with LatexLoggingFilter():
			TestFormatMixin.testFormat(self)

	def testFormatReference(self):
		# Double check reference did not get broken in updating
		text = self.getReferenceData()

		# Inlined equation is there
		self.assertFalse('equation001.png' in text, 'This equation should be inlined')
		self.assertTrue(r'\begin{math}' in text)
		self.assertTrue(r'\end{math}' in text)

	def testEncode(self):
		'''test the escaping of certain characters'''
		format = get_format('latex')

		input = r'\foo $ % ^ \% bar < >'
		wanted = r'$\backslash$foo \$  \% \^{} $\backslash$\% bar \textless{} \textgreater{}'
		self.assertEqual(format.tex_encode(input), wanted)

	def testExport(self):
		'''test the export of a wiki page to latex'''
		with LatexLoggingFilter():
			format = get_format('LaTeX')
			testpage = tests.WikiTestData.get('Test:wiki')
			tree = get_format('wiki').Parser().parse(testpage)
			output = format.Dumper(linker=StubLinker()).dump(tree)
			#~ print '>>>\n' + ''.join(output) + '<<<'
			self.assertTrue('\chapter{Foo Bar}\n' in output)

		# Test template_options.document_type
		input = r'''
[% options.document_type = 'book' -%]
\title{[% page.basename %]}

\begin{document}
\maketitle
\tableofcontents
[% page.body %]
\end{document}
'''
		wanted = r'''
\title{FooBar}

\begin{document}
\maketitle
\tableofcontents
\textbf{foo bar !}



\chapter{Heading 2}

duss


\end{document}
'''

		notebook = tests.new_notebook()
		page = notebook.get_page(Path('FooBar'))
		page.parse('wiki', '''\
====== Page Heading ======
**foo bar !**

===== Heading 2 =====
duss
''')

		template = Template(input, 'latex', linker=StubLinker())
		result = template.process(notebook, page)
		self.assertEqual(''.join(result), wanted)


class TestParseTreeBuilder(tests.TestCase):

	def runTest(self):
		'''Test ParseTreeBuilder class'''
		# - Test \n before and after h / p / pre
		# - Test break line into lines
		input = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
foo<h level="1">bar</h>baz

dus<pre>ja</pre>hmm

<h level="2">foo
</h>bar

dus ja <emphasis>hmm
dus ja
</emphasis>grrr

<strong>foo

bar
</strong>
<strike></strike><emphasis>   </emphasis>.
</zim-tree>'''

		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
foo

<h level="1">bar</h>
baz

dus
<pre>ja
</pre>hmm

<h level="2">foo</h>
bar

dus ja <emphasis>hmm</emphasis>
<emphasis>dus ja</emphasis>
grrr

<strong>foo</strong>

<strong>bar</strong>

   .
</zim-tree>'''

		# For some reason this does not work with cElementTree.XMLBuilder ...
		from xml.etree.ElementTree import XMLTreeBuilder
		builder = XMLTreeBuilder(target=ParseTreeBuilder())
		builder.feed(input)
		root = builder.close()
		tree = ParseTree(root)
		self.assertEqual(tree.tostring(), wanted)
