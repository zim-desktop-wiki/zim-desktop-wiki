# -*- coding: utf-8 -*-

# Copyright 2009-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

import os

from zim.fs import _md5, File, Dir

from zim.config import data_file, SectionedConfigDict
from zim.notebook import Path, Notebook, init_notebook, \
	interwiki_link, get_notebook_list, NotebookInfo
#~ from zim.exporter import Exporter, StaticLinker
#~ from zim.applications import Application
from zim.templates import list_templates

from zim.main import ExportCommand

# TODO add check that attachments are copied correctly


from functools import partial


from zim.export import *
from zim.export.layouts import *
from zim.export.linker import *
from zim.export.selections import *
from zim.export.template import *
from zim.export.exporters.files import *
from zim.export.exporters.mhtml import MHTMLExporter

from zim.templates import Template
from zim.templates.expression import ExpressionParameter, \
	ExpressionFunctionCall, ExpressionList

from zim.notebook import Path

from zim.command import UsageError


def md5(f):
	return _md5(f.raw())



class TestMultiFileLayout(tests.TestCase):

	#  dir/
	#   `--> _resources/
	#   `--> page.html
	#   `--> page/
	#         `--> attachment.png

	def runTest(self):
		dir = Dir(self.get_tmp_name())
		rdir = dir.subdir('_resources')


		layout = MultiFileLayout(dir, 'html')
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Foo'), dir.file('Foo.html'), dir.subdir('Foo')),
			(Path('Foo:Bar'), dir.file('Foo/Bar.html'), dir.subdir('Foo/Bar')),
		):
			self.assertEqual(layout.page_file(path), file)
			self.assertEqual(layout.attachments_dir(path), adir)

		self.assertRaises(PathLookupError, layout.page_file, Path(':'))


		layout = MultiFileLayout(dir, 'html', namespace=Path('Test'))
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Test:Foo'), dir.file('Foo.html'), dir.subdir('Foo')),
			(Path('Test:Foo:Bar'), dir.file('Foo/Bar.html'), dir.subdir('Foo/Bar')),
		):
			self.assertEqual(layout.page_file(path), file)
			self.assertEqual(layout.attachments_dir(path), adir)

		self.assertRaises(PathLookupError, layout.page_file, Path(':'))
		self.assertRaises(PathLookupError, layout.page_file, Path('Foo'))


class TestFileLayout(tests.TestCase):

	#  page.html
	#  page_files/
	#   `--> attachment.png
	#   `--> subpage.html
	#   `--> subpage/attachment.pdf
	#   `--> _resources/

	def runTest(self):
		tdir = Dir(self.get_tmp_name())
		topfile = tdir.file('page.html')
		dir = tdir.subdir('page_files')
		rdir = dir.subdir('_resources')

		layout = FileLayout(topfile, Path('Test'), 'html')
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Test'), topfile, dir),
			(Path('Test:Foo'), dir.file('Foo.html'), dir.subdir('Foo')),
			(Path('Test:Foo:Bar'), dir.file('Foo/Bar.html'), dir.subdir('Foo/Bar')),
		):
			self.assertEqual(layout.page_file(path), file)
			self.assertEqual(layout.attachments_dir(path), adir)

		self.assertRaises(PathLookupError, layout.page_file, Path(':'))
		self.assertRaises(PathLookupError, layout.page_file, Path('Foo'))


class TestSingleFileLayout(tests.TestCase):

	# page.html
	#  page_files/
	#   `--> attachment.png
	#   `--> subpage/attachment.pdf
	#   `--> _resources/

	def runTest(self):
		tdir = Dir(self.get_tmp_name())
		topfile = tdir.file('page.html')
		dir = tdir.subdir('page_files')
		rdir = dir.subdir('_resources')

		layout = SingleFileLayout(topfile, page=Path('Test'))
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Test'), topfile, dir),
			(Path('Test:Foo'), topfile, dir.subdir('Foo')),
			(Path('Test:Foo:Bar'), topfile, dir.subdir('Foo/Bar')),
		):
			self.assertEqual(layout.page_file(path), file)
			self.assertEqual(layout.attachments_dir(path), adir)

		self.assertRaises(PathLookupError, layout.page_file, Path(':'))
		self.assertRaises(PathLookupError, layout.page_file, Path('Foo'))



