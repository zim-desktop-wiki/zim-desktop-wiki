# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import os
import sys
import socket
import gobject
import logging

try:
	import json # in standard lib since 2.6
except:
	import simplejson as json # extra dependency

from zim.fs import get_tmpdir
from zim.config import XDG_CACHE_HOME

# FUTURE: implement a DBus based subclass for usage on the linux desktop

logger = logging.getLogger('zim.daemon')


class DaemonError(Exception):
	pass


class UnixDaemon(object):

	def daemonize(self):
		'''Spawn new process that is disasociated from current environment'''
		showoutput = logger.isEnabledFor(logging.INFO)

		# First fork
		pid = os.fork()
		if pid > 0:
			# return in calling process
			return False

		# Decouple from parent environment
		os.chdir("/")
		os.setsid()
		os.umask(0)

		# Second fork
		pid = os.fork()
		if pid > 0:
			# exit from second parent
			sys.exit(0)

		# Redirect standard file descriptors
		sys.stdout.flush()
		sys.stderr.flush()
		si = file(os.devnull, 'r')
		so = file(os.devnull, 'a+')
		se = file(os.devnull, 'a+', 0)
		os.dup2(si.fileno(), sys.stdin.fileno())
		if not showoutput:
			os.dup2(so.fileno(), sys.stdout.fileno())
			os.dup2(se.fileno(), sys.stderr.fileno())

		# Run daemon in child process
		self.main()
		sys.exit(0)


class SocketDaemon(object):
	'''Makes the daemon listen for instructions from a socket'''

	# TODO common base class with the zim.www Server object ?

	def main(self):
		self.start()
		gobject.MainLoop().run()
		self.stop()

	def start(self):
		'''Open a socket and start listening'''
		logger.info('Starting %s', self.__class__.__name__)

		# open sockets for connections
		self.socket = socket.socket(self.socket_family)
		self.socket.bind(self.socket_address) # TODO use socket.gethostname() for public server
		self.socket.listen(5)

		gobject.io_add_watch(self.socket, gobject.IO_IN,
			lambda *a: self.do_accept_request())

	def stop(self):
		'''Close the socket and stop listening, emits the 'stopped' signal'''
		try:
			self.socket.close()
		except Exception, error:
			logger.error(error)
		self.socket = None

		logger.info('Stopped %s', self.__class__.__name__)

	def do_accept_request(self):
		# set up handler for new connection
		clientsocket, clientaddress = self.socket.accept() # TODO timeout ?

		rfile = clientsocket.makefile('rb')
		cmd, args = json.loads(rfile.readline())
		rfile.close()

		try:
			handler = getattr(self, "cmd_%s" % cmd)
			value = handler(args)
		except Exception, error:
			value = ('Error', str(error))

		wfile = clientsocket.makefile('wb')
		wfile.write(json.dumps(value, separators=(',',':')) + '\n')
		wfile.flush()
		wfile.close()

		clientsocket.close()
		return True # else io watch gets deleted

	def cmd_ping(self, arg):
		return 'Ack'

	def cmd_quit(self, arg):
		gobject.MainLoop().quit()
		# HACK just calling MainLoop.quit()should be enough..
		self.stop()
		sys.exit(0)
		#~ return 'Ack'


class UnixSocketDaemon(UnixDaemon, SocketDaemon):

	socket_family = socket.AF_UNIX
	socket_address = get_tmpdir().file('daemon-socket').path

	def start(self):
		if os.path.exists(self.socket_address):
			os.remove(self.socket_address)
		SocketDaemon.start(self)


class WindowsSocketDaemon(UnixDaemon, SocketDaemon):

	# No named sockets avaialble on windows, need to use a network socket.
	# Let's hope nobody is using the same port number
	# Ow, and let's really hope we are running single user...

	socket_family = socket.AF_INET
	socket_address = ('localhost', 52342)
	# used an arbitrary port number - may need changing if conflicts seen


if os.name == 'posix':
	Daemon = UnixSocketDaemon
elif os.name == 'nt':
	Daemon = WindowsSocketDaemon
else:
	logger.warn('Unknown OS, assuming POSIX process semantics')


class SocketDaemonProxy(object):

	def __init__(self):
		# Start daemon if none exists
		# Determine if the daemon exists by a handshake
		try:
			self.ping()
		except socket.error:
			Daemon().daemonize()
			self.ping()

	def ping(self): return self._call('ping', reply=True)

	def quit(self): return self._call('quit')

	def _call(self, cmd, args=None, reply=False):
		s = socket.socket(Daemon.socket_family)
		s.connect(Daemon.socket_address)

		line = json.dumps((cmd, args), separators=(',',':'))
		logger.debug('Sending to daemon: %s', line)

		wfile = s.makefile('wb')
		wfile.write(line + '\n')
		wfile.flush()
		wfile.close()

		if reply:
			rfile = s.makefile('rb')
			line = rfile.readline()
			rfile.close()

			logger.debug('Daemon replied: %s', line.strip())
			value = json.loads(line)

			if isinstance(value, list) and value[0] == 'Error':
				raise DaemonError(value[1])

			return value


DaemonProxy = SocketDaemonProxy


if __name__ == '__main__':
	logging.basicConfig(
		level=logging.DEBUG, format='%(levelname)s: %(message)s')
	daemon = DaemonProxy()
	print 'Enter methods to call on the daemon proxy'
	print 'Type "quit" to exit'
	while True:
		sys.stdout.write('Daemon> ')
		cmd = sys.stdin.readline().strip()
		method = getattr(daemon, cmd)
		method()
		if cmd == 'quit':
			break
