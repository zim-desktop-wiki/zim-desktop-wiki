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
		self.assertTrue(page1.valid)
		self.assertTrue(id(page2) == id(page1)) # check usage of weakref
		self.notebook.flush_page_cache(Path('Tree:foo'))
		page3 = self.notebook.get_page(Path('Tree:foo'))
		self.assertTrue(id(page3) != id(page1))
		self.assertFalse(page1.valid)

		pages = list(self.notebook.get_pagelist(Path(':')))
		self.assertTrue(len(pages) > 0)
		for page in pages:
			self.assertTrue(isinstance(page, Page))

		index = set()
		for page in self.notebook.walk():
			self.assertTrue(isinstance(page, Page))
			index.add(page.name)
		self.assertEqual(index, self.notebook.testdata_manifest)

	def testManipulate(self):
		'''Test renaming, moving and deleting pages in the notebook'''

		# check test setup OK
		for path in (Path('Test:BAR'), Path('NewPage')):
			page = self.notebook.get_page(path)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

		# check errors
		self.assertRaises(LookupError,
			self.notebook.move_page, Path('NewPage'), Path('Test:BAR'))
		self.assertRaises(PageExistsError,
			self.notebook.move_page, Path('Test:foo'), Path('TODOList'))


		for oldpath, newpath in (
			(Path('Test:foo'), Path('Test:BAR')),
			(Path('TODOList'), Path('NewPage:Foo:Bar:Baz')),
		):
			page = self.notebook.get_page(oldpath)
			text = page.dump('wiki')
			self.assertTrue(page.haschildren)

			self.notebook.move_page(oldpath, newpath)

			# newpath should exist and look like the old one
			page = self.notebook.get_page(newpath)
			self.assertTrue(page.haschildren)
			self.assertEqual(page.dump('wiki'), text)

			# oldpath should be deleted
			page = self.notebook.get_page(oldpath)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

			# let's delete the newpath again
			self.assertTrue(self.notebook.delete_page(newpath))
			page = self.notebook.get_page(newpath)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

			# delete again should silently fail
			self.assertFalse(self.notebook.delete_page(newpath))

		# check cleaning up works OK
		page = self.notebook.get_page(Path('NewPage'))
		self.assertFalse(page.haschildren)
		self.assertFalse(page.hascontent)

		# Try rename
		page = self.notebook.get_page(Path('Test:wiki'))
		self.assertTrue(page.hascontent)
		copy = page
			# we now have a copy of the page object - this is an important
			# part of the test - see if caching of page objects doesn't bite

		self.notebook.rename_page(Path('Test:wiki'), 'foo')
		page = self.notebook.get_page(Path('Test:wiki'))
		self.assertFalse(page.hascontent)
		page = self.notebook.get_page(Path('Test:foo'))
		self.assertTrue(page.hascontent)

		self.notebook.rename_page(Path('Test:foo'), 'Foo')
		page = self.notebook.get_page(Path('Test:foo'))
		self.assertFalse(page.hascontent)
		page = self.notebook.get_page(Path('Test:Foo'))
		self.assertTrue(page.hascontent)


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

	def testResolveFile(self):
		'''Test notebook.resolve_file()'''
		dir = Dir(tests.create_tmp_dir('notebook_testResolveFile'))
		path = Path('Foo:Bar')
		self.notebook.dir = dir
		self.notebook.get_store(path).dir = dir
		self.notebook.config['document_root'] = './notebook_document_root'
		doc_root = self.notebook.get_document_root()
		for link, wanted, cleaned in (
			('~/test.txt', File('~/test.txt'), '~/test.txt'),
			('file:///test.txt', File('file:///test.txt'), None),
			('file:/test.txt', File('file:///test.txt'), None),
			('file://localhost/test.txt', File('file:///test.txt'), None),
			('/test.txt', doc_root.file('test.txt'), '/test.txt'),
			('./test.txt', dir.file('Foo/Bar/test.txt'), './test.txt'),
			('../test.txt', dir.file('Foo/test.txt'), '../test.txt'),
			('../Bar/Baz/test.txt', dir.file('Foo/Bar/Baz/test.txt'), './Baz/test.txt'),
		):
			#~ print link, '>>', self.notebook.resolve_file(link, path)
			self.assertEqual(
				self.notebook.resolve_file(link, path), wanted)
			self.assertEqual(
				self.notebook.relative_filepath(wanted, path), cleaned)

		# check relative path without Path
		self.assertEqual(
			self.notebook.relative_filepath(doc_root.file('foo.txt')), '/foo.txt')
		
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
