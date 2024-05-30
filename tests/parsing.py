
# Copyright 2009-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import zim.datetimetz as datetime

from zim.parse import convert_space_to_tab, fix_unicode_whitespace
from zim.parse.builder import BuilderTextBuffer
from zim.parse.encode import \
	escape_string, unescape_string, split_escaped_string, \
	url_decode, url_encode, \
	URL_ENCODE_READABLE, URL_ENCODE_PATH, URL_ENCODE_DATA
from zim.parse.links import *
from zim.parse.dates import *
from zim.parse.dates import old_parse_date
from zim.parse.regexparser import *
from zim.parse.simpletree import *
from zim.parse.tokenlist import EndOfTokenListError, TokenBuilder, TokenParser, \
	collect_until_end_token, filter_token, reverseTopLevelLists, \
	testTokenStream, tokens_to_text, topLevelLists
from zim.formats import ParseTreeBuilder, PARAGRAPH


class TestEscapeStringFunctions(tests.TestCase):

	def testEscapeString(self):
		for raw, escaped in (
			('Newline \n', 'Newline \\n'),
			('Tab \t', 'Tab \\t'),
			('Special char |', 'Special char \\|'),
			('Backslash \\', 'Backslash \\\\'),
			('Backslashed special char \\|', 'Backslashed special char \\\\\\|'),
			('Not a newline \\n', 'Not a newline \\\\n'),
		):
			self.assertEqual(escape_string(raw, chars='|'), escaped)
			self.assertEqual(unescape_string(escaped), raw)

	def testSplitEscapedString(self):
		for string, parts in (
			('Part A|Part B|Part C', ['Part A', 'Part B', 'Part C']),
			('Part A\\| with pipe|Part B|Part C', ['Part A\\| with pipe', 'Part B', 'Part C']),
			('Part A\\\\\\| with multiple backslash|Part B|Part C', ['Part A\\\\\\| with multiple backslash', 'Part B', 'Part C']),
			('Part A with backslash\\\\|Part B|Part C', ['Part A with backslash\\\\', 'Part B', 'Part C']),
			('No agressive strip \\', ['No agressive strip \\'])
		):
			self.assertEqual(split_escaped_string(string, '|'), parts)


class TestURLEncode(tests.TestCase):

	def testURLEncoding(self):
		'''Test encoding and decoding urls'''
		for url, readable in (
			('file:///foo/file%25%20%5D', 'file:///foo/file%25 %5D'),
			('http://foo/bar%20monkey%E2%80%99s', 'http://foo/bar monkey\u2019s'), # Multibyte unicode char

			# from bug report lp:545712
			('http://www.moneydj.com/e/newage/JAVA%B4%FA%B8%D5%B0%CF.htm',
				'http://www.moneydj.com/e/newage/JAVA%B4%FA%B8%D5%B0%CF.htm'),
			('http://www.moneydj.com/e/newage/JAVA%20%B4%FA%B8%D5%B0%CF.htm',
				'http://www.moneydj.com/e/newage/JAVA %B4%FA%B8%D5%B0%CF.htm'),
		):
			self.assertEqual(url_decode(url, mode=URL_ENCODE_READABLE), readable)
			self.assertEqual(url_decode(readable, mode=URL_ENCODE_READABLE), readable)
			self.assertEqual(url_encode(url, mode=URL_ENCODE_READABLE), url)
			self.assertEqual(url_encode(readable, mode=URL_ENCODE_READABLE), url)

		for path, encoded in (
			('/foo/file% ]', '/foo/file%25%20%5D'),
			('/foo/bar monkey\u2019s', '/foo/bar%20monkey%E2%80%99s'),
		):
			self.assertEqual(url_encode(path, mode=URL_ENCODE_PATH), encoded)
			self.assertEqual(url_decode(encoded, mode=URL_ENCODE_PATH), path)

		self.assertEqual(url_encode('foo?bar/baz', mode=URL_ENCODE_DATA), 'foo%3Fbar%2Fbaz')
		self.assertEqual(url_decode('foo%3Fbar%2Fbaz', mode=URL_ENCODE_DATA), 'foo?bar/baz')
		# from bug report lp:545712
		self.assertEqual(url_decode('%B4%FA%B8%D5%B0%CF', mode=URL_ENCODE_DATA), '%B4%FA%B8%D5%B0%CF')

		## test round trip for utf-8
		data = '\u0421\u0430\u0439'
		encoded = url_encode(data)
		decoded = url_decode(data)
		#~ print("DATA, ENCODED, DECODED:", (data, encoded, decoded))
		self.assertEqual(decoded, data)
		self.assertEqual(url_decode(encoded), data)
		self.assertEqual(url_encode(decoded), encoded)


