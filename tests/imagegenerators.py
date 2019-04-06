
# Copyright 2009-2019 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests

from tests.mainwindow import setUpMainWindow
from tests.pageview import setUpPageView

from zim.formats.wiki import Dumper as WikiDumper

from gi.repository import Gtk

from zim.fs import Dir
from zim.newfs import LocalFolder
from zim.notebook import Path

from zim.plugins import PluginManager
from zim.plugins.base.imagegenerator import \
	ImageGeneratorClass, ImageGeneratorDialog, BackwardImageGeneratorObjectType

from zim.plugins.equationeditor import InsertEquationPlugin
from zim.plugins.diagrameditor import InsertDiagramPlugin
from zim.plugins.gnu_r_ploteditor import InsertGNURPlotPlugin
from zim.plugins.gnuplot_ploteditor import InsertGnuplotPlugin
from zim.plugins.scoreeditor import InsertScorePlugin
from zim.plugins.ditaaeditor import InsertDitaaPlugin
from zim.plugins.sequencediagrameditor import InsertSequenceDiagramPlugin


def assertIsPNG(file):
	with open(file.path, "rb") as fh:
		data = fh.read(8)
		assert data == b'\x89PNG\x0d\x0a\x1a\x0a', 'Not a PNG file: %s' % file.path


@tests.slowTest
class TestBackwardImageGeneratorNoPlugins(tests.TestCase):

	def testDumpWiki(self):
		attachment_dir = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		LocalFolder(tests.ZIM_DATADIR).file('zim.png').copyto(attachment_dir.file('test.png'))

		notebook = self.setUpNotebook()
		notebook.get_attachments_dir = lambda *a: attachment_dir

		pageview = setUpPageView(notebook, text='{{./test.png?type=equation}}')
		pageview.textview.get_buffer().set_modified(True)
		tree = pageview.get_parsetree()
		text = WikiDumper().dump(tree)
		self.assertEquals(text, ['{{./test.png?type=equation}}\n'])


@tests.skipUnless(InsertEquationPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestBackwardImageGeneratorWithPlugin(TestBackwardImageGeneratorNoPlugins):

	def setUp(self):
		PluginManager.load_plugin('equationeditor')

	def testInsertObjectDialog(self):
		attachment_dir = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)

		notebook = self.setUpNotebook()
		notebook.get_attachments_dir = lambda *a: attachment_dir
		page = notebook.get_page(Path('Test'))
		otype = PluginManager.insertedobjects['image+equation']

		def edit_dialog(dialog):
			self.assertIsInstance(dialog, ImageGeneratorDialog)
			dialog.set_text(r'c = \sqrt{ a^2 + b^2 }')
			dialog.update_image()
			dialog.assert_response_ok()

		with tests.DialogContext(edit_dialog):
			model = otype.new_model_interactive(None, notebook, page)
			attrib, data = otype.data_from_model(model)
			self.assertTrue(attrib['src'])

		self.assertEquals(attachment_dir.file('equation.tex').read(), r'c = \sqrt{ a^2 + b^2 }')
		assertIsPNG(attachment_dir.file('equation.png'))

	def testEditObjectDialog(self):
		attachment_dir = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		LocalFolder(tests.ZIM_DATADIR).file('zim.png').copyto(attachment_dir.file('test.png'))

		notebook = self.setUpNotebook()
		notebook.get_attachments_dir = lambda *a: attachment_dir

		pageview = setUpPageView(notebook, text='{{./test.png?type=equation}}')

		def edit_dialog(dialog):
			self.assertIsInstance(dialog, ImageGeneratorDialog)
			dialog.set_text(r'c = \sqrt{ a^2 + b^2 }')
			dialog.update_image()
			dialog.assert_response_ok()

		with tests.DialogContext(edit_dialog):
			pageview.edit_object()

		self.assertEquals(attachment_dir.file('test.tex').read(), r'c = \sqrt{ a^2 + b^2 }')
		assertIsPNG(attachment_dir.file('test.png'))

	def testNewFile(self):
		attachment_dir = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		notebook = self.setUpNotebook()
		notebook.get_attachments_dir = lambda *a: attachment_dir
		page = notebook.get_page(Path('Test'))

		for name in (
			'equation.png', 'equation.tex',
			'equation001.png', 'equation001.tex',
			'equation002.tex',
			'equation003.png',
			'equation004.png', 'equation004.tex',
		):
			attachment_dir.file(name).touch()


		otype = PluginManager.insertedobjects['image+equation']
		model = otype.model_from_data(notebook, page, {}, '')
		self.assertEqual(model.image_file.basename, 'equation005.png')
		self.assertEqual(model.script_file.basename, 'equation005.tex')



