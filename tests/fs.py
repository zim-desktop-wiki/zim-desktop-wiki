# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.fs module.'''

import unittest
import os

from zim.fs import *

class TestFS(unittest.TestCase):

	def testPath(self):
		'''Test Path constructor'''
		path = Path(['foo', 'bar'])
		test = os.path.abspath( os.path.join('foo', 'bar') )
		self.assertEqual(path.path, test)

		path = Path('/foo/bar')
		self.assertEqual(path.uri, 'file:///foo/bar')

		# TODO test Path('file:///foo/bar') => '/foo/bar'
		# TODO test Path('file://localhost/foo/bar') => '/foo/bar'

		path = Path('/foo//bar/baz/')
		self.assertEqual(path.split(), ['foo', 'bar', 'baz'])
		dirs = []
		for d in path: dirs.append(d)
		self.assertEqual(dirs, ['/foo', '/foo/bar', '/foo/bar/baz'])

	def testFile(self):
		'''Test File object'''
		file = File('tmp/foo/bar/baz.txt')
		assert not file.exists()
		file.touch()
		self.assertTrue(os.path.isfile('./tmp/foo/bar/baz.txt'))
		file.cleanup()
		self.assertFalse(os.path.isfile('./tmp/foo/bar/baz.txt'))
		self.assertFalse(os.path.isdir('./tmp/foo'))
		# TODO: more test here

	def testDir(self):
		'''Test Dir object'''
		dir = Dir('tmp/foo/bar')
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
