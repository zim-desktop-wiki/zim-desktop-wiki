# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.notebook module.'''

import tests

from zim.fs import *
from zim.notebook import *

# TODO: test get_notebook and friends
# TODO: test construction of notebooks with Dir and File path arguments

class TestNotebook(tests.TestCase):

	def setUp(self):
		if not hasattr(self, 'notebook'):
			self.notebook = tests.get_test_notebook()
			self.notebook.index.update()

	def testAPI(self):
		'''Test various notebook methods'''
		# TODO now do the same with multiple stores
		self.assertEqual(
			self.notebook.get_store(':foo'), self.notebook._stores[''])

		self.assertTrue(
			isinstance(self.notebook.get_home_page(), Page))

		page1 = self.notebook.get_page(Path('Tree:foo'))
		page2 = self.notebook.get_page(Path('Tree:foo'))
		self.assertTrue(id(page1) == id(page2)) # check usage of weakref

		pages = list(self.notebook.get_pagelist(Path(':')))
		self.assertTrue(len(pages) > 0)
		for page in pages:
			self.assertTrue(isinstance(page, Page))

		index = set()
		for page in self.notebook.walk():
			self.assertTrue(isinstance(page, Page))
			index.add(page.name)
		self.assertEqual(index, self.notebook.testdata_manifest)

	def testResolvePath(self):
		'''Test notebook.resolve_path()'''

		# cleaning absolute paths
		for name, wanted in (
			('foo:::bar', 'foo:bar'),
			('::foo:bar:', 'foo:bar'),
			(':foo', 'foo'),
			(':Bar', 'Bar'),
			# TODO more ambigous test cases
		): self.assertEqual(
			self.notebook.resolve_path(name), Path(wanted) )

		# resolving relative paths
		for name, ns, wanted in (
			('foo:bar', 'Test', 'Test:foo:bar'),
			('test', 'Test', 'Test'),
			('foo', 'Test', 'Test:foo'),
			('Test', 'TODOList:bar', 'Test'),
			('test:me', 'TODOList:bar', 'Test:me'),
		): self.assertEqual(
			self.notebook.resolve_path(name, Path(ns)), Path(wanted) )

		self.assertRaises(PageNameError, self.notebook.resolve_path, ':::')

#	def testResolveLink(self):
#		'''Test page.resolve_link()'''
#		page = self.notebook.get_page(':Test:foo')
#		for link, wanted in (
			#~ (':foo:bar', ('page', ':foo:bar')),
#			('foo:bar', ('page', ':Test:foo:bar')),
#			('Test', ('page', ':Test')),
#			('Test:non-existent', ('page', ':Test:non-existent')),
#			('user@domain.com', ('mailto', 'mailto:user@domain.com')),
#			('mailto:user@domain.com', ('mailto', 'mailto:user@domain.com')),
#			('http://zim-wiki.org', ('http', 'http://zim-wiki.org')),
#			('foo://zim-wiki.org', ('foo', 'foo://zim-wiki.org')),
			#~ ('file://'),
			#~ ('/foo/bar', ('file', '/foo/bar')),
			#~ ('man?test', ('man', 'test')),
#		): self.assertEqual(self.notebook.resolve_link(link, page), wanted)

	#~ def testResolveName(self):
		#~ '''Test store.resolve_name().'''
		#~ print '\n'+'='*10+'\nSTORE: %s' % self.store
#~
		#~ # First make sure basic list function is working
		#~ def list_pages(name):
			#~ for page in self.store.get_pages(name):
				#~ yield page.basename
		#~ self.assertTrue('Test' in list_pages(''))
		#~ self.assertTrue('foo' in list_pages(':Test'))
		#~ self.assertTrue('bar' in list_pages(':Test:foo'))
		#~ self.assertFalse('Dus' in list_pages(':Test:foo'))
#~
		#~ # Now test the resolving algorithm - only testing low level
		#~ # function in store, so path "anchor" does not work, search
		#~ # is strictly right to left through the namespace, if any
		#~ for link, namespace, name in (
			#~ ('BAR','Test:foo','Test:foo:bar'),
			#~ ('test',None,'Test'),
			#~ ('test','Test:foo:bar','Test'),
			#~ ('FOO:Dus','Test:foo:bar','Test:foo:Dus'),
			#~ # FIXME more ambigous test data
		#~ ):
			#~ print '-'*10+'\nLINK %s (%s)' % (link, namespace)
			#~ r = self.store.resolve_name(link, namespace=namespace)
			#~ print 'RESULT %s' % r
			#~ self.assertEqual(r, name)


class TestPath(tests.TestCase):
	'''Test path object'''

	def generator(self, name):
		return Path(name)

	def runTest(self):

		for name, namespace, basename in [
			('Test:foo', 'Test', 'foo'),
			('Test', '', 'Test'),
		]:
			path = self.generator(name)

			# test basic properties
			self.assertEqual(path.name, name)
			self.assertEqual(path.basename, basename)
			self.assertEqual(path.namespace, namespace)
			self.assertTrue(path.name in path.__repr__())

	# TODO test get / set parse tree with and without source


class TestPage(TestPath):
	'''Test page object'''

	def setUp(self):
		self.notebook = tests.get_test_notebook()

	def generator(self, name):
		return self.notebook.get_page(Path(name))
