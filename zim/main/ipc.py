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

SERVER_ADDRESS += '-%i'
COUNTER = 0

# For robustness against unavailable sockets, if socket exists but error
# occurs when connecting, we increase COUNTER and try again. Thus trying to
# find the first socket that is avaialable
#
# Errors that we encountered:
#
# On windows:
# - Client:
#   - WindowsError: [Errno 2] -- pipe does not exist
#   - EOFError -- no reply (close while waiting)
# - Listener
#   - no errors seen, seems to allow multiple listeners on one pipe !
#
# On Linux:
# - Client
#   - socket.error: [Errno 2] - 'No such file or directory'
#   - IOError: [Errno 104] - 'Connection reset by peer' - close while sending
#   - EOFError close while waiting for reply
# - Listener
#   - socket.error: [Errno 98]  - 'Address already in use'



def dispatch(*args):
	'''If there is an existing zim process pass along the arguments
	@param args: commandline arguments
	@raises AssertionError: when no existing zim process or connection failed
	'''
	global COUNTER
	assert not get_in_main_process()
	try:
		conn = Client(SERVER_ADDRESS % COUNTER, SERVER_ADDRESS_FAMILY)
		conn.send(args)
		re = conn.recv()
	except Exception, e:
		if hasattr(e, 'errno') and e.errno == 2:
			raise AssertionError, 'No-one is listening'
		else:
			COUNTER += 1
			if COUNTER < 100:
				return dispatch(*args) # recurs
			else:
				raise
	else:
		if not re == 'OK':
			raise AssertionError, 'Error in response: got %s' % re


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
	global COUNTER
	try:
		l = Listener(SERVER_ADDRESS % COUNTER, SERVER_ADDRESS_FAMILY)
	except:
		COUNTER += 1
		if COUNTER < 100:
			return _listener_thread_main(started, handler) # recurs
		else:
			raise

	started.set()
	logger.debug('Listening on %s', SERVER_ADDRESS % COUNTER)
	while True:
		conn = l.accept()
		args = conn.recv()

		#~ print ">>", argv
		logger.debug('Recieved remote call: %r', args)

		if args == 'CLOSE':
			conn.send('OK')
			conn.close()
			break
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
	conn = Client(SERVER_ADDRESS % COUNTER, SERVER_ADDRESS_FAMILY)
	conn.send('CLOSE')
	re = conn.recv()
