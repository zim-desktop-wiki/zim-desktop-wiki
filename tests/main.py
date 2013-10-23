# -*- coding: utf-8 -*-

# Copyright 2012,2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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

import zim.main


class TestInitFunctions(tests.TestCase):

	def setUp(self):
		self.old_exe = zim.main.ZIM_EXECUTABLE

	def tearDown(self):
		zim.main.ZIM_EXECUTABLE = self.old_exe

		if hasattr(FS, '_signal_handlers') \
		and 'mount' in FS._signal_handlers:
			del FS._signal_handlers['mount']

	def testGetApplication(self):
		zim.main._set_zim_executable('/foo/bar/zim.py')
		self.assertEqual(zim.main.ZIM_EXECUTABLE, '/foo/bar/zim.py')
		app = zim.main.get_zim_application('--help')
		self.assertEqual(app.cmd[:4], (sys.executable, '/foo/bar/zim.py', '--help', '--standalone'))
			# limit to cmd[:4] because running test with "-D" or "-V" can add more

	def testInitApplication(self):
		dir = Dir(self.create_tmp_dir())
		exe = dir.file('zim.py')
		exe.touch()
		init = dir.file('init.conf')
		init.write(
			'[Environment]\n'
			'TEST_ENV=bar\n'
			'TEST_ENV_REL=./foo\n'
			'TEST_ENV_HOME=~/baz\n'
			'LANGUAGE=nl_NL\n'
			'\n'
			'[Path /foo/bar]\n'
			'mount=dus\n'
			'\n'
		)
		automountfile = \
			zim.config.basedirs.XDG_CONFIG_HOME.file('zim/automount.conf')
		automountfile.write(
			'[Path /foo/bar]\n'
			'mount=dus\n'
			'\n'
			'[Path /foo/dus]\n'
			'mount=dus\n'
			'\n'
		)

		with EnvironmentConfigContext({
			'TEST_ENV': None,
			'TEST_ENV_REL': None,
			'TEST_ENV_HOME': None,
			'LANGUAGE': 'en_US',
		}):
			zim.init_gettext()
			self.assertNotEqual(_('Page'), 'Pagina', 'LANGUAGE not picked up correctly')

			zim.main.init_zim_application(exe.path, config=None)

			self.assertTrue(environ['TEST_ENV'], 'bar')
			self.assertTrue(environ['TEST_ENV_REL'], dir.subdir('foo').path)
			self.assertTrue(environ['TEST_ENV_HOME'], Dir('~/baz').path)

			self.assertEqual(_('Page'), 'Pagina', 'LANGUAGE not set correctly')

			self.assertTrue((
					hasattr(FS, '_signal_handlers')
					and 'mount' in FS._signal_handlers
				), 'mount signal not connected')
			self.assertEqual(len(FS._signal_handlers['mount']), 3)


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


## ExportCommand() is tested in tests/export.py



