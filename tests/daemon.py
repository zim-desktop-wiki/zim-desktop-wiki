
# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests
from tests import TestCase

import os
import time
import signal
import gobject

from zim.fs import *
from zim.daemon import *


def waitfile(file, exists=True):
	'''Wait for a file to (dis-)appear - timeout of 10 seconds'''
	i = 0
	while i < 10:
		if file.exists() != exists:
			time.sleep(1)
			i += 1
		else:
			break
	assert file.exists() == exists, 'File did not (dis-)appear'


class TestDaemon(TestCase):

	slowTest = True

	@classmethod
	def skipTestZim(klass):
		if os.name == 'nt':
			return 'Daemon not supported on Windows'
		else:
			return False


	def runTest(self):
		'''Test GUI daemon interaction'''
		dir = Dir(tests.create_tmp_dir('daemon'))
		socket = dir.file('test-socket')
		pidfile = dir.file('daemon.pid')

		assert Daemon == UnixSocketDaemon
		Daemon.socket_address = socket.path
		Daemon.pidfile = pidfile.path

		pid = None
		klass = 'tests.daemon.MockDaemonClient'
		try:
			# Start daemon
			proxy = SocketDaemonProxy()
			pid = int(pidfile.read())
			self.assertTrue(pid > 0)

			# Check child object interaction
			object1 = proxy.get_object(klass, 'Obj1', 'ID1')

			file = dir.file('test1.txt')
			self.assertTrue(object1.write(file.path, msg='foobar\n'))
			waitfile(file)
			self.assertEqual(file.read(), 'ID1: foobar\n')

			object2 = proxy.get_object(klass, 'Obj2', 'ID2')

			file = dir.file('test2.txt')
			self.assertTrue(object2.write(file.path, msg='baz\n'))
			waitfile(file)
			self.assertEqual(file.read(), 'ID2: baz\n')

			self.assertEqual(proxy.list_objects(),
				[(klass, 'Obj1'), (klass, 'Obj2')]
			)

			# See daemon quit after last child
			object1.exit()
			object2.exit()

			waitfile(pidfile, exists=False)
			try:
				os.kill(pid, signal.SIGUSR1)
			except OSError:
				pass # no such process
			else:
				assert False, 'Process still running'

		except Exception, error:
			# clean up process by pidfile
			if pid and pid > 0:
				try:
					print 'Kill process %i' % pid
					os.kill(pid, signal.SIGKILL)
				except OSError:
					pass
			raise error


class MockDaemonClient(object):

	# Mock client for the daemion to run. It doesn't do much except
	# telling you it's ID by touching a file.

	def __init__(self, id):
		self.id = id

	def main(self):
		gobject.MainLoop().run()

	def write(self, file, msg):
		File(file).write(self.id+': '+msg)

	def exit(self):
		gobject.MainLoop().quit()
		os._exit(0) # just to be sure
