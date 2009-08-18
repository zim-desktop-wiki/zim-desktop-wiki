
# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import tests
from tests import TestCase

import os

from zim.gui.applications import *

def replace(l, old, new):
	l = list(l)
	while old in l:
		i = l.index(old)
		l[i] = new
	return tuple(l)


class TestApplications(TestCase):

	def testParseExec(self):
		'''Test parsing of .desktop Exec strings'''

		entry = DesktopEntryDict()
		entry['Desktop Entry']['Name'] = 'Foo'
		for app, args, wanted in (
			# Test cases should be compliant with spec
			('foo %f', (), ('foo',)),
			('foo %f %i', (), ('foo',)), # no icon set
			('foo %f %k', (), ('foo', '')), # no source set
			('foo %f %c', (), ('foo', 'Foo')),
			('foo', ('bar',), ('foo', 'bar')),
			('foo', ('bar baz',), ('foo', 'bar baz')),
			('foo "hmm ja"', ('bar',), ('foo', 'hmm ja', 'bar')),
			('foo %f', ('bar baz',), ('foo', 'bar baz')),
			('foo %F', ('bar baz',), ('foo', 'bar baz')),
			('foo %u', ('bar baz',), ('foo', 'bar baz')),
			('foo %U', ('bar baz',), ('foo', 'bar baz')),
			('foo %F', ('bar', 'baz'), ('foo', 'bar', 'baz')),
			('foo %F hmm', ('bar', 'baz'), ('foo', 'bar', 'baz', 'hmm')),
			('foo %U', ('bar', 'baz'), ('foo', 'bar', 'baz')),
			('foo %U hmm', ('bar', 'baz'), ('foo', 'bar', 'baz', 'hmm')),
			('foo %f', (File('/foo/bar'),), ('foo', '/foo/bar')),
			('foo %u', (File('/foo/bar'),), ('foo', 'file:///foo/bar')),
			('foo %F', (File('/foo/bar'),), ('foo', '/foo/bar')),
			('foo %U', (File('/foo/bar'),), ('foo', 'file:///foo/bar')),
		):
			if os.name == 'nt':
				wanted = replace(wanted, '/foo/bar', r'C:\foo\bar')
				wanted = replace(wanted, 'file:///foo/bar', r'file:///C:/foo/bar')

			#print app, args
			entry['Desktop Entry']['Exec'] = app
			result = entry.parse_exec(args)
			self.assertEqual(result, wanted)
		
		entry['Desktop Entry']['Icon'] = 'xxx'
		entry.file = File('/foo.desktop')
		for app, args, wanted in (
			# Test cases should be compliant with spec
			('foo %f %i', (), ('foo', '--icon', 'xxx')),
			('foo %f %k', (), ('foo', '/foo.desktop')),
			('foo %f %c', (), ('foo', 'Foo')),
		):
			if os.name == 'nt':
				wanted = replace(wanted, '/foo.desktop', r'C:\foo.desktop')
			#print app, args
			entry['Desktop Entry']['Exec'] = app
			result = entry.parse_exec(args)
			self.assertEqual(result, wanted)


