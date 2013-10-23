# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This module contains a number of meta test to check coding style
# and packaging

import tests

import os
import copy
import re

import inspect


def zim_modules():
	'''Get the all module in the zim source'''
	for file in tests.zim_pyfiles():
		name = file[:-3].replace('/', '.')
		if os.name == 'nt':
			name = name.replace('\\', '.')

		if name.endswith('.__init__'):
			name = name[:-9]

		mod = __import__(name)
		for part in name.split('.')[1:]:
			mod = getattr(mod, part)

		yield name, mod



class TestCompileAll(tests.TestCase):

	def runTest(self):
		'''Test if all modules compile'''
		for name, module in zim_modules():
			#~ print '>>', name
			self.assertIsNotNone(module)


class TestMetaData(tests.TestCase):

	def runTest(self):
		import zim
		revision = zim.get_zim_revision()
			# This call could fail if bazaar revision format changed
		self.assertTrue(isinstance(revision, basestring))


@tests.slowTest
class TestNotebookUpgrade(tests.TestCase):

	def runTest(self):
		'''Test if included notebooks are up to date'''
		from zim.fs import Dir
		from zim.notebook import Notebook
		for path in ('data/manual', 'HACKING'):
			notebook = Notebook(dir=Dir(path))
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
						file = dir.replace('\\', '/') + '/' + basename
						if file == 'tests/package.py': # skip ourselve
								continue
						#~ print 'READING', file
						fh = open(file)
						self._code_files.append((file, fh.read()))
						fh.close()

	def testWrongDependencies(self):
		'''Check clean dependencies'''
		#~ for klass in ('gobject', 'gtk', 'gio'): # TODO get rid of gobject as well

		allow_gtk = ('zim/gui/', 'zim/inc/', 'zim/plugins/', 'tests/')
		for klass in ('gtk', 'gio'):
			import_re = re.compile(r'^(import|from)\s+%s' % klass, re.M)
				# only match global imports - allow import in limitted scope
			for file, code in self.list_code():
				if os.name == 'nt':
					file = file.replace('\\', '/')
				if any(map(file.startswith, allow_gtk)):
					continue # skip
				match = import_re.search(code)
				#~ if match: print '>>>', match.group(0)
				self.assertFalse(match, '%s imports %s, this is not allowed' % (file, klass))

	def testWrongMethod(self):
		'''Check for a couple of constructs to be avoided'''
		for file, code in self.list_code():
			self.assertFalse('gtk.Entry(' in code, '%s uses gtk.Entry - use zim.gui.widgets.InputEntry instead' % file)
			self.assertFalse('get_visible(' in code, '%s uses get_visible() - use get_property() instead' % file)
			self.assertFalse('set_visible(' in code, '%s uses set_visible() - use set_property() instead' % file)
			self.assertFalse('get_sensitive(' in code, '%s uses get_sensitive() - requires Gtk >= 2.18 - use set_property() instead' % file)
			#~ self.assertFalse('connect_object(' in code, '%s uses connect_object() - use connect() instead to prevent reference leaking' % file)
			self.assertFalse('gtk.HPaned(' in code, '%s uses gtk.HPaned - use zim.gui.widgets.HPaned instead' % file)
			self.assertFalse('gtk.VPaned(' in code, '%s uses gtk.VPaned - use zim.gui.widgets.VPaned instead' % file)

			if not file.endswith('widgets.py'):
				self.assertFalse('gtk.ScrolledWindow(' in code, '%s uses gtk.ScrolledWindow - use zim.gui.widgets.ScrolledWindow instead' % file)

			if not file.endswith('clipboard.py'):
				self.assertFalse('gtk.Clipboard(' in code, '%s uses gtk.Clipboard - use zim.gui.clipboard.Clipboard instead' % file)

			if not file.endswith('config.py'):
				self.assertFalse('os.environ\[' in code, '%s uses os.environ - use zim.config.get_environ() instead' % file)


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

	def testIndenting(self):
		# FIXME need real parser to be more robust for comments, multi-line strings etc.
		# for now we just check lines after a line ending with ":"
		# assume python itself warns us for changes in the middle of a block
		white = re.compile(r'^(\s*)')
		for file, code in self.list_code():
			if file.startswith('zim/inc/'):
				continue
			lineno = 0
			start_block = False
			for line in code.splitlines():
				lineno += 1
				text = line.strip()
				def_line = text.startswith('def ') or text.startswith('class ')
				if start_block or def_line:
					m = white.match(line)
					indent = str(m.groups(1))
					self.assertFalse(' ' in indent, 'Indenting should use tabs - file: %s line %s' % (file, lineno))
				start_block = def_line and line.rstrip().endswith(':')

