
# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>




import tests

from tests import os_native_path

import os
import sys
import shutil

from gi.repository import Gtk

from zim.newfs import LocalFile, FilePath
from zim.gui.applications import *
from zim.gui.applications import _create_application
from zim.notebook import Path
from zim.newfs.base import xdgmime

THUMB_SIZE_NORMAL = 128


@tests.skipIf(xdgmime is None, 'No XDG mime info found')
class TestXDGMimeInfo(tests.TestCase):

	def setUp(self):
		data_dir = XDG_DATA_DIRS[0]
		tests.TEST_DATA_FOLDER.file('png.xml').copyto(data_dir.file('mime/image/png.xml'))

	def runTest(self):
		file = tests.ZIM_DATA_FOLDER.file('zim.png')
		icon = get_mime_icon(file, 128)
		self.assertIsInstance(icon, GdkPixbuf.Pixbuf)
		desc = get_mime_description(file.mimetype())
		self.assertIsInstance(desc, str)
		self.assertTrue(len(desc) > 5)


def replace(l, old, new):
	l = list(l)
	while old in l:
		i = l.index(old)
		l[i] = new
	return tuple(l)


class TestApplications(tests.TestCase):

	def testParseQuotes(self):
		# Test split quoting rules according to Destop spec
		for string, list in (
			('"foo bar" "\\"foooo bar\\"" dusss ja \'foo\'',
				['foo bar', '"foooo bar"', 'dusss', 'ja', '\'foo\'']),
			("If you don't mind me' asking", # don't use single quote escapes
				["If", "you", "don't", "mind", "me'", "asking"]),
			("C:\\some\\path here",
				["C:\\some\\path", "here"]), # Don't touch \ in this path!
			("Some stray quote \"here", # invalid, handle gracefully
				["Some", "stray", "quote", "\"here"]),
		):
			result = split_quoted_strings(string)
			self.assertEqual(result, list)

	def testDesktopFileQuoting(self):
		# From the spec:
		#
		#    Note that the general escape rule for values of type string states
		#    that the backslash character can be escaped as ("\\") as well and
		#    that this escape rule is applied before the quoting rule. As such,
		#    to unambiguously represent a literal backslash character in a
		#    quoted argument in a desktop entry file requires the use of four
		#    successive backslash characters ("\\\\")
		#
		for exec, cmd in (
			('foo bar', ['foo', 'bar']),
			('foo "two words"', ['foo', 'two words']),
			(r'foo "escapes \\\\ here \\$"', ['foo', r'escapes \ here $']),
			(r'C:\some\path here', [r'C:\some\path', 'here']), # Don't touch \ in this path!
		):
			entry = DesktopEntryDict()
			entry['Desktop Entry'].input(Exec=exec)
			self.assertEqual(entry.cmd, cmd)


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
			('foo %f', (LocalFile(os_native_path('/foo/bar')),), ('foo', os_native_path('/foo/bar'))),
			('foo %f', (FilePath(os_native_path('/foo/bar')),), ('foo', os_native_path('/foo/bar'))),
			('foo %u', (LocalFile(os_native_path('/foo/bar')),), ('foo', os_native_path('file:///foo/bar'))),
			('foo %F', (LocalFile(os_native_path('/foo/bar')),), ('foo', os_native_path('/foo/bar'))),
			('foo %U', (LocalFile(os_native_path('/foo/bar')),), ('foo', os_native_path('file:///foo/bar'))),
			('foo "%f"', (LocalFile(os_native_path('/foo/bar')),), ('foo', os_native_path('/foo/bar'))),
			('foo "file:%f"', (LocalFile(os_native_path('/foo/bar')),), ('foo', 'file:'+os_native_path('/foo/bar'))),
			('foo "file:%F"', (LocalFile(os_native_path('/foo/bar')),), ('foo', 'file:%F', os_native_path('/foo/bar'))),
			('foo "%u"', (LocalFile(os_native_path('/foo/bar')),), ('foo', os_native_path('file:///foo/bar'))),
			('foo "url:%u"', (LocalFile(os_native_path('/foo/bar')),), ('foo', 'url:'+os_native_path('file:///foo/bar'))),
			('foo "file:%U"', (LocalFile(os_native_path('/foo/bar')),), ('foo', 'file:%U', os_native_path('/foo/bar'))),
			('foo %%f', ('file',), ('foo', '%f', 'file')),
			('foo %%u', ('uri',), ('foo', '%u', 'uri')),
		):
			#print app, args
			entry['Desktop Entry']['Exec'] = app
			result = entry.parse_exec(args)
			self.assertEqual(result, wanted)

			cwd, argv = entry._checkargs(None, args)
			self.assertEqual(argv, wanted)

		entry['Desktop Entry']['Icon'] = 'xxx'
		entry.file = LocalFile(os_native_path('/foo.desktop'))
		for app, args, wanted in (
			# Test cases should be compliant with spec
			('foo %f %i', (), ('foo', '--icon', 'xxx')),
			('foo %f %k', (), ('foo', os_native_path('/foo.desktop'))),
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


class TestTerminalCommand(tests.TestCase):

	@tests.skipUnless(Application(('ls',)).tryexec(), 'Missing dependency')
	def testLookUpTerminalOK(self):
		# Using 'ls' as arbitrairy command we always expect to succeed
		import zim.gui.applications
		zim.gui.applications._terminal_commands = [('ls', '-la')]
		cmd = zim.gui.applications._get_terminal_command(['foo', '-x'])
		self.assertEqual(cmd, ('ls', '-la', 'foo', '-x'))

		app = DesktopEntryDict()
		app.update(Exec='foo -x', Terminal='true')
		cmd = app._cmd([])
		self.assertEqual(cmd, ('ls', '-la', 'foo', '-x'))

	def testLookUpTerminalNOK(self):
		import zim.gui.applications
		zim.gui.applications._terminal_commands = [('non_existing_application', '-x')]
		with self.assertRaises(TerminalLookUpError):
			cmd = zim.gui.applications._get_terminal_command(['foo', '-x'])

		app = DesktopEntryDict()
		app.update(Exec='foo -x', Terminal='true')
		with self.assertRaises(TerminalLookUpError):
			cmd = app._cmd([])


@tests.slowTest
class TestApplicationManager(tests.TestCase):

	def tearDown(self):
		ApplicationManager._defaults_app_cache.clear()

		def remove_file(path):
			#print("REMOVE", path)
			assert path.replace('\\', '/').startswith(tests.TMPDIR.replace('\\', '/'))
			if os.path.exists(path):
				os.unlink(path)

		remove_file(XDG_CONFIG_HOME.file('mimeapps.list').path)
		dir = XDG_DATA_HOME.folder('applications')
		if dir.exists():
			for file in dir.list_files():
				remove_file(file.path)

	def testGetMimeType(self):
		for obj, mimetype in (
			(LocalFile(os_native_path('/non-existent/file.txt')), 'text/plain'),
			('file.txt', 'text/plain'),
			('ssh://host', 'x-scheme-handler/ssh'),
			('http://host', 'x-scheme-handler/http'),
			('file.png', 'image/png'),
			('mailto:foo@bar.org', 'x-scheme-handler/mailto'),
		):
			self.assertEqual(get_mimetype(obj), mimetype)

	def testGetSetListApplications(self):
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
		defaults = XDG_CONFIG_HOME.file('mimeapps.list')
		self.assertEqual(
			defaults.read(),
			'[Added Associations]\n'
			'text/plain=test_entry_text-usercreated.desktop\n'
			'text/html=test_entry_html-usercreated.desktop\n'
			'x-scheme-handler/ssh=test_entry_ssh-usercreated.desktop\n'
		)

		cache = XDG_DATA_HOME.file('applications/mimeinfo.cache')
		self.assertEqual(
			cache.read(),
			'[MIME Cache]\n'
			'text/plain=test_entry_text-usercreated.desktop\n'
			'text/html=test_entry_html-usercreated.desktop\n'
			'x-scheme-handler/ssh=test_entry_ssh-usercreated.desktop\n'
		)

		default = manager.get_default_application('text/plain')
		self.assertIsInstance(default, (None.__class__, DesktopEntryFile))
			# system default or None

		manager.set_default_application('text/plain', entry_html) # create
		manager.set_default_application('text/plain', entry_text) # update

		self.assertTrue(defaults.exists())
		self.assertEqual(defaults.read(),
			'[Added Associations]\n'
			'text/plain=test_entry_text-usercreated.desktop\n'
			'text/html=test_entry_html-usercreated.desktop\n'
			'x-scheme-handler/ssh=test_entry_ssh-usercreated.desktop\n'
			'\n'
			'[Default Applications]\n'
			'text/plain=test_entry_text-usercreated.desktop\n'
		)
		self.assertEqual(manager.get_default_application('text/plain'), entry_text)

		manager.set_default_application('text/plain', None)
		self.assertEqual(defaults.read(),
			'[Added Associations]\n'
			'text/plain=test_entry_text-usercreated.desktop\n'
			'text/html=test_entry_html-usercreated.desktop\n'
			'x-scheme-handler/ssh=test_entry_ssh-usercreated.desktop\n'
			'\n'
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

	def testSetGetWithoutCache(self):
		manager = ApplicationManager()
		entry_text = manager.create('text/plain', 'Test_Entry_Text', 'test_text 123', NoDisplay=False)
		manager.set_default_application('text/plain', entry_text)
		self.assertEqual(manager.get_default_application('text/plain'), entry_text)
		manager._defaults_app_cache.clear()
		self.assertEqual(manager.get_default_application('text/plain'), entry_text)

	def testSetGetForMimeappsWithMultipleSections(self):
		# Make sure we respect the section when writing
		defaults_file = XDG_CONFIG_HOME.file('mimeapps.list')
		defaults_file.write(
			'[Default Applications]\n'
			'text/html=foo.desktop\n'
			'\n'
			'[Added Associations]\n'
			'text/plain=bar.desktop\n'
		)
		manager = ApplicationManager()
		entry_text = manager.create('text/plain', 'Test_Entry_Text', 'test_text 123', NoDisplay=False)
		manager.set_default_application('text/plain', entry_text)
		self.assertEqual(
			defaults_file.read(),
			'[Default Applications]\n'
			'text/html=foo.desktop\n'
			'text/plain=test_entry_text-usercreated.desktop\n'
			'\n'
			'[Added Associations]\n'
			'text/plain=test_entry_text-usercreated.desktop;bar.desktop\n'
		)

	def testSupportDesktopMimeappsList(self):
		orig_desktop = os.environ.get('XDG_CURRENT_DESKTOP')
		def restore_desktop():
			if orig_desktop:
				os.environ['XDG_CURRENT_DESKTOP'] = orig_desktop
			else:
				del os.environ['XDG_CURRENT_DESKTOP']
		self.addCleanup(restore_desktop)

		os.environ['XDG_CURRENT_DESKTOP'] = 'Test'
		desktopfile = XDG_CONFIG_HOME.file('test-mimeapps.list')
		defaultfile = XDG_CONFIG_HOME.file('mimeapps.list')

		dir = XDG_DATA_HOME.folder('applications')
		for basename in ('desktop-foo.desktop', 'normal-foo.desktop', 'ignore_this.desktop'):
			_create_application(dir, basename, 'test', 'test')

		desktopfile.write(
			'[Default Applications]\n'
			'text/plain=desktop-foo.desktop\n'
			'\n'
			'[Removed Associations]\n'
			'text/html=ignore_this.desktop\n'
		)
		defaultfile.write(
			'[Default Applications]\n'
			'text/plain=normal-foo.desktop\n'
			'text/html=ignore_this.desktop\n'
			'\n'
		)
		manager = ApplicationManager()

		# Test default picked up from desktop file
		self.assertEqual(manager.get_default_application('text/plain').key, 'desktop-foo')

		# Test blacklist in effect
		self.assertNotIn('ignore_this', manager.list_applications('text/plain'))

	def testSupportBackwardDefaultsList(self):
		defaultfile = XDG_CONFIG_HOME.file('mimeapps.list')
		backwardfile = XDG_DATA_HOME.file('applications/defaults.list')

		dir = XDG_DATA_HOME.folder('applications')
		for basename in ('foo.desktop', 'bar.desktop', 'ignore_this.desktop'):
			_create_application(dir, basename, 'test', 'test')

		defaultfile.write(
			'[Default Applications]\n'
			'text/html=bar.desktop\n'
			'\n'
		)
		backwardfile.write(
			'[Default Applications]\n'
			'text/plain=foo.desktop\n'
			'text/html=ignore_this.desktop\n'
			'\n'
		)

		manager = ApplicationManager()
		self.assertEqual(manager.get_default_application('text/plain').key, 'foo')
		self.assertEqual(manager.get_default_application('text/html').key, 'bar')

	def testListApplications(self):
		defaultfile = XDG_CONFIG_HOME.file('mimeapps.list')
		cachefile = XDG_DATA_HOME.file('applications/mimeinfo.cache')

		dir = XDG_DATA_HOME.folder('applications')
		for basename in ('aaa.desktop', 'bbb.desktop', 'ccc.desktop', 'ddd.desktop', 'ignore_this.desktop', 'browser.desktop'):
			_create_application(dir, basename, 'test', 'test', NoDisplay=False)
		_create_application(dir, 'do_not_list.desktop', 'test', 'test', NoDisplay=True)

		defaultfile.write(
			'[Default Applications]\n'
			'text/plain=aaa.desktop\n'
			'text/html=browser.desktop\n'
			'\n'
			'[Added Associations]\n'
			'text/plain=bbb.desktop;ccc.desktop;do_not_list.desktop\n'
			'\n'
			'[Removed Associations]\n'
			'text/plain=ignore_this.desktop\n'
		)
		cachefile.write(
			'[MIME Cache]\n'
			'text/plain=ddd.desktop;ignore_this.desktop\n'
		)

		manager = ApplicationManager()
		self.assertEqual(
			[e.key for e in manager.list_applications('text/plain')],
			['aaa', 'bbb', 'ccc', 'ddd']
		)

		# Test url scheme also falls back to text/html
		self.assertEqual(
			[e.key for e in manager.list_applications('text/html')],
			['browser']
		)
		self.assertEqual(
			[e.key for e in manager.list_applications('x-scheme-handler/http')],
			['browser']
		)



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
			(LocalFile(os_native_path('/non-existent/file.txt')), 'text/plain', entry_text),
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

		widget = tests.MockObject()

		with self.assertRaises(FileNotFoundError):
			open_file(widget, LocalFile(os_native_path('/non-existing')))

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		myfile = folder.file('test.txt')
		myfile.touch()

		manager = ApplicationManager()
		entry = manager.create('text/plain', 'test', 'test')
		manager.set_default_application('text/plain', entry)

		open_file(widget, myfile)
		self.assertEqual(self.calls[-1], (widget, entry, myfile, None))

		open_file(widget, myfile, mimetype='text/plain')
		self.assertEqual(self.calls[-1], (widget, entry, myfile, None))

		with self.assertRaises(NoApplicationFoundError):
			open_file(widget, myfile, mimetype='x-mimetype/x-with-no-application')

		# TODO: how to test file for mimetype without application?
		#       need to mock ApplicationManager to control environemnt ?

	def testOpenFolder(self):
		from zim.gui.applications import open_folder

		widget = tests.MockObject()

		with self.assertRaises(FileNotFoundError):
			open_folder(widget, LocalFile(os_native_path('/non-existing')))

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		myfolder = folder.folder('test')
		myfolder.touch()

		entry = ApplicationManager().get_fallback_filebrowser()
		open_folder(widget, myfolder)
		self.assertEqual(self.calls[-1], (widget, entry, myfolder, None))

	def testOpenFolderCreate(self):
		from zim.gui.applications import open_folder_prompt_create

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
		self.assertEqual(self.calls, [(widget, entry, myfolder, None)])

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
