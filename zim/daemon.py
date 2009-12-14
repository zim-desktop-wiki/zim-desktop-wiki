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
import time

try:
	import json # in standard lib since 2.6
except:
	import simplejson as json # extra dependency

from zim.fs import get_tmpdir, File
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

	pidfile = get_tmpdir().file('daemon.pid').path

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
			File(self.pidfile).write('%i\n' % pid)
			os._exit(0)

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
		os.unlink(self.pidfile)
		os._exit(0)


class SocketDaemon(object):
	'''Makes the daemon listen for instructions from a socket'''

	# TODO common base class with the zim.www Server object ?

	def __init__(self, persistent=False, modules='zim'):
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
		logger.debug('Socket address: %s', self.socket_address)

		# open sockets for connections
		self.socket = socket.socket(self.socket_family)
		self.socket.bind(self.socket_address)
		self.socket.listen(5)

		gobject.io_add_watch(self.socket, gobject.IO_IN,
			lambda *a: self.do_accept_request())

	def stop(self):
		'''Close the socket and stop listening'''
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

	def cmd_vivicate(self, klass, name, *args, **kwargs):
		id = (klass, name)
		child = self.get_child(id)
		if child is None:
			child = ChildProxy(klass, id, *args, **kwargs)
			self.children.append(child)
			gobject.child_watch_add(child.pid, self._on_child_exit)
		return True

	def cmd_relay(self, id, method, *args, **kwargs):
		child = self.get_child(id)
		if child:
			child.call(method, *args, **kwargs)
			return True
		else:
			return False

	def get_child(self, id):
		id = tuple(id)
		for child in self.children:
			if child.id == id:
				return child
		else:
			return None

	def cmd_list_objects(self):
		return [child.id for child in self.children]

	#~ def cmd_quit_all(self):
		#~ for child in self.children:
			#~ child.quit()
		#~ return 'Ack'

	def cmd_quit_if_nochild(self):
		gobject.idle_add(self._check_quit_if_nochild)
		return True

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
			os.unlink(self.pidfile)
			os._exit(0)
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
		# timeout on 10 seconds
		ack = None
		try:
			ack = self.ping()
		except socket.error:
			Daemon().daemonize()
			i = 0
			while i < 10:
				try:
					ack = self.ping()
				except socket.error:
					i += 1
					time.sleep(1)
				else:
					break
		assert ack == 'Ack', 'Could not start daemon'

	def ping(self):
		'''Returns 'Ack' to test daemon interaction'''
		return self._call('ping')

	def get_object(self, klass, name, *args, **kwargs):
		'''Returns a proxy object for an object of klass 'klass'
		which is uniquely identified by 'name'. All other arguments
		are passed on to the object constructor if it needs to be
		created.
		'''
		assert self._call('vivicate', klass, name, *args, **kwargs)
		return DaemonProxyObject(self, (klass, name))

	def list_objects(self):
		'''Returns a list of tuples giving the class name and
		object name of each running object.
		'''
		return map(tuple, self._call('list_objects'))

	def get_notebook(self, notebook):
		'''Returns a proxy object for a GtkInterface for notebook'''
		if isinstance(notebook, basestring):
			assert notebook.startswith('file://')
		else:
			assert hasattr(notebook, 'uri')
			notebook = notebook.uri
		klass = 'zim.gui.GtkInterface'
		assert self._call('vivicate', klass, notebook,
			notebook=notebook, usedaemon=True)
		return DaemonProxyNotebookObject(self, (klass, notebook))

	def list_notebooks():
		'''Returns a list of notebook URIs for open notebooks'''
		for klass, name in self.list_objects():
			if klass == 'zim.gui.GtkInterface':
				yield name

	#~ def emit():
		#~ '''Broadcast a signal to all notebooks'''

	#~ def quit_all(self):
		#~ '''Quit all running instances'''

	def quit_if_nochild(self):
		'''Have the daemon check if it should quit itself'''
		return self._call('quit_if_nochild') == 'Ack'

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


class DaemonProxyObject(object):

	def __init__(self, daemonproxy, id):
		self.proxy = daemonproxy
		self.id = id

	def __getattr__(self, name):
		return lambda *a, **k: self._relay(name, *a, **k)

	def _relay(self, method, *args, **kwargs):
		return self.proxy._call('relay', self.id, method, *args, **kwargs)


class DaemonProxyNotebookObject(DaemonProxyObject):

	@property
	def uri(self): return self.id[1]

	def present(self, page=None, geometry=None, fullscreen=None):
		'''Present a specific page and/or set window mode'''
		if page and not isinstance(page, basestring):
			assert hasattr(page, 'name')
			page = page.name
		return self._relay('present', page,
				geometry=geometry, fullscreen=fullscreen)

	def hide(self):
		'''Hide a specific notebook window'''
		return self._relay('hide')

	def quit(self):
		'''Quit a single notebook'''
		return self._relay('quit')


class UnixPipeProxy(object):

	def __init__(self, klass, id, *args, **kwargs):
		self.id = id
		self.klass = klass
		self.opts = (args, kwargs)
		self.spawn()

	def spawn(self):
		r, w = os.pipe()
		pid = os.fork()
		if pid > 0:
			# parent
			os.close(r)
			self.pipe = w
			self.pid = pid
			logger.debug('Child spawned %i %s', self.pid, self.id)
		else:
			# child
			os.close(w)
			self.pipe = r
			try:
				self._main()
			except:
				logger.exception('Error in child main:')
				os._exit(1)
			else:
				os._exit(0)

	def _main(self):
		# Main function in the child process:
		# import class module, instantiate object,
		# hook it to recieve calls and run main()

		# __import__ has some quirks, see the reference manual
		modname, klassname = self.klass.rsplit('.', 1)
		mod = __import__(modname)
		for name in modname.split('.')[1:]:
			mod = getattr(mod, name)

		klassobj = getattr(mod, klassname)

		args, kwargs = self.opts
		obj = klassobj(*args, **kwargs)
		#~ print '>>> klass', klassobj
		#~ print '>>> obj', obj

		def _recieve(fd, *a):
			# For some reason things go wrong when we use fdopen().readline()
			# So writing this small readline function
			line = ''
			while not line.endswith('\n'):
				line += os.read(fd, 1)
			#~ print 'GOT %s' % line
			func, arg, karg = deserialize_call(line)
			try:
				method = getattr(obj, func)
				assert method, 'BUG: no such method %s.%s' % (obj.__class__.__name__, func)
				method(*arg, **karg)
			except:
				logger.exception('Error in child handler:')
			return True # keep listening

		gobject.io_add_watch(self.pipe, gobject.IO_IN, _recieve)
		obj.main()

	def call(self, func, *arg, **karg):
		line = serialize_call(func, *arg, **karg)
		logger.debug('Sending to child %i: %s', self.pid, line)
		os.write(self.pipe, line)

	def close(self):
		logger.debug('Child exited %i %s', self.pid, self.id)
		try:
			os.close(self.pipe)
		except IOError:
			pass


ChildProxy = UnixPipeProxy



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