class TestDocumentation(tests.TestCase):

	def runTest(self):
		for modname, mod in zim_modules():
			self.assertDocumentationOK(mod, modname)
			for name, obj in self.walk_code(mod, modname):
				if not '.inc.' in name:
					self.assertDocumentationOK(obj, name)

	def walk_code(self, obj, objname):
		# Yield classes, methods, and functions top down
		for name, member in inspect.getmembers(obj):
			if name == '__class__':
				continue

			name = objname + '.' + name
			if inspect.isclass(member):
				if member.__module__ != objname:
					continue # skip imported class

				yield name, member
				for child in self.walk_code(member, name): # recurs
					yield child
			elif inspect.isfunction(member) \
			or inspect.ismethod(member):
				yield name, member

	def assertDocumentationOK(self, obj, name):
		#~ print 'CHECK docs for', name
		doc = inspect.getdoc(obj)
		if not doc:
			return # For now do not bitch about missing docs..

		# Check fields
		fields = self.parseFields(doc, name)
		if not fields:
			return

		# Check call signature for functions
		if inspect.isfunction(obj) \
		or inspect.ismethod(obj):
			# For now we do not complain about missing docs, just mismatches
			documented = set(
				fields.get('param', {}).keys() +
				fields.get('keyword', {}).keys()
			)
			if documented:
				(args, varargs, keywords, defaults) = inspect.getargspec(obj)
				defined = set(args)
				if args and args[0] in ('self', 'klass'):
					defined.discard(args[0])
				if varargs:
					defined.add(varargs)
				if keywords:
					defined.add(keywords)

				self.assertEqual(documented, defined,
					msg='Mismatch in documented parameters for %s\n'
					'Declared: %s\nDocumented: %s' %
					(name, tuple(defined), tuple(documented))
				)

		# TODO can we also check whether doc should define @returns ??

		# Check signature for @signal
		if 'signal' in fields:
			for spec in fields['signal']:
				# e.g.  "C{open-page (L{Page}, L{Path})}: Emitted when opening"
				if not re.match('^C\{[\w-]+ \(.*?\)\}:', spec):
					self.fail('Signal description in %s does not follow templates\n'
					'Is: %s\nShould be like "C{signal-name (arg1, arg2)}: description"'
					% (name, spec)
					)


	known_fields = {
		# keys are known fields, if values is True, a param is
		# required for the first ":"
		'param': True,
		'type': True,
		'keyword': True,
		'returns': False,
		'rtype': False,
		'raises': True,
		'cvar': True,
		'ivar': True,
		'todo': False,
		'note': False,
		'newfield': True,
	}
	collect_fields = ('signal',)

	def parseFields(self, doc, name):
		# Parse files same as epydoc - and check them on the fly
		fields = {}
		for line in doc.splitlines():
			m = re.match('@(\w+)\s*(.*?):', line)
			if m:
				line = line[m.end():].strip()
				field, arg = m.group(1), m.group(2)
				if field in self.known_fields:
					if self.known_fields[field]:
						if not arg:
							self.fail('Doc for %s is missing argument for @%s' % (name, field))
						else:
							if not field in fields:
								fields[field] = {}
							fields[field][arg] = line

							# special case - learn new fields
							if field == 'newfield':
								self.known_fields[arg] = False
					elif field in self.collect_fields:
						if not field in fields:
							fields[field] = []
						fields[field].append(line)
					else:
						fields[field] = line
				else:
					self.fail('Doc for %s has unknown field @%s' % (name, field))
			elif re.match('@(\w+)', line):
				self.fail('Syntax error in docs for %s\nMissing \':\' in "%s"' % (name, line))
			else:
				pass

		return fields
