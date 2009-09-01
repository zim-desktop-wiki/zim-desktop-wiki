# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import tests
from tests import TestCase

from zim.plugins.diagrameditor import *

class TestDiagramEditor(TestCase):

	slowTest = True

	@classmethod
	def skipTest(klass):
		if not InsertDiagramPlugin.check_dependencies():
			return 'GraphViz \'dot\' command not found'
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
