# -*- coding: utf-8 -*-

# Copyright 2008,2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for basic stores modules.'''

from __future__ import with_statement

import tests

import os
import time

from zim.fs import File, Dir, FileWriteError
from zim.errors import TrashNotSupportedError
from zim.notebook import Notebook, Path, LookupError, PageExistsError
import zim.stores
from zim.formats import ParseTree


def walk(store, namespace=None):
	if namespace == None:
		namespace = Path(':')
	for page in store.get_pagelist(namespace):
		yield namespace, page
		if page.haschildren:
			for parent, child in walk(store, page): # recurs
				yield parent, child


def ascii_page_tree(store, namespace=None, level=0):
	'''Returns an ascii page tree. Used for debugging the test'''
	if namespace is None:
		namespace = store.namespace

	if namespace.isroot: basename = '<root>'
	else: basename = namespace.basename

	text = '  '*level + basename + '\n'
	level += 1
	for page in store.get_pagelist(namespace):
		if page.haschildren:
			text += ascii_page_tree(store, page, level) # recurs
		else:
			text += '  '*level + page.basename + '\n'

	return text


class FilterOverWriteWarning(tests.LoggingFilter):

	logger = 'zim.fs'
	message = 'mtime check failed'


class TestUtils(tests.TestCase):

	def testFilenameEncodeing(self):
		'''Test mapping page names to filenames'''
		import zim.fs
		realencoding = zim.fs.ENCODING
		try:
			zim.fs.ENCODING = 'utf-8'
			pagename = u'utf8:\u03b1\u03b2\u03b3'
			filename = zim.stores.encode_filename(pagename)
			self.assertEqual(filename, u'utf8/\u03b1\u03b2\u03b3')
			roundtrip = zim.stores.decode_filename(filename)
			self.assertEqual(roundtrip, pagename)

			zim.fs.ENCODING = 'ascii'
			pagename = u'utf8:\u03b1\u03b2\u03b3'
			filename = zim.stores.encode_filename(pagename)
			self.assertEqual(filename, u'utf8/%CE%B1%CE%B2%CE%B3')
			roundtrip = zim.stores.decode_filename(filename)
			self.assertEqual(roundtrip, pagename)

			zim.fs.ENCODING = 'gb2312'
			pagename = u'utf8:\u2022:\u4e2d\u6587:foo' # u2022 can not be encoded in gb2312
			filename = zim.stores.encode_filename(pagename)
			self.assertEqual(filename, u'utf8/%E2%80%A2/\u4e2d\u6587/foo')
			roundtrip = zim.stores.decode_filename(filename)
			self.assertEqual(roundtrip, pagename)
		except Exception:
			zim.fs.ENCODING = realencoding
			raise
		else:
			zim.fs.ENCODING = realencoding

		# try roundtrip with actual current encoding
		pagename = u'utf8:\u03b1\u03b2\u03b3:\u2022:\u4e2d\u6587:foo'
		filename = zim.stores.encode_filename(pagename)
		roundtrip = zim.stores.decode_filename(filename)
		self.assertEqual(roundtrip, pagename)

class TestReadOnlyStore(object):

	# This class does not inherit from TestCase itself as it is used
	# as a mixin for TestCase classes below but isn't a test case
	# in itself

	def normalize_index(self):
		'''Make sure the index conains namespaces for all page names'''
		pages = self.index.copy()
		for name in pages:
			parts = name.split(':')
			parts.pop()
			while parts:
				self.index.add(':'.join(parts))
				parts.pop()

	def testIndex(self):
		'''Test we get a proper index for the memory store'''
		names = set()
		for parent, page in walk(self.store):
			self.assertTrue(len(page.name) > 0)
			self.assertTrue(len(page.basename) > 0)
			self.assertTrue(page.namespace == parent.name)
			names.add( page.name )
		#~ import pprint
		#~ pprint.pprint(self.index)
		#~ pprint.pprint(names)
		self.assertTrue(u'utf8:\u03b1\u03b2\u03b3' in names) # Check usage of unicode
		self.assertEqual(names, self.index)


