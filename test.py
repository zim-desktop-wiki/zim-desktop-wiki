#!/usr/bin/python

# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import os
import sys
import unittest

import tests

# TODO overload one of the unittest classes to test add file names

def main(argv=None):
	'''Run either all tests, or those specified in argv'''
	if argv is None:
		argv = sys.argv

	if argv[1:]:
		modules = [ 'tests.'+name for name in argv[1:] ]
	else:
		modules = [ 'tests.'+name for name in tests.__all__ ]

	suite = unittest.TestSuite()

	for name in modules:
		test = unittest.defaultTestLoader.loadTestsFromName(name)
		suite.addTest(test)

	unittest.TextTestRunner(verbosity=3).run(suite)


if __name__ == '__main__':
	main()
