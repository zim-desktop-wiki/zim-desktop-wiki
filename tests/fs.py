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

	def testFile(self):
		'''Test File object'''
		file = File('/foo/bar')
		assert not file.exists()
		# TODO: real test here

	def testDir(self):
		'''Test Dir object'''
		dir = Dir('/foo/bar')
		assert not dir.exists()
		# TODO: real test here

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


if __name__ == '__main__':
	unittest.main()
