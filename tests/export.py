
# Copyright 2009-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

import os

from gi.repository import Gtk

from functools import partial

from zim.config import data_file, SectionedConfigDict
from zim.notebook import Path, Page, Notebook, init_notebook, \
	interwiki_link, get_notebook_list, NotebookInfo
from zim.templates import list_templates

from zim.main import ExportCommand, UsageError

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

from zim.fs import File as OldFile
from zim.fs import Dir as OldDir
from zim.newfs import File, Folder, FilePath


def md5(f):
	return _md5(f.raw())



class TestMultiFileLayout(tests.TestCase):

	#  dir/
	#   `--> _resources/
	#   `--> page.html
	#   `--> page/
	#         `--> attachment.png

	def runTest(self):
		dir = self.setUpFolder()
		rdir = dir.folder('_resources')


		layout = MultiFileLayout(dir, 'html')
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Foo'), dir.file('Foo.html'), dir.folder('Foo')),
			(Path('Foo:Bar'), dir.file('Foo/Bar.html'), dir.folder('Foo/Bar')),
		):
			self.assertEqual(layout.page_file(path), file)
			self.assertEqual(layout.attachments_dir(path), adir)

		self.assertRaises(PathLookupError, layout.page_file, Path(':'))


		layout = MultiFileLayout(dir, 'html', namespace=Path('Test'))
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Test:Foo'), dir.file('Foo.html'), dir.folder('Foo')),
			(Path('Test:Foo:Bar'), dir.file('Foo/Bar.html'), dir.folder('Foo/Bar')),
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
		tdir = self.setUpFolder()
		topfile = tdir.file('page.html')
		dir = tdir.folder('page_files')
		rdir = dir.folder('_resources')

		layout = FileLayout(topfile, Path('Test'), 'html')
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Test'), topfile, dir),
			(Path('Test:Foo'), dir.file('Foo.html'), dir.folder('Foo')),
			(Path('Test:Foo:Bar'), dir.file('Foo/Bar.html'), dir.folder('Foo/Bar')),
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
		tdir = self.setUpFolder()
		topfile = tdir.file('page.html')
		dir = tdir.folder('page_files')
		rdir = dir.folder('_resources')

		layout = SingleFileLayout(topfile, page=Path('Test'))
		self.assertEqual(layout.relative_root, dir)
		self.assertEqual(layout.resources_dir(), rdir)

		for path, file, adir in (
			(Path('Test'), topfile, dir),
			(Path('Test:Foo'), topfile, dir.folder('Foo')),
			(Path('Test:Foo:Bar'), topfile, dir.folder('Foo/Bar')),
		):
			self.assertEqual(layout.page_file(path), file)
			self.assertEqual(layout.attachments_dir(path), adir)

		self.assertRaises(PathLookupError, layout.page_file, Path(':'))
		self.assertRaises(PathLookupError, layout.page_file, Path('Foo'))



class TestLinker(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content=('foo', 'bar', 'foo:bar',))
		dir = Dir(notebook.folder.parent().folder('layout').path)

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

		extpath = 'C:\\dus.pdf' if os.name == 'nt' else '/duf.pdf'
		self.assertEqual(linker.link(extpath), FilePath(extpath).uri)

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
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		output_folder = self.setUpFolder()
		layout = MultiFileLayout(output_folder, 'html')
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
		self.assertIsInstance(get('generator.name'), str)
		self.assertTrue(get('generator.name').startswith('Zim'))
		self.assertIsInstance(get('generator.user'), str)

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
		self.assertIsInstance(get('mypage.content'), str)
		self.assertIsInstance(get('mypage.body'), str)
		#TODO self.assertIsInstance(get('mypage.meta'), dict)


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
		self.assertIsInstance(get('h1.heading'), str)
		self.assertIsInstance(get('h1.body'), str)
		self.assertIsInstance(get('h1.content'), str)

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
		##      test setting page meta is NOT allowed

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
		selection = AllPages(self.setUpNotebook(content=tests.FULL_NOTEBOOK))
		self._test_iface(selection)

	def testSinglePage(self):
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		page = notebook.get_page(Path('Test'))
		selection = SinglePage(notebook, page)
		self._test_iface(selection)
		self.assertIsNotNone(selection.prefix)

	def testSubPages(self):
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		page = notebook.get_page(Path('Test'))
		selection = SinglePage(notebook, page)
		self._test_iface(selection)
		self.assertIsNotNone(selection.prefix)


