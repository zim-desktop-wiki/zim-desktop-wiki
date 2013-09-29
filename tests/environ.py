# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import os

from zim.environ import environ
from zim.fs import File, Dir


class TestEnviron(tests.TestCase):

	def testGetSet(self):
		k = 'TEST_ZIM_ENVIRON_MODULE'

		self.assertNotIn(k, environ)
		self.assertRaises(KeyError, environ.__getitem__, k)
		self.assertIsNone(environ.get(k))
		self.assertEqual(environ.get(k, 'FOO'), 'FOO')

		environ[k] = 'BAR'
		self.assertEqual(environ.get(k, 'FOO'), 'BAR')
		self.assertEqual(environ[k], 'BAR')
		self.assertGreater(len(environ), 0)
		self.assertIn(k, environ)

		del environ[k]
		self.assertNotIn(k, environ)

	def testGetListPath(self):
		path = environ.get_list('PATH')
		self.assertGreater(len(path), 0)
		for dir in map(Dir, path):
			if dir.exists():
				break
		else:
			raise AssertionError, 'No existing dirs found in PATH: %s' % path

	def testHomeAndUser(self):
		user = environ.get('USER')
		self.assertIsNotNone(user)

		home = environ.get('HOME')
		self.assertIsNotNone(home)
		self.assertTrue(Dir(home).exists())

		if os.name == 'nt':
			appdata = environ.get('APPDATA')
			self.assertIsNotNone(appdata)
			self.assertTrue(Dir(appdata).exists())



