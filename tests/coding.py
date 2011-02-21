
from tests import TestCase

import os
import copy


class TestCoding(TestCase):
	'''This test case enforces some coding style items'''

	def __init__(self, *a):
		self._code_files = []
		TestCase.__init__(self, *a)

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
				if 'coding.py' in files:
					files.remove('coding.py') # Skip this file itself
				for basename in files:
					if basename.endswith('.py'):
						file = dir + '/' + basename
						#print 'READING', file
						fh = open(file)
						self._code_files.append((file, fh.read()))
						fh.close()

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
			in_comment = False
			n = 0
			for line in code.splitlines():
				n += 1
				line = line.lstrip()
				if line.startswith('from __future__ ') \
				and 'with_statement' in line.split():
					import_seen = True
				elif in_comment:
					if line.endswith("'''"):
						in_comment = False
					else:
						pass
				elif line.startswith("'''"):
					if not line.endswith("'''"):
						in_comment = True
					else:
						pass
				elif line.startswith('with '):
					self.assertTrue(import_seen, '%s missing with_statement import from __future__ ("with" seen on line %i)' % (file, n))

