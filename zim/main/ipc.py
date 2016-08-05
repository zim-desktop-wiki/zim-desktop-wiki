# -*- coding: utf-8 -*-

# Copyright 2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This module is responsible for the inter-process communication (ipc)
between zim instances.

It provides low level functions to:

  1. Dispatching a list of commandline arguments to a socket
  2. Listening to a socket for commandline arguments. If recieved,
     a callback is invoked to handle those arguments.

'''

import sys
import threading
import logging
import hashlib

from multiprocessing.connection import Listener, Client

import zim
import zim.fs

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



version = zim.__version__
_m = hashlib.md5()
_m.update(zim.ZIM_EXECUTABLE)

version += '-' + _m.hexdigest() ## Make it specific for the install location


if sys.platform == 'win32':
	# Windows named pipe
	userstring = zim.fs.get_tmpdir().basename # "zim-$USER" without unicode!
	SERVER_ADDRESS = '\\\\.\\pipe\\%s-%s-primary' % (userstring, version)
	SERVER_ADDRESS_FAMILY = 'AF_PIPE'
else:
	# Unix domain socket
	SERVER_ADDRESS = str(zim.fs.get_tmpdir().file('primary-%s' % version).path)
		# BUG in multiprocess, name must be str instead of basestring
	SERVER_ADDRESS_FAMILY = 'AF_UNIX'



def dispatch(*args):
	'''If there is an existing zim process pass along the arguments
	@param args: commandline arguments
	@raises AssertionError: when no existing zim process or connection failed
	'''
	assert not get_in_main_process()
	conn = Client(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
	conn.send(args)
	re = conn.recv()
	if not re == 'OK':
		raise AssertionError, 'Got %s' % re



def start_listening(handler):
	'''Start listening to socket or named pipe for new commandline
	calls. Also sets current process to be the main process.
	@param handler: the method to call when new commands are recieveds
	'''
	set_in_main_process(True)
	started = threading.Event()
	t = threading.Thread(target=_listener_thread_main, args=(started, handler))
	t.daemon = True
	t.start()
	ok = started.wait(5)
	if not ok:
		raise AssertionError, 'Listener did not start'


def _listener_thread_main(started, handler):
	l = Listener(SERVER_ADDRESS)
	started.set()
	while True:
		conn = l.accept()
		args = conn.recv()

		#~ print ">>", argv
		logger.debug('Recieved remote call: %r', args)

		if args == 'CLOSE':
			conn.send('OK')
			conn.close()
		else:
			assert isinstance(args, (list, tuple))

			# Throw back into the main thread -- assuming gtk main running
			import gobject

			def callback():
				handler(*args)
				return False # delete signal
			gobject.idle_add(callback)

			conn.send('OK')
			conn.close()


def _close_listener():
	# For testing
	conn = Client(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
	conn.send('CLOSE')
	re = conn.recv()

