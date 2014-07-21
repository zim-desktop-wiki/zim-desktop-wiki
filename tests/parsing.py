# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.parsing import *
from zim.parser import *

class TestParsing(tests.TestCase):

	def testSplitWords(self):
		'''Test parsing quoted strings'''
		string = r'''"foo bar", "\"foooo bar\"" dusss ja'''
		list = ['foo bar', ',', '"foooo bar"', 'dusss', 'ja']
		result = split_quoted_strings(string)
		self.assertEquals(result, list)
		list = ['"foo bar"', ',', r'"\"foooo bar\""', 'dusss', 'ja']
		result = split_quoted_strings(string, unescape=False)
		self.assertEquals(result, list)

		string = r'''"foo bar", False, True'''
		list = ['foo bar', ',', 'False', ',', 'True']
		result = split_quoted_strings(string)
		self.assertEquals(result, list)

		self.assertRaises(ValueError, split_quoted_strings, "If you don't mind me asking")
		string = "If you don't mind me asking"
		list = ["If", "you", "don", "'t", "mind", "me", "asking"]
		result = split_quoted_strings(string, strict=False)
		self.assertEquals(result, list)

	def testParseDate(self):
		'''Test parsing dates'''
		from datetime import date
		today = date.today()
		year = today.year
		if today.month > 6:
			year += 1 # Starting July next year January is closer
		self.assertEqual(parse_date('1/1'), (year, 1, 1))
		self.assertEqual(parse_date('1-1'), (year, 1, 1))
		self.assertEqual(parse_date('1:1'), (year, 1, 1))
		self.assertEqual(parse_date('11/11/99'), (1999, 11, 11))
		self.assertEqual(parse_date('11/11/11'), (2011, 11, 11))
		self.assertEqual(parse_date('1/11/2001'), (2001, 11, 1))
		self.assertEqual(parse_date('1-11-2001'), (2001, 11, 1))
		self.assertEqual(parse_date('1:11:2001'), (2001, 11, 1))
		self.assertEqual(parse_date('2001/11/1'), (2001, 11, 1))

	def testRe(self):
		'''Test parsing Re class'''
		string = 'foo bar baz';
		re = Re('f(oo)\s*(bar)')
		if re.match(string):
			self.assertEquals(len(re), 3)
			self.assertEquals(re[0], 'foo bar')
			self.assertEquals(re[1], 'oo')
			self.assertEquals(re[2], 'bar')
		else:
			assert False, 'fail'

	def testTextBuffer(self):
		'''Test parsing TextBuffer class'''
		buffer = TextBuffer()
		buffer += ['test 123\n test !', 'fooo bar\n', 'duss']
		self.assertEqual(
			buffer.get_lines(),
			['test 123\n', ' test !fooo bar\n', 'duss\n'] )

	def testURLEncoding(self):
		'''Test encoding and decoding urls'''
		for url, readable in (
			('file:///foo/file%25%20%5D', 'file:///foo/file%25 %5D'),
			('http://foo/bar%20monkey%E2%80%99s', u'http://foo/bar monkey\u2019s'), # Multibyte unicode char

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
			(u'/foo/bar monkey\u2019s', '/foo/bar%20monkey%E2%80%99s'),
		):
			self.assertEqual(url_encode(path, mode=URL_ENCODE_PATH), encoded)
			self.assertEqual(url_decode(encoded, mode=URL_ENCODE_PATH), path)

		self.assertEqual(url_encode('foo?bar/baz', mode=URL_ENCODE_DATA), 'foo%3Fbar%2Fbaz')
		self.assertEqual(url_decode('foo%3Fbar%2Fbaz', mode=URL_ENCODE_DATA), 'foo?bar/baz')
		# from bug report lp:545712
		self.assertEqual(url_decode('%B4%FA%B8%D5%B0%CF', mode=URL_ENCODE_DATA), '\xb4\xfa\xb8\xd5\xb0\xcf')

		## test round trip for utf-8
		data = u'\u0421\u0430\u0439'
		encoded = url_encode(data)
		decoded = url_decode(data)
		#~ print "DATA, ENCODED, DECODED:", (data, encoded, decoded)
		self.assertEqual(decoded, data)
		self.assertEqual(url_decode(encoded), data)
		self.assertEqual(url_encode(decoded), encoded)

	def testLinkType(self):
		'''Test link_type()'''
		for href, type in (
			('zim+file://foo/bar?dus.txt', 'notebook'),
			('file:///foo/bar', 'file'),
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
			#~ print '>>', href
			self.assertEqual(link_type(href), type)


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
		self.assertEqual(root, [
			E('root', {}, [
					'foo', 'bar',
					E('dus', {}, ['ja']),
					'foo', 'bar',
					E('br', {}, []),
					'foo', 'bar',
				]
			)
		])


		realbuilder = SimpleTreeBuilder()
		builder = BuilderTextBuffer(realbuilder)

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

		root = realbuilder.get_root()
		self.assertEqual(root, [
			E('root', {}, [
					'foobar',
					E('dus', {}, ['ja']),
					'foobar',
					E('br', {}, []),
					'foobar',
				]
			)
		])



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
		self.assertEqual(builder.get_root(), [
			E('FOO', None, [
				u'aaa\nbbb\nccc\n',
				E('BAR', None, []),
				u'ddd\neee',
			])
		])



class TestParser(tests.TestCase):

	def testFunctions(self):
		# Helper functions
		for input, wanted in (
			('foo', 'foo\n'),
			('foo\nbar', 'foo\nbar\n'),
			('    foo\n\t     bar', '\tfoo\n\t\t bar\n'),
		):
			output = prepare_text(input)
			self.assertEqual(output, wanted)

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
