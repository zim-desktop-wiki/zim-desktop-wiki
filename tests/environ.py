# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

import os

from zim.environ import environ
from zim.fs import File, Dir


class EnvironmentContext(object):
	'''Context manager to be able to run test cases for
	environment parameters and restore the previous values on
	exit or error. Usage as::

		with EnvironmentContext({
			'HOME': '/test/foo',
			'XDG_HOME': None,
		}):
			...
	'''
	# Use os.environ here for to avoid any errors with
	# our environ object - may bite when testing with non-ascii data.
	# But overloaded in EnvironmentConfigContext()

	environ = os.environ

	def __init__(self, environ_context):
		self.environ_context = environ_context
		self.environ_backup = {}

	def __enter__(self):
		for k, v in self.environ_context.items():
			self.environ_backup[k] = self.environ.get(k)
			if v:
				self.environ[k] = v
			elif k in self.environ:
				del self.environ[k]
			else:
				pass

	def __exit__(self, *exc_info):
		for k, v in self.environ_backup.items():
			if v:
				self.environ[k] = v
			elif k in self.environ:
				del self.environ[k]
			else:
				pass

		return False # Raise



class TestEnviron(tests.TestCase):

	def testGetSet(self):
		k = 'TEST_ZIM_ENVIRON_MODULE'

		with EnvironmentContext({k: None}):
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



