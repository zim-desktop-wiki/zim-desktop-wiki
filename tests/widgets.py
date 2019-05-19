
# Copyright 2011-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests


from zim.fs import File, Dir
from zim.notebook import Path
from zim.gui.widgets import *

from zim.newfs.mock import os_native_path

class TestFunctions(tests.TestCase):

	def testEncodeDecode(self):
		self.assertEqual(encode_markup_text('<foo> &bar'), '&lt;foo&gt; &amp;bar')
		self.assertEqual(decode_markup_text('&lt;foo&gt; &amp;bar'), '<foo> &bar')
		self.assertEqual(decode_markup_text('&lt;foo&gt; <b>&amp;bar</b>'), '<foo> &bar')

	# FIXME: Can't run this without pointer over Gtk window
	#def testGtkMenuPopup(self):
	#	menu = Gtk.Menu()
	#	gtk_popup_at_pointer(menu)
	#	menu.destroy()

	def testGtkMenuPopupBackward(self):
		from zim.gui.widgets import _gtk_popup_at_pointer_backward, _ref_cache
		menu = Gtk.Menu()
		_gtk_popup_at_pointer_backward(menu, None, 3)
		self.assertIn(id(menu), _ref_cache)
		menu.destroy()
		self.assertNotIn(id(menu), _ref_cache)


class TestInputEntry(tests.TestCase):

	def runTest(self):
		'''Test InputEntry widget'''
		entry = InputEntry()
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_text(), '')

		# test unicode and whitespace
		entry.set_text('\u2022 foo   ')
		text = entry.get_text()
		self.assertTrue(isinstance(text, str))
		self.assertEqual(text, '\u2022 foo')
		self.assertTrue(entry.get_input_valid())

		# test set invalid + change
		entry.set_input_valid(False)
		self.assertFalse(entry.get_input_valid())
		entry.set_text('foo bar')
		self.assertTrue(entry.get_input_valid())

		# test invalid but now with allow_empty=False
		entry = InputEntry(allow_empty=False)
		self.assertFalse(entry.get_input_valid())
		entry.set_text('foo bar')
		self.assertTrue(entry.get_input_valid())
		entry.set_text('')
		self.assertFalse(entry.get_input_valid())

		# and with a function
		entry = InputEntry(check_func=lambda text: text.startswith('a'))
		self.assertFalse(entry.get_input_valid())
		entry.set_text('foo bar')
		self.assertFalse(entry.get_input_valid())
		entry.set_text('aa foo bar')
		self.assertTrue(entry.get_input_valid())
		entry.set_text('')
		self.assertFalse(entry.get_input_valid())

		# and with placeholder text
		entry = InputEntry(allow_empty=False, placeholder_text='PLACEHOLDER')
		self.assertEqual(entry.get_text(), '')
		self.assertFalse(entry.get_input_valid())
		entry.set_text('foo bar')
		self.assertEqual(entry.get_text(), 'foo bar')
		self.assertTrue(entry.get_input_valid())
		entry.set_text('')
		self.assertEqual(entry.get_text(), '')
		self.assertFalse(entry.get_input_valid())


class TestFileEntry(tests.TestCase):

	def setUp(self):
		self.notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		self.entry = FileEntry()

	def runTest(self):
		'''Test FileEntry widget'''
		from zim.fs import adapt_from_newfs, Dir
		dir = Dir(self.notebook.folder) # XXX

		path = Path('Foo:Bar')
		entry = self.entry
		entry.set_use_relative_paths(self.notebook, path)

		home = Dir('~')
		for file, text in (
			(home.file('zim-test.txt'), '~/zim-test.txt'),
			(dir.file('Foo/Bar/test.txt'), './test.txt'),
			(File('/test.txt'), File('/test.txt').path), # win32 save
		):
			entry.set_file(file)
			self.assertEqual(entry.get_text(), os_native_path(text))
			self.assertEqual(entry.get_file(), file)

		self.notebook.config['Notebook']['document_root'] = './notebook_document_root'
		doc_root = self.notebook.document_root
		self.assertEqual(doc_root, dir.subdir('notebook_document_root'))

		for file, text in (
			(home.file('zim-test.txt'), os_native_path('~/zim-test.txt')),
			(dir.file('Foo/Bar/test.txt'), os_native_path('./test.txt')),
			(File('/test.txt'), File('/test.txt').uri), # win32 save
			(doc_root.file('test.txt'), '/test.txt'),
		):
			entry.set_file(file)
			self.assertEqual(entry.get_text(), text)
			self.assertEqual(entry.get_file(), file)

		entry.set_use_relative_paths(self.notebook, None)

		for file, text in (
			(home.file('zim-test.txt'), os_native_path('~/zim-test.txt')),
			(dir.file('Foo/Bar/test.txt'), os_native_path('./Foo/Bar/test.txt')),
			(File('/test.txt'), File('/test.txt').uri), # win32 save
			(doc_root.file('test.txt'), '/test.txt'),
		):
			entry.set_file(file)
			self.assertEqual(entry.get_text(), text)
			self.assertEqual(entry.get_file(), file)

		entry.set_use_relative_paths(notebook=None)

		for file, text in (
			(home.file('zim-test.txt'), '~/zim-test.txt'),
			#~ (dir.file('Foo/Bar/test.txt'), './test.txt'),
			(File('/test.txt'), File('/test.txt').path), # win32 save
		):
			entry.set_file(file)
			self.assertEqual(entry.get_text(), text)
			self.assertEqual(entry.get_file(), file)