class TestLinker(tests.TestCase):

	def runTest(self):
		dir = Dir(self.get_tmp_name())
		notebook = tests.new_notebook(fakedir=dir.subdir('notebook'))
		layout = MultiFileLayout(dir.subdir('layout'), 'html')
		source = Path('foo:bar')
		output = layout.page_file(source)

		linker = ExportLinker(notebook, layout,
			source=source, output=output, usebase=True
		)

		self.assertEqual(linker.link('+dus'), './bar/dus.html')
		self.assertEqual(linker.link('dus'), './dus.html')
		self.assertEqual(linker.link('./dus.pdf'), './bar/dus.pdf')
		self.assertEqual(linker.link('../dus.pdf'), './dus.pdf')
		self.assertEqual(linker.link('../../dus.pdf'), '../dus.pdf')
		self.assertEqual(linker.link('/dus.pdf'), File('/dus.pdf').uri)

		# TODO:
		# 	img
		# 	icon
		# 	resource
		# 	resolve_source_file
		# 	page_object
		# 	file_object
		#
		#	document_root_url

		## setup environment for interwiki link
		if os.name == 'nt':
			uri = 'file:///C:/foo'
		else:
			uri = 'file:///foo'

		list = get_notebook_list()
		list.append(NotebookInfo(uri, interwiki='foo'))
		list.write()
		##

		href = interwiki_link('foo?Ideas:Task List')
		self.assertIsNotNone(href)
		self.assertEqual(linker.link('foo?Ideas:Task List'), uri + '/Ideas/Task_List.txt')





class TestExportTemplateContext(tests.TestCase):

	def setUp(self):
		tmpdir = self.get_tmp_name()
		notebook = tests.new_notebook(tmpdir + '/notebook')
		layout = MultiFileLayout(Dir(tmpdir + '/export'), 'html')
		linker_factory = partial(ExportLinker,
			notebook=notebook,
			layout=layout,
			output=layout.page_file(Path('test')),
			usebase=True
		)
		dumper_factory = get_format('html').Dumper

		title = 'Test Export'
		self.content = [notebook.get_page(Path('Test:foo'))]
		self.context = ExportTemplateContext(
			notebook, linker_factory, dumper_factory,
			title, self.content, special=None,
			home=None, up=None, prevpage=None, nextpage=None,
			links=None,
		)

	def runTest(self):
		def get(name):
			param = ExpressionParameter(name)
			return param(self.context)

		# Test context setup
		self.assertIsInstance(get('generator.name'), basestring)
		self.assertTrue(get('generator.name').startswith('Zim'))
		self.assertIsInstance(get('generator.user'), basestring)

		self.assertEqual(get('title'), 'Test Export')

		pages = list(get('pages'))
		self.assertEqual(len(pages), 1)
		self.assertTrue(all(isinstance(o, PageProxy) for o in pages))
		self.assertEqual(pages[0]._page, self.content[0])
		## TODO
		# pages
		#   content
		#   special
		#
		# navigation	- links to other export pages (if not included here)
		#	home
		#	up
		# 	prev			-- prev export file or None
		# 	next			-- next export file or None
		#
		# links			-- links to other export pages (index & plugins / ...) - sorted dict to have Index, Home first followed by plugins
		#
		#	link
		#		.name
		#		.basename


		# Test PageProxy
		self.context['mypage'] = pages[0]
		self.assertEqual(get('mypage.title'), 'Foo')
		self.assertEqual(get('mypage.name'), 'Test:foo')
		self.assertEqual(get('mypage.namespace'), 'Test')
		self.assertEqual(get('mypage.basename'), 'foo')

		self.assertEqual(get('mypage.heading'), 'Foo')
		self.assertIsInstance(get('mypage.content'), basestring)
		self.assertIsInstance(get('mypage.body'), basestring)
		self.assertIsInstance(get('mypage.properties'), dict)


		#			.links
		#			.backlinks
		#			.attachments
		#


		# Test HeadingsProxy
		mycall = ExpressionFunctionCall(
			ExpressionParameter('mypage.headings'),
			ExpressionList(),
		)
		headings = list(mycall(self.context))
		self.assertEqual(len(headings), 2)

		self.context['h1'] = headings[0]
		self.context['h2'] = headings[1]
		self.assertEqual(get('h1.level'), 1)
		self.assertEqual(get('h2.level'), 2)
		self.assertIsInstance(get('h1.heading'), basestring)
		self.assertIsInstance(get('h1.body'), basestring)
		self.assertIsInstance(get('h1.content'), basestring)

		# Test FileProxy
		#				file
		#					.basename
		#					.mtime
		#					.size
		#

		## TODO
		# options		-- dict with template options (for format)
		#
		# toc([page])			-- iter of headings in this page or all of pages
		# index([namespace])	-- index of full export job, not just in this page
		# uri(link|file)
		# resource(file)
		# anchor(page|section)
		#
		# From template:
		# range() / len() / sorted() / reversed()
		# strftime()
		# strfcal()
		#
		# test single page by "IF loop.first and loop.last"


		## TODO test all of the attributes / items accesible through the
		##      context dict are string, expressionfunction, or proxy defined in this module

		## TODO test modification of options by template ends up in context
		##      test setting other local paramters in template does NOT affect context object
		##      test setting page properties is NOT allowed

		## TODO list simple template with processor to test looping through pages




