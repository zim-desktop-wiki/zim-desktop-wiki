#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import os
import sys
import shutil
import getopt
import logging

import unittest
import time
import types

import tests

# TODO overload one of the unittest classes to test add file names

pyfiles = []
for d, dirs, files in os.walk('zim'):
	pyfiles.extend([d+'/'+f for f in files if f.endswith('.py')])
pyfiles.sort()

class FastTestLoader(unittest.TestLoader):
	'''Extension of TestLoader which ignores all classes which have an
	attribute 'slowTest' set to True.
	'''

	def __init__(self, alltests=True):
		unittest.TestLoader.__init__(self)
		self.ignored = 0
		self.skipped = 0
		self.alltests = alltests

	def loadTestsFromModule(self, module):
		"""Return a suite of all tests cases contained in the given module"""
		tests = []
		for name in dir(module):
			obj = getattr(module, name)
			if (isinstance(obj, (type, types.ClassType)) and
				issubclass(obj, unittest.TestCase)):
				if not self.alltests and hasattr(obj, 'slowTest') and obj.slowTest:
					print 'Ignoring slow test:', obj.__name__
					self.ignored += 1
				elif hasattr(obj, 'skipTestZim') and obj.skipTestZim():
					print 'Skipping test:', obj.__name__, '-', obj.skipTestZim()
					self.skipped += 1
				else:
					tests.append(self.loadTestsFromTestCase(obj))
		return self.suiteClass(tests)


class MyTextTestRunner(unittest.TextTestRunner):
	'''Extionsion of TextTestRunner to report number of ignored tests in the
	proper place.
	'''

	def __init__(self, verbosity, ignored, skipped):
		unittest.TextTestRunner.__init__(self, verbosity=verbosity)
		self.ignored = ignored
		self.skipped = skipped

	def run(self, test):
		"Run the given test case or test suite."
		result = self._makeResult()
		startTime = time.time()
		test(result)
		stopTime = time.time()
		timeTaken = stopTime - startTime
		result.printErrors()
		self.stream.writeln(result.separator2)
		run = result.testsRun
		self.stream.writeln("Ran %d test%s in %.3fs" %
							(run, run != 1 and "s" or "", timeTaken))
		ignored = self.ignored
		if ignored > 0:
			self.stream.writeln("Ignored %d slow test%s" %
							(ignored, ignored != 1 and "s" or ""))
		skipped = self.skipped
		if skipped > 0:
			self.stream.writeln("Skipped %d test%s" %
							(skipped, skipped != 1 and "s" or ""))
		self.stream.writeln()
		if not result.wasSuccessful():
			self.stream.write("FAILED (")
			failed, errored = map(len, (result.failures, result.errors))
			if failed:
				self.stream.write("failures=%d" % failed)
			if errored:
				if failed: self.stream.write(", ")
				self.stream.write("errors=%d" % errored)
			self.stream.writeln(")")
		else:
			self.stream.writeln("OK")
		return result



def main(argv=None):
	'''Run either all tests, or those specified in argv'''
	if argv is None:
		argv = sys.argv

	# parse options
	coverage = None
	alltests = True
	loglevel = logging.WARNING
	opts, args = getopt.gnu_getopt(argv[1:], 'hVD', ['help', 'coverage', 'fast', 'debug', 'verbose'])
	for o, a in opts:
		if o in ('-h', '--help'):
			print '''\
usage: %s [OPTIONS] [MODULES]

Where MODULE should a module name from ./tests/
If no module is given the whole test suite is run.

Options:
  -h, --help     print this text
  --fast         skip a number of slower tests
  --coverage     report test coverage statistics
  -V, --verbose  run with verbose output from logging
  -D, --debug    run with debug output from logging
''' % argv[0]
			return
		elif o == '--coverage':
			try:
				import coverage as coverage_module
			except ImportError:
				print >>sys.stderr, '''\
Can not run test coverage without module coverage.
On Ubuntu or Debian install package 'python-coverage'.
'''
				sys.exit(1)
			coverage = coverage_module
			coverage.erase() # clean up old date set
			coverage.exclude('assert ')
			coverage.exclude('raise NotImplementedError')
			coverage.start()
		elif o == '--fast':
			alltests = False
		elif o in ('-V', '--verbose'):
			loglevel = logging.INFO
		elif o in ('-D', '--debug'):
			loglevel = logging.DEBUG
		else:
			assert False

	# Set logging handler
	logging.basicConfig(level=loglevel, format='%(levelname)s: %(message)s')

	# Set environment - so we can be sure we don't see
	# any data from a previous installed version
	tests.set_environ()

	# Collect the test cases
	suite = unittest.TestSuite()
	loader = FastTestLoader(alltests=alltests)

	if args:
		modules = [ 'tests.'+name for name in args ]
	else:
		suite.addTest(TestCompileAll())
		suite.addTest(TestNotebookUpgrade())
		modules = [ 'tests.'+name for name in tests.__all__ ]

	for name in modules:
		test = loader.loadTestsFromName(name)
		suite.addTest(test)

	# And run them
	MyTextTestRunner(verbosity=3,
		ignored=loader.ignored, skipped=loader.skipped).run(suite)

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

	if coverage:
		coverage.stop()
		report_coverage(coverage)


