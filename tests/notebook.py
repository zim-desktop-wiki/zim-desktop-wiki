# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.notebook module.'''

import unittest

from zim.fs import *
from zim.notebook import *

class TestNotebook(unittest.TestCase):

#	def setUp(self):
#		self.template = ...

	def testNormalizeName(self):
		'''Test normalizing page names'''
		notebook = Notebook(Dir('.'))
		for name, norm in (
			('foo:::bar', ':foo:bar'),
			('::foo:bar:', ':foo:bar'),
			('foo', ':foo'),
		):
			self.assertEqual(notebook.normalize_name(name), norm)
