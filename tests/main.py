# -*- coding: utf-8 -*-

# Copyright 2012-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the base zim module.'''

from __future__ import with_statement


import tests

from tests.config import EnvironmentConfigContext

import sys
import cStringIO as StringIO
#~ import threading
#~ import time


from zim.fs import Dir, File, FS
from zim.environ import environ

from zim.main import *

import zim
import zim.main
import zim.main.ipc


class capture_stdout:

		def __enter__(self):
			self.real_stdout = sys.stdout
			sys.stdout = StringIO.StringIO()
			return sys.stdout

		def __exit__(self, type, value, traceback):
			sys.stdout = self.real_stdout


class TestParseCommand(tests.TestCase):

	def runTest(self):
		for command, klass in zim.main.commands.items():
			obj = zim.main.build_command(['--%s' % command])
			self.assertIsInstance(obj, klass)

		obj = zim.main.build_command(['-v'])
		self.assertIsInstance(obj, VersionCommand)

		obj = zim.main.build_command(['-h'])
		self.assertIsInstance(obj, HelpCommand)

		obj = zim.main.build_command(['foo'])
		self.assertIsInstance(obj, GuiCommand)

		# TODO test plugins



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


class TestNotebookCommand(tests.TestCase):

	
	def runTest(self):
		cmd = NotebookCommand('gui')
		cmd.arguments = ('NOTEBOOK', '[PAGE]')
		cmd.parse_options('./Notes')

		# check if PWD at "parse_options" is remembered after changing dir
		from zim.notebook.info import NotebookInfo
		pwd = os.getcwd()
		self.addCleanup(os.chdir, pwd)

		myinfo = NotebookInfo(pwd + '/Notes')
		os.chdir('/')
		notebookinfo, page = cmd.get_notebook_argument()
		
		self.assertEqual(notebookinfo, myinfo)
		os.chdir(pwd)

#~ class TestGui(tests.TestCase):

	#~ def runTest(self):
		#~ cmd = GuiCommand('gui')
		#~ cmd.parse_options('../../Notes')
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


## ExportCommand() is tested in tests/export.py


class TestIPC(tests.TestCase):

	def runTest(self):
		inbox = [None]
		def handler(*args):
			inbox[0] = args

		zim.main.ipc.start_listening(handler)
		self.addCleanup(zim.main.ipc._close_listener)

		self.assertRaises(AssertionError, zim.main.ipc.dispatch, '--manual')

		zim.main.ipc.set_in_main_process(False) # overrule sanity check
		zim.main.ipc.dispatch('test', '123')

		tests.gtk_process_events()
		self.assertEqual(inbox[0], ('test', '123'))


### TODO test various ways of calling ZimApplication ####

# Start main
# Handle incoming
# Toplevel life cycle
# Spawn new
# Spawn standalone
