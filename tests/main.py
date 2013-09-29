# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the base zim module.'''

from __future__ import with_statement


import tests

import sys
import cStringIO as StringIO
import threading
import time

from zim.__main__ import *


class capture_stdout:

		def __enter__(self):
			self.real_stdout = sys.stdout
			sys.stdout = StringIO.StringIO()
			return sys.stdout

		def __exit__(self, type, value, traceback):
			sys.stdout = self.real_stdout


class TestVersion(tests.TestCase):

	def runTest(self):
		cmd = VersionCommand('version')
		with capture_stdout() as output:
			cmd.run()
		self.assertTrue(output.getvalue().startswith('zim'))


class TestHelp(tests.TestCase):

	def runTest(self):
		cmd = HelpCommand('help')
		with capture_stdout() as output:
			cmd.run()
		self.assertTrue(output.getvalue().startswith('usage:'))


#~ class TestGui(tests.TestCase):
#~
	#~ def runTest(self):
		#~ cmd = GuiCommand()
		#~ with DialogContext():
			#~ cmd.run()

	# Check default notebook
	# Check dialog list prompt
	# Check mainwindow pops up


#~ @tests.slowTest
#~ class TestServer(tests.TestCase):
#~
	#~ def testServerGui(self):
		#~ cmd = ServerCommand('server')
		#~ cmd.parse_options('--gui')
		#~ with DialogContext():
			#~ cmd.run()
#~
	#~ def testServer(self):
		#~ cmd = ServerCommand('server', 'testnotebook')
		#~ t = threading.Thread(target=cmd.run)
		#~ t.start()
		#~ time.sleep(3) # give time to startup
		#~ re = urlopen('http://localhost:8080')
		#~ self.assertEqual(re.getcode(), 200)
		#~ cmd.server.shutdown()
		#~ t.join()


#~ @tests.slowTest
#~ class ExportTest(tests.TestCase):
#~
	#~ def runTest(self):
		#~ cmd = ExportCommand('export')
		#~ cmd.parse_options('--template', 'foo', notebook, page, '-o', tmpdir)
		#~ cmd.run()
		#~ self.assertTrue(tmpdir.file().exists())


