# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from tests import TestCase, create_tmp_dir, get_test_notebook, get_test_data

from subprocess import check_call

from zim.fs import *
from zim.notebook import Path, Notebook
from zim.exporter import Exporter, StaticLinker

# TODO add check that attachments are copied correctly

class TestLinker(TestCase):

	def runTest(self):
		notebook = get_test_notebook()
		notebook.get_store(Path(':')).dir = Dir('/source/dir/') # fake source dir

		linker = StaticLinker('html', notebook)
		linker.set_usebase(True) # normally set by html format module
		linker.set_path(Path('foo:bar')) # normally set by exporter
		linker.set_base(Dir('/source/dir/foo')) # normally set by exporter

		self.assertEqual(linker.page('+dus'), './bar/dus.html')
		self.assertEqual(linker.page('dus'), './dus.html')
		self.assertEqual(linker.file('./dus.pdf'), './bar/dus.pdf')
		self.assertEqual(linker.file('../dus.pdf'), './dus.pdf')
		self.assertEqual(linker.file('../../dus.pdf'), '../dus.pdf')

class TestExport(TestCase):

	slowTest = True

	options = {'format': 'html', 'template': 'Default'}

	def setUp(self):
		self.dir = Dir(create_tmp_dir('export_ExportedFiles'))

	def export(self):
		notebook = get_test_notebook()
		notebook.get_store(Path(':')).dir = Dir('/foo/bar') # fake source dir
		notebook.index.update()
		exporter = Exporter(notebook, **self.options)
		exporter.export_all(self.dir)

	def runTest(self):
		'''Test export notebook to html'''
		self.export()

		file = self.dir.file('Test/foo.html')
		self.assertTrue(file.exists())
		text = file.read()
		self.assertTrue('<!-- Wiki content -->' in text, 'template used')
		self.assertTrue('<h1>Foo</h1>' in text)


class TestExportFullOptions(TestExport):

	options = {'format': 'html', 'template': 'Default',
			'index_page': 'index', 'document_root_url': 'http://foo.org/'}

	def runTest(self):
		'''Test export notebook to html with all options'''
		TestExport.runTest(self)
		file = self.dir.file('index.html')
		self.assertTrue(file.exists())
		# print file.read() TODO check content of index


class TestExportCommandLine(TestExport):

	def export(self):
		dir = Dir(create_tmp_dir('export_SourceFiles'))
		notebook = Notebook(dir=dir)
		for name, text in get_test_data('wiki'):
			page = notebook.get_page(Path(name))
			page.parse('wiki', text)
			notebook.store_page(page)
		file = dir.file('Test/foo.txt')
		self.assertTrue(file.exists())

		check_call(['python', './zim.py', '--export', '--template=Default', dir.path, '--output', self.dir.path])

	def runTest(self):
		'''Test export notebook to html from commandline'''
		TestExport.runTest(self)

# TODO test export single page from command line
