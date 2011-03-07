# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests
from tests import TestCase

from zim.plugins.diagrameditor import *

class TestDiagramEditor(TestCase):

	slowTest = True

	@classmethod
	def skipTestZim(klass):
		if not InsertDiagramPlugin.check_dependencies_ok():
			return 'Missing dependencies'
		else:
			return False

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