class TestPageSelections(tests.TestCase):

	def _test_iface(self, selection):
		self.assertIsNotNone(selection.name)
		self.assertIsNotNone(selection.title)
		self.assertIsNotNone(selection.notebook)
		for p in selection:
			self.assertIsInstance(p, Page)

	# TODO add alternative method to walk names for ToC
	# TODO add __len__ that gives total pages for progress
	# TODO Use collections subclass to make interface complete ?

	def testAllPages(self):
		selection = AllPages(tests.new_notebook())
		self._test_iface(selection)

	def testSinglePage(self):
		notebook = tests.new_notebook()
		page = notebook.get_page(Path('Test'))
		selection = SinglePage(notebook, page)
		self._test_iface(selection)
		self.assertIsNotNone(selection.prefix)

	def testSubPages(self):
		notebook = tests.new_notebook()
		page = notebook.get_page(Path('Test'))
		selection = SinglePage(notebook, page)
		self._test_iface(selection)
		self.assertIsNotNone(selection.prefix)


class TestMultiFileExporter(tests.TestCase):

	def runTest(self):
		dir =  Dir(self.create_tmp_dir())
		#~ dir =  VirtualDir('/test')
		notebook = tests.new_notebook(fakedir='/foo')
		pages = AllPages(notebook)

		exporter = build_notebook_exporter(dir, 'html', 'Default')
		self.assertIsInstance(exporter, MultiFileExporter)
		exporter.export(pages)

		file = exporter.layout.page_file(Path('roundtrip'))
		text =  file.read()
		self.assertIn('Lorem ipsum dolor sit amet', text)



class TestSingleFileExporter(tests.TestCase):

	def runTest(self):
		dir =  Dir(self.create_tmp_dir())
		#~ dir =  VirtualDir('/test')
		file = dir.file('export.html')
		notebook = tests.new_notebook(fakedir='/foo')
		pages = AllPages(notebook)

		exporter = build_single_file_exporter(file, 'html', 'Default')
		self.assertIsInstance(exporter, SingleFileExporter)
		exporter.export(pages)

		text =  file.read()
		self.assertIn('Lorem ipsum dolor sit amet', text)


@tests.slowTest # Slow because it uses a tmp file internally
class TestMHTMLExporter(tests.TestCase):

	def runTest(self):
		dir =  Dir(self.create_tmp_dir())
		#~ dir =  VirtualDir('/test')
		file = dir.file('export.mht')
		notebook = tests.new_notebook(fakedir='/foo')
		pages = AllPages(notebook)

		exporter = build_mhtml_file_exporter(file, 'Default')
		self.assertIsInstance(exporter, MHTMLExporter)
		exporter.export(pages)

		text =  file.read()
		self.assertIn('Lorem ipsum dolor sit amet', text)


