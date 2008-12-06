# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.notebook module.'''

import tests

from zim.fs import *
from zim.notebook import *

# TODO: test get_notebook and friends
# TODO: test construction of notebooks with Dir and File path arguments

class TestNotebook(tests.TestCase):

	def __init__(self, *args, **opts):
		tests.TestCase.__init__(self, *args, **opts)
		self.notebook = tests.get_test_notebook()

	def testAPI(self):
		'''Test various notebook methods'''
		# TODO now do the same with multiple stores
		self.assertEqual(
			self.notebook.get_store(':foo'), self.notebook.stores[''])
		self.assertEqual(
			self.notebook.get_stores(':foo')[0], (':foo', self.notebook.stores['']))
		self.assertTrue(
			isinstance(self.notebook.get_namespace(':Test'), Namespace))
		self.assertTrue(
			isinstance(self.notebook.get_home_page(), Page))

		# check usage of weakref
		page1 = self.notebook.get_page(':Tree:foo')
		page2 = self.notebook.get_page(':Tree:foo')
		self.assertTrue(id(page1) == id(page2))

	def testNormalizeName(self):
		'''Test normalizing page names'''
		for name, norm in (
			('foo:::bar', ':foo:bar'),
			('::foo:bar:', ':foo:bar'),
			('foo', ':foo'),
		): self.assertEqual(
				self.notebook.normalize_name(name), norm)
		self.assertRaises(LookupError, self.notebook.normalize_name, '')

	def testResolveName(self):
		'''Test notebook.resolve_name()'''
		for name, ns, wanted in (
			('foo:bar', ':Test', ':Test:foo:bar'),
			('Test', ':Test', ':Test'),
			('foo', ':Test', ':Test:foo'),
			(':Bar', None, ':Bar'),
			# TODO more ambigous test cases
		): self.assertEqual(self.notebook.resolve_name(name, ns), wanted)

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


class TestNamespace(tests.TestCase):

	def runTest(self):
		'''Test namespace object'''
		notebook = tests.get_test_notebook()
		namespace = notebook.get_root()
		self.assertTrue(isinstance(namespace, Namespace))

		# first test the __iter__
		wanted = [name for name in notebook.testdata_manifest if name.rfind(':') == 0]
		wanted.sort()
		pages = [page.name for page in namespace]
		pages.sort()
		self.assertEqual(pages, wanted)

		# now test walk()
		wanted = [name for name in notebook.testdata_manifest]
		wanted.sort()
		pages = [page.name for page in namespace.walk()]
		pages.sort()
		self.assertEqual(pages, wanted)

		# test if we are actually used as advertised
		namespace = notebook.get_page(':Test').children
		self.assertTrue(isinstance(namespace, Namespace))


#~ class Testpage(tests.TestCase):

	#~ def __init__(self, *args, **opts):
		#~ tests.TestCase.__init__(self, *args, **opts)
		#~ self.notebook = tests.get_test_notebook()

	# TODO exercise the page object a bit more...