class TestParseLinks(tests.TestCase):

	def testLinkType(self):
		'''Test link_type()'''
		for href, type in (
			('zim+file://foo/bar?dus.txt', 'notebook'),
			('file:///foo/bar', 'file'),
			('file://foo/bar', 'file'),
			('file://localhost/foo/bar', 'file'),
			('file:/foo/bar', 'file'),
			('http://foo/bar', 'http'),
			('http://192.168.168.100', 'http'),
			('file+ssh://foo/bar', 'file+ssh'),
			('mailto:foo@bar.com', 'mailto'),
			('mailto:foo.com', 'page'),
			('foo@bar.com', 'mailto'),
			('mailto:foo//bar@bar.com', 'mailto'), # is this a valid mailto uri ?
			('mid:foo@bar.org', 'mid'),
			('cid:foo@bar.org', 'cid'),
			('./foo/bar', 'file'),
			('/foo/bar', 'file'),
			('~/foo', 'file'),
			('C:\\foo', 'file'),
			('wp?foo', 'interwiki'),
			('http://foo?bar', 'http'),
			('\\\\host\\foo\\bar', 'smb'),
			('foo', 'page'),
			('foo:bar', 'page'),
		):
			# print('>>', href)
			self.assertEqual(link_type(href), type)


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
		#('https://vimhelp.org/options.txt.html#\'iskeyword\'', True, None),
		#	-> this example is overruled by new behavior
		('https://example.com/foo]', True, None),

		# Zim extensions
		('https://localhost', True, None),
		('https://localhost/path', True, None),
		('file:///home/foo', True, None),
		('file://home/foo', True, None),
		('file:/home/foo', True, None),
		('foo://bar', True, None),
	)

	def testFunctions(self):
		for input, input_is_url, tail in self.examples:
			if input_is_url:
				if tail:
					self.assertEqual(match_url_link(input), input[:-len(tail)])
					self.assertFalse(is_url_link(input))
				else:
					self.assertEqual(match_url_link(input), input)
					self.assertTrue(is_url_link(input))
			else:
				self.assertEqual(match_url_link(input), None)
				self.assertFalse(is_url_link(input))


class TestParseDates(tests.TestCase):

	def testParseDate(self):
		date = datetime.date(2017, 3, 27)
		for text in (
			'2017-03-27', '2017-03',
			'2017-W13', '2017-W13-1',
			'2017W13', '2017W13-1',
			'2017w13', '2017w13-1',
			'W1713', 'W1713-1', 'W1713.1',
			'Wk1713', 'Wk1713-1', 'Wk1713.1',
			'wk1713', 'wk1713-1', 'wk1713.1',
		):
			m = date_re.match(text)
			self.assertIsNotNone(m, 'Failed to match: %s' % text)
			self.assertEqual(m.group(0), text)
			obj = parse_date(m.group(0))
			self.assertIsInstance(obj, (Day, Week, Month))
			self.assertTrue(obj.first_day <= date <= obj.last_day)

		for text in (
			'foo', '123foo', '2017-03-270',
			'20170317', '17-03-27', '17-03'
			'17W', '2017W131', '2017-W131'
		):
			m = date_re.match(text)
			if m:
				print('>>', m.group(0))
			self.assertIsNone(m, 'Did unexpectedly match: %s' % text)

	def testWeekNumber(self):
		self.assertEqual(
			Day(2017, 3, 27),
			Day.new_from_weeknumber(2017, 13, 1)
		)
		self.assertEqual(
			Day(2017, 3, 27).weekformat(),
			('2017-W13-1')
		)
		self.assertEqual(
			Day.new_from_weeknumber(2017, 13, 7),
			Day.new_from_weeknumber(2017, 14, 0)
		)

	def testOldParseDate(self):
		'''Test parsing dates'''
		from datetime import date
		today = date.today()
		year = today.year
		if today.month > 6:
			year += 1 # Starting July next year January is closer
		self.assertEqual(old_parse_date('1/1'), (year, 1, 1))
		self.assertEqual(old_parse_date('1-1'), (year, 1, 1))
		self.assertEqual(old_parse_date('1:1'), (year, 1, 1))
		self.assertEqual(old_parse_date('11/11/99'), (1999, 11, 11))
		self.assertEqual(old_parse_date('11/11/11'), (2011, 11, 11))
		self.assertEqual(old_parse_date('1/11/2001'), (2001, 11, 1))
		self.assertEqual(old_parse_date('1-11-2001'), (2001, 11, 1))
		self.assertEqual(old_parse_date('1:11:2001'), (2001, 11, 1))
		self.assertEqual(old_parse_date('2001/11/1'), (2001, 11, 1))


