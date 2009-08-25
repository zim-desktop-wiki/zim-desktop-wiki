# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.fs module.'''

import tests

import os
import time

import tests
from zim.fs import *
from zim.fs import Path, FileHandle, OverWriteError

# TODO: also test dir.new_file()

class TestFS(tests.TestCase):

	def testPath(self):
		'''Test Path constructor'''
		path = Path(['foo', 'bar'])
		test = os.path.abspath( os.path.join('foo', 'bar') )
		self.assertEqual(path.path, test)

		path = Path('/foo/bar')
		uri = 'file:///' + os.path.abspath('/foo/bar').replace('\\', '/').strip('/')
		self.assertEqual(path.uri, uri)

		# TODO test Path('file:///foo/bar') => '/foo/bar'
		# TODO test Path('file://localhost/foo/bar') => '/foo/bar'

		path = Path('/foo//bar/baz/')
		drive, p = os.path.splitdrive(path.path)
		self.assertEqual(path.split(), [drive + os.sep + 'foo', 'bar', 'baz'])
		dirs = []
		for d in path: dirs.append(d)
		wanted = map(lambda p: os.path.abspath(drive+p),
					['/foo', '/foo/bar', '/foo/bar/baz'])
		self.assertEqual(dirs, wanted)

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

		# without codecs
		file = File(tmpdir+'/foo.txt')
		fh = file.open('w', encoding=None)
		self.assertTrue(isinstance(fh, FileHandle))
		fh.write('tja')
		fh.close()

		# with codecs
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
		self.assertTrue(os.path.isfile(file.path+'.zim.new~'))

		# test read-only
		path = tmpdir+'/read-only-file.txt'
		open(path, 'w').write('test 123')
		os.chmod(path, 0444)
		file = File(path)
		self.assertRaises(OverWriteError, file.write, 'Overwritten!')
		os.chmod(path, 0644) # make it removable again

		# with windows line-ends
		file = open(tmpdir+'/newlines.txt', 'wb')
			# binary mode means no automatic newline conversions
		file.write('Some lines\r\nWith win32 newlines\r\n')
		file = File(tmpdir+'/newlines.txt')
		self.assertEqual(file.read(), 'Some lines\nWith win32 newlines\n')

		# TODO: more test here

	def testDir(self):
		'''Test Dir object'''
		tmpdir = tests.create_tmp_dir('fs_testDir')
		dir = Dir(tmpdir+'/foo/bar')
		assert not dir.exists()
		# TODO: real test here
		# TODO - test file(), + test exception
		# TODO - test subdir(), + test excepion


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
		self.assertRaises(OverWriteError, file.write, 'foo')
		self.assertEquals(file.read(), 'XXX')

		file = File(self.path, checkoverwrite=True)
		file.write('bar')
		self.modify(lambda p: open(p, 'w').write('bar'))
			# modify mtime but keep content the same
		file.write('foo')
		self.assertEquals(file.read(), 'foo')

