# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


import tests

import os
import sys
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


class TestApplications(tests.TestCase):

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

			cwd, argv = entry._checkargs(None, args)
			self.assertEqual(tuple(a.decode(zim.fs.ENCODING) for a in argv), wanted)

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

	def testPythonCmd(self):
		app = Application('foo.py')
		cwd, argv = app._checkargs(None, ())
		exe = argv[0].decode(zim.fs.ENCODING)
		cmd = argv[1].decode(zim.fs.ENCODING)
		self.assertEqual(exe, sys.executable)
		self.assertEqual(cmd, 'foo.py')

		sys.frozen = True
		try:
			cwd, argv = app._checkargs(None, ())
			self.assertEqual(argv, ['foo.py'])
		except:
			del sys.frozen
			raise
		else:
			del sys.frozen

	# TODO fully test _decode_value
	# test e.g. values with '"' or '\t' in a string
	# see that json.loads does what it is supposed to do


@tests.slowTest
class TestApplicationManager(tests.TestCase):

	def testGetMimeType(self):
		for obj, mimetype in (
			(File('README.txt'), 'text/plain'),
			('README.txt', 'text/plain'),
			('ssh://host', 'x-scheme-handler/ssh'),
			('http://host', 'x-scheme-handler/http'),
			('README.html', 'text/html'),
			('mailto:foo@bar.org', 'x-scheme-handler/mailto'),
		):
			self.assertEqual(get_mimetype(obj), mimetype)

	def testGetSetApplications(self):
		# Typically a system will have multiple programs installed for
		# text/plain and text/html, but do not rely on them for
		# testing, so create our own first to test.

		#~ print XDG_DATA_HOME, XDG_DATA_DIRS
		manager = ApplicationManager()

		## Test Create & Get
		entry_text = manager.create('text/plain', 'Test_Entry_Text', 'test_text 123', NoDisplay=False)
		entry_html = manager.create('text/html', 'Test_Entry_HTML', 'test_html %u', NoDisplay=False)
		entry_url = manager.create('x-scheme-handler/ssh', 'Test_Entry_SSH', 'test_ssh %u', NoDisplay=False)
		for entry in (entry_text, entry_html, entry_url):
			self.assertTrue(entry.file.exists())
			self.assertEqual(manager.get_application(entry.key), entry)
			self.assertFalse(entry['Desktop Entry']['NoDisplay'])

		## Test Set & Get Default
		defaults = XDG_DATA_HOME.file('applications/defaults.list')
		self.assertFalse(defaults.exists())

		default = manager.get_default_application('text/plain')
		self.assertIsInstance(default, (None.__class__, DesktopEntryFile))
			# system default or None

		manager.set_default_application('text/plain', entry_html) # create
		manager.set_default_application('text/plain', entry_text) # update

		self.assertTrue(defaults.exists())
		self.assertEqual(defaults.read(),
			'[Default Applications]\n'
			'text/plain=test_entry_text-usercreated.desktop\n'
		)
		self.assertEqual(manager.get_default_application('text/plain'), entry_text)

		manager.set_default_application('text/plain', None)
		self.assertEqual(defaults.read(),
			'[Default Applications]\n'
		)
		self.assertNotEqual(manager.get_default_application('text/plain'), entry_text)

		## Test listing
		#~ print manager.list_applications('text/plain')
		applications = manager.list_applications('text/plain')
		self.assertGreaterEqual(len(applications), 1)
		self.assertIn(entry_text, applications)

		#~ print manager.list_applications('text/html')
		for mimetype in ('text/html', 'x-scheme-handler/http'):
			applications = manager.list_applications(mimetype)
			self.assertGreaterEqual(len(applications), 1)
			self.assertIn(entry_html, applications)

		#~ print manager.list_applications('text/plain')
		applications = manager.list_applications('x-scheme-handler/ssh')
		self.assertGreaterEqual(len(applications), 1)
		self.assertIn(entry_url, applications)

		## Increase coverage
		self.assertIsInstance(manager.get_application('webbrowser'), WebBrowser)
		self.assertIsInstance(manager.get_application('startfile'), StartFile)
		self.assertIsNone(manager.get_application('non_existing_application'))



