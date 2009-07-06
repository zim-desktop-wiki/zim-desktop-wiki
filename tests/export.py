# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from tests import TestCase, create_tmp_dir, get_test_notebook, get_notebook_data

from subprocess import check_call

from zim.fs import *
from zim.notebook import Path, Notebook
from zim.exporter import Exporter

class TestExport(TestCase):

	slowTest = True

	def setUp(self):
		self.dir = Dir(create_tmp_dir('export_ExportedFiles'))

	def export(self):
		notebook = get_test_notebook()
		notebook.index.update()
		exporter = Exporter(notebook, format='html', template='Default')
		exporter.export_all(self.dir)

	def runTest(self):
		'''Test export notebook to html'''
		self.export()

		file = self.dir.file('Test/foo.html')
		self.assertTrue(file.exists())
		text = file.read()
		self.assertTrue('<!-- Wiki content -->' in text, 'template used')
		self.assertTrue('<h1>Foo</h1>' in text)


class TestExportCommandLine(TestExport):

	def export(self):
		dir = Dir(create_tmp_dir('export_SourceFiles'))
		notebook = Notebook(path=dir)
		for name, text in get_notebook_data('wiki'):
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
