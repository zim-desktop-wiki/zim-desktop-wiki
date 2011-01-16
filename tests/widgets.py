
from tests import TestCase, create_tmp_dir, get_test_notebook

from zim.fs import File, Dir
from zim.notebook import Path
from zim.gui.widgets import *

class TestInputEntry(TestCase):

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


class TestInputForm(TestCase):

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

		notebook = get_test_notebook()
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


class TestFileDialog(TestCase):

	slowTest = True

	def runTest(self):
		tmp_dir = create_tmp_dir('widgets_TestFileDialog')

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


