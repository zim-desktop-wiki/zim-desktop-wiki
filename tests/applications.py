
# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>




import tests

import os
import sys
import shutil

from gi.repository import Gtk

from zim.gui.applications import *
from zim.notebook import Path
from zim.fs import Dir, TmpFile

THUMB_SIZE_NORMAL = 128


@tests.skipIf(os.name == 'nt', 'Skip for windows')
@tests.slowTest
class TestXDGMimeInfo(tests.TestCase):

	def runTest(self):
		os.makedirs('tests/tmp/data_dir/mime/image/')
		shutil.copyfile('./tests/data/png.xml', 'tests/tmp/data_dir/mime/image/png.xml')

		dir = Dir('./data')
		file = dir.file('zim.png')
		icon = get_mime_icon(file, 128)
		self.assertIsInstance(icon, GdkPixbuf.Pixbuf)
		desc = get_mime_description(file.get_mimetype())
		self.assertIsInstance(desc, str)
		self.assertTrue(len(desc) > 5)


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
				wanted = replace(wanted, '/foo/bar', 'C:\\foo\\bar')
				wanted = replace(wanted, 'file:///foo/bar', r'file:///C:/foo/bar')

			#print app, args
			entry['Desktop Entry']['Exec'] = app
			result = entry.parse_exec(args)
			self.assertEqual(result, wanted)

			cwd, argv = entry._checkargs(None, args)
			self.assertEqual(argv, wanted)

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
		self.assertEqual(argv[0], sys.executable)
		self.assertEqual(argv[1], 'foo.py')

		sys.frozen = True
		try:
			cwd, argv = app._checkargs(None, ())
			self.assertEqual(argv, ('foo.py',))
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
			(File('file.txt'), 'text/plain'),
			('file.txt', 'text/plain'),
			('ssh://host', 'x-scheme-handler/ssh'),
			('http://host', 'x-scheme-handler/http'),
			('file.png', 'image/png'),
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

		# Check menu
		for obj, mimetype, test_entry in (
			(File('file.txt'), 'text/plain', entry_text),
			('ssh://host', 'x-scheme-handler/ssh', entry_url),
		):
			manager.set_default_application(mimetype, test_entry)

			menu = OpenWithMenu(None, obj)
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


class TestOpenFunctions(tests.TestCase):

	def setUp(self):
		import zim.gui.applications
		self.calls = []
		def mockmethod(*a):
			self.calls.append(a)

		origmethod = zim.gui.applications._open_with
		zim.gui.applications._open_with = mockmethod

		def restore():
			zim.gui.applications._open_with = origmethod
		self.addCleanup(restore)

	def testOpenFile(self):
		from zim.gui.applications import open_file, NoApplicationFoundError
		from zim.fs import adapt_from_newfs

		widget = tests.MockObject()

		with self.assertRaises(FileNotFoundError):
			open_file(widget, File('/non-existing'))

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		myfile = folder.file('test.txt')
		myfile.touch()

		manager = ApplicationManager()
		entry = manager.create('text/plain', 'test', 'test')
		manager.set_default_application('text/plain', entry)

		open_file(widget, myfile)
		self.assertEqual(self.calls[-1], (widget, entry, adapt_from_newfs(myfile), None))

		open_file(widget, myfile, mimetype='text/plain')
		self.assertEqual(self.calls[-1], (widget, entry, adapt_from_newfs(myfile), None))

		with self.assertRaises(NoApplicationFoundError):
			open_file(widget, myfile, mimetype='x-mimetype/x-with-no-application')

		# TODO: how to test file for mimetype without application?
		#       need to mock ApplicationManager to control environemnt ?

	def testOpenFolder(self):
		from zim.gui.applications import open_folder
		from zim.fs import adapt_from_newfs

		widget = tests.MockObject()

		with self.assertRaises(FileNotFoundError):
			open_folder(widget, File('/non-existing'))

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		myfolder = folder.folder('test')
		myfolder.touch()

		entry = ApplicationManager().get_fallback_filebrowser()
		open_folder(widget, myfolder)
		self.assertEqual(self.calls[-1], (widget, entry, adapt_from_newfs(myfolder), None))

	def testOpenFolderCreate(self):
		from zim.gui.applications import open_folder_prompt_create
		from zim.fs import adapt_from_newfs

		widget = tests.MockObject()
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		myfolder = folder.folder('test')
		entry = ApplicationManager().get_fallback_filebrowser()

		def answer_yes(dialog):
			dialog.answer_yes()

		def answer_no(dialog):
			dialog.answer_no()

		with tests.DialogContext(answer_no):
			open_folder_prompt_create(widget, myfolder)

		self.assertFalse(myfolder.exists())
		self.assertEqual(self.calls, [])

		with tests.DialogContext(answer_yes):
			open_folder_prompt_create(widget, myfolder)

		self.assertTrue(myfolder.exists())
		self.assertEqual(self.calls[-1], (widget, entry, adapt_from_newfs(myfolder), None))

	def testOpenUrl(self):
		from zim.gui.applications import open_url

		widget = tests.MockObject()

		with self.assertRaises(ValueError):
			open_url(widget, '/test/some/file.txt')

		for uri in (
			'file://test/some/file.txt',
			'http://example.com',
			'mailto:foo@example.com',
		):
			open_url(widget, uri)
			self.assertEqual(self.calls[-1][2], uri)

		wanted = '\\\\host\\share\\file.txt' if os.name == 'nt' else 'smb://host/share/file.txt'
		for uri in (
			'smb://host/share/file.txt',
			'\\\\host\\share\\file.txt'
		):
			open_url(widget, '\\\\host\\share\\file.txt')
			self.assertEqual(self.calls[-1][2], wanted)


if __name__ == '__main__':
	import unittest
	unittest.main()
