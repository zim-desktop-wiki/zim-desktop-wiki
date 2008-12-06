# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.fs module.'''

import tests

import os

import tests
from zim import fs
from zim.fs import *


class TestFS(tests.TestCase):

	def testPath(self):
		'''Test Path constructor'''
		path = fs.Path(['foo', 'bar'])
		test = os.path.abspath( os.path.join('foo', 'bar') )
		self.assertEqual(path.path, test)

		path = fs.Path('/foo/bar')
		self.assertEqual(path.uri, 'file:///foo/bar')

		# TODO test Path('file:///foo/bar') => '/foo/bar'
		# TODO test Path('file://localhost/foo/bar') => '/foo/bar'

		path = fs.Path('/foo//bar/baz/')
		self.assertEqual(path.split(), ['foo', 'bar', 'baz'])
		dirs = []
		for d in path: dirs.append(d)
		self.assertEqual(dirs, ['/foo', '/foo/bar', '/foo/bar/baz'])

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
		# TODO: more test here

	def testDir(self):
		'''Test Dir object'''
		tmpdir = tests.create_tmp_dir('fs_testDir')
		dir = Dir(tmpdir+'/foo/bar')
		assert not dir.exists()
		# TODO: real test here
		# TODO - test file(), + test exception
		# TODO - test subdir(), + test excepion

	def testBuffer(self):
		'''Test Buffer object'''
		buf = Buffer()
		self.assertFalse(buf.exists())
		self.assertRaises(IOError, buf.open, 'r') # buf does not exist
		io = buf.open('w')
		self.assertRaises(IOError, buf.open, 'w') # buf already open
		print >>io, 'hello world'
		io.close()
		self.assertTrue(buf.exists())
		self.assertEqual(buf.getvalue(), 'hello world\n')
		io = buf.open('r')
		self.assertEqual(io.readline(), 'hello world\n')
		io.close()

		def callback(buffer):
			self.assertEqual(buffer.getvalue(), 'check !\n')
			buffer.called = True

		buf = Buffer('foo bar', on_write=callback)
		buf.called = False
		io = buf.open('w')
		print >> io, 'check !'
		io.close()
		self.assertTrue(buf.called)