class TestMultiFileExporter(tests.TestCase):

	def runTest(self):
		folder = self.setUpFolder()
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		pages = AllPages(notebook)

		exporter = build_notebook_exporter(folder, 'html', 'Default', index_page='Index')
		self.assertIsInstance(exporter, MultiFileExporter)
		exporter.export(pages)

		file = exporter.layout.page_file(Path('roundtrip'))
		text = file.read()
		self.assertIn('Lorem ipsum dolor sit amet', text)

		file = exporter.layout.page_file(Path('Index'))
		text = file.read()
		self.assertIn('<li><a href="./roundtrip.html" title="roundtrip" class="page">roundtrip</a></li>', text)


class TestSingleFileExporter(tests.TestCase):

	def runTest(self):
		folder = self.setUpFolder()
		file = folder.file('export.html')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		pages = AllPages(notebook)

		exporter = build_single_file_exporter(file, 'html', 'Default')
		self.assertIsInstance(exporter, SingleFileExporter)
		exporter.export(pages)

		text = file.read()
		self.assertIn('Lorem ipsum dolor sit amet', text)


class TestMHTMLExporter(tests.TestCase):

	def runTest(self):
		dir = Dir(self.create_tmp_dir())
		file = dir.file('export.mht')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		pages = AllPages(notebook)

		exporter = build_mhtml_file_exporter(file, 'Default')
		self.assertIsInstance(exporter, MHTMLExporter)
		exporter.export(pages)

		text = file.read()
		self.assertIn('Lorem ipsum dolor sit amet', text)


class TestTemplateOptions(tests.TestCase):

	def runTest(self):
		dir = Dir(self.create_tmp_dir())
		file = dir.file('test.tex')
		page = Path('roundtrip')
		exporter = build_page_exporter(file, 'latex', 'Article', page)

		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		selection = SinglePage(notebook, page)

		with tests.LoggingFilter('zim.formats.latex', 'Could not find latex equation'):
			exporter.export(selection)
		result = file.read()
		#~ print result
		self.assertIn('\section{Head1}', result) # this implies that document_type "article" was indeed used


class TestExportFormat(object):

	def runTest(self):
		output_folder = self.setUpFolder()
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)

		i = 0
		print('')
		for template, file in list_templates(self.format):
			#print 'Testing template: %s' % template
			pages = AllPages(notebook) # TODO - sub-section ?
			exporter = build_notebook_exporter(output_folder.folder(template), self.format, template)
			self.assertIsInstance(exporter, MultiFileExporter)

			with tests.LoggingFilter('zim.formats.latex', 'Could not find latex equation'):
				exporter.export(pages)

			file = exporter.layout.page_file(Path('roundtrip'))
			text = file.read()
			self.assertIn('Lorem ipsum dolor sit amet', text)

			i += 1

		if self.format in ('html', 'latex'):
			self.assertTrue(i >= 3) # Ensure we actually tested something ..


class TestExportFormatHtml(TestExportFormat, tests.TestCase):
	format = 'html'


class TestExportFormatLatex(TestExportFormat, tests.TestCase):
	format = 'latex'


class TestExportFormatMarkDown(TestExportFormat, tests.TestCase):
	format = 'markdown'


class TestExportFormatRst(TestExportFormat, tests.TestCase):
	format = 'rst'