class TestTemplateOptions(tests.TestCase):

	def runTest(self):
		dir =  Dir(self.create_tmp_dir())
		file = dir.file('test.tex')
		page = Path('roundtrip')
		exporter = build_page_exporter(file, 'latex', 'Article', page)

		notebook = tests.new_notebook(fakedir='/foo')
		selection = SinglePage(notebook, page)

		exporter.export(selection)
		result = file.read()
		#~ print result
		self.assertIn('\section{Head1}', result) # this implies that document_type "article" was indeed used

class TestExportFormat(object):

	def runTest(self):
		dir =  Dir(self.create_tmp_dir())
		#~ dir =  VirtualDir('/test')

		i = 0
		print ''
		for template, file in list_templates(self.format):
			print 'Testing template: %s' % template
			notebook = tests.new_notebook(fakedir='/foo')
			pages = AllPages(notebook) # TODO - sub-section ?
			exporter = build_notebook_exporter(dir.subdir(template), self.format, template)
			self.assertIsInstance(exporter, MultiFileExporter)
			exporter.export(pages)

			file = exporter.layout.page_file(Path('roundtrip'))
			text =  file.read()
			self.assertIn('Lorem ipsum dolor sit amet', text)

			i += 1

		if self.format in ('html', 'latex'):
			self.assertTrue(i >= 3)


class TestExportFormatHtml(TestExportFormat, tests.TestCase):
	format = 'html'


class TestExportFormatLatex(TestExportFormat, tests.TestCase):
	format = 'latex'


class TestExportFormatMarkDown(TestExportFormat, tests.TestCase):
	format = 'markdown'


class TestExportFormatRst(TestExportFormat, tests.TestCase):
	format = 'rst'



## TODO test all exports templates


#~ @tests.slowTest
#~ class TestExportTemplateResources(TestExport):
#~
	#~ data = './tests/data/templates/'
#~
	#~ options = {
		#~ 'format': 'html',
		#~ 'template': './tests/data/templates/html/Default.html'
	#~ }
#~
	#~ def runTest(self):
		#~ pass # should not run, block just in case
#~
	#~ def testExportResources(self):
		#~ '''Test export notebook to html with template resources'''
		#~ self.export()
#~
		#~ file = self.dir.file('Test/foo.html')
		#~ self.assertTrue(file.exists())
		#~ text = file.read()
		#~ self.assertTrue('src="../_resources/foo/bar.png"' in text)
		#~ self.assertTrue(self.dir.file('_resources/foo/bar.png').exists())
#~
		#~ for icon in ('checked-box',): #'unchecked-box', 'xchecked-box'):
			#~ # Template has its own checkboxes
			#~ self.assertTrue(self.dir.file('_resources/%s.png' % icon).exists())
			#~ self.assertNotEqual(
				#~ md5(self.dir.file('_resources/%s.png' % icon)),
				#~ md5(data_file('pixmaps/%s.png' % icon))
			#~ )
#~
	#~ def testListTemplates(self):
		#~ '''Assert list templates still works with resource folders present'''
		#~ import shutil
		#~ from zim.config import XDG_DATA_HOME
		#~ from zim.templates import list_templates, get_template
#~
		#~ # Make sure our template with resources is first in line
		#~ datahome = XDG_DATA_HOME.subdir('zim/templates/')
		#~ assert not datahome.exists()
		#~ shutil.copytree(self.data, datahome.path)
#~
		#~ for name, basename in list_templates('html'):
			#~ if name == 'Default':
				#~ self.assertEqual(basename, 'Default.html')
#~
		#~ template = get_template('html', 'Default')
		#~ self.assertEqual(template.file, datahome.file('html/Default.html').path)
		#~ self.assertEqual(template.resources_dir, datahome.subdir('html/Default'))
		#~ self.assertTrue(template.resources_dir.exists())



