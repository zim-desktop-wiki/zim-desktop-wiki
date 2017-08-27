#!/usr/bin/python

# -*- coding: utf-8 -*-

# This is a wrapper script to run tests using the unittest
# framework. It setups the environment properly and defines some
# commandline options for running tests.
#
# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import os
import sys
import shutil
import getopt
import logging

import tests
from tests import unittest

try:
    import coverage
except ImportError:
    coverage = None


def main(argv=None):
    '''Run either all tests, or those specified in argv'''
    if argv is None:
        argv = sys.argv

    # parse options
    covreport = False
    failfast = False
    loglevel = logging.WARNING
    opts, args = getopt.gnu_getopt(argv[1:],
                                   'hVD', ['help', 'coverage', 'fast', 'failfast', 'ff', 'full', 'debug', 'verbose'])
    for o, a in opts:
        if o in ('-h', '--help'):
            print '''\
usage: %s [OPTIONS] [MODULES]

Where MODULE should a module name from ./tests/
If no module is given the whole test suite is run.

Options:
  -h, --help     print this text
  --fast         skip a number of slower tests and mock filesystem
  --failfast     stop after the first test that fails
  --ff           alias for "--fast --failfast"
  --full         full test for using filesystem without mock
  --coverage     report test coverage statistics
  -V, --verbose  run with verbose output from logging
  -D, --debug    run with debug output from logging
''' % argv[0]
            return
        elif o == '--coverage':
            if coverage:
                covreport = True
            else:
                print >>sys.stderr, '''\
Can not run test coverage without module 'coverage'.
On Ubuntu or Debian install package 'python-coverage'.
'''
                sys.exit(1)
        elif o == '--fast':
            tests.FAST_TEST = True
            # set before any test classes are loaded !
        elif o == '--failfast':
            failfast = True
        elif o == '--ff':  # --fast --failfast
            tests.FAST_TEST = True
            failfast = True
        elif o == '--full':
            tests.FULL_TEST = True
        elif o in ('-V', '--verbose'):
            loglevel = logging.INFO
        elif o in ('-D', '--debug'):
            loglevel = logging.DEBUG
        else:
            assert False, 'Unkown option: %s' % o

    # Start tracing
    if coverage:
        cov = coverage.coverage(source=['zim'], branch=True)
        cov.erase()  # clean up old date set
        cov.exclude('assert ')
        cov.exclude('raise NotImplementedError')
        cov.start()

    # Set logging handler (don't use basicConfig here, we already installed stuff)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger = logging.getLogger()
    logger.setLevel(loglevel)
    logger.addHandler(handler)
    # logging.captureWarnings(True) # FIXME - make all test pass with this enabled

    # Build the test suite
    loader = unittest.TestLoader()
    try:
        if args:
            suite = unittest.TestSuite()
            for name in args:
                module = name if name.startswith('tests.') else 'tests.' + name
                test = loader.loadTestsFromName(module)
                suite.addTest(test)
        else:
            suite = tests.load_tests(loader, None, None)
    except AttributeError as error:
        # HACK: unittest raises and attribute errors if import of test script
        # fails try to catch this and show the import error instead - else raise
        # original error
        import re
        m = re.match(r"'module' object has no attribute '(\w+)'", error.args[0])
        if m:
            module = m.group(1)
            m = __import__('tests.' + module)  # should raise ImportError
        raise error

    # And run it
    unittest.installHandler()  # Fancy handling for ^C during test
    result = \
        unittest.TextTestRunner(verbosity=2, failfast=failfast, descriptions=False).run(suite)

    # Check the modules were loaded from the right location
    # (so no testing based on modules from a previous installed version...)
    mylib = os.path.abspath('./zim')
    for module in [m for m in sys.modules.keys()
                   if m == 'zim' or m.startswith('zim.')]:
        if sys.modules[module] is None:
            continue
        file = sys.modules[module].__file__
        assert file.startswith(mylib), \
            'Module %s was loaded from %s' % (module, file)

    test_report(result, 'test_report.html')
    print '\nWrote test report to test_report.html\n'

    # Stop tracing
    if coverage:
        cov.stop()
        cov.save()

    # Create coverage output if asked to do so
    if covreport:
        print 'Writing coverage reports...'
        cov.html_report(directory='./coverage', omit=['zim/inc/*'])
        print 'Done - Coverage reports can be found in ./coverage/'


def test_report(result, file):
    '''Produce html report of test failures'''
    output = open(file, 'w')
    output.write('''\
<html>
<head>
<title>Zim unitest Test Report</title>
</head>
<body>
<h1>Zim unitest Test Report</h1>
<p>
%i tests run<br/>
%i skipped<br/>
%i errors<br/>
%i failures<br/>
</p>
<hr/>
''' % (
        result.testsRun,
        len(result.skipped),
        len(result.errors),
        len(result.failures),
    ))

    def escape_html(text):
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def add_errors(flavour, errors):
        for test, err in errors:
            output.write("<h2>%s: %s</h2>\n" % (flavour, escape_html(result.getDescription(test))))
            output.write("<pre>%s\n</pre>\n" % escape_html(err))
            output.write("<hr/>\n")

    add_errors('ERROR', result.errors)
    add_errors('FAIL', result.failures)

    output.close()


if __name__ == '__main__':
    main()
