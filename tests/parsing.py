# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from tests import TestCase

from zim.parsing import *

class TestParsing(TestCase):

	def testSplitWords(self):
		'''Test parsing quoted strings'''
		string = r'''"foo bar", "\"foooo bar\"" dusss ja'''
		list = ['foo bar', ',', '"foooo bar"', 'dusss', 'ja']
		result = split_quoted_strings(string)
		self.assertEquals(result, list)
		list = ['"foo bar"', ',', r'"\"foooo bar\""', 'dusss', 'ja']
		result = split_quoted_strings(string, unescape=False)
		self.assertEquals(result, list)

	def testParseDate(self):
		'''Test parsing dates'''
		from datetime import date
		today = date.today()
		self.assertEqual(parse_date('1/1'), (today.year, 1, 1)) 
		self.assertEqual(parse_date('1-1'), (today.year, 1, 1)) 
		self.assertEqual(parse_date('1:1'), (today.year, 1, 1)) 
		self.assertEqual(parse_date('11/11'), (today.year, 11, 11)) 
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
		# Try finding edge cases for detecting when we encode / decode double
		for url, wanted in (
			('file:///foo/bar', 'file:///foo/bar'),
			('file:///C:/My Documents', 'file:///C:/My%20Documents'),
			('file:///C:/My%20Documents', 'file:///C:/My%20Documents'),
			('file:///foo/file[20%]', 'file:///foo/file%5B20%25%5D'),
			('file:///foo/file%5B20%25%5D', 'file:///foo/file%5B20%25%5D'),
			('file:///foo bar/foo%20bar', 'file:///foo%20bar/foo%2520bar'),
		):
			#~ print 'url_encode(\'%s\') == \'%s\'' % (url, url_encode(wanted))
			self.assertEqual(url_encode(url), wanted)
		
		for url, wanted in (
			('file:///foo/bar', 'file:///foo/bar'),
			('file:///C:/My Documents', 'file:///C:/My Documents'),
			('file:///C:/My%20Documents', 'file:///C:/My Documents'),
			('file:///foo/file[20%]', 'file:///foo/file[20%]'),
			('file:///foo/file%5B20%25%5D', 'file:///foo/file[20%]'),
			('file:///foo bar/foo%20bar', 'file:///foo bar/foo%20bar'),
		):
			#~ print 'url_decode(\'%s\') == \'%s\'' % (url, url_decode(wanted))
			self.assertEqual(url_decode(url), wanted)
		
# TODO - test link_type including win32 paths