class TestExportCommand(tests.TestCase):

	def setUp(self):
		self.tmpdir = Dir(self.create_tmp_dir())
		self.notebook = self.tmpdir.subdir('notebook')
		init_notebook(self.notebook)

	def testOptions(self):
		# Only testing we get a valid exporter, not the full command,
		# because the command is very slow

		## Full notebook, minimal options
		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path)
		self.assertRaises(UsageError, cmd.get_exporter, None)

		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path,
			'--output', self.tmpdir.subdir('output').path,
		)
		exp = cmd.get_exporter(None)
		self.assertIsInstance(exp, MultiFileExporter)
		self.assertIsInstance(exp.layout, MultiFileLayout)
		self.assertIsInstance(exp.layout.dir, Dir)
		self.assertIsInstance(exp.template, Template)
		self.assertIsNone(exp.document_root_url)
		self.assertIsNotNone(exp.format)
		self.assertIsNone(exp.index_page)

		## Full notebook, full options
		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path,
			'--format', 'markdown',
			'--template', './tests/data/TestTemplate.html',
			'--output', self.tmpdir.subdir('output').path,
			'--root-url', '/foo/',
			'--index-page', 'myindex',
			'--overwrite',
		)
		exp = cmd.get_exporter(None)
		self.assertIsInstance(exp, MultiFileExporter)
		self.assertIsInstance(exp.layout, MultiFileLayout)
		self.assertIsInstance(exp.layout.dir, Dir)
		self.assertIsInstance(exp.template, Template)
		self.assertIsNotNone(exp.document_root_url)
		self.assertIsNotNone(exp.format)
		self.assertIsNotNone(exp.index_page)

		## Single page
		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path, 'Foo:Bar',
			'--output', self.tmpdir.subdir('output').path,
		)
		exp = cmd.get_exporter(Path('Foo:Bar'))
		self.assertIsInstance(exp, MultiFileExporter)
		self.assertIsInstance(exp.layout, FileLayout)
		self.assertIsInstance(exp.layout.file, File)
		self.assertIsInstance(exp.template, Template)
		self.assertIsNone(exp.document_root_url)
		self.assertIsNotNone(exp.format)
		self.assertIsNone(exp.index_page)

		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path, 'Foo:Bar',
			'--recursive',
			'--output', self.tmpdir.subdir('output').path,
		)
		exp = cmd.get_exporter(Path('Foo:Bar'))
		self.assertIsInstance(exp, MultiFileExporter)
		self.assertIsInstance(exp.layout, FileLayout)
		self.assertIsInstance(exp.layout.file, File)
		self.assertIsInstance(exp.template, Template)
		self.assertIsNone(exp.document_root_url)
		self.assertIsNotNone(exp.format)
		self.assertIsNone(exp.index_page)

		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path, 'Foo:Bar',
			'-rs',
			'--output', self.tmpdir.subdir('output').path,
		)
		exp = cmd.get_exporter(Path('Foo:Bar'))
		self.assertIsInstance(exp, SingleFileExporter)
		self.assertIsInstance(exp.layout, SingleFileLayout)
		self.assertIsInstance(exp.layout.file, File)
		self.assertIsInstance(exp.template, Template)
		self.assertIsNone(exp.document_root_url)
		self.assertIsNotNone(exp.format)

		## MHTML exporter
		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path, 'Foo:Bar',
			'-rs', '--format', 'mhtml',
			'--output', self.tmpdir.subdir('output').path,
		)
		exp = cmd.get_exporter(Path('Foo:Bar'))
		self.assertIsInstance(exp, MHTMLExporter)
		self.assertIsInstance(exp.file, File)
		self.assertIsInstance(exp.template, Template)
		self.assertIsNone(exp.document_root_url)

	@tests.slowTest
	def testExport(self):
		# Only test single page, just to show "run()" works
		file = self.notebook.file('Foo/Bar.txt')
		file.write('=== Foo\ntest 123\n')

		output = self.tmpdir.file('output.html')

		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path, 'Foo:Bar',
			'--output', output.path,
			'--template', 'tests/data/TestTemplate.html'
		)
		cmd.run()

		self.assertTrue(output.exists())
		html = output.read()
		self.assertTrue('<h1>Foo' in html)
		self.assertTrue('test 123' in html)


