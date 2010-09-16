# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.fs module.'''

from __future__ import with_statement

import tests

import os
import time
import logging

from zim.fs import *
from zim.fs import Path, FileHandle, FileWriteError, TmpFile, get_tmpdir, normalize_win32_share, PathLookupError, FileNotFoundError, FilteredDir, isabs, joinpath
from zim.errors import Error


logger = logging.getLogger('zim.fs')


class FilterOverWriteWarning(object):

	def __enter__(self):
		logger.addFilter(self)

	def __exit__(self, *a):
		logger.removeFilter(self)

	def filter(self, record):
		return not record.getMessage().startswith('mtime check failed')


class TestFS(tests.TestCase):

	def testFunctions(self):
		smb_urls = (
			('smb://MyHost.local/share/My%20Documents', r'\\MyHost.local\share\My Documents'),
		)
		for url, share in smb_urls:
			if os.name == 'nt':
				self.assertEqual(normalize_win32_share(share), share)
				self.assertEqual(normalize_win32_share(url), share)
			else:
				self.assertEqual(normalize_win32_share(share), url)
				self.assertEqual(normalize_win32_share(url), url)

		self.assertTrue(isabs('/foo/bar'))
		self.assertFalse(isabs('./bar'))

		self.assertEqual(joinpath('foo', 'bar'), os.sep.join(('foo', 'bar')))

	def testPath(self):
		'''Test Path object'''
		path = Path(['foo', 'bar'])
		test = os.path.abspath( os.path.join('foo', 'bar') )
		self.assertEqual(path.path, test)

		path = Path('/foo/bar')
		uri = 'file:///' + os.path.abspath('/foo/bar').replace('\\', '/').strip('/')
		self.assertEqual(path.uri, uri)

		self.assertEqual(Path('file:///foo/bar'), Path('/foo/bar'))
		self.assertEqual(Path('file:/foo/bar'), Path('/foo/bar'))
		self.assertEqual(Path('file://localhost/foo/bar'), Path('/foo/bar'))
		self.assertEqual(Path('file:///C:/foo/bar'), Path('/C:/foo/bar'))
		if os.name == 'nt':
			self.assertEqual(Path('file:///C:/foo/bar'), Path(r'C:\foo\bar'))

		path = Path('/foo//bar/baz/')
		drive, p = os.path.splitdrive(path.path)
		self.assertEqual(path.split(), [drive + os.sep + 'foo', 'bar', 'baz'])
		dirs = []
		for d in path: dirs.append(d)
		wanted = map(lambda p: Dir(os.path.abspath(drive+p)),
					['/foo', '/foo/bar', '/foo/bar/baz'])
		self.assertEqual(dirs, wanted)

		for path1, path2, common in (
			('/foo/bar/baz/', '/foo/dus', '/foo'),
			('/foo/bar', '/dus/ja', '/'),
		):
			self.assertEqual(Path(path1).commonparent(Path(path2)), Dir(common))

		if os.name == 'nt':
			path1 = 'C:\foo\bar'
			path2 = 'D:\foo\bar\baz'
			self.assertEqual(Path(path1).commonparent(Path(path2)), None)

		for path1, path2, relpath in (
			('/foo/bar/baz', '/foo', 'bar/baz'),
		):
			self.assertEqual(Path(path1).relpath(Path(path2)), relpath)

		self.assertRaises(AssertionError, Path('/foo/bar').relpath, Path('/dus/ja'))

		for path1, path2, relpath in (
			('/foo/bar', '/dus/ja/', '../../foo/bar'),
			('/source/dir/foo/bar/dus.pdf', '/source/dir/foo', 'bar/dus.pdf'),
			('/source/dir/foo/dus.pdf', '/source/dir/foo', 'dus.pdf'),
			('/source/dir/dus.pdf', '/source/dir/foo', '../dus.pdf'),
		):
			self.assertEqual(Path(path1).relpath(Path(path2), allowupward=True), relpath)

		if os.name == 'nt':
			path1 = 'C:\foo\bar'
			path2 = 'D:\foo\bar\baz'
			self.assertEqual(Path(path1).relpath(Path(path2), allowupward=True), None)

		self.assertEqual(Path('/foo') + 'bar', Path('/foo/bar'))

		# Test unicode compat
		string = u'\u0421\u0430\u0439\u0442\u043e\u0432\u044b\u0439'
		path = Path(string)
		self.assertTrue(path.path.endswith(string))
		#~ self.assertRaises(Error, Path, string.encode('utf-8'))
		path = Path((string, 'foo'))
		self.assertTrue(path.path.endswith(os.sep.join((string, 'foo'))))
		#~ self.assertRaises(Error, Path, (string.encode('utf-8'), 'foo'))

	def testFileHandle(self):
		'''Test FileHandle object'''
		self.on_close_called = False
		tmpdir = tests.create_tmp_dir('fs_testFile')
		fh = FileHandle(
			tmpdir+'/foo.txt', mode='w', on_close=self.on_close)
		fh.write('duss')
		fh.close()
		self.assertTrue(self.on_close_called)

	def on_close(self):
		self.on_close_called = True

	def testFile(self):
		'''Test File object'''
		tmpdir = tests.create_tmp_dir('fs_testFile')
		file = File(tmpdir+'/foo/bar/baz.txt')
		assert not file.exists()
		file.touch()
		self.assertTrue(os.path.isfile(tmpdir+'/foo/bar/baz.txt'))
		File(tmpdir+'/anotherfile.txt').touch()
		file.cleanup()
		self.assertTrue(os.path.isfile(tmpdir+'/anotherfile.txt'))
		self.assertTrue(os.path.isdir(tmpdir))
		self.assertFalse(os.path.isfile(tmpdir+'/foo/bar/baz.txt'))
		self.assertFalse(os.path.isdir(tmpdir+'/foo'))

		file = File(tmpdir+'/bar.txt')
		file.writelines(['c\n', 'd\n'])
		self.assertEqual(file.readlines(), ['c\n', 'd\n'])

		# with error
		try:
			fh = file.open('w')
			fh.write('foo')
			raise IOError
		except IOError:
			del fh
		self.assertEqual(file.readlines(), ['c\n', 'd\n'])
		self.assertTrue(os.path.isfile(file.encodedpath+'.zim-new~'))

		# test recovery on windows
		if os.name == 'nt':
			new = file.encodedpath+'.zim-new~'
			orig = file.encodedpath+'.zim-orig~'
			bak = file.encodedpath+'.bak~'
			os.remove(file.encodedpath) # don't clean up folder
			open(new, 'w').write('NEW\n')
			open(orig, 'w').write('ORIG\n')
			self.assertTrue(file.exists())
			self.assertEqual(file.read(), 'NEW\n')
			self.assertFalse(os.path.isfile(new))
			self.assertFalse(os.path.isfile(orig))
			self.assertTrue(os.path.isfile(file.encodedpath))
			self.assertTrue(os.path.isfile(bak))

			bak1 = file.encodedpath+'.bak1~'
			os.remove(file.encodedpath) # don't clean up folder
			open(orig, 'w').write('ORIG 1\n')
			self.assertFalse(file.exists())
			self.assertRaises(FileNotFoundError, file.read)
			self.assertFalse(os.path.isfile(orig))
			self.assertTrue(os.path.isfile(bak))
			self.assertTrue(os.path.isfile(bak1))

		# test read-only
		path = tmpdir+'/read-only-file.txt'
		open(path, 'w').write('test 123')
		os.chmod(path, 0444)
		file = File(path)
		self.assertRaises(FileWriteError, file.write, 'Overwritten!')
		os.chmod(path, 0644) # make it removable again

		# with windows line-ends
		file = open(tmpdir+'/newlines.txt', 'wb')
			# binary mode means no automatic newline conversions
		file.write('Some lines\r\nWith win32 newlines\r\n')
		file = File(tmpdir+'/newlines.txt')
		self.assertEqual(file.read(), 'Some lines\nWith win32 newlines\n')

		# test compare & copyto
		file1 = File(tmpdir + '/foo.txt')
		file2 = File(tmpdir + '/bar.txt')
		file1.write('foo\nbar\n')
		file2.write('foo\nbar\n')
		self.assertTrue(file1.compare(file2))
		file2.write('foo\nbar\nbaz\n')
		self.assertFalse(file1.compare(file2))
		file2.copyto(file1)
		self.assertTrue(file1.compare(file2))

		# rename is being used when testing Dir

		# test mimetype
		file = File('test.txt')
		self.assertFalse(file.isimage())
		file = File('test.jpg')
		self.assertTrue(file.isimage())

		file = File(tmpdir+'/foo/')
		self.assertFalse(file.isdir())

		dir = Dir(tmpdir+'/foo/')
		dir.touch()
		self.assertTrue(file.isdir())

	def testTmpFile(self):
		'''Test TmpFile object'''
		dir = get_tmpdir()
		file = TmpFile('foo.txt')
		self.assertTrue(file.ischild(dir))
		# What else to test here ?

	def testDir(self):
		'''Test Dir object'''
		tmpdir = tests.create_tmp_dir('fs_testDir')
		dir = Dir(tmpdir+'/foo/bar')
		assert not dir.exists()

		file1 = dir.file('unique.txt')
		file1.touch()
		file2 = dir.new_file('unique.txt')
		file2.touch()
		file3 = dir.new_file('unique.txt')
		self.assertEqual(file1.basename, 'unique.txt')
		self.assertEqual(file2.basename, 'unique001.txt')
		self.assertEqual(file3.basename, 'unique002.txt')

		self.assertEqual(dir.list(), ['unique.txt', 'unique001.txt'])
			# we did not touch unique002.txt, so don't want to see it show up here

		file1.rename(dir.file('foo.txt'))
		self.assertEqual(file1.basename, 'unique.txt') # don't update the object !
		self.assertEqual(dir.list(), ['foo.txt', 'unique001.txt'])

		file1 = dir.file('foo.txt')
		file1.rename(dir.subdir('foo').file('bar.txt'))
		self.assertEqual(dir.list(), ['foo', 'unique001.txt'])
		self.assertEqual(dir.subdir('foo').list(), ['bar.txt'])

		fdir = FilteredDir(dir)
		fdir.ignore('*.txt')
		self.assertEqual(fdir.list(), ['foo'])

		self.assertEqual(File((dir, 'foo.txt')), dir.file('foo.txt'))
		self.assertEqual(dir.file(File((dir, 'foo.txt'))), dir.file('foo.txt'))
		self.assertRaises(PathLookupError, dir.file, File('/foo/bar.txt')) # not below dir

		self.assertEqual(Dir((dir, 'bar')), dir.subdir('bar'))
		self.assertEqual(dir.subdir(Dir((dir, 'bar'))), dir.subdir('bar'))
		self.assertRaises(PathLookupError, dir.subdir, Dir('/foo/bar')) # not below dir

		self.assertRaises(OSError, dir.remove) # dir not empty
		self.assertTrue(dir.exists())
		dir.cleanup()
		self.assertTrue(dir.exists())
		dir.remove_children()
		self.assertEqual(dir.list(), [])
		self.assertTrue(dir.exists())
		dir.remove()
		self.assertFalse(dir.exists())
		self.assertEqual(dir.list(), []) # list non-existing dir


