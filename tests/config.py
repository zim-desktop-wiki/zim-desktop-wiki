# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

from tests import TestCase

from zim.config import *


class testUtils(TestCase):

	def testListDict(self):
		keys = ['foo', 'bar', 'baz']
		mydict = ListDict()
		for k in keys:
			mydict[k] = 'dusss'
		mykeys = [k for k, v in mydict.items()]
		self.assertEquals(mykeys, keys)

	def testConfigList(self):
		input = u'''\
foo	bar
	dusss ja
# comments get taken out
some\ space he\ re # even here
'''
		output = u'''\
foo\tbar
dusss\tja
some\ space\the\ re
'''
		keys = ['foo', 'dusss', 'some space']
		mydict = ConfigList()
		mydict.parse(input)
		mykeys = [k for k, v in mydict.items()]
		self.assertEquals(mykeys, keys)
		result = mydict.dump()
		self.assertEqualDiff(result, output.splitlines(True))

class TestHeaders(TestCase):

	def runTest(self):
		# normal operation
		text='''\
Foobar: 123
More-Lines: test
	1234
	test
Aaa: foobar
'''
		headers = HeadersDict(text)
		self.assertEqual(headers['Foobar'], '123')
		self.assertEqual(headers['More-Lines'], 'test\n1234\ntest')
		self.assertEqualDiff(headers.tostring(), text)

		# error tolerance and case insensitivity
		text = '''\
more-lines: test
1234
test
'''
		self.assertRaises(ParsingError, HeadersDict, text)

		text = '''\
fooo
more-lines: test
1234
test
'''
		self.assertRaises(ParsingError, HeadersDict, text)

		text = 'foo-bar: test'
		headers = HeadersDict(text)
		self.assertEqual(headers['Foo-Bar'], 'test')
		self.assertEqual(headers.tostring(), 'Foo-Bar: test\n')