class TestSimpleTreeBuilder(tests.TestCase):

	def runTest(self):
		E = SimpleTreeElement

		builder = SimpleTreeBuilder()

		builder.start('root', {})
		builder.text('foo')
		builder.text('bar')
		builder.append('dus', {}, 'ja')
		builder.text('foo')
		builder.text('bar')
		builder.append('br', {})
		builder.text('foo')
		builder.text('bar')
		builder.end('root')

		root = builder.get_root()
		self.assertEqual(root,
			E('root', {}, [
					'foo', 'bar',
					E('dus', {}, ['ja']),
					'foo', 'bar',
					E('br', {}, []),
					'foo', 'bar',
				]
			)
		)


		realbuilder = SimpleTreeBuilder()
		builder = BuilderTextBuffer(realbuilder)

		builder.start('root', None)
		builder.text('foo')
		builder.text('bar')
		builder.append('bold', {'level': 3}, 'ja')
		builder.text('foo')
		builder.text('bar')
		builder.append('br', None)
		builder.text('foo')
		builder.text('bar')
		builder.end('root')

		root = realbuilder.get_root()
		self.assertEqual(root,
				E('root', None, [
					'foobar',
					E('bold', {'level': 3}, ['ja']),
					'foobar',
					E('br', None, []),
					'foobar',
				]
			)
		)


class TestTokensToSimpleTree(tests.TestCase):

	def setUp(self):
		E = SimpleTreeElement
		self.elt = E('root', None, [
				'foobar',
				E('bold', {'level': 3}, ['ja']),
				'foobar',
				E('br', None, []),
				'foobar',
			]
		)
		self.tokens = [
			('root', None),
				(TEXT, 'foobar'),
				('bold', {'level': 3}), (TEXT, 'ja'), (END, 'bold'),
				(TEXT, 'foobar'),
				('br', None), (END, 'br'),
				(TEXT, 'foobar'),
			(END, 'root')
		]

	def testSimpleTreeToTokens(self):
		self.assertEqual(simpletree_to_tokens(self.elt), self.tokens)

	def testSimpleTreeToTokensWithParserBuilder(self):
		builder = TokenBuilder()
		SimpleTreeParser(builder).parse(self.elt)
		self.assertEqual(builder.tokens, self.tokens)

	def testTokensToSimpleTree(self):
		self.assertEqual(tokens_to_simpletree(self.tokens), self.elt)

	def testTokensToSimpleTreeWithParserBuilder(self):
		builder = SimpleTreeBuilder()
		TokenParser(builder).parse(self.tokens)
		self.assertAlmostEqual(builder.get_root(), self.elt)


class TestBuilderTextBuffer(tests.TestCase):

	def runTest(self):
		builder = SimpleTreeBuilder()
		buffer = BuilderTextBuffer(builder)

		buffer.start('FOO')
		buffer.text('aaa\n')
		buffer.text('bbb\n')
		buffer.text('ccc\n')
		self.assertEqual(buffer.get_text(), 'aaa\nbbb\nccc\n')

		buffer.append('BAR')
		self.assertEqual(buffer.get_text(), '')

		buffer.text('qqq\n')
		self.assertEqual(buffer.get_text(), 'qqq\n')
		buffer.clear_text()

		buffer.text('qqq\n')
		self.assertEqual(buffer.get_text(), 'qqq\n')
		buffer.set_text('ddd\n')
		self.assertEqual(buffer.get_text(), 'ddd\n')

		buffer.text('')
		buffer.text('eee')
		buffer.end('FOO')

		E = SimpleTreeElement
		self.assertEqual(builder.get_root(), 
			E('FOO', None, [
				'aaa\nbbb\nccc\n',
				E('BAR', None, []),
				'ddd\neee',
			])
		)