class TestFileOverwrite(tests.TestCase):

	slowTest = True

	def setUp(self):
		self.path = tests.create_tmp_dir('fs_testOverwrite')+'/file.txt'

	def modify(self, func):
		mtime = os.stat(self.path).st_mtime
		m = mtime
		i = 0
		while m == mtime:
			time.sleep(1)
			func(self.path)
			m = os.stat(self.path).st_mtime
			i += 1
			assert i < 5
		#~ print '>>>', m, mtime

	def runTest(self):
		'''Test file overwrite check'''
		file = File(self.path, checkoverwrite=True)
		file.write('bar')
		self.assertEquals(file.read(), 'bar')
		self.modify(lambda p: open(p, 'w').write('XXX'))
			# modify mtime and content
		with FilterOverWriteWarning():
			self.assertRaises(FileWriteError, file.write, 'foo')
		self.assertEquals(file.read(), 'XXX')

		file = File(self.path, checkoverwrite=True)
		file.write('bar')
		self.modify(lambda p: open(p, 'w').write('bar'))
			# modify mtime but keep content the same
		with FilterOverWriteWarning():
			file.write('foo')
		self.assertEquals(file.read(), 'foo')


class TestSymlinks(tests.TestCase):

	slowTest = True

	@staticmethod
	def skipTest():
		if not hasattr(os, 'symlink'):
			return 'OS does not supprot symlinks'
		else:
			return False

	def runTest(self):
		'''Test file operations are safe for symlinks'''

		# Set up a file structue with a symlink
		tmpdir = tests.create_tmp_dir('fs_TestSymLinks')
		targetdir = Dir(tmpdir + '/target')
		targetdir.file('foo.txt').touch()
		targetfile = File(tmpdir + '/target.txt')
		targetfile.write('foo\n')

		dir = Dir(tmpdir + '/data')
		file = dir.file('bar.txt')
		file.touch()
		os.symlink(targetdir.encodedpath, dir.encodedpath + '/link')
		os.symlink(targetfile.encodedpath, dir.encodedpath + '/link.txt')

		# Test transparent access to the linked data
		linkedfile = dir.file('link.txt')
		self.assertTrue(linkedfile.read(), 'foo\n')
		self.assertEqual(dir.list(), ['bar.txt', 'link', 'link.txt'])
		linkeddir = dir.subdir('link')
		self.assertEqual(linkeddir.list(), ['foo.txt'])

		# Test modifying a linked file
		linkedfile.write('bar\n')
		self.assertTrue(linkedfile.read(), 'bar\n')
		self.assertTrue(targetfile.read(), 'bar\n')
		linkedfile.rename(dir.file('renamed_link.txt'))
		self.assertEqual(dir.list(), ['bar.txt', 'link', 'renamed_link.txt'])
		linkedfile = dir.file('renamed_link.txt')
		linkedfile.write('foobar\n')
		self.assertTrue(linkedfile.read(), 'foobar\n')
		self.assertTrue(targetfile.read(), 'foobar\n')

		# Test removing the links (but not the data)
		linkedfile.remove()
		self.assertFalse(linkedfile.exists())
		self.assertTrue(targetfile.exists())
		self.assertTrue(targetfile.read(), 'foobar\n')
		dir.remove_children()
		self.assertEqual(dir.list(), [])
		self.assertTrue(targetdir.exists())
		self.assertEqual(targetdir.list(), ['foo.txt'])