class TestStoresMemory(TestReadOnlyStore, tests.TestCase):
	'''Test the store.memory module'''

	def setUp(self):
		klass = zim.stores.get_store('memory')
		self.store = klass(path=Path(':'), notebook=Notebook())
		self.index = set()
		for name, text in tests.WikiTestData:
			self.store.set_node(Path(name), text)
			self.index.add(name)
		self.normalize_index()

	def testManipulate(self):
		'''Test moving and deleting pages in the memory store'''

		# Check we can get / store a page
		page = self.store.get_page(Path('Test:foo'))
		self.assertTrue(page.get_parsetree())
		self.assertTrue('Foo' in ''.join(page.dump('plain')))
		self.assertFalse(page.modified)
		wikitext = tests.WikiTestData.get('roundtrip')
		page.parse('wiki', wikitext)
		self.assertEqual(''.join(page.dump('wiki')), wikitext)
		self.assertTrue(page.modified)
		self.store.store_page(page)
		self.assertFalse(page.modified)
		self.assertEqual(''.join(page.dump('wiki')), wikitext)
		page = self.store.get_page(Path('Test:foo'))
		self.assertEqual(''.join(page.dump('wiki')), wikitext)


		page = self.store.get_page(Path('Test:foo'))
		text = page.dump('plain')
		newtext = ['Some new content\n']
		assert newtext != text
		self.assertEqual(page.dump('plain'), text)
		page.parse('plain', newtext)
		self.assertEqual(page.dump('plain'), newtext)
		self.assertTrue(page.modified)
		re = self.store.revert_page(page)
		self.assertFalse(re) # no return value
		self.assertEqual(page.dump('plain'), text) # object reverted
		self.assertFalse(page.modified) # no longer modified
		page = self.store.get_page(page) # new object
		self.assertEqual(page.dump('plain'), text)
		page.parse('plain', newtext)
		self.assertEqual(page.dump('plain'), newtext)
		self.store.store_page(page)
		page = self.store.get_page(page) # new object
		self.assertEqual(page.dump('plain'), newtext)

		# check revert page triggers ui object
		page._ui_object = tests.MockObject()
		self.store.revert_page(page)
		self.assertEqual(page._ui_object.mock_calls[-1][0], 'set_parsetree')

		if hasattr(page, 'source') and isinstance(page.source, File):
			# check revert also works when the actual file changed
			# (and not trigger mtime check failure)
			from tests.fs import modify_file_mtime, FilterOverWriteWarning
			page = self.store.get_page(Path('Test:foo'))
			text = page.dump('plain')
			newtext = ['Foo bar baz\n']
			othertext = ['Dus ja\n']
			assert newtext != text
			assert othertext != text
			page.parse('plain', newtext)
			modify_file_mtime(page.source.path, lambda p: open(p, 'w').writelines(othertext))
			with FilterOverWriteWarning():
				self.assertRaises(FileWriteError, self.store.store_page, page)
			self.store.revert_page(page)
			self.assertEqual(page.dump('plain'), othertext)
			page.parse('plain', newtext)
			self.store.store_page(page)
			page = self.store.get_page(page) # new object
			self.assertEqual(page.dump('plain'), newtext)

		# check test setup OK
		for path in (Path('Test:BAR'), Path('NewPage')):
			page = self.store.get_page(path)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

		# check errors
		self.assertRaises(LookupError,
			self.store.move_page, Path('NewPage'), Path('Test:BAR'))
		self.assertRaises(PageExistsError,
			self.store.move_page, Path('Test:foo'), Path('TaskList'))

		for oldpath, newpath in (
			(Path('Test:foo'), Path('Test:BAR')),
			(Path('TaskList'), Path('NewPage:Foo:Bar:Baz')),
		):
			page = self.store.get_page(oldpath)
			text = page.dump('wiki')
			self.assertTrue(page.haschildren)

			#~ print ascii_page_tree(self.store)
			self.store.move_page(oldpath, newpath)
			#~ print ascii_page_tree(self.store)

			# newpath should exist and look like the old one
			page = self.store.get_page(newpath)
			self.assertTrue(page.haschildren)
			self.assertEqual(page.dump('wiki'), text)

			# oldpath should be deleted
			page = self.store.get_page(oldpath)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

			# let's delete the newpath again
			page = self.store.get_page(newpath)
			self.assertTrue(self.store.delete_page(page))
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)
			page = self.store.get_page(newpath)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

			# delete again should silently fail
			self.assertFalse(self.store.delete_page(newpath))

		# check cleaning up works OK
		page = self.store.get_page(Path('NewPage'))
		self.assertFalse(page.haschildren)
		self.assertFalse(page.hascontent)

		# check case-sensitive move
		self.store.move_page(Path('utf8'), Path('UTF8'))
		page = self.store.get_page(Path('utf8'))
		# self.assertFalse(page.haschildren) - fails on case-insensitive FS
		self.assertFalse(Path('utf8')
			in list(self.store.get_pagelist(Path(':'))))
		self.assertTrue(Path('UTF8')
			in list(self.store.get_pagelist(Path(':'))))
		newpage = self.store.get_page(Path('UTF8'))
		self.assertTrue(newpage.haschildren)
		self.assertFalse(newpage == page)
		# TODO here we only move dir case insensitive - also test file

		# check hascontents
		page = self.store.get_page(Path('NewPage'))
		tree = ParseTree().fromstring('<zim-tree></zim-tree>')
		self.assertFalse(tree.hascontent)
		page.set_parsetree(tree)
		self.assertFalse(page.hascontent)
		self.store.store_page(page)
		page = self.store.get_page(Path('NewPage'))
		self.assertFalse(page.hascontent)

		# check trashing
		trashing = True
		try:
			page = self.store.get_page(Path('TrashMe'))
			self.assertTrue(page.haschildren)
			self.assertTrue(page.hascontent)
			self.store.trash_page(page)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)
			page = self.store.get_page(Path('TrashMe'))
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)
		except TrashNotSupportedError:
			trashing = False
			print '(trashing not supported for this store)'
			self.assertTrue(page.haschildren)
			self.assertTrue(page.hascontent)
			page = self.store.get_page(Path('TrashMe'))
			self.assertTrue(page.haschildren)
			self.assertTrue(page.hascontent)

		page = self.store.get_page(Path('NonExistingPage'))
		if trashing:
			# fail silently for non-existing page
			self.assertFalse(self.store.trash_page(page))
		else:
			# check error consistent
			self.assertRaises(TrashNotSupportedError, self.store.trash_page, page)