@tests.slowTest
class TestExportDialog(tests.TestCase):

	def testDialog(self):
		'''Test ExportDialog'''
		from zim.gui.exportdialog import ExportDialog, ExportDoneDialog

		dir = Dir(self.create_tmp_dir())

		notebook = tests.new_notebook(fakedir='/foo/bar')

		ui = tests.MockObject()
		ui.notebook = notebook
		ui.page = Path('foo')
		ui.mainwindow = None
		ui.uistate = SectionedConfigDict()

		## Test export all pages
		dialog = ExportDialog(ui)
		dialog.set_page(0)

		page = dialog.get_page()
		page.form['selection'] = 'all'
		dialog.next_page()

		page = dialog.get_page()
		page.form['format'] = 'HTML'
		page.form['template'] = 'Print'
		dialog.next_page()

		page = dialog.get_page()
		page.form['folder'] = dir
		page.form['index'] = 'INDEX_PAGE'
		with tests.DialogContext(ExportDoneDialog):
			dialog.assert_response_ok()

		file = dir.file('Test/foo.html')
		self.assertTrue(file.exists())
		text = file.read()
		self.assertTrue('<!-- Wiki content -->' in text, 'template used')
		self.assertTrue('<h1>Foo</h1>' in text)

		#~ print dialog.uistate
		self.assertEqual(dialog.uistate, ui.uistate['ExportDialog'])
		self.assertIsInstance(dialog.uistate['output_folder'], Dir)

		## Test export single page
		dialog = ExportDialog(ui)
		dialog.set_page(0)

		page = dialog.get_page()
		page.form['selection'] = 'page'
		page.form['page'] = 'Test:foo'
		dialog.next_page()

		page = dialog.get_page()
		page.form['format'] = 'HTML'
		page.form['template'] = 'Print'
		dialog.next_page()

		page = dialog.get_page()
		page.form['file'] = dir.file('SINGLE_FILE_EXPORT.html').path
		with tests.DialogContext(ExportDoneDialog):
			dialog.assert_response_ok()

		file = dir.file('SINGLE_FILE_EXPORT.html')
		self.assertTrue(file.exists())
		text = file.read()
		self.assertTrue('<!-- Wiki content -->' in text, 'template used')
		self.assertTrue('<h1>Foo</h1>' in text)

		#~ print dialog.uistate
		self.assertEqual(dialog.uistate, ui.uistate['ExportDialog'])
		self.assertIsInstance(dialog.uistate['output_file'], File)
		self.assertIsInstance(dialog.uistate['output_folder'], Dir) # Keep this in state as well

	def testLogging(self):
		from zim.gui.exportdialog import LogContext

		mylogger = logging.getLogger('zim.export')
		foologger = logging.getLogger('zim.foo')
		log_context = LogContext()

		with tests.LoggingFilter(message='Test'):
			with log_context:
				mylogger.warn('Test export warning')
				mylogger.debug('Test export debug')
				foologger.warn('Test foo')

		file = log_context.file
		self.assertTrue(file.exists())
		#~ print ">>>\n", file.read(), "\n<<<"
		self.assertTrue('Test export warning' in file.read())
		self.assertFalse('Test export debug' in file.read())
		self.assertFalse('Test foo' in file.read())


class VirtualDir(object):

	def __init__(self, path):
		self.path = path
		if '/' in path:
			x, self.basename = path.rsplit('/', 1)
		else:
			self.basename = path
		self._contents = {}

	def file(self, path):
		# TODO normalize path
		if path in self._contents:
			assert isinstance(self._contents[path], VirtualFile)
		else:
			self._contents[path] = VirtualFile(self, self.path + '/' + path)
		return self._contents[path]

	def subdir(self, path):
		# TODO normalize path
		if path in self._contents:
			assert isinstance(self._contents[path], VirtualDir)
		else:
			self._contents[path] = VirtualDir(self.path + '/' + path)
		return self._contents[path]


class VirtualFile(object):

	def __init__(self, dir, path):
		self.path = path
		if '/' in path:
			x, self.basename = path.rsplit('/', 1)
		else:
			self.basename = path
		self.dir = dir
		self._contents = []

	def write(self, text):
		self._contents.append(text)

	def writelines(self, lines):
		self._contents.extend(lines)

	def read(self):
		return ''.join(self._contents)

	def readlines(self):
		return ''.join(self._contents).splitlines(True)
