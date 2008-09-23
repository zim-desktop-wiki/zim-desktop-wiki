#!/usr/bin/python

# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import os
import sys
import unittest


def main(argv=None):
	'''FIXME'''
	if argv is None:
		argv = sys.argv

	if argv[1:]:
		modules = [ 'tests.'+name for name in argv[1:] ]
	else:
		modules = [ 'tests.'+file[:-3]
			for file in os.listdir('tests') if file.endswith('.py') ]
		modules.pop( modules.index('tests.__init__') )

	suite = unittest.TestSuite()

	for name in modules:
		test = unittest.defaultTestLoader.loadTestsFromName(name)
		suite.addTest(test)

	unittest.TextTestRunner().run(suite)


if __name__ == '__main__':
	main()