class TextXMLStore(TestReadOnlyStore, tests.TestCase):

	xml = u'''\
<?xml version='1.0' encoding='utf-8'?>
<section>
<page name='Foo'>
Fooo!
<page name="Bar">
Foooo Barrr
</page>
</page>
<page name='Baz'>
Fooo barrr bazzz
</page>
<page name='utf8'>
<page name='\u03b1\u03b2\u03b3'>
Utf8 content here
</page>
</page>
</section>
'''

	def setUp(self):
		buffer = StubFile(self.xml)
		klass = zim.stores.get_store('xml')
		self.store = klass(path=Path(':'), notebook=Notebook(), file=buffer)
		self.index = set(['Foo', 'Foo:Bar', 'Baz', u'utf8:\u03b1\u03b2\u03b3'])
		self.normalize_index()

	def testIndex(self):
		'''Test we get a proper index for the XML store'''
		TestReadOnlyStore.testIndex(self)

	def testContent(self):
		page = self.store.get_page(Path('Foo:Bar'))
		self.assertEqual(page.dump(format='wiki'), ['Foooo Barrr\n'])
		ref = self.xml.replace("'", '"')
		self.assertEqual(''.join(self.store.dump()), ref)


@tests.slowTest
class TestFiles(TestStoresMemory):
	'''Test the store.files module'''

	def setUp(self):
		TestStoresMemory.setUp(self)
		tmpdir = self.create_tmp_dir(u'_some_utf8_here_\u0421\u0430\u0439')
		self.dir = Dir([tmpdir, 'store-files'])
		self.mem = self.store
		klass = zim.stores.get_store('files')
		self.store = klass(path=Path(':'), notebook=Notebook(), dir=self.dir)
		for parent, page in walk(self.mem):
			if page.hascontent:
				mypage = self.store.get_page(page)
				mypage.set_parsetree(page.get_parsetree())
				self.store.store_page(mypage)

	def modify(self, path, func):
		mtime = os.stat(path).st_mtime
		m = mtime
		i = 0
		while m == mtime:
			time.sleep(1)
			func(path)
			m = os.stat(path).st_mtime
			i += 1
			assert i < 5
		#~ print '>>>', m, mtime

	def testIndex(self):
		'''Test we get a proper index for files store'''
		TestStoresMemory.testIndex(self)

	def testManipulate(self):
		'''Test moving and deleting pages in the files store'''
		TestStoresMemory.testManipulate(self)

		# test overwrite check
		page = self.store.get_page(Path('Test:overwrite'))
		page.parse('plain', 'BARRR')
		self.store.store_page(page)
		self.assertTrue('BARRR' in ''.join(page.dump('plain')))
		self.modify(page.source.path, lambda p: open(p, 'w').write('bar'))
		with FilterOverWriteWarning():
			self.assertRaises(FileWriteError, self.store.store_page, page)

		# test headers
		page = self.store.get_page(Path('Test:New'))
		page.parse('plain', 'Foo Bar')
		self.store.store_page(page)
		self.assertEqual(page.properties['Content-Type'], 'text/x-zim-wiki')
		self.assertEqual(page.properties['Wiki-Format'], 'zim 0.4')
		self.assertTrue('Creation-Date' in page.properties)
		firstline = page.source.readlines()[0]
		self.assertEqual(firstline, 'Content-Type: text/x-zim-wiki\n')

		# test moving page into itself
		oldpath = Path('Test:New')
		newpath = Path('Test:New:NewSub')

		self.store.move_page(oldpath, newpath)
		page = self.store.get_page(newpath)
		self.assertEqual(page.dump('plain'), ['Foo Bar\n'])


class StubFile(File):

	def __init__(self, text):
		self.text = text

	def read(self):
		return self.text

	def readlines(self):
		return self.text.splitlines(True)

	def write(self, *a):
		assert False

	def writelines(self, *a):
		assert False

	def open(self, *a):
		assert False

	def exists(self):
		return len(self.text) > 0
