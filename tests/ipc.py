# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import os
import sys
import signal
import gobject

import zim.ipc
from zim.ipc import *

import zim

from zim.fs import File, get_tmpdir
from zim.notebook import NotebookInfo, Path, Page
from zim.stores.files import FileStorePage


@tests.slowTest
class TestIPC(tests.TestCase):

	def setUp(self):
		self.OLD_SERVER_ADDRESS = zim.ipc.SERVER_ADDRESS
		self.OLD_AUTHKEY_FILE = zim.ipc.AUTHKEY_FILE
		zim.ipc.SERVER_ADDRESS += '-test-%i' % os.getpid()
		zim.ipc.AUTHKEY_FILE = get_tmpdir().file('zim-server-authkey-test-%i' % os.getpid())
		zim.ZIM_EXECUTABLE = './zim.py'

	def tearDown(self):
		stop_server_if_running()
		zim.ipc.SERVER_ADDRESS = self.OLD_SERVER_ADDRESS
		zim.ipc.AUTHKEY_FILE = self.OLD_AUTHKEY_FILE
		zim.ZIM_EXECUTABLE = None

	def runTest(self):
		# Test setting up the server
		start_server_if_not_running()
		server = ServerProxy()
		ack = server.ping()
		self.assertEqual(ack[0], 'ACK')
		start_server_if_not_running() # Should do nothing..
		server = ServerProxy()
		self.assertEqual(server.ping(), ack) # ack has pid, so we know still same server process

		# Test adding a child and interact with it
		child = server.get_proxy(RemoteObject('tests.ipc.ChildClass', 'file:///foo'))
		ack = child.ping()
		self.assertEqual(ack[0], 'CHILD')

		child = server.get_proxy(RemoteObject('tests.ipc.ChildClass', 'file:///foo'))
			# should not vivicate again, verify by pid in ack
		self.assertEqual(child.ping(), ack)

		# Error handling
		self.assertRaises(ValueError, child.error)

		# Add a second child
		child2 = server.get_proxy(RemoteObject('tests.ipc.ChildClass', 'file:///bar'))
			# should not vivicate again, verify by pid in ack
		self.assertNotEqual(child2.ping(), ack)

		children = server.list_objects()
		children.sort(key=lambda c: c.id)
		self.assertEqual(children, [
			RemoteObject('tests.ipc.ChildClass', 'file:///bar'),
			RemoteObject('tests.ipc.ChildClass', 'file:///foo')
		])

		# Test API for notebooks
		server._notebookklass = 'tests.ipc.ChildClass' # HACK to test convenience methods
		self.assertEqual(server.list_notebooks(), ['file:///bar', 'file:///foo'])
		proxy = server.get_notebook('file:///foo')
		self.assertEqual(child.ping(), ack)

		# Test these are serializable
		for obj in (
			File('file:///test'),
			NotebookInfo('file:///test'),
			Path('foo'),
			Page(Path('foo')),
			FileStorePage(Path('foo'), File('file:///test'), File('file:///test'), format='wiki'),
		):
			#~ print ">>> %r" % obj
			re = proxy.echo(obj)
			self.assertEqual(re, obj)

		# send a signal
		n = child.get_n_signals()
		server.emit('notebook-list-changed')
		self.assertEqual(child.get_n_signals(), n+1)

		# Wrap up
		server.quit()


class ChildClass(object):
	# Mock client for the daemon to run. It doesn't do much except
	# telling you it's ID by touching a file.

	def __init__(self, id):
		self.id = id
		self.n_signals = 0

	def main(self):
		zim.ipc.SERVER_CONTEXT._notebookklass = 'tests.ipc.ChildClass' # HACK to test convenience methods
		ServerProxy().connect('notebook-list-changed', self)
		gobject.MainLoop().run()

	def quit(self):
		gobject.MainLoop().quit()
		os._exit(0) # just to be sure

	def ping(self):
		return ('CHILD', os.getpid())

	def echo(self, value):
		return value

	def error(self):
		raise ValueError, 'Test Error'

	def on_notebook_list_changed(self):
		notebooks = ServerProxy().list_notebooks()
		assert len(notebooks) > 0, 'list_notebooks() returned: %s' % notebooks
		self.n_signals += 1

	def get_n_signals(self):
		return self.n_signals

