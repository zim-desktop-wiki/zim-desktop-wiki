
# Copyright 2008-2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.formats module.'''




import tests

from zim.formats import *
from zim.fs import File
from zim.notebook import Path
from zim.parsing import link_type
from zim.templates import Template

from xml.etree.ElementTree import ElementTree, Element


if not ElementTreeModule.__name__.endswith('cElementTree'):
	print('WARNING: using ElementTree instead of cElementTree')


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
			self.assertIsInstance(self.format.info[key], str,
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
		if pwd.user_path is not None:
			self.assertFalse(pwd.user_path in text, 'Absolute path ended up in reference')

		return text

	def testFormat(self):
		'''Test if formats supports full syntax
		Uses data in C{tests/data/formats} as reference data.
		'''
		# Dumper
		wanted = self.getReferenceData()
		reftree = tests.new_parsetree_from_xml(self.reference_xml)
		linker = StubLinker(Dir('tests/data/formats'))
		dumper = self.format.Dumper(linker=linker)
		result = ''.join(dumper.dump(reftree))
		#~ print('\n' + '>'*80 + '\n' + result + '\n' + '<'*80 + '\n')
		self.assertMultiLineEqual(result, wanted)
		#import ipdb; ipdb.set_trace()
		self.assertNoTextMissing(result, reftree)

		# Check that dumper did not modify the tree
		self.assertMultiLineEqual(reftree.tostring(), self.reference_xml)

		# partial dumper
		parttree = tests.new_parsetree_from_xml("<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial=\"True\">try these <strong>bold</strong>, <emphasis>italic</emphasis></zim-tree>")
		result = ''.join(dumper.dump(parttree))
		#~ print(">>>%s<<<" % result)
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
				#~ print('\n' + '>'*80 + '\n' + string + '\n' + '<'*80 + '\n')
			self.assertNoTextMissing(string, reftree)

	_nonalpha_re = re.compile('\W')

	def assertNoTextMissing(self, text, tree):
		'''Assert that no plain text from C{tree} is missing in C{text}
		intended to make sure that even for lossy formats all information
		is preserved.
		'''
		# TODO how to handle objects ??
		assert isinstance(text, str)

		def check_text(wanted):
			if not wanted:
				return

			wanted = self._nonalpha_re.sub(' ', wanted)
			# Non-alpha chars may be replaced with escapes
			# so no way to hard test them

			if wanted.isspace():
				return

			for piece in wanted.strip().split():
				# ~ print("| >>%s<< @ offset %i" % (piece, offset))
				try:
					start = text.index(piece, self.offset)
				except ValueError:
					self.fail('Could not find text piece "%s" in text after offset %i\n>>>%s<<<' % (
						piece, self.offset, text[self.offset:self.offset + 100]))
				else:
					self.offset = start + len(piece)

		def loop_tree(tree):  # parse elements one by one, in-depth
			if type(tree) is Element:
				if tree.text and tree.tag != "img":  # img text is optional
					check_text(tree.text)

			for elt in tree.findall("*"):  # if that's a tree or a parent element, dive further
				loop_tree(elt)

			if type(tree) is Element:
				check_text(tree.tail)

		self.offset = 0
		loop_tree(tree._etree)



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

	def testGetHeadingText(self):
		tree = ParseTree().fromstring(self.xml)
		self.assertEqual(tree.get_heading_text(), "Head 1")

	def testGetHeadingTextNestedFormat(self):
		xml = '''<?xml version='1.0' encoding='utf-8'?>
		<zim-tree>
		<h level="1">Head 1 <strong>BOLD</strong> <link>URL</link></h>
		<h level="2">Head 2</h>
		</zim-tree>
		'''
		tree = ParseTree().fromstring(xml)
		self.assertEqual(tree.get_heading_text(), "Head 1 BOLD URL")

	def testSetHeadingText(self):
		tree = ParseTree().fromstring(self.xml)
		tree.set_heading_text('Foo')
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

	def testFindall(self):
		tree = ParseTree().fromstring(self.xml)
		wanted = [
			(1, 'Head 1'),
			(2, 'Head 2'),
			(3, 'Head 3'),
			(2, 'Head 4'),
			(5, 'Head 5'),
			(4, 'Head 6'),
			(5, 'Head 7'),
			(6, 'Head 8'),
		]
		found = []
		for elt in tree.findall(HEADING):
			found.append((int(elt.get('level')), elt.gettext()))
		self.assertEqual(found, wanted)

	def testReplace(self):
		def replace(elt):
			# level 2 becomes 3
			# level 3 is replaced by text
			# level 4 is removed
			# level 5 is skipped
			# level 1 and 6 stay as is
			level = int(elt.get('level'))
			if level == 2:
				elt.attrib['level'] = 3
				return elt
			elif level == 3:
				return DocumentFragment(*elt)
			elif level == 4:
				return None
			elif level == 5:
				raise VisitorSkip
			else:
				return elt
		tree = ParseTree().fromstring(self.xml)
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree>
<h level="1">Head 1</h>
<h level="3">Head 2</h>
Head 3
<h level="3">Head 4</h>
<h level="5">Head 5</h>

<h level="5">Head 7</h>
<h level="6">Head 8</h>
</zim-tree>'''
		tree.replace(HEADING, replace)
		text = tree.tostring()
		self.assertEqual(text, wanted)


class TestTextFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('plain')


class TestWikiFormat(TestTextFormat):

	def setUp(self):
		self.format = get_format('wiki')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		self.page = notebook.get_page(Path('Foo'))

	def testFormattingBelowHeading(self):
		input = "====== heading @foo **bold** ======\n"
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><h level="1">heading <tag name="foo">@foo</tag> <strong>bold</strong></h>\n</zim-tree>'''
		t = self.format.Parser().parse(input)
		self.assertEqual(t.tostring(), xml)
		output = self.format.Dumper().dump(t)
		self.assertEqual(output, input.splitlines(True))

	def testNoNestingBelowVerbatim(self):
		input = "test 1 2 3 ''code here **not bold!**''\n"
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>test 1 2 3 <code>code here **not bold!**</code>\n</p></zim-tree>'''
		t = self.format.Parser().parse(input)
		self.assertEqual(t.tostring(), xml)

	def testUnicodeBullet(self):
		'''Test support for unicode bullets in source'''
		input = '''\
A list
• foo
	• bar
	• baz
'''
		text = '''\
A list
* foo
	* bar
	* baz
'''
		tree = self.format.Parser().parse(input)
		#~ print tree.tostring()
		output = self.format.Dumper().dump(tree)
		self.assertEqual(''.join(output), text)

	def testLink(self):
		'''Test iterator function for link'''
		# + check for bugs in link encoding
		text = '[[FooBar]] [[Foo|]] [[|Foo]] [[||]]'
		tree = self.format.Parser().parse(text)
		#~ print tree.tostring()
		found = 0
		for elt in tree.findall(LINK):
			self.assertTrue(elt.gettext())
			self.assertTrue(elt.get('href'))
			found += 1
		self.assertEqual(found, 3)

	def testNoURLWithinLink(self):
		# Ensure nested URL is not parsed
		text = '[[http://link.com/23060.html|//http://link.com/23060.html//]]'
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><link href="http://link.com/23060.html"><emphasis>http://link.com/23060.html</emphasis></link>
</p></zim-tree>'''
		tree = self.format.Parser().parse(text)
		self.assertEqual(tree.tostring(), xml)

	def testBackwardVerbatim(self):
		'''Test backward compatibility for wiki format'''
		input = '''\
test 1 2 3

	Some Verbatim block
	here ....

test 4 5 6
'''
		wanted = '''\
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

	def testBackwardURLParsing(self):
		input = 'Old link: http://///foo.com\n'
		wanted = 'Old link: [[http://///foo.com]]\n'
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>Old link: <link href="http://///foo.com">http://///foo.com</link>
</p></zim-tree>'''

		t = self.format.Parser(version='zim 0.4').parse(input)
		self.assertEqual(t.tostring(), xml)
		output = self.format.Dumper().dump(t)
		self.assertEqual(output, wanted.splitlines(True))

	def testList(self):
		def check(text, xml, wanted=None):
			if wanted is None:
				wanted = text

			tree = self.format.Parser().parse(text)
			#~ print('>>>\n' + tree.tostring() + '\n<<<')
			self.assertEqual(tree.tostring(), xml)

			lines = self.format.Dumper().dump(tree)
			result = ''.join(lines)
			#~ print('>>>\n' + result + '<<<')
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


		# Incosistent list with different checkbox types
		text = '''\
* foo
[ ] bar
* dus
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ul><li bullet="*">foo</li><li bullet="unchecked-box">bar</li><li bullet="*">dus</li></ul></p></zim-tree>'''
		wanted = '''\
* foo
[ ] bar
* dus
'''
		check(text, xml, wanted)

		# Inconsistent lists get broken in multiple lists
		text = '''\
1. foo
4. bar
* hmmm
a. dus
'''
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><ol start="1"><li>foo</li><li>bar</li></ol><ul><li bullet="*">hmmm</li></ul><ol start="a"><li>dus</li></ol></p></zim-tree>'''
		wanted = '''\
1. foo
2. bar
* hmmm
a. dus
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
<zim-tree><p><ul><li bullet="*">foo</li></ul><ol start="4"><li>bar</li><li>hmmm</li></ol><ul><li bullet="*">dus</li></ul></p></zim-tree>'''
		wanted = '''\
* foo
4. bar
5. hmmm
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
		text = ''.join(self.format.Dumper().dump(tree))
		self.assertEqual(text, wanted)

	def testStringEscapeDoesNotGetEvaluated(self):
		text = "this is not a newline: \\name\n This is not a tab: \\tab \n"
		tree = self.format.Parser().parse(text)
		#~ print tree.tostring()
		output = self.format.Dumper().dump(tree)
		self.assertEqual(''.join(output), text)

	def testGFMAutolinks(self):
		text = 'Test 123 www.google.com/search?q=Markup+(business))) 456'
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>Test 123 <link href="www.google.com/search?q=Markup+(business)">www.google.com/search?q=Markup+(business)</link>)) 456
</p></zim-tree>'''
		t = self.format.Parser().parse([text])
		self.assertEqual(t.tostring(), xml)

	def testMatchingLinkBrackets(self):
		text = '[[[foo]]] [[[bar[baz]]]'
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p>[<link href="foo">foo</link>] [<link href="bar[baz]">bar[baz]</link>
</p></zim-tree>'''
		t = self.format.Parser().parse([text])
		self.assertEqual(t.tostring(), xml)

	def testNoNestedURLs(self):
		text = '[[http://example.com|example@example.com]]'
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><link href="http://example.com">example@example.com</link>
</p></zim-tree>'''
		t = self.format.Parser().parse([text])
		self.assertEqual(t.tostring(), xml)

	def testNoNestedLinks(self):
		text = '[[http://example.com|[[example@example.com]]]]'
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><link href="http://example.com">[[example@example.com]]</link>
</p></zim-tree>'''
		t = self.format.Parser().parse([text])
		self.assertEqual(t.tostring(), xml)

	def testLinkWithFormatting(self):
		text = '[[http://example.com| //Example// ]]' # spaces are crucial in this example - see issue #1306
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><link href="http://example.com"> <emphasis>Example</emphasis> </link>
</p></zim-tree>'''
		t = self.format.Parser().parse([text])
		self.assertEqual(t.tostring(), xml)

	def testAnchor(self):
		text = '{{id: test}}'
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><p><anchor name="test">test</anchor>
</p></zim-tree>'''
		tree = self.format.Parser().parse(text)
		self.assertEqual(tree.tostring(), xml)


