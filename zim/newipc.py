# -*- coding: utf-8 -*-

# Copyright 2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This module supports:
#  1. Dispatching a list of commandline arguments to a socket
#  2. Listening to a socket for commandline arguments. If recieved,
#     zim.main.main() to called to handle those arguments.
#
# It is up to the commands in zim.main() to decide whether to execute
# in the current process or to dispatch.


import sys
import threading
import logging

from multiprocessing.connection import Listener, Client

import zim.fs
import zim.main

# TODO - make robust if socket already exists, but not responsive
# TODO - for tests force the socket name ?


logger = logging.getLogger('zim.ipc')


_IN_MAIN_PROCESS = False


def get_in_main_process():
	'''Returns C{True} if we are already in the main process'''
	return _IN_MAIN_PROCESS


def set_in_main_process(in_main_process):
	'''Set whether we are in the main process or not'''
	global _IN_MAIN_PROCESS
	_IN_MAIN_PROCESS = in_main_process



if sys.platform == 'win32':
	# Windows named pipe
	userstring = zim.fs.get_tmpdir().basename # "zim-$USER" without unicode!
	SERVER_ADDRESS = '\\\\.\\pipe\\%s-server' % userstring
	SERVER_ADDRESS_FAMILY = 'AF_PIPE'
else:
	# Unix domain socket
	SERVER_ADDRESS = str(zim.fs.get_tmpdir().file('zim-server-socket').path)
		# BUG in multiprocess, name must be str instead of basestring
	SERVER_ADDRESS_FAMILY = 'AF_UNIX'



def dispatch(*argv):
	'''If there is an existing zim process pass along the arguments
	@param argv: commandline arguments
	@raises: error when no existing zim process or connection failed
	'''
	assert not get_in_main_process()
	conn = Client(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
	conn.send((None,) + argv) # pad with None for exe
	re = conn.recv()
	if not re == 'OK':
		raise AssertionError, 'Got %s' % re



def start_listening():
	'''Start listening to socket or named pipe for new commandline
	calls. Also sets current process to be the main process.
	'''
	set_in_main_process(True)
	started = threading.Event()
	t = threading.Thread(target=_listener_thread_main, args=(started,))
	t.daemon = True
	t.start()
	ok = started.wait(5)
	if not ok:
		raise AssertionError, 'Listener did not start'


def _listener_thread_main(started):
	l = Listener(SERVER_ADDRESS)
	started.set()
	while True:
		conn = l.accept()
		argv = conn.recv()

		#~ print ">>", argv
		logger.debug('Recieved remote call: %r', argv)

		if argv == 'CLOSE':
			conn.send('OK')
			conn.close()
		else:
			assert isinstance(argv, (list, tuple))

			# Throw back into the main thread -- assuming gtk main running
			import gobject

			def callback():
				zim.main.main(*argv)
				return False # delete signal
			gobject.idle_add(callback)

			conn.send('OK')
			conn.close()


def _close_listener():
	# For testing
	conn = Client(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
	conn.send('CLOSE')
	re = conn.recv()

