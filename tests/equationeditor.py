# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import tests
from tests import TestCase

from zim.plugins.equationeditor import *

class TestEquationEditor(TestCase):

	# TODO: test availability of latex / dvipng
	# implement check in plugn (also have plugin load check this)
	# have special method name to test from test.py
	# base this test on virtual application object with tryExec method

	slowTest = True

	@classmethod
	def skipTest(klass):
		if not InsertEquationPlugin.check_dependencies():
			return 'latex and/or dvipng not found'
		else:
			return False

	def runTest(self):
		'Test Equation Editor plugin'
		# TODO empty tmp dir
		# TODO make commands more silent - redirect to dev null ?
		text = r'''
c = \sqrt{ a^2 + b^2 }

\int_{-\infty}^{\infty} \frac{1}{x} \, dx

f(x) = \sum_{n = 0}^{\infty} \alpha_n x^n

x_{1,2}=\frac{-b\pm\sqrt{\color{Red}b^2-4ac}}{2a}

\hat a  \bar b  \vec c  x'  \dot{x}  \ddot{x}
'''
		generator = EquationGenerator()
		imagefile, logfile = generator.generate_image(text)
		self.assertTrue(imagefile.exists())
		self.assertTrue(logfile.exists())