class TestPageEntry(tests.TestCase):

	entryklass = PageEntry

	def setUp(self):
		self.notebook = self.setUpNotebook(content={
			'Test:foo': 'test 123',
			'Test:link': '[[:Placeholder]]', # link
			'Test:foo:bar': 'test 123',
			'Test:bar': 'test 123',
			'Bar': 'test 123',
			'Maßnahmen': 'test 123', # unicode
			'žžž': 'test 123' # unicde with accent
		})

		self.reference = Path('Test:foo')
		widgets_before = tests.find_widgets(Gtk.TreeView)
		self.entry = self.entryklass(self.notebook, self.reference)

		# There's no direct way to access the model that contains the final
		# completion items. There is no getter for it in Gtk.EntryCompletion.
		# Instead, walk through children of all top level windows and find the
		# view that is used to render the completion popup, that view provides
		# access to the completion model
		completion_view = (set(tests.find_widgets(Gtk.TreeView)) - set(widgets_before)).pop()
		self.completion_model = completion_view.get_model()

	def runTest(self):
		'''Test PageEntry widget'''
		entry = self.entry

		entry.set_path(Path('Test'))
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_text(), ':Test')
		self.assertEqual(entry.get_path(), Path('Test'))

		entry.set_text('placeholder')
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_path(), Path('Placeholder'))
				# unlike links, we do use placeholders when resolving pages

		entry.set_text('non existing')
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_path(), Path('Test:non existing'))

		entry.set_text('bar')
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_path(), Path('Test:bar'))

		entry.set_text('+bar')
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_path(), Path('Test:foo:bar'))

		entry.set_text(':bar')
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_path(), Path('Bar'))

		for text, wanted in (
			('', []),
			('+', ['+bar']),
			('+B', ['+bar']),
			('+Bar', ['+bar']),
			('+T', []),
			(':', [':Bar', ':Maßnahmen', ':Placeholder', ':Test', ':žžž']),
			('b', ['bar', '+bar', ':Bar']),
			('Test:', ['Test:bar', 'Test:foo', 'Test:link']),
			('Maß', ['Maßnahmen']),
			(':Maß', [':Maßnahmen']),
			('ž', ['žžž']),
		):
			# Take into account that extending the string does not reset the
			# model but just filters in the widget - so we reset for each string
			entry.set_text('')
			entry.update_completion()
			entry.set_text(text)
			entry.update_completion()
			self.assertTrue(entry.get_input_valid())
			self.assertEqual([r[0] for r in self.completion_model], wanted)


class TestNamespaceEntry(TestPageEntry):

	entryklass = NamespaceEntry

	def runTest(self):
		'''Test NamespaceEntry widget'''
		entry = self.entry
		entry.set_text('')

		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_text(), '')
		self.assertEqual(entry.get_path(), Path(':'))

		TestPageEntry.runTest(self)


class TestLinkEntry(TestPageEntry, TestFileEntry):

	entryklass = LinkEntry

	def runTest(self):
		'''Test LinkEntry widget'''
		TestPageEntry.runTest(self)
		TestFileEntry.runTest(self)


