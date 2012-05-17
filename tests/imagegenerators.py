# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

from zim.fs import Dir

from zim.plugins.equationeditor import *
from zim.plugins.diagrameditor import *
from zim.plugins.gnu_r_ploteditor import *
from zim.plugins.gnuplot_ploteditor import *


@tests.slowTest
class TestGenerator(tests.TestCase):

	def _test_generator(self):
		# Check properties
		self.assertIsNotNone(self.generatorklass.type)
		self.assertIsNotNone(self.generatorklass.scriptname)
		self.assertIsNotNone(self.generatorklass.imagename)

		# Input OK
		generator = self.generatorklass()
		generator.cleanup() # ensure files did not yet exist
		imagefile, logfile = generator.generate_image(self.validinput)
		self.assertTrue(imagefile.exists())
		if generator.uses_log_file:
			self.assertTrue(logfile.exists())
		else:
			self.assertIsNone(logfile)

		# Cleanup
		generator.cleanup()
		self.assertFalse(imagefile.exists())
		if generator.uses_log_file:
			self.assertFalse(logfile.exists())

		# Input NOK
		generator = self.generatorklass()
		imagefile, logfile = generator.generate_image(self.invalidinput)
		self.assertIsNone(imagefile)
		if generator.uses_log_file:
			self.assertTrue(logfile.exists())
		else:
			self.assertIsNone(logfile)

		# Dialog OK
		attachment_dir = Dir(self.create_tmp_dir())
		dialog = self.dialogklass(MockUI(attachment_dir))
		dialog.set_text(self.validinput)
		dialog.assert_response_ok()

		# Dialog NOK
		def ok_store(dialog):
			# Click OK in the "Store Anyway" question dialog
			dialog.do_response(gtk.RESPONSE_YES)

		with tests.DialogContext(ok_store):
			dialog = self.dialogklass(MockUI(attachment_dir))
			dialog.set_text(self.invalidinput)
			dialog.assert_response_ok()

		# Check menu
		#~ plugin = self.pluginklass(MockUI())
		#~ menu = gtk.Menu()
		#~ plugin.do_populate_popup(menu, buffer, iter, image)


@tests.skipUnless(InsertEquationPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestEquationEditor(TestGenerator):

	def setUp(self):
		self.generatorklass = EquationGenerator
		self.dialogklass = InsertEquationDialog
		self.validinput = r'''
c = \sqrt{ a^2 + b^2 }

\int_{-\infty}^{\infty} \frac{1}{x} \, dx

f(x) = \sum_{n = 0}^{\infty} \alpha_n x^n

x_{1,2}=\frac{-b\pm\sqrt{\color{Red}b^2-4ac}}{2a}

\hat a  \bar b  \vec c  x'  \dot{x}  \ddot{x}
'''
		self.invalidinput = r'\int_{'

	def runTest(self):
		'Test Equation Editor plugin'
		TestGenerator._test_generator(self)


@tests.skipUnless(InsertDiagramPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestDiagramEditor(TestGenerator):

	def setUp(self):
		self.generatorklass = DiagramGenerator
		self.dialogklass = InsertDiagramDialog
		self.validinput = r'''
digraph G {
	foo -> bar
	bar -> baz
	baz -> foo
}
'''
		self.invalidinput = r'sdf sdfsdf sdf'

	def runTest(self):
		'Test Diagram Editor plugin'
		TestGenerator._test_generator(self)


@tests.skipUnless(InsertGNURPlotPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestGNURPlotEditor(TestGenerator):

	def setUp(self):
		self.generatorklass = GNURPlotGenerator
		self.dialogklass = InsertGNURPlotDialog
		self.validinput = r'''
x = seq(-4,4,by=0.01)
y = sin(x) + 1
plot(x,y,type='l')
'''
		self.invalidinput = r'sdf sdfsdf sdf'

	def runTest(self):
		'Test GNU R Plot Editor plugin'
		TestGenerator._test_generator(self)


@tests.skipUnless(InsertGNURPlotPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestGnuplotEditor(TestGenerator):

	def setUp(self):
		self.generatorklass = GnuplotGenerator
		self.dialogklass = InsertGnuplotDialog
		self.validinput = r'plot sin(x), cos(x)'
		self.invalidinput = r'sdf sdfsdf sdf'

	def runTest(self):
		'Test Gnuplot Plot Editor plugin'
		TestGenerator._test_generator(self)


class MockUI(tests.MockObject):

	def __init__(self, dir):
		self.notebook = tests.MockObject()
		self.notebook.mock_method('get_attachments_dir', dir)
		self.mainwindow = tests.MockObject()
		self.mainwindow.pageview = tests.MockObject()
