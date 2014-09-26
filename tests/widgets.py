# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests


from zim.fs import File, Dir
from zim.notebook import Path
from zim.gui.widgets import *


class TestFunctions(tests.TestCase):

	def runTest(self):
		self.assertEqual(encode_markup_text('<foo> &bar'), '&lt;foo&gt; &amp;bar')
		self.assertEqual(decode_markup_text('&lt;foo&gt; &amp;bar'), '<foo> &bar')
		self.assertEqual(decode_markup_text('&lt;foo&gt; <b>&amp;bar</b>'), '<foo> &bar')


class TestInputEntry(tests.TestCase):

	def runTest(self):
		'''Test InputEntry widget'''
		entry = InputEntry()
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_text(), '')

		# test unicode nd whitespace
		entry.set_text(u'\u2022 foo   ')
		text = entry.get_text()
		self.assertTrue(isinstance(text, unicode))
		self.assertEqual(text, u'\u2022 foo')
		self.assertTrue(entry.get_input_valid())

		# test set invalid + change
		entry.set_input_valid(False)
		self.assertFalse(entry.get_input_valid())
		entry.set_text(u'foo bar')
		self.assertTrue(entry.get_input_valid())

		# test invalid but now with allow_empty=False
		entry = InputEntry(allow_empty=False)
		self.assertFalse(entry.get_input_valid())
		entry.set_text(u'foo bar')
		self.assertTrue(entry.get_input_valid())
		entry.set_text(u'')
		self.assertFalse(entry.get_input_valid())

		# and with a function
		entry = InputEntry(check_func=lambda text: text.startswith('a'))
		self.assertFalse(entry.get_input_valid())
		entry.set_text(u'foo bar')
		self.assertFalse(entry.get_input_valid())
		entry.set_text(u'aa foo bar')
		self.assertTrue(entry.get_input_valid())
		entry.set_text(u'')
		self.assertFalse(entry.get_input_valid())

		# and with placeholder text
		entry = InputEntry(allow_empty=False, placeholder_text='PLACEHOLDER')
		self.assertEqual(entry.get_text(), u'')
		self.assertFalse(entry.get_input_valid())
		entry.set_text(u'foo bar')
		self.assertEqual(entry.get_text(), u'foo bar')
		self.assertTrue(entry.get_input_valid())
		entry.set_text(u'')
		self.assertEqual(entry.get_text(), u'')
		self.assertFalse(entry.get_input_valid())


class TestFileEntry(tests.TestCase):

	def setUp(self):
		path = self.get_tmp_name()
		self.notebook = tests.new_notebook(fakedir=path)

		self.entry = FileEntry()

	def runTest(self):
		'''Test FileEntry widget'''
		path = Path('Foo:Bar')
		entry = self.entry
		entry.set_use_relative_paths(self.notebook, path)

		home = Dir('~')
		dir = self.notebook.dir
		for file, text in (
			(home.file('zim-test.txt'), '~/zim-test.txt'),
			(dir.file('Foo/Bar/test.txt'), './test.txt'),
			(File('/test.txt'), File('/test.txt').path), # win32 save
		):
			entry.set_file(file)
			self.assertEqual(entry.get_text(), text)
			self.assertEqual(entry.get_file(), file)

		self.notebook.config['Notebook']['document_root'] = './notebook_document_root'
		self.notebook.do_properties_changed() # parse config
		doc_root = self.notebook.document_root
		self.assertEqual(doc_root, dir.subdir('notebook_document_root'))

		for file, text in (
			(home.file('zim-test.txt'), '~/zim-test.txt'),
			(dir.file('Foo/Bar/test.txt'), './test.txt'),
			(File('/test.txt'), File('/test.txt').uri), # win32 save
			(doc_root.file('test.txt'), '/test.txt'),
		):
			entry.set_file(file)
			self.assertEqual(entry.get_text(), text)
			self.assertEqual(entry.get_file(), file)

		entry.set_use_relative_paths(self.notebook, None)

		for file, text in (
			(home.file('zim-test.txt'), '~/zim-test.txt'),
			(dir.file('Foo/Bar/test.txt'), './Foo/Bar/test.txt'),
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
		path = self.get_tmp_name()
		self.notebook = tests.new_notebook(fakedir=path)

		self.reference = Path('Test:foo')
		self.entry = self.entryklass(self.notebook, self.reference)

	def runTest(self):
		'''Test PageEntry widget'''
		entry = self.entry
		reference = self.reference

		entry.set_path(Path('Test'))
		self.assertEqual(entry.get_text(), ':Test')
		self.assertEqual(entry.get_path(), Path('Test'))

		entry.set_text('bar')
		self.assertEqual(entry.get_path(), Path('Bar')) # resolved due to placeholder

		entry.set_text('non existing')
		self.assertEqual(entry.get_path(), Path('Test:non existing'))

		entry.set_text('+bar')
		self.assertEqual(entry.get_path(), Path('Test:foo:bar'))

		entry.set_text(':bar')
		self.assertEqual(entry.get_path(), Path('Bar'))

		## Test completion
		def get_completions(entry):
			completion = entry.get_completion()
			model = completion.get_model()
			return [r[0] for r in model]

		entry.set_text('+T')
		self.assertEqual(get_completions(entry), ['+bar'])

		entry.set_text(':T')
		completions = get_completions(entry)
		self.assertTrue(len(completions) > 5 and ':Test' in completions)

		entry.set_text('T')
		self.assertTrue(len(completions) > 5 and ':Test' in completions)
		# completion now has full notebook

		entry.set_text('Test:')
		self.assertEqual(get_completions(entry), ['Test:foo', 'Test:Foo Bar', 'Test:Foo(Bar)', 'Test:tags', 'Test:wiki'])


class TestNamespaceEntry(TestPageEntry):

	entryklass = NamespaceEntry

	def runTest(self):
		'''Test NamespaceEntry widget'''
		entry = self.entry
		entry.set_text('')

		entry.do_focus_in_event(gtk.gdk.Event(gtk.gdk.FOCUS_CHANGE))
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_text(), '') # No '<Top>' or something !
		self.assertEqual(entry.get_path(), Path(':'))

		entry.do_focus_out_event(gtk.gdk.Event(gtk.gdk.FOCUS_CHANGE))
		self.assertTrue(entry.get_input_valid())
		self.assertEqual(entry.get_text(), '') # No '<Top>' or something !
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
			'page': ':foo:bar:Baz', # explicit string input
			'namespace': ':foo:bar:Baz',
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

			for k, v in V.items():
				if isinstance(U[k], Path) and isinstance(v, basestring):
					v = Path(v)
				elif isinstance(U[k], File) and isinstance(v, basestring):
					v = File(v)
				elif isinstance(U[k], Dir) and isinstance(v, basestring):
					v = Dir(v)

				self.assertEqual(U[k], v)

		notebook = tests.new_notebook()
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

	def runTest(self):
		tmp_dir = self.create_tmp_dir()

		file = File((tmp_dir, 'test.txt'))
		file.write('test 123')
		self.assertTrue(file.exists())

		dialog = FileDialog(None, 'Test')
		dialog.set_file(file)
		#~ myfile = dialog.get_file()
		#~ self.assertTrue(myfile)
		#~ self.assertTrue(myfile == file)
		#~ dialog.assert_response_ok()
		#~ self.assertTrue(dialog.result == file)

		# TODO select multiple

		# TODO select folder

		# TODO add filters