class TestInputForm(tests.TestCase):

	def runTest(self):
		'''Test InputForm widget'''
		inputs = [
			('foo', 'string', 'Foo'),
			('bar', 'password', 'Bar'),
			('check', 'bool', 'Check'),
			('width', 'int', 'Width', (0, 10)),
			('app', 'choice', 'Application', ['foo', 'bar', 'baz']),
			('page', 'page', 'Page'),
			('namespace', 'namespace', 'Namespace'),
			#~ ('link', 'link', 'Link'),
			('file', 'file', 'File'),
			('image', 'image', 'Image'),
			('folder', 'dir', 'Folder')
		]

		values1 = {
			'foo': '',
			'bar': 'dus',
			'check': True,
			'width': 1,
			'app': 'foo',
			'page': ':Foo:bar:Baz', # explicit string input
			'namespace': ':Foo:bar:Baz',
			#~ 'link': '+Baz',
			'file': '/foo/bar',
			'image': '/foo/bar.png',
			'folder': '/foo/bar',
		}

		values2 = {
			'foo': 'tja',
			'bar': 'hmm',
			'check': False,
			'width': 3,
			'app': 'bar',
			'page': Path(':Dus:Baz'), # explicit Path input
			'namespace': Path(':Dus:Baz'),
			#~ 'link': ':Foo',
			'file': '/foo/bar/baz',
			'image': '/foo.png',
			'folder': '/foo/bar/baz',
		}

		def assertEqual(U, V):
			self.assertEqual(set(U.keys()), set(V.keys()))

			for k, v in list(V.items()):
				if isinstance(U[k], Path) and isinstance(v, str):
					v = Path(v)
				elif isinstance(U[k], File) and isinstance(v, str):
					v = File(v)
				elif isinstance(U[k], Dir) and isinstance(v, str):
					v = Dir(v)

				self.assertEqual(U[k], v)

		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		form = InputForm(inputs, values1, notebook=notebook)

		for input in inputs:
			name = input[0]
			self.assertTrue(form.widgets[name], 'Missing input "%s"' % name)

		assertEqual(form, values1)

		form.update(values2)

		assertEqual(form, values2)

		config = {}
		config.update(form)
		assertEqual(config, values2)

		form.show_all()
		form.focus_first()
		i = 0
		while form.focus_next():
			i += 1
		self.assertEqual(i, 9)


@tests.slowTest
class TestFileDialog(tests.TestCase):
	## Something weird in how the filechooser works internally
	## need a lot of gtk_process_events() to get it work OK in test
	## and still it fails at random :(
	## Maybe fixes in Gtk3 - let's see if we encounter more failures

	def runTest(self):
		tmp_dir = Dir(self.create_tmp_dir())

		for name in ('test1.txt', 'test2.txt', 'test3.txt'):
			tmp_dir.file(name).write('test 123')

		tmp_dir.subdir('folder1').touch()

		# Single file
		file = tmp_dir.file('test1.txt')
		self.assertTrue(file.exists())

		dialog = FileDialog(None, 'Test')
		self.assertIsNone(dialog.get_file())

		dialog.set_file(file)
		tests.gtk_process_events()
		dialog.set_file(file)
		tests.gtk_process_events()
		dialog.set_file(file)
		tests.gtk_process_events()

		myfile = dialog.get_file()
		self.assertIsInstance(myfile, File)
		self.assertEqual(myfile.uri, file.uri)

		dialog.assert_response_ok()
		self.assertIsInstance(dialog.result, File)
		self.assertEqual(dialog.result.uri, file.uri)

		# Multiple files
		file1 = tmp_dir.file('test1.txt')
		file2 = tmp_dir.file('test2.txt')
		self.assertTrue(file1.exists())
		self.assertTrue(file2.exists())

		dialog = FileDialog(None, 'Test', multiple=True)
		assert dialog.filechooser.select_uri(file1.uri)
		assert dialog.filechooser.select_uri(file2.uri)
		tests.gtk_process_events()

		self.assertRaises(AssertionError, dialog.get_file)

		files = dialog.get_files()
		self.assertTrue(all(isinstance(f, File) for f in files))
		#~ self.assertEqual([f.uri for f in files], [file1.uri, file2.uri]) -- TODO

		## FIXME, fails for unclear reason on windows under msys
		#dialog.assert_response_ok()
		#self.assertIsInstance(dialog.result, list)

		# Select folder
		folder = tmp_dir.subdir('folder1')
		self.assertTrue(folder.exists())

		dialog = FileDialog(None, 'Test', action=Gtk.FileChooserAction.SELECT_FOLDER)
		assert dialog.filechooser.select_uri(folder.uri)
		tests.gtk_process_events()
		assert dialog.filechooser.select_uri(folder.uri)
		tests.gtk_process_events()
		assert dialog.filechooser.select_uri(folder.uri)
		tests.gtk_process_events()

		myfolder = dialog.get_dir()
		self.assertIsInstance(myfolder, Dir)
		self.assertEqual(myfolder.uri, folder.uri)

		dialog.assert_response_ok()
		self.assertIsInstance(dialog.result, Dir)


		# TODO test adding filters
		# TODO test preview
		# TODO test remember_folder
