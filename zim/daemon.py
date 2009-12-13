# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''Daemon IPC infrastucture parts for the zim GUI.

We rely on a daemon process spawning instances of the zim gui
and managing those instances. A new process that is stated talks
to the daemon, which talks to the actual gui instance.

Current implementation the daemon listens to a socket, so any
process can connect to it, while communication from the daemon to the
gui instances uses anonymous pipes.

  DaemonProxy --socket--> Daemon
                            |
                            |--- ChildProxy --pipe--> GtkInterface
                            |--- ChildProxy --pipe--> GtkInterface
                            |--- ChildProxy --pipe--> GtkInterface
                            ...

Of course the instances in turn can also connect to the socket of
the daemon, e.g. to spawn a new instance.
'''

import os
import sys
import socket
import gobject
import logging
import signal

try:
	import json # in standard lib since 2.6
except:
	import simplejson as json # extra dependency

from zim.fs import get_tmpdir
from zim.config import XDG_CACHE_HOME

# FUTURE: implement a DBus based subclass for usage on the linux desktop

# TODO split this in a GUI part and a daemon part that is not GUI specific

logger = logging.getLogger('zim.daemon')


def serialize_call(func, *args, **kwargs):
	'''Returns single line encoding this function call'''
	return json.dumps((func, args, kwargs), separators=(',',':')) + '\n'

def deserialize_call(line):
	'''Returns tuple of (func, arguments, keywordargumentss)'''
	func, args, kwargs = json.loads(line)
	if kwargs:
		# get rid of unicode in keyword names
		kwargs = dict([(str(key), value) for key, value in kwargs.items()])
	return func, args, kwargs

class DaemonError(Exception):
	pass


class UnixDaemon(object):

	def daemonize(self):
		'''Spawn new process that is disasociated from current environment'''
		showoutput = logger.isEnabledFor(logging.INFO)

		# First fork
		pid = os.fork()
		if pid > 0:
			# return in calling process after second parent exits
			os.waitpid(pid, 0)
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

	def __init__(self, persistent=False):
		'''Constructor. If 'persistent' is True the daemon stays alive
		even after the last child exited. Otherwise we exit after the
		last child exits.
		'''
		self.children = []
		self.persistent = persistent

	def main(self):
		self.start()
		signal.signal(signal.SIGPIPE, signal.SIG_IGN)
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
		func, args, kwargs = deserialize_call(rfile.readline())
		rfile.close()

		try:
			handler = getattr(self, "cmd_%s" % func)
			value = handler(*args, **kwargs)
		except Exception, error:
			logger.exception('Exception in zim daemon:')
			value = ('Error', str(error))

		wfile = clientsocket.makefile('wb')
		wfile.write(json.dumps(value, separators=(',',':')) + '\n')
		wfile.flush()
		wfile.close()

		clientsocket.close()
		return True # else io watch gets deleted

	def cmd_ping(self):
		return 'Ack'

	def cmd_list_notebooks(self):
		return [child.notebook for child in self.children]

	def cmd_quit_all(self):
		for child in self.children:
			child.quit()
		return 'Ack'

	def cmd_quit_if_nochild(self):
		gobject.idle_add(self._check_quit_if_nochild)
		return 'Ack'

	def cmd_present(self, notebook, page=None, **opts):
		child = self.get_child(notebook)
		if child:
			child.present(page, **opts)
		else:
			child = ChildProxy(notebook, page, **opts)
			self.children.append(child)
			gobject.child_watch_add(child.pid, self._on_child_exit)
		return 'Ack'

	def cmd_hide(self, notebook):
		child = self.get_child(notebook)
		if child:
			child.hide()
			return 'Ack'
		else:
			return 'NotFound'

	def cmd_quit(self, notebook):
		child = self.get_child(notebook)
		if child:
			child.quit()
			return 'Ack'
		else:
			return 'NotFound'

	def cmd_emit(self, signal):
		for child in self.children:
			child.emit(signal)

	def get_child(self, notebook):
		for child in self.children:
			if child.notebook == notebook:
				return child
		else:
			return None

	def _on_child_exit(self, pid, status):
		for child in self.children:
			if child.pid == pid:
				child.close()
				self.children.remove(child)
				break
		else:
			logger.warn('Child exiting that is not in our list %i', pid)

		self._check_quit_if_nochild()

	def _check_quit_if_nochild(self):
		if not self.persistent and not self.children:
			logger.info('Last instance quit - exiting daemon')
			gobject.MainLoop().quit()
			# HACK just calling MainLoop.quit()should be enough..
			self.stop()
			sys.exit(0)
		return False # in case we are called from event


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

	def ping(self):
		'''Returns 'Ack' to test daemon interaction'''
		return self._call('ping')

	def list_notebooks(self):
		'''Returns a list of open notebooks'''
		return self._call('list_notebooks')

	def quit_all(self):
		'''Quit all running instances'''
		return self._call('quit_all') == 'Ack'

	def quit_if_nochild(self):
		'''Have the daemon check if it should quit itself'''
		return self._call('quit_if_nochild') == 'Ack'

	def present(self, notebook, page=None, **opts):
		'''Present a specific notebook and page. Could start a new instance'''
		notebook = self._notebook(notebook)
		if page:
			page = self._page(page)
		return self._call('present', notebook, page, **opts) == 'Ack'
		# TODO pass fullscreen and geometry

	def hide(self, notebook):
		'''Hide a specific notebook window'''
		notebook = self._notebook(notebook)
		return self._call('hide', notebook) == 'Ack'

	def quit(self, notebook):
		'''Quit a single notebook'''
		notebook = self._notebook(notebook)
		return self._call('quit', notebook) == 'Ack'

	def emit(self, signal):
		'''Broadcast a signal to all notebooks'''
		return self._call('emit', signal) == 'Ack'

	def _notebook(self, notebook):
		if isinstance(notebook, basestring):
			assert notebook.startswith('file://')
		else:
			assert hasattr(notebook, 'uri')
			notebook = notebook.uri
		return notebook

	def _page(self, page):
		if not isinstance(page, basestring):
			assert hasattr(page, 'name')
			page = page.name
		return page

	def _call(self, func, *args, **kwargs):
		s = socket.socket(Daemon.socket_family)
		s.connect(Daemon.socket_address)

		line = serialize_call(func, *args, **kwargs)
		logger.debug('Sending to daemon: %s', line)

		wfile = s.makefile('wb')
		wfile.write(line + '\n')
		wfile.flush()
		wfile.close()

		rfile = s.makefile('rb')
		line = rfile.readline()
		rfile.close()

		logger.debug('Daemon replied: %s', line.strip())
		value = json.loads(line)

		if isinstance(value, list) and value[0] == 'Error':
			raise DaemonError(value[1])

		return value


DaemonProxy = SocketDaemonProxy


class UnixPipeProxy(object):

	def spawn(self):
		r, w = os.pipe()
		pid = os.fork()
		if pid > 0:
			# parent
			os.close(r)
			self.pipe = w
			self.pid = pid
			logger.debug('Child spawned %i %s', self.pid, self.notebook)
		else:
			# child
			os.close(w)
			self.pipe = r
			try:
				self._main()
			except:
				logger.exception('Error in child main:')
				sys.exit(1)
			else:
				sys.exit(0)

	def _send(self, func, *arg, **karg):
		line = serialize_call(func, *arg, **karg)
		logger.debug('Sending to child %i: %s', self.pid, line)
		os.write(self.pipe, line)


class ChildProxy(UnixPipeProxy):

	def __init__(self, notebook, page=None, **opts):
		self.notebook = notebook
		self.page = page
		self.opts = opts
		self.spawn()

	def _main(self):
		'''Main function in the child process'''

		import zim.gui
		gui = zim.gui.GtkInterface(self.notebook, self.page, usedaemon=True, **self.opts)
		# TODO pass along command line options

		def _recieve(fd, *a):
			# For some reason things go wrong when we use fdopen().readline()
			# So writing this small readline function
			line = ''
			while not line.endswith('\n'):
				line += os.read(fd, 1)
			#~ print 'GOT %s' % line
			func, arg, karg = deserialize_call(line)
			try:
				handler = getattr(gui, func)
				assert handler, 'BUG: no such method %s' % func
				handler(*arg, **karg)
			except:
				logger.exception('Error in child handler:')
			return True # keep listening

		gobject.io_add_watch(self.pipe, gobject.IO_IN, _recieve)
		gui.main()

	def present(self, page=None, **opts):
		self._send('present', page, **opts)

	def hide(self):
		self._send('hide')

	def quit(self):
		self._send('quit')

	def emit(self, signal):
		self.emit('emit', signal)

	def close(self):
		'''Called in parent process after child process exited'''
		logger.debug('Child exited %i %s', self.pid, self.notebook)
		try:
			os.close(self.pipe)
		except IOError:
			pass


# Debug code to have a small shell to send commands to the daemon
def shell():
	'''This method is used for debugging the zim daemon. It spawns
	a simple commandline that allows you to send commands to the
	daemon process.
	'''
	import shlex
	logging.basicConfig(
		level=logging.DEBUG, format='%(levelname)s: %(message)s')

	daemon = DaemonProxy()

	print 'Enter methods to call on the daemon proxy'
	while True:
		sys.stdout.write('zim.daemon> ')
		line = sys.stdin.readline().strip()
		if not line:
			break
		words = shlex.split(line)
		try:
			cmd = words.pop(0)
			method = getattr(daemon, cmd)
			method(*words)
		except:
			logging.exception('Error in shell process:')


if __name__ == '__main__':
	shell()
