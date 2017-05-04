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
import os

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



_m = hashlib.md5()
_m.update(zim.ZIM_EXECUTABLE)

key = zim.__version__ + '-' + _m.hexdigest()[:8]
	# Make name specific for the install location
	# But don't worry about collisons, first few bytes should do it

if sys.platform == 'win32':
	# Windows named pipe
	userstring = zim.fs.get_tmpdir().basename # "zim-$USER" without unicode!
	SERVER_ADDRESS = '\\\\.\\pipe\\%s-%s-primary' % (userstring, key)
	SERVER_ADDRESS_FAMILY = 'AF_PIPE'
else:
	# Unix domain socket
	SERVER_ADDRESS = str(zim.fs.get_tmpdir().file('primary-%s' % key).path)
		# BUG in multiprocess, name must be str instead of basestring
	SERVER_ADDRESS_FAMILY = 'AF_UNIX'


# Try to be as obust as possible for all kind of socket errors.
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
	assert not get_in_main_process()
	try:
		logger.debug('Connecting to %s', SERVER_ADDRESS)
		conn = Client(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
		conn.send(args)
		if conn.poll(5):
			re = conn.recv()
		else:
			re = 'No response'
	except Exception, e:
		if hasattr(e, 'errno') and e.errno == 2:
			raise AssertionError, 'No such file or directory'
		else:
			raise AssertionError, 'Connection failed'
	else:
		if re != 'OK':
			raise AssertionError, 'Error in response: %s' % re


def start_listening(handler):
	'''Start listening to socket or named pipe for new commandline
	calls. Also sets current process to be the main process.
	@param handler: the method to call when new commands are recieveds
	'''
	set_in_main_process(True)

	logger.debug('Start listening on: %s', SERVER_ADDRESS)
	try:
		if SERVER_ADDRESS_FAMILY == 'AF_UNIX' \
		and os.path.exists(SERVER_ADDRESS):
			# Clean up old socket (someone should already have checked
			# before whether or not it is functional)
			os.unlink(SERVER_ADDRESS)
		listener = Listener(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
	except:
		logger.exception('Error setting up Listener')
		return False
	else:
		t = threading.Thread(target=_listener_thread_main, args=(listener, handler))
		t.daemon = True
		t.start()
		return True


def _listener_thread_main(listener, handler):
	while True:
		try:
			conn = listener.accept()
			args = conn.recv()
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
		except:
			logger.exception('Error while handling incoming connection')


def _close_listener():
	# For testing
	conn = Client(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
	conn.send('CLOSE')
	re = conn.recv()
