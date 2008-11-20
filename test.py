#!/usr/bin/python

# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import os
import sys
import unittest
import getopt

import tests

# TODO overload one of the unittest classes to test add file names

def main(argv=None):
	'''Run either all tests, or those specified in argv'''
	if argv is None:
		argv = sys.argv

	opts, args = getopt.gnu_getopt(argv[1:], '', ['cover'])
	if '--cover' in [o[0] for o in opts]:
		try:
			import coverage
		except ImportError:
			print >>sys.stderr, '''\
Can not run test coverage without module coverage.
On Ubuntu or Debian install package 'python-coverage'.
'''
			sys.exit(1)
		tests.coverage = coverage
		tests.coverage.erase()

	if args:
		modules = [ 'tests.'+name for name in args ]
	else:
		modules = [ 'tests.'+name for name in tests.__all__ ]

	suite = unittest.TestSuite()

	for name in modules:
		test = unittest.defaultTestLoader.loadTestsFromName(name)
		suite.addTest(test)

	unittest.TextTestRunner(verbosity=3).run(suite)
	
	if tests.coverage:
		pyfiles = []
		for dir, dirs, files in os.walk('zim'):
			pyfiles.extend([dir+'/'+f for f in files if f.endswith('.py')])
		tests.coverage.report(pyfiles, show_missing=False)
		print '\nTODO: detailed html coverage'


if __name__ == '__main__':
	main()