class TestParser(tests.TestCase):

	def testFixUnicode(self):
		self.assertEqual(fix_unicode_whitespace('foo\u2028bar\u2029check\n'), 'foo\nbar check\n')

	def testConvertSpaceToTab(self):
		self.assertEqual(convert_space_to_tab('    foo\n\t     bar\n'), '\tfoo\n\t\t bar\n')

	def testGetLineCount(self):
		text = 'foo\nbar\nbaz\n'
		for offset, wanted in (
			(0, (1, 0)),
			(3, (1, 3)),
			(4, (2, 0)),
			(8, (3, 0)),
			(9, (3, 1)),
		):
			line = get_line_count(text, offset)
			self.assertEqual(line, wanted)

	## TODO -- Parser test cases ##


class TestTokenParser(tests.TestCase):

	def walk(self, tree, builder):
		# Iter tree without toplevellist
		for t in tree._get_tokens(tree._etree.getroot()):
			if t[0] == TEXT:
				builder.text(t[1])
			elif t[0] == END:
				builder.end(t[1])
			else:
				builder.start(t[0], t[1])

	def testRoundtrip(self):
		tree = tests.new_parsetree()
		#~ print tree
		tb = TokenBuilder()
		self.walk(tree, tb)
		tokens = tb.tokens
		#~ import pprint; pprint.pprint(tokens)

		testTokenStream(tokens)

		builder = ParseTreeBuilder()
		TokenParser(builder).parse(tokens)
		newtree = builder.get_parsetree()

		self.assertEqual(tree.tostring(), newtree.tostring())


	def testTopLevelLists(self):
		tree = tests.new_parsetree()
		tb = TokenBuilder()
		self.walk(tree, tb)
		tokens = tb._tokens # using raw tokens

		newtokens = topLevelLists(tokens)
		testTokenStream(newtokens)
		revtokens = reverseTopLevelLists(newtokens)

		def correct_none_attrib(t):
			if t[0] == PARAGRAPH and not t[1]:
				return (PARAGRAPH, {})
			else:
				return t

		revtokens = list(map(correct_none_attrib, revtokens))

		self.assertEqual(revtokens, tokens)


class TestFunctions(tests.TestCase):

	def testCollectTokens(self):
		# simple
		self.assertEqual(
			collect_until_end_token(
				[('B', {}), ('T', ''), (END, 'B'), (END, 'A'), ('T', '')],
				'A'
			),
				[('B', {}), ('T', ''), (END, 'B')]
		)
		# nested
		self.assertEqual(
			collect_until_end_token(
				[('A', {}), ('T', ''), (END, 'A'), (END, 'A'), ('T', '')],
				'A'
			),
				[('A', {}), ('T', ''), (END, 'A')]
		)
		# error case: no closing tag found
		with self.assertRaises(EndOfTokenListError):
			collect_until_end_token(
				[('B', {}), ('T', ''), (END, 'B'), ('T', '')],
				'A'
			)

	def testFilterTokens(self):
		self.assertEqual(
			list(filter_token(
				[('T', 'pre'), ('A', {}), ('T', 'inner'), (END, 'A'), ('T', 'post')],
				'A'
			)),
			[('T', 'pre'), ('T', 'post')]
		)
		self.assertEqual(
			list(filter_token(
				[('T', 'pre'), ('A', {}), ('A', {}), ('T', 'inner'), (END, 'A'), (END, 'A'), ('T', 'post')],
				'A'
			)),
			[('T', 'pre'), ('T', 'post')]
		)

	def testTokensToText(self):
		self.assertEqual(
			tokens_to_text([('B', {}), ('T', 'Foo'), (END, 'B'), ('T', 'Bar')]),
			'FooBar'
		)