@tests.slowTest
class TestCustomTools(tests.TestCase):

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

		path = self.get_tmp_name()
		notebook = tests.new_notebook(fakedir=path)
		page = notebook.get_page(Path('Test:Foo'))
		pageview = StubPageView()
		args = (notebook, page, pageview)

		tmpfile = TmpFile('tmp-page-source.txt').path
		dir = notebook.dir

		tool = CustomToolDict()
		tool.update( {
			'Name': 'Test',
			'Comment': 'Test 1 2 3',
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


#~ class TestOpenWithMenu(tests.TestCase):
class Foo(object): # FIXME - this test blocks on full test runs ??

	def runTest(self):
		# Create some custom entries - should NOT appear in menu
		manager = ApplicationManager()
		entry_text = manager.create('text/plain', 'Test_Entry_Text', 'test_text 123')
		entry_url = manager.create('x-scheme-handler/ssh', 'Test_Entry_SSH', 'test_ssh %u')
		for entry in (entry_text, entry_url):
			self.assertTrue(entry.file.exists())
			self.assertEqual(manager.get_application(entry.key), entry)
			self.assertTrue(entry['Desktop Entry']['NoDisplay'])
				# do not show custom items in menus

		# Mock main ui object
		ui = tests.MockObject()
		ui.windows = []

		# Check menu
		for obj, mimetype, test_entry in (
			(File('README.txt'), 'text/plain', entry_text),
			('ssh://host', 'x-scheme-handler/ssh', entry_url),
		):
			manager.set_default_application(mimetype, test_entry)

			menu = OpenWithMenu(ui, obj)
			self.assertEqual(menu.mimetype, mimetype)
			for item in menu.get_children():
				if hasattr(item, 'entry'):
					self.assertFalse(item.entry['Desktop Entry'].get('NoDisplay', False),
						msg='Entry %s should not be in menu' % item.entry)

			def test_configure_applications_dialog(dialog):
				self.assertIsInstance(dialog, CustomizeOpenWithDialog)

				# test default displays as set above
				active = dialog.default_combo.get_active()
				self.assertEqual(active, test_entry)
				self.assertEqual(
					manager.get_default_application(mimetype).key,
					test_entry.key
				)

				# test changing to system default and back
				last = len(dialog.default_combo.get_model()) - 1
				dialog.default_combo.set_active(last)
				active = dialog.default_combo.get_active()
				self.assertIsInstance(active, SystemDefault)
				default = manager.get_default_application(mimetype)
				self.assertTrue(default is None or default.key != test_entry.key)

				dialog.default_combo.set_active(0)
				active = dialog.default_combo.get_active()
				self.assertEqual(active, test_entry)
				self.assertEqual(
					manager.get_default_application(mimetype).key,
					test_entry.key
				)

				# trigger new app dialog and check new default set
				dialog.on_add_application(None)

				active = dialog.default_combo.get_active()
				self.assertEqual(active.name, 'Test New App Dialog')
				self.assertEqual(
					manager.get_default_application(mimetype).key,
					active.key
				)

			def test_new_app_dialog(dialog):
				self.assertIsInstance(dialog, AddApplicationDialog)
				dialog.form['name'] = 'Test New App Dialog'
				dialog.form['exec'] = 'Test 123'
				dialog.form['default'] = True
				entry = dialog.assert_response_ok()
				self.assertTrue(entry.file.exists())
				self.assertTrue(entry.nodisplay) # implied by default = True

				manager = ApplicationManager()
				self.assertEqual(manager.get_default_application(mimetype), entry)

			with tests.DialogContext(
				test_configure_applications_dialog,
				test_new_app_dialog
			):
				tests.gtk_activate_menu_item(menu, menu.CUSTOMIZE)


class StubPageView(object):

	def get_selection(self, format=None):
		return None

	def get_word(self, format=None):
		if format:
			return '**FooBar**'
		else:
			return 'FooBar'


if __name__ == '__main__':
	import unittest
	unittest.main()

