# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

from tests import TestCase

from zim.utils import *

class testUtils(TestCase):

	def testSplitWords(self):
		string = r'''"foo bar", "\"foooo bar\"" dusss ja'''
		list = ['foo bar', ',', '"foooo bar"', 'dusss', 'ja']
		result = split_quoted_strings(string)
		self.assertEquals(result, list)
		list = ['"foo bar"', ',', r'"\"foooo bar\""', 'dusss', 'ja']
		result = split_quoted_strings(string, unescape=False)
		self.assertEquals(result, list)

	def testRe(self):
		string = 'foo bar baz';
		re = Re('f(oo)\s*(bar)')
		if re.match(string):
			self.assertEquals(len(re), 3)
			self.assertEquals(re[0], 'foo bar')
			self.assertEquals(re[1], 'oo')
			self.assertEquals(re[2], 'bar')
		else:
			assert False, 'fail'