@tests.slowTest
class TestImageGeneratorPluginMixin(object):

	plugin = None
	object_types = None

	validinput = None
	invalidinput = None

	def testObjectTypes(self):
		PluginManager.load_plugin(self.plugin)
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))

		for name in self.object_types:
			otype = PluginManager.insertedobjects[name]
			attrib, data = otype.new_object()
			model = otype.model_from_data(notebook, page, attrib, data)
			self.assertIsNotNone(model)
			widget = otype.create_widget(model)
			self.assertIsNotNone(widget)
			attrib, data = otype.data_from_model(model)

			self.assertIsNotNone(otype.label)
			if isinstance(model, BackwardImageGeneratorObjectType):
				self.assertIsNotNone(otype.scriptname)
				self.assertIsNotNone(otype.imagefile_extension)

	def testGenerator(self):
		plugin = PluginManager.load_plugin(self.plugin)
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))

		generator_classes = list(plugin.discover_classes(ImageGeneratorClass))
		assert len(generator_classes) == 1
		generator_class = generator_classes[0]

		for name in self.object_types:
			if name.startswith('image+'):
				backward_otype = PluginManager.insertedobjects[name]
				break
		else:
			backward_otype = None

		# Input OK
		generator = generator_class(plugin, notebook, page)
		generator.cleanup() # ensure files did not yet exist
		imagefile, logfile = generator.generate_image(self.validinput)
		if imagefile.path.endswith('.png'):
			assertIsPNG(imagefile)
		# else: TODO other types

		if backward_otype:
			self.assertTrue(imagefile.basename.endswith(backward_otype.imagefile_extension))
		self.assertTrue(imagefile.exists())
		if logfile is not None:
			self.assertTrue(logfile.exists())

		# Cleanup
		generator.cleanup()
		self.assertFalse(imagefile.exists())
		if logfile is not None:
			self.assertFalse(logfile.exists())

		# Input NOK
		if self.invalidinput is not None:
			generator = generator_class(plugin, notebook, page)
			imagefile, logfile = generator.generate_image(self.invalidinput)
			self.assertIsNone(imagefile)
			if logfile is not None:
				self.assertTrue(logfile.exists())


@tests.skipUnless(InsertEquationPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestEquationEditor(TestImageGeneratorPluginMixin, tests.TestCase):

	plugin = 'equationeditor'
	object_types = ['image+equation']

	validinput = r'''
c = \sqrt{ a^2 + b^2 }

\int_{-\infty}^{\infty} \frac{1}{x} \, dx

f(x) = \sum_{n = 0}^{\infty} \alpha_n x^n

x_{1,2}=\frac{-b\pm\sqrt{\color{Red}b^2-4ac}}{2a}

\hat a  \bar b  \vec c  x'  \dot{x}  \ddot{x}
'''
	invalidinput = r'\int_{'

	def testLatexExport(self):
		from zim.formats.wiki import Parser as WikiParser
		from zim.formats.latex import Dumper as LatexDumper

		folder = self.setUpFolder()
		folder.file('equation001.tex').write('a + b')
		# equation002.tex does not exist - check fallback to image

		wiki = '{{./equation001.png?type=equation}}\n{{./equation002.png?type=equation}}\n'
		wanted = '\\begin{math}\na + b\n\\end{math}\n\n\\includegraphics[]{./equation002.png}\n\n'

		linker = tests.MockObject()
		linker.resolve_source_file = lambda name: folder.file(name)
		linker.img = lambda name: name

		tree = WikiParser().parse(wiki)
		latex = LatexDumper(linker).dump(tree)

		self.assertEquals(latex, wanted.splitlines(True))


@tests.skipUnless(InsertDiagramPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestDiagramEditor(TestImageGeneratorPluginMixin, tests.TestCase):

	plugin = 'diagrameditor'
	object_types = ['image+diagram']

	validinput = r'''
digraph G {
	foo -> bar
	bar -> baz
	baz -> foo
}
'''
	invalidinput = r'sdf sdfsdf sdf'


@tests.skipUnless(InsertGNURPlotPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestGNURPlotEditor(TestImageGeneratorPluginMixin, tests.TestCase):

	plugin = 'gnu_r_ploteditor'
	object_types = ['image+gnu_r_plot']

	validinput = r'''
x = seq(-4,4,by=0.01)
y = sin(x) + 1
plot(x,y,type='l')
'''
	invalidinput = r'sdf sdfsdf sdf'



@tests.skipUnless(InsertGnuplotPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestGnuplotEditor(TestImageGeneratorPluginMixin, tests.TestCase):

	plugin = 'gnuplot_ploteditor'
	object_types = ['image+gnuplot']

	validinput = r'plot sin(x), cos(x)'
	invalidinput = r'sdf sdfsdf sdf'


@tests.skipUnless(InsertScorePlugin.check_dependencies_ok(), 'Missing dependencies')
class TestScoreEditor(TestImageGeneratorPluginMixin, tests.TestCase):

	plugin = 'scoreeditor'
	object_types = ['image+score']

	validinput = r'''
\version "2.18.2"
\relative c {
        \clef bass
        \key d \major
        \time 4/4

        d4 a b fis
        g4 d g a
}
'''
	invalidinput = r'sdf sdfsdf sdf'


@tests.skipUnless(InsertDitaaPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestDitaaEditor(TestImageGeneratorPluginMixin, tests.TestCase):

	plugin = 'ditaaeditor'
	object_types = ['image+ditaa']

	def setUp(self):
		self.validinput = r'''
+--------+   +-------+    +-------+
|        | --+ ditaa +--> |       |
|  Text  |   +-------+    |diagram|
|Document|   |!magic!|    |       |
|     {d}|   |       |    |       |
+---+----+   +-------+    +-------+
    :                         ^
    |       Lots of work      |
    +-------------------------+
'''
		self.invalidinput = None # ditaa seems to render anything ...


@tests.skipUnless(InsertSequenceDiagramPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestSequenceDiagramEditor(TestImageGeneratorPluginMixin, tests.TestCase):

	plugin = 'sequencediagrameditor'
	object_types = ['image+seqdiagram']

	def setUp(self):
		self.validinput = r'''
seqdiag {
  browser  -> webserver [label = "GET /index.html"];
  browser <-- webserver;
  browser  -> webserver [label = "POST /blog/comment"];
              webserver  -> database [label = "INSERT comment"];
              webserver <-- database;
  browser <-- webserver;
}
'''
		self.invalidinput = 'sdfsdf sdfsdf'
