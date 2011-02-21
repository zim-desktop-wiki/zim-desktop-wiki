
# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests
from tests import TestCase, create_tmp_dir

import os
import gtk

from zim.gui.applications import *
from zim.notebook import Path
from zim.fs import Dir, TmpFile


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


class TestCustomTools(TestCase):

	def testManager(self):
		'''Test CustomToolManager API'''
		# initialize the list
		manager = CustomToolManager()
		self.assertEqual(list(manager), [])
		self.assertEqual(list(manager.names), [])

		# add a tool
		properties = {
			'Name': 'Foo',
			'Comment': 'Test 1 2 3',
			'Icon': '',
			'X-Zim-ExecTool': 'foo %t "quoted"',
			'X-Zim-ReadOnly': False,
			'X-Zim-ShowInToolBar': True,
		}
		tool = manager.create(**properties)
		self.assertEqual(list(manager), [tool])
		self.assertEqual(list(manager.names), ['foo-usercreated'])

		self.assertTrue(tool.isvalid)
		self.assertEqual(tool.name, 'Foo')
		self.assertEqual(tool.comment, 'Test 1 2 3')
		self.assertFalse(tool.isreadonly)
		self.assertTrue(tool.showintoolbar)
		self.assertTrue(tool.get_pixbuf(gtk.ICON_SIZE_MENU))
		self.assertEqual(tool.showincontextmenu, 'Text') # Auto generated

		# test file saved correctly
		#~ from pprint import pprint
		#~ pprint(tool)
		lines = tool.dump()
		self.assertTrue(len(lines) > 5)
		lines = tool.file.readlines()
		self.assertTrue(len(lines) > 5)

		# refresh list
		manager = CustomToolManager()
		self.assertEqual(list(manager), [tool])
		self.assertEqual(list(manager.names), ['foo-usercreated'])

		# add a second tool
		tool1 = tool
		properties = {
			'Name': 'Foo',
			'Comment': 'Test 1 2 3',
			'Icon': None,
			'X-Zim-ExecTool': 'foo %f',
			'X-Zim-ReadOnly': False,
			'X-Zim-ShowInToolBar': True,
		}
		tool = manager.create(**properties)
		self.assertEqual(list(manager), [tool1, tool])
		self.assertEqual(list(manager.names), ['foo-usercreated', 'foo-usercreated-1'])

		self.assertTrue(tool.isvalid)
		self.assertEqual(tool.name, 'Foo')
		self.assertEqual(tool.comment, 'Test 1 2 3')
		self.assertFalse(tool.isreadonly)
		self.assertTrue(tool.showintoolbar)
		self.assertTrue(tool.get_pixbuf(gtk.ICON_SIZE_MENU))
		self.assertEqual(tool.showincontextmenu, 'Page') # Auto generated

		# switch order
		i = manager.index(tool)
		self.assertTrue(i == 1)
		manager.reorder(tool, 0)
		i = manager.index(tool)
		self.assertTrue(i == 0)
		self.assertEqual(list(manager.names), ['foo-usercreated-1', 'foo-usercreated'])

		# delete
		file = tool1.file
		self.assertTrue(file.exists())
		manager.delete(tool1)
		self.assertEqual(list(manager.names), ['foo-usercreated-1'])
		self.assertFalse(file.exists())

	def testParseExec(self):
		'''Test parsing of custom tool Exec strings'''
		# %f for source file as tmp file current page
		# %d for attachment directory
		# %s for real source file (if any)
		# %n for notebook location (file or directory)
		# %D for document root
		# %t for selected text or word under cursor
		# %T for selected text or word under cursor with wiki format

		notebook = tests.get_test_notebook()
		page = notebook.get_page(Path('Test:Foo'))
		pageview = StubPageView()
		args = (notebook, page, pageview)

		tmpfile = TmpFile('tmp-page-source.txt').path
		dir = Dir(tests.create_tmp_dir('applications_TestCustomTools'))
		notebook.dir = dir # fake file store
		notebook._stores[''].dir = dir # fake file store

		tool = CustomToolDict()
		tool.update( {
			'Name': 'Test',
			'Description': 'Test 1 2 3',
			'X-Zim-ExecTool': 'foo',
		} )
		for cmd, wanted in (
			('foo %f', ('foo', tmpfile)),
			('foo %d', ('foo', dir.subdir('Test/Foo').path)),
			('foo %s', ('foo', '')), # no file source
			('foo %n', ('foo', dir.path)),
			('foo %D', ('foo', '')), # no document root
			('foo %t', ('foo', 'FooBar')),
			('foo %T', ('foo', '**FooBar**')),
		):
			#~ print '>>>', cmd
			tool['Desktop Entry']['X-Zim-ExecTool'] = cmd
			self.assertEqual(tool.parse_exec(args), wanted)


class StubPageView(object):

	def get_selection(self, format=None):
		return None

	def get_word(self, format=None):
		if format:
			return '**FooBar**'
		else:
			return 'FooBar'