class TestExportCommand(tests.TestCase):

	def setUp(self):
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		self.tmpdir = OldDir(folder.path) # XXX
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
		self.assertIsInstance(exp.layout.dir, Folder)
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
		self.assertIsInstance(exp.layout.dir, Folder)
		self.assertIsInstance(exp.template, Template)
		self.assertIsNotNone(exp.document_root_url)
		self.assertIsNotNone(exp.format)
		self.assertIsNotNone(exp.index_page)


		## Full notebook, single page
		cmd = ExportCommand('export')
		cmd.parse_options(self.notebook.path,
			'--format', 'markdown',
			'--template', './tests/data/TestTemplate.html',
			'--output', self.tmpdir.file('output.md').path,
			'-s'
		)
		exp = cmd.get_exporter(None)
		self.assertIsInstance(exp, SingleFileExporter)
		self.assertIsInstance(exp.layout, SingleFileLayout)
		self.assertIsInstance(exp.layout.file, File)

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


class TestExportDialog(tests.TestCase):

	def testDialog(self):
		'''Test ExportDialog'''
		from zim.gui.exportdialog import ExportDialog, ExportDoneDialog

		dir = Dir(self.create_tmp_dir())
		notebook = self.setUpNotebook(content={'foo': 'test 123\n', 'bar': 'test 123\n'})

		window = Gtk.Window()
		window.notebook = notebook

		## Test export all pages
		dialog = ExportDialog(window, notebook, Path('foo'))
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

		file = dir.file('foo.html')
		self.assertTrue(file.exists())
		text = file.read()
		self.assertTrue('<!-- Wiki content -->' in text, 'template used')

		#~ print dialog.uistate
		self.assertEqual(dialog.uistate, window.notebook.state['ExportDialog'])
		self.assertIsInstance(dialog.uistate['output_folder'], Dir)

		## Test export single page
		dialog = ExportDialog(window, notebook, Path('foo'))
		dialog.set_page(0)

		page = dialog.get_page()
		page.form['selection'] = 'page'
		page.form['page'] = 'foo'
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

		#~ print dialog.uistate
		self.assertEqual(dialog.uistate, window.notebook.state['ExportDialog'])
		self.assertIsInstance(dialog.uistate['output_file'], OldFile)
		self.assertIsInstance(dialog.uistate['output_folder'], OldDir) # Keep this in state as well

	def testLogging(self):
		from zim.gui.exportdialog import LogContext

		mylogger = logging.getLogger('zim.export')
		foologger = logging.getLogger('zim.foo')
		log_context = LogContext()

		with tests.LoggingFilter(logger='zim', message='Test'):
			with log_context:
				mylogger.warn('Test export warning')
				mylogger.debug('Test export debug')
				foologger.warn('Test foo')

		file = log_context.file
		self.assertTrue(file.exists())
		#~ print(">>>\n", file.read(), "\n<<<")
		self.assertTrue('Test export warning' in file.read())
		self.assertFalse('Test export debug' in file.read())
		self.assertFalse('Test foo' in file.read())


class TestOverwrite(tests.TestCase):

	def testSingleFile(self):
		# TODO: run this with mock file
		# TODO: ensure template has resources
		# TODO: add attachements to test notebook

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('test.html')
		exporter = build_single_file_exporter(file, 'html', 'Default.html')

		notebook = self.setUpNotebook(content={'foo': 'test 123\n', 'bar': 'test 123\n'})
		pages = AllPages(notebook)

		# Now do it twice - should not raise for file exists
		exporter.export(pages)
		exporter.export(pages)

	def testMultiFile(self):
		# TODO: ensure template has resources
		# TODO: add attachements to test notebook

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		exporter = build_notebook_exporter(folder, 'html', 'Default.html')

		notebook = self.setUpNotebook(content={'foo': 'test 123\n', 'bar': 'test 123\n'})
		pages = AllPages(notebook)

		# Now do it twice - should not raise for file exists
		exporter.export(pages)
		exporter.export(pages)
