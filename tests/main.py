# -*- coding: utf-8 -*-

# Copyright 2012-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the base zim module.'''

from __future__ import with_statement


import tests

from tests.config import EnvironmentConfigContext, ConfigManager

import sys
import cStringIO as StringIO
import threading
import time


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

		obj = zim.main.build_command(['--plugin', 'quicknote'])
		self.assertIsInstance(obj, Command)

		obj = zim.main.build_command(['--server', '--gui'])
		self.assertIsInstance(obj, ServerGuiCommand)


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


class TestGui(tests.TestCase):

	def setUp(self):
		config = ConfigManager() # XXX should be passed in
		file = config.get_config_file('notebooks.list')
		file.remove()

	def runTest(self):

		## Without argument should prompt
		def testAddNotebookDialog(dialog):
			self.assertIn(dialog.__class__.__name__,
				('AddNotebookDialog', 'NotebookDialog')
			)

		cmd = GuiCommand('gui')
		with tests.DialogContext(testAddNotebookDialog):
			self.assertRaises(NotebookLookupError, cmd.run)

		### Try again with argument
		dir = self.create_tmp_dir()
		cmd = GuiCommand('gui')
		cmd.parse_options(dir)
		window = cmd.run()
		self.addCleanup(window.destroy)

		self.assertEqual(window.__class__.__name__, 'MainWindow')
		self.assertEqual(window.ui.notebook.uri, Dir(dir).uri) # XXX

		window2 = cmd.run()
		self.assertIs(window2, window)
			# Ensure repeated calling gives unique window

	# TODO
	# Check default notebook
	# Check dialog list prompt


class TestManual(tests.TestCase):

	def runTest(self):
		cmd = ManualCommand('manual')
		window = cmd.run()
		self.addCleanup(window.destroy)
		self.assertEqual(window.__class__.__name__, 'MainWindow')


@tests.slowTest
class TestServer(tests.TestCase):

	def runTest(self):
		from urllib import urlopen

		dir = self.create_tmp_dir()
		cmd = ServerCommand('server')
		cmd.parse_options(dir)
		t = threading.Thread(target=cmd.run)
		t.start()
		try:
			time.sleep(3) # give time to startup
			re = urlopen('http://localhost:8080')
			self.assertEqual(re.getcode(), 200)
		finally:
			cmd.server.shutdown()
			t.join()


class TestServerGui(tests.TestCase):

	def runTest(self):
		cmd = ServerGuiCommand('server')
		window = cmd.run()
		self.addCleanup(window.destroy)
		self.assertEqual(window.__class__.__name__, 'ServerWindow')




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

class TestZimApplication(tests.TestCase):

	def testSimple(self):
		app = ZimApplication()

		class MockCmd(object):

			def __init__(self):
				self.opts = {}
				self.commandline = ['mockcommand']
				self.hasrun = False

			def run(self):
				self.hasrun = True

		cmd = MockCmd()
		self.assertFalse(cmd.hasrun)
		app._run_cmd(cmd, ())
		self.assertTrue(cmd.hasrun)


	def testGtk(self):
		app = ZimApplication()

		class MockCmd(GtkCommand):

			def __init__(self):
				self.opts = {'standalone': True}
				self.hasrun = False

			def _quit(self, *a):
				import gobject, gtk
				gtk.main_quit()
				return False # stop timer

			def run(self):
				import gobject, gtk
				self.hasrun = True
				gobject.timeout_add(500, self._quit)
				return gtk.Window()

		cmd = MockCmd()
		self.assertFalse(cmd.hasrun)
		app._run_cmd(cmd, ())
		self.assertTrue(cmd.hasrun)
