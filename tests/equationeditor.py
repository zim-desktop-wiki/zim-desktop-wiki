# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests
from tests import TestCase

from zim.plugins.equationeditor import *

class TestEquationEditor(TestCase):

	slowTest = True

	@classmethod
	def skipTestZim(klass):
		if not InsertEquationPlugin.check_dependencies_ok():
			return 'Missing dependencies'
		else:
			return False

	def runTest(self):
		'Test Equation Editor plugin'
		generator = EquationGenerator()
		generator.cleanup() # ensure files did not yet exist
		text = r'''
c = \sqrt{ a^2 + b^2 }

\int_{-\infty}^{\infty} \frac{1}{x} \, dx

f(x) = \sum_{n = 0}^{\infty} \alpha_n x^n

x_{1,2}=\frac{-b\pm\sqrt{\color{Red}b^2-4ac}}{2a}

\hat a  \bar b  \vec c  x'  \dot{x}  \ddot{x}
'''
		imagefile, logfile = generator.generate_image(text)
		self.assertTrue(imagefile.exists())
		self.assertTrue(logfile.exists())
		generator.cleanup()