def report_coverage(coverage):
	print ''
	print 'Writing detailed coverage reports...'
	coverage.report(pyfiles, show_missing=False)

	# Detailed report in html
	if os.path.exists('coverage/'):
		shutil.rmtree('coverage/') # cleanup
	os.mkdir('coverage')

	index = []
	for path in pyfiles:
		if '_lib' in path or '_version' in path: continue
		htmlfile = path[:-3].replace('/', '.')+'.html'
		html = open('coverage/'+htmlfile, 'w')
		html.write('''\
<html>
<head>
<title>Coverage report for %s</title>
<style>
	.code { white-space: pre; font-family: monospace }
	.executed { background-color: #9f9 }
	.excluded { background-color: #ccc }
	.missing  { background-color: #f99 }
	.comment  { }
</style>
</head>
<body>
<h1>Coverage report for %s</h1>
<table width="100%%">
<tr><td class="executed">&nbsp;</td><td>Executed statement</td></tr>
<tr><td class="missing">&nbsp;</td><td>Untested statement</td></tr>
<tr><td class="excluded">&nbsp;</td><td>Ignored statement</td></tr>
<tr><td>&nbsp</td><td>&nbsp</td></tr>
''' % (path, path))


		p, statements, excluded, missing, l = coverage.analysis2(path)
		nstat = len(statements)
		nexec = nstat - len(missing)
		index.append((path, htmlfile, nstat, nexec))
		file = open(path)
		i = 0
		for line in file:
			i += 1
			line = line.replace('<', '&lt;')
			line = line.replace('>', '&gt;')
			if   i in missing: type = 'missing'
			elif i in excluded: type = 'excluded'
			elif i in statements: type = 'executed'
			else: type = 'comment'

			html.write('<tr><td class="%s">%i</td><td class="code">%s</td></tr>\n'
							% (type, i, line.rstrip()) )
		html.write('''\
</table>
</body>
</html>
''')
		html.close()

	# Index for detailed reports
	html = open('coverage/index.html', 'w')
	html.write('''\
<html>
<head>
<title>Test Coverage Index</title>
<style>
	.good    { background-color: #9f9; text-align: right }
	.close   { background-color: #cf9; text-align: right }
	.ontrack { background-color: #ff9; text-align: right }
	.lacking { background-color: #fc9; text-align: right }
	.bad     { background-color: #f99; text-align: right }
	.int     { text-align: right }
</style>
</head>
<body>
<h1>Test Coverage Index</h1>
<table>
<tr><td><b>File</b></td><td><b>Stmts</b></td><td><b>Exec</b></td><td><b>Cover</b></td></tr>
''')

	total_stat = reduce(int.__add__, [r[2] for r in index])
	total_exec = reduce(int.__add__, [r[3] for r in index])
	total_perc = int( float(total_exec) / total_stat * 100 )
	if total_perc >= 90: type = 'good'
	elif total_perc >= 80: type = 'close'
	elif total_perc >= 60: type = 'ontrack'
	elif total_perc >= 40: type = 'lacking'
	else: type = 'bad'
	html.write('<tr><td><b>Total</b></td>'
		       '<td class="int">%i</td><td class="int">%i</td>'
			   '<td class="%s">%.0f%%</td></tr>\n'
				   % (total_stat, total_exec, type, total_perc) )

	for report in index:
		pyfile, htmlfile, statements, executed = report
		if statements: percentage = int( float(executed) / statements * 100 )
		else: percentage = 100
		if percentage >= 90: type = 'good'
		elif percentage >= 80: type = 'close'
		elif percentage >= 60: type = 'ontrack'
		elif percentage >= 40: type = 'lacking'
		else: type = 'bad'
		html.write('<tr><td><a href="%s">%s</a></td>'
		           '<td class="int">%i</td><td class="int">%i</td>'
				   '<td class="%s">%.0f%%</td></tr>\n'
				   % (htmlfile, pyfile, statements, executed, type, percentage) )
	html.write('''\
</table>
</body>
</html>
''')
	html.close()

	print '\nDetailed coverage reports can be found in ./coverage/'


class TestCompileAll(unittest.TestCase):

	def runTest(self):
		'''Test if all modules compile'''
		for file in pyfiles:
			module = file[:-3].replace('/', '.')
			assert __import__(module)


class TestNotebookUpgrade(unittest.TestCase):

	def runTest(self):
		'''Test if included notebooks are up to date'''
		from zim.fs import Dir
		from zim.notebook import get_notebook
		for path in ('data/manual', 'HACKING'):
			notebook = get_notebook(Dir(path))
			self.assertTrue(not notebook.needs_upgrade)


if __name__ == '__main__':
	main()
