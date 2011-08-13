# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This module contains a number of meta test to check coding style
# and packaging

import tests

import os
import copy
import re


class TestCompileAll(tests.TestCase):

	def runTest(self):
		'''Test if all modules compile'''
		for file in tests.zim_pyfiles():
			module = file[:-3].replace('/', '.')
			assert __import__(module)


@tests.slowTest
class TestNotebookUpgrade(tests.TestCase):

	def runTest(self):
		'''Test if included notebooks are up to date'''
		from zim.fs import Dir
		from zim.notebook import get_notebook
		for path in ('data/manual', 'HACKING'):
			notebook = get_notebook(Dir(path))
			self.assertTrue(not notebook.needs_upgrade)


class TestCoding(tests.TestCase):
	'''This test case enforces some coding style items'''

	def __init__(self, *a):
		self._code_files = []
		tests.TestCase.__init__(self, *a)

	def list_code(self):
		'''Return all python files as text'''
		if not self._code_files:
			self._read_code()
			assert len(self._code_files) > 10
		return copy.deepcopy(self._code_files)

	def _read_code(self):
		self._code_files = []
		for root in ('zim', 'tests'):
			for dir, dirs, files in os.walk(root):
				for basename in files:
					if basename.endswith('.py'):
						file = dir + '/' + basename
						if file == 'tests/package.py': # skip ourselve
								continue
						#~ print 'READING', file
						fh = open(file)
						self._code_files.append((file, fh.read()))
						fh.close()

	def testWrongDependencies(self):
		'''Check clean dependencies'''
		#~ for klass in ('gobject', 'gtk', 'gio'): # TODO get rid of gobject as well
		for klass in ('gtk', 'gio'):
			import_re = re.compile(r'^(import|from)\s+%s' % klass, re.M)
				# only match global imports - allow import in limitted scope
			for file, code in self.list_code():
				if file.startswith('zim/gui') \
				or file.startswith('zim/inc/') \
				or file.startswith('zim/plugins/') \
				or file.startswith('tests/'):
					continue # skip
				match = import_re.search(code)
				if match: print '>>>', match.group(0)
				self.assertFalse(match, '%s imports %s, this is not allowed' % (file, klass))

	def testWrongMethog(self):
		'''Check for a couple of constructs to be avoided'''
		for file, code in self.list_code():
			self.assertFalse('gtk.Entry(' in code, '%s uses gtk.Entry - use zim.gui.widgets.InputEntry instead' % file)
			self.assertFalse('get_visible(' in code, '%s uses get_visible() - use get_property() instead' % file)
			self.assertFalse('set_visible(' in code, '%s uses set_visible() - use set_property() instead' % file)
			self.assertFalse('get_sensitive(' in code, '%s uses get_sensitive() - requires Gtk >= 2.18 - use set_property() instead' % file)

	def testImportFuture(self):
		'''Check python 2.5 compatibility'''
		for file, code in self.list_code():
			import_seen = False
			suspect = False
			for line in code.splitlines():
				line = line.strip()
				if line.startswith('from __future__ ') \
				and 'with_statement' in line.split():
					import_seen = True
				elif line.startswith('with') and line.endswith(':'):
					suspect = True

			#~ if suspect: print file, 'uses "with" statement'

			if suspect and not import_seen:
				# Need real parsing to avoid false positives
				import tokenize
				import StringIO

				for token in tokenize.generate_tokens(StringIO.StringIO(code).readline):
					if token[0] == tokenize.NAME and token[1] == 'with':
						lineno = token[2][0]
						line = token[-1]
						self.assertTrue(import_seen, '%s missing with_statement import from __future__ ("with" seen on line %i):\n%s' % (file, lineno, line))