class TestGFMAutolinks(tests.TestCase):
	# See https://github.github.com/gfm/#autolinks-extension-

	examples = (
		# Basic match
		('www.commonmark.org', True, None),
		('www.commonmark.org/help', True, None),
		('http://commonmark.org', True, None),
		('http://commonmark.org/help', True, None),
		('commonmark.org', False, None),
		('commonmark.org/help', False, None),


		# No "_" in last two parts domain
		('www.common_mark.org', False, None),
		('www.commonmark.org_help', False, None),
		('www.test_123.commonmark.org', True, None),

		# Trailing punctuation
		('www.commonmark.org/a.b.', True, '.'),
		('www.commonmark.org.', True, '.'),
		('www.commonmark.org?', True, '?'),

		# Trailing ")"
		('www.google.com/search?q=Markup+(business)', True, None),
		('www.google.com/search?q=Markup+(business))', True, ')'),
		('www.google.com/search?q=Markup+(business)))', True, '))'),
		('www.google.com/search?q=(business))+ok', True, None),

		# Trailing entity reference
		('www.google.com/search?q=commonmark&hl=en', True, None),
		('www.google.com/search?q=commonmark&hl;', True, '&hl;'),

		# A "<" always breaks the link
		('www.commonmark.org/he<lp', True, '<lp'),

		# Email
		('foo@bar.baz', True, None),
		('hello@mail+xyz.example', False, None),
		('hello+xyz@mail.example', True, None),
		('a.b-c_d@a.b', True, None),
		('a.b-c_d@a.b.', True, '.'),
		('a.b-c_d@a.b-', False, None),
		('a.b-c_d@a.b_', False, None),
		('@tag', False, None),

		# Examples from bug tracker
		('https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.10/#container-core-v1-', True, None),
		('https://da.sharelatex.com/templates/books/springer\'s-monograph-type-svm', True, None),
		('https://en.wikipedia.org/wiki/80/20_(framing_system)', True, None),
		('https://bugs.kde.org/buglist.cgi?resolution=---', True, None),
		('https://vimhelp.org/options.txt.html#\'iskeyword\'', True, None),
		('https://example.com/foo]', True, None),
	)

	def testFunctions(self):
		from zim.formats.wiki import match_url, is_url

		for input, input_is_url, tail in self.examples:
			if input_is_url:
				if tail:
					self.assertEqual(match_url(input), input[:-len(tail)])
					self.assertFalse(is_url(input))
				else:
					self.assertEqual(match_url(input), input)
					self.assertTrue(is_url(input))
			else:
				self.assertEqual(match_url(input), None)
				self.assertFalse(is_url(input))


class TestHtmlFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('html')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		self.page = notebook.get_page(Path('Foo'))

	def testEncoding(self):
		'''Test HTML encoding'''
		builder = ParseTreeBuilder()
		builder.start(FORMATTEDTEXT)
		builder.append(PARAGRAPH, None, '<foo>"foo" & "bar"</foo>\n')
		builder.end(FORMATTEDTEXT)
		tree = builder.get_parsetree()
		html = self.format.Dumper(linker=StubLinker()).dump(tree)
		self.assertEqual(''.join(html),
			'<p>\n&lt;foo&gt;"foo" &amp; "bar"&lt;/foo&gt;\n</p>\n')

	# TODO add test using http://validator.w3.org

	def testEmptyLines(self):
		builder = ParseTreeBuilder()
		builder.start(FORMATTEDTEXT)
		builder.append(HEADING, {'level': 1}, 'head1')
		builder.text('\n')
		builder.append(HEADING, {'level': 2}, 'head2')
		builder.end(FORMATTEDTEXT)
		tree = builder.get_parsetree()

		html = self.format.Dumper(
			linker=StubLinker(),
			template_options={'empty_lines': 'default'}
		).dump(tree)
		self.assertEqual(''.join(html),
			'<h1>head1</h1>\n\n'
			'<br>\n\n'
			'<h2>head2</h2>\n\n'
		)

		html = self.format.Dumper(
			linker=StubLinker(),
			template_options={'empty_lines': 'remove'}
		).dump(tree)
		self.assertEqual(''.join(html),
			'<h1>head1</h1>\n\n'
			'<h2>head2</h2>\n\n'
		)

		html = self.format.Dumper(
			linker=StubLinker(),
			template_options={'empty_lines': 'Remove'} # case sensitive
		).dump(tree)
		self.assertEqual(''.join(html),
			'<h1>head1</h1>\n\n'
			'<h2>head2</h2>\n\n'
		)


	def testLineBreaks(self):
		builder = ParseTreeBuilder()
		builder.start(FORMATTEDTEXT)
		builder.append(PARAGRAPH, None,
			'bla bla bla\n'
			'bla bla bla\n'
		)
		builder.end(FORMATTEDTEXT)
		tree = builder.get_parsetree()

		html = self.format.Dumper(
			linker=StubLinker(),
			template_options={'line_breaks': 'default'}
		).dump(tree)
		self.assertEqual(''.join(html),
			'<p>\n'
			'bla bla bla<br>\n'
			'bla bla bla\n'
			'</p>\n'
		)

		html = self.format.Dumper(
			linker=StubLinker(),
			template_options={'line_breaks': 'remove'}
		).dump(tree)
		self.assertEqual(''.join(html),
			'<p>\n'
			'bla bla bla\n'
			'bla bla bla\n'
			'</p>\n'
		)



class TestMarkdownFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('markdown')


class TestRstFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('rst')


class TestLatexFormat(tests.TestCase, TestFormatMixin):

	def setUp(self):
		self.format = get_format('latex')

	def testEncode(self):
		'''test the escaping of certain characters'''
		format = get_format('latex')

		input = r'\foo $ % ^ \% bar < >'
		wanted = r'$\backslash$foo \$  \% \^{} $\backslash$\% bar \textless{} \textgreater{}'
		self.assertEqual(format.Dumper.encode_text(PARAGRAPH, input), wanted)

	def testDocumentType(self):
		builder = ParseTreeBuilder()
		builder.start(FORMATTEDTEXT)
		builder.append(HEADING, {'level': 1}, 'head1')
		builder.text('\n')
		builder.append(HEADING, {'level': 2}, 'head2')
		builder.end(FORMATTEDTEXT)
		tree = builder.get_parsetree()

		for type, head1 in (
			('report', 'chapter'),
			('article', 'section'),
			('book', 'part'),
		):
			lines = self.format.Dumper(
				linker=StubLinker(),
				template_options={'document_type': type}
			).dump(tree)
			self.assertIn(head1, ''.join(lines))

	def testImagesWhitelist(self):
		builder = ParseTreeBuilder()
		builder.start(FORMATTEDTEXT)
		builder.append(IMAGE, {'src': 'test.png'})
		builder.text('\n')
		builder.append(IMAGE, {'src': 'test.tiff'})
		builder.text('\n')
		builder.append(IMAGE, {'src': 'test.tiff', 'href': 'foo'})
		builder.text('\n')
		builder.end(FORMATTEDTEXT)
		tree = builder.get_parsetree()

		wanted = [
			'\\includegraphics[]{test.png}\n', '\n',
			'\\href{test.tiff}{test.tiff}\n', '\n',
			'\\href{foo}{foo}\n', '\n'
		]
		lines = self.format.Dumper(linker=StubLinker()).dump(tree)
		self.assertEqual(lines, wanted)


class StubFile(object):

	def __init__(self, path, text):
		self.path = path
		self.text = text

	def read(self):
		return self.text


class TestParseHeaderLines(tests.TestCase):

	def runTest(self):
		text = '''\
Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
X-Foo: Some text
	here
Creation-Date: 2010-12-14T14:15:09.134955

Blaat
'''
		body, meta = parse_header_lines(text)
		self.assertEqual(dict(meta), {
			'Content-Type': 'text/x-zim-wiki',
			'Wiki-Format': 'zim 0.4',
			'Creation-Date': '2010-12-14T14:15:09.134955',
			'X-Foo': 'Some text\nhere'
		})
		self.assertEqual(body, 'Blaat\n')

		out = dump_header_lines(meta)
		self.assertEqual(out + '\nBlaat\n', text)
