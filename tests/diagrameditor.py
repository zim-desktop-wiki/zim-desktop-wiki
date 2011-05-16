# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.plugins.diagrameditor import *


@tests.slowTest
@tests.skipUnless(InsertDiagramPlugin.check_dependencies_ok(), 'Missing dependencies')
class TestDiagramEditor(tests.TestCase):

	def runTest(self):
		'Test Diagram Editor plugin'
		generator = DiagramGenerator()
		generator.cleanup() # Ensure files did not exist
		text = r'''
digraph G {
	foo -> bar
	bar -> baz
	baz -> foo
}
'''
		imagefile, _ = generator.generate_image(text)
		self.assertTrue(imagefile.exists())
		generator.cleanup()
