# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.notebook module.'''

import unittest

from zim.fs import *
from zim.notebook import *

class TestTemplate(unittest.TestCase):

#	def setUp(self):
#		self.template = ...

	def testNormPagename(self):
		notebook = Notebook(Dir('.'))
		for name, norm in (
			('foo:::bar', ':foo:bar'),
			('::foo:bar:', ':foo:bar'),
			('foo', ':foo'),
		):
			self.assertEqual(notebook.norm_pagename(name), norm)

if __name__ == '__main__':
	unittest.main()


