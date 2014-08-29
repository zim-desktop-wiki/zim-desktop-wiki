# -*- coding: utf-8 -*-

# Copyright 2012,2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''IPC infrastructure parts for the zim GUI.

We rely on a background process spawning instances of the zim gui
and managing those instances. A new process that is started talks
to this background process, which talks to the actual gui instance.

The background process, or server, listens to a socket, so any
process can connect to it, while communication to the
gui instances uses anonymous pipes::

  Client --socket--> Server
                       |
                       |---pipe--> GtkInterface
                       |---pipe--> GtkInterface
                       |---pipe--> GtkInterface
                       ...

The instances in turn can also connect to the server, e.g. to spawn a
new instance when a user selects another notebook from the notebook
dialog.

Any class can become the main application class of a child process.
In most cases this will be the GtkInterFace class which is used
to represent a single notebook window. However another example is the
DaemonTrayIcon class in the trayicon plugin which shows a single
tray icon for all open notebooks. A class for running a child process
should at least implement a "main()" and a "quit()" method, and its
constructor should take an identifyer as the first argument (if
there can be multiple instances of the same class).


@signal: C{notebook-list-changed ()}:
emitted when it is likely the notebook list changed
'''

# NOTE: DO NOT move this module to zim.gui.ipc, doing so would result
# in python loading zim.gui and thus gtk for each daemon instance.

# Re-using multiprocessing infrastructure here, even though it
# was not really intended for this. Main advantage is that it
# already handles forking, pipes etc. in a very robust way
# on both unix and windows. And allows us to send real objects :)
# We build our own RPC infrastructure on top to dispatch
# between processes.
# (Main focus for high level functions in multiprocessing is
# shared state, but that is not really our interest)

# In some cases a child also acts as a client and sends a request
# that way to e.g. another child, it that case it will still use
# the client connection to the server.
# A limitation for this scenario is that the child is not allowed
# to do so in response to a remote call - this will daed lock the
# server.
# (Hypothetically can be fixed by making the client use the pipe to send
# the message iff the server is waiting for a response, and have the server
# handle it and come back...)

# The server is multi-threading to ensure we are not blocking while
# a specific client is processing.

# TODO: re-enable code for using authkey - needs debugging


import sys
import gobject
import os
import re

import logging
import traceback

import multiprocessing
from multiprocessing import Process, Pipe
from multiprocessing.connection import Listener, Client

import threading
from Queue import Queue


import zim.main
import zim.errors
import zim.fs


logger = logging.getLogger('zim.ipc')


# globals
SERVER_CONTEXT = None #: used to in child process know about server
_recursive_conn_lock = False

VALID_NOTEBOOK_URI = re.compile(r"(\w+\+)?file://")


def in_child_process():
	'''Returns C{True} is the current process is a child process
	of a server process.
	'''
	global SERVER_CONTEXT
	return SERVER_CONTEXT is not None


def handle_argv():
	'''Check for special commandline args does not return
	if handled. Called in the beginning of the main script to allow
	bootstrap of subprocesses.
	'''
	multiprocessing.freeze_support()
		# also does not return if arguments are handled

	if len(sys.argv) > 1 and sys.argv[1] == '--ipc-server-main':
		assert len(sys.argv) == 4, 'Invalid ipc args: %s' % sys.argv

		global SERVER_ADDRESS
		SERVER_ADDRESS = sys.argv[2] # for testing

		loglevel = sys.argv[3]
		logging.getLogger().setLevel(int(loglevel))

		servermain()
		sys.exit()

	else:
		pass


class RemoteObject(object):
	'''Placeholder for a remote object that is accessible through the
	server.

	Used as an object identifier that can be send over a connection. To
	access the real object see L{RemoteObjectProxy}.
	'''
	# Note that we can construct these without having
	# 'seen' the real object, this is required to setup
	# connections from a client.

	# Also note that we could just pickle the class object instead
	# of bothering with class names ourselves, but this would cause
	# unnecessary imports in the client and server processes,
	# and conflict with gtk not being initialized in the parent process..

	def __init__(self, klass, id=None):
		'''Constructor
		@param klass: the fully specified class name as string
		(e.g. C{'zim.gui.GtkInterface'})
		@param id: an object id as string, in case multiple objects of
		the same class can be present (e.g. C{'file:///my/notebook'})
		'''
		assert isinstance(klass, basestring)
		self.klassname = klass
		self.id = id

	def __eq__(self, other):
		return (self.klassname, self.id) == (other.klassname, other.id)

	def __ne__(self, other):
		return not self.__eq__(other)

	def __hash__(self):
		return hash((self.klassname, self.id))

	def __repr__(self):
		return '<%s: %s(%s)>' % (
			self.__class__.__name__,
			self.klassname, self.id)


class RemoteMethodCall(object):
	'''Message object for a remote method call'''

	def __init__(self, remoteobject, methodname, args=None, kwargs=None, async=False):
		'''Constructor
		@param remoteobject: a L{RemoteObject} object
		@param methodname: the name of the method to call
		@param args: list arguments to pass on to the call
		@param kwargs: keyword arguments to pass on to the call
		@param async: if C{True} do not wait for the return value
		(this also means no error handling)
		'''
		if methodname.startswith('_') or '.' in methodname:
			raise AssertionError, 'BUG: Invalid method name: %s' % methodname
		self.obj = remoteobject
		self.methodname = methodname
		self.args = args or ()
		self.kwargs = kwargs or {}
		self.senderpid = os.getpid()
		self.async = async

	def __repr__(self):
		if self.async:
			async = ' async:'
		else:
			async = ''

		return '<%s: %i:%s %s(%s).%s(%s, %s)>' % (
			self.__class__.__name__, self.senderpid, async,
			self.obj.klassname, self.obj.id,
			self.methodname, self.args, self.kwargs )

	def call(self, obj):
		'''Call the actual method on the actual object. To be called in
		the recieving process.
		@param obj: the real object matching the remoteobject
		@returns: the return value of the method, or an C{Exception} object
		'''
		try:
			method = getattr(obj, self.methodname)
			return method(*self.args, **self.kwargs)
		except Exception, error:
			if self.async:
				logger.exception('Exception in remote call to %i:', os.getpid())
			else:
				trace = traceback.format_exc()
				logger.debug('Exception in remote call to %i:\n%s', os.getpid(), trace)
					# Not using logger.exception here, since we do not know
					# if this exception is caught by the calling process
					# or not.
			return error


class RemoteSignal(object):
	'''Message object for a remote signal call'''

	def __init__(self, name, args=None):
		'''Constructor
		@param name: the signal name
		@param args: list arguments to pass on
		'''
		self.name = name
		self.args = args or ()


def start_server_if_not_running():
	'''Start a new server process if none is running already. Used to
	initialize the server process.
	@raises AssertionError: if after a timeout the server is stil not
	responding
	'''
	# We start server process by spawn() for multiple reasons,
	# one is that gtk init prevents forking after gtk is imported
	# (and multiprocess forks on unix), another is that using
	# multiprocess keeps initiating client process open,
	# last is that fork is not available on windows, this code
	# allows single solution for all platforms, without need of
	# complicated double-fork daemonization code on unix.

	# Test if server already running
	s = ServerProxy()
	try:
		s.ping()
	except:
		pass
	else:
		return

	# Call new process that has not loaded gtk to do the work for us
	logger.debug('Starting server by spawning new process')
	loglevel = logging.getLogger().getEffectiveLevel()
	zim.main.get_zim_application(
		'--ipc-server-main', SERVER_ADDRESS, str(loglevel),
	).spawn()

	# Ensure server is running, but allow bit of timeout since
	# process has to start
	import time
	for i in range(10):
		try:
			s.ping()
		except:
			if i == 9: # last
				trace = traceback.format_exc()
				logger.debug('Cannot connect to server %i:\n%s', os.getpid(), trace)
			else:
				time.sleep(0.5)
		else:
			break
	else:
		raise AssertionError, 'Failed to start server (spawning)'


def stop_server_if_running():
	'''Stop the server process (and quit all children)'''
	s = ServerProxy()
	try:
		s.quit()
		# kill pid ?
		#pid = ack[1]
	except:
		pass # not running


def servermain():
	'''Main function for the server process'''
	# Make absolutely sure no gtk loaded in server, will cause all kind
	# of vague issues in child processes when it is loaded already..
	if 'gtk' in sys.modules:
		raise AssertionError, 'Cannot start server after importing gtk in same process'

	# Decouple from parent environment
	# and redirect standard file descriptors
	os.chdir("/")

	try:
		si = file(os.devnull, 'r')
		os.dup2(si.fileno(), sys.stdin.fileno())
	except:
		pass

	loglevel = logging.getLogger().getEffectiveLevel()
	if loglevel <= logging.INFO and sys.stdout.isatty() and sys.stderr.isatty():
		# more detailed logging has lower number, so WARN > INFO > DEBUG
		# log to file unless output is a terminal and logging <= INFO
		pass
	else:
		# Redirect output to file
		dir = zim.fs.get_tmpdir()
		err_stream = open(os.path.join(dir.path, "zim-daemon.log"), "w")

		# First try to dup handles for anyone who still has a reference
		# if that fails, just set them
		sys.stdout.flush()
		sys.stderr.flush()
		try:
			os.dup2(err_stream.fileno(), sys.stdout.fileno())
			os.dup2(err_stream.fileno(), sys.stderr.fileno())
		except:
			# Maybe stdout / stderr were not real files
			# in the first place..
			sys.stdout = err_stream
			sys.stderr = err_stream
			err_stream.write('WARNIGN: Could not dup stdout / stderr\n')

		# Re-initialize logging handler, in case it keeps reference
		# to the old stderr object
		try:
			rootlogger = logging.getLogger()
			for handler in rootlogger.handlers:
				rootlogger.removeHandler(handler)

			handler = logging.StreamHandler()
			handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
			rootlogger.addHandler(handler)
		except:
			err_stream.write('ERROR: Failed to set up logging')

	# Run actual server object
	server = Server()
	server.start()
	server.main()
	logger.debug('Server process %i quit', os.getpid())


if sys.platform == 'win32':
	# Windows named pipe
	from zim.environ import environ
	userstring = zim.fs.get_tmpdir().basename # "zim-$USER" without unicode!
	SERVER_ADDRESS = '\\\\.\\pipe\\%s-server' % userstring
	SERVER_ADDRESS_FAMILY = 'AF_PIPE'
else:
	# Unix domain socket
	SERVER_ADDRESS = str(zim.fs.get_tmpdir().file('zim-server-socket').path)
		# BUG in multiprocess, name must be str instead of basestring
	SERVER_ADDRESS_FAMILY = 'AF_UNIX'


AUTHKEY_FILE = zim.fs.get_tmpdir().file('zim-server-authkey')
	# Zim always initializes the tmpdir with mode 700, so should be private


class Server(object):
	'''Main object in the server process, handling all communication'''

	_signals = ('notebook-list-changed')

	def __init__(self):
		self.listener = None
		self.remoteobjects = {}
		self._running = False
		self.logqueue = multiprocessing.Queue()
		self.logqueue_reader = None

	def start(self):
		# setup listener
		logger.info('Server starting %s at %s', os.getpid(), SERVER_ADDRESS)
		#~ authkey = multiprocessing.current_process().authkey
		#~ fh = open(AUTHKEY_FILE.path, 'w')
		#~ fh.write(authkey)
		#~ fh.close()
		#~ print "SERVER >>%s<<" % authkey

		if SERVER_ADDRESS_FAMILY == 'AF_UNIX' \
		and os.path.exists(SERVER_ADDRESS):
			# Clean up old socket (someone should already have checked
			# before whether or not it is functional)
			os.unlink(SERVER_ADDRESS)

		#~ self.listener = Listener(SERVER_ADDRESS, authkey=authkey)
		self.listener = Listener(SERVER_ADDRESS)

	def main(self):
		self._running = True
		while self._running:
			conn = self.listener.accept()
			self._check_children()
				# Do this *before* _handle, so we know if an object
				# does not longer exist and maybe can init again
			self._handle(conn)

		logger.debug('Server stopped listening')
		self.listener.close()
		AUTHKEY_FILE.remove()

		for worker in self.remoteobjects.values():
			if worker.is_alive():
				worker.join()

	def _check_children(self):
		children = multiprocessing.active_children()
		if len(children) != len(self.remoteobjects):
			for obj, worker in self.remoteobjects.items():
				if worker.process not in children:
					logger.warn('Child quit unexpectedly: %s', worker.process.pid)
					self.on_object_quit(obj)

	def _handle(self, conn):
		try:
			msg = conn.recv()
			if isinstance(msg, RemoteMethodCall):
				#~ logger.debug('Server: Remote call: %s', msg)
				if msg.obj.klassname == 'zim.ipc.Server':
					re = msg.call(self)
					if not msg.async:
						#~ logger.debug('Remote call returns: %s', re)
						conn.send(re)
					conn.close()
				else:
					objconn = self.remoteobjects.get(msg.obj)
					if objconn:
						objconn.handle(msg, conn)
					else:
						logger.debug('Known objects: %s', self.remoteobjects.keys())
						conn.send(ValueError('No such object: %s' % msg.obj))
						conn.close()
			else:
				logger.error('Invalid message to server (%i): %s', os.getpid(), msg)
				conn.close()
		except Exception:
			logger.exception('Exception in server while handling request')

	def ping(self):
		'''Returns C{"ACK"} and the process id, used to test server is
		alive.
		'''
		return ('ACK', os.getpid())

	def init_object(self, remoteobject, *args, **kwargs):
		'''Create a new child process hosting an object.
		@param remoteobject: a L{RemoteObject} representation for the
		to be created object
		@param args: list arguments to pass on to the constructor
		@param kwargs: keyword arguments to pass on to the constructor
		'''
		loglevel = logging.getLogger().getEffectiveLevel()
		if not (self.logqueue_reader and self.logqueue_reader.is_alive()):
			self.logqueue_reader = LogQueueReader(self.logqueue)
			self.logqueue_reader.start()

		conn1, conn2 = Pipe()
		p = Process(
			target=childmain,
			args=(conn2, remoteobject, loglevel, self.logqueue, args, kwargs)
		)
		p.daemon = True # child process exit with parent
		p.start()
		obj = conn1.recv()
		logger.debug('Child process started %i for %s', p.pid, obj)
		worker = ConnectionWorker(conn1, p)
		worker.start()
		self.remoteobjects[obj] = worker
		self._running = True
			# for the odd case that last child quit and new
			# child start come in at the same time
		return True

	def on_object_quit(self, remoteobject):
		'''Handler called when a child process quits'''
		worker = self.remoteobjects.pop(remoteobject)
		if worker.queue.qsize() > 0:
			logger.warn('Child quit, dropping pending calls')
			# In this case the pipe being closed will cause some
			# exceptions in the thread (or already did)

		if worker.isAlive():
			worker.quit()

		if not self.remoteobjects:
			logger.info('Last child quit, stopping server')
			self._running = False
		else:
			self.emit('notebook-list-changed')

		return not self._running

	def has_object(self, remoteobject):
		'''Returns C{True} if the server has a child process matching
		this object
		'''
		return remoteobject in self.remoteobjects

	def list_objects(self):
		'''Return a list of C{RemoteObject} objects representing all
		objects known to the server
		'''
		return self.remoteobjects.keys()

	def emit(self, signal, *args):
		'''Emit a signal to all interested child processes
		@param signal: the signal name
		@param args: list arguments to be passed on
		'''
		assert signal in self._signals
		msg = RemoteSignal(signal, args)
		logger.debug('Server emit signal: %s', msg)
		for obj, conn in self.remoteobjects.items():
			conn.send(msg)

	def quit(self):
		'''Tell all child processes to quit'''
		logger.debug('Server closing all children')
		for obj, conn in self.remoteobjects.items():
			msg = RemoteMethodCall(obj, 'quit', async=True)
			conn.send(msg)


class ConnectionWorker(threading.Thread):
	'''This class wraps a single child connection (pipe) in a thread
	queue. This way the server can handle multiple children, without
	locking up, while requests for the same child are still processed
	linearly.
	'''

	_QUIT = 0

	def __init__(self, conn, process):
		threading.Thread.__init__(self)
		self.queue = Queue()
		self.conn = conn
		self.process = process

	def send(self, msg):
		'''Called in main thread to send a single message.
		Can only be used for signals and asynchronous method calls.
		@param msg: a L{RemoteMethodCall} or a L{RemoteSignal}
		'''
		assert isinstance(msg, RemoteSignal) \
			or (isinstance(msg, RemoteMethodCall) and msg.async)
		self.queue.put((msg, None))

	def handle(self, msg, remoteconn):
		'''Called in main thread to handle a remote method call.
		@param msg: a L{RemoteMethodCall} or a L{RemoteSignal}
		@param remoteconn: a connection object which will recieve the
		return value
		'''
		if msg.async and remoteconn:
			remoteconn.close()
			remoteconn = None
		self.queue.put((msg, remoteconn))

	def quit(self):
		'''Quit the thread, to be called after the process itself quit'''
		self.queue.put((self._QUIT, None))
			# bit of a hack, but it works

	def run(self):
		'''Main function for the thread'''
		try:
			while True:
				msg, remoteconn = self.queue.get()
				if msg == self._QUIT:
					break # stop listening, exit the thread
				self.conn.send(msg)
				if isinstance(msg, RemoteMethodCall) and not msg.async:
					re = self.conn.recv()
					#~ logger.debug('Server: Remote call returns: %s', re)
					remoteconn.send(re)
					remoteconn.close()
				self.queue.task_done()

			self.conn.close()
		except:
			logger.exception('Server thread exited with exception')

		if self.process.is_alive():
			self.process.join() # avoid zombie processes
		logger.debug('Server thread for process %i quit', self.process.pid)


def childmain(conn, remoteobject, loglevel, logqueue, arg, kwarg):
	'''Main function for child processes'''
	global SERVER_CONTEXT
	global _recursive_conn_lock
	_recursive_conn_lock = True

	setup_child_logging(loglevel, logqueue)
	zim.errors.set_use_gtk(True)
		# Assume any child process to be a gui process

	try:
		klassname, id = remoteobject.klassname, remoteobject.id

		# __import__ has some quirks, see the reference manual
		modname, klassname = klassname.rsplit('.', 1)
		mod = __import__(modname)
		for name in modname.split('.')[1:]:
			mod = getattr(mod, name)
		klass = getattr(mod, klassname)
		assert hasattr(klass, 'main'), 'Child process objects should at least have a "main()" and a "quit()"'
		assert hasattr(klass, 'quit'), 'Child process objects should at least have a "main()" and a "quit()"'

		SERVER_CONTEXT = ServerProxyClass(ischildprocess=True)

		if id is None:
			obj = klass(*arg, **kwarg)
		else:
			obj = klass(id, *arg, **kwarg)
		#~ print '>>>> CREATED', obj

		adapter = ConnectionAdapter(conn, remoteobject, obj)
		RemoteObjectProxy._client_proxy_authkey = multiprocessing.current_process().authkey
			# Since we inherit from the server, we inherit authkey
		SERVER_CONTEXT.set_adapter(adapter)
			# Need to set adapter to allow "connect()" via SERVER_CONTEXT
			# FIXME - improve object dependencies to allow connect from
			# klass init as well

		if sys.platform == 'win32':
			# Windows pipe
			# idle handler uses a bit to much CPU for my taste,
			# timeout every 0.5 sec is better - poll() check for queue
			gobject.timeout_add(500, adapter.poll)
		else:
			# multiprocessing uses unix file desriptors
			gobject.io_add_watch(conn.fileno(), gobject.IO_IN, adapter.poll)
	except Exception, err:
		logger.exception('Exception while setting up child process')
		conn.send(err)
		_recursive_conn_lock = False
	else:
		conn.send(remoteobject)
		_recursive_conn_lock = False
		#~ print '>>> START MAIN', obj
		obj.main()
		SERVER_CONTEXT.on_object_quit(remoteobject)

	logger.debug('Child process %i quit', os.getpid())


class ConnectionAdapter(object):
	'''Wrapper for the receiving end of the connection between the server
	and a child process. Handles incoming messages.
	'''

	def __init__(self, conn, remoteobject, obj):
		'''Constructor
		@param conn: the connection object
		@param remoteobject: the C{RemoteObject} representing C{obj}
		@param obj: the actual object
		'''
		self.conn = conn
		self.remoteobject = remoteobject
		self.obj = obj
		self._listento = []

	def listento(self, signal, object):
		'''Register a signal to listen to
		@param signal: signal name
		@param object: the object that wants to receive the signal
		'''
		assert object == self.obj, 'Only main object can connect to server for now'
		methodname = 'on_' + signal.replace('-', '_')
		assert hasattr(self.obj, methodname), 'BUG: %s needs method "%s"' % (object, methodname)
		self._listento.append(signal)

	def poll(self, *a):
		try:
			while self.conn.poll(0):
				self.handle()
		except IOError:
			# Broken pipe, quit ourselves
			logger.exception('Exception in poll')
			self.obj.quit()
			return False
		else:
			return True

	def handle(self):
		global _recursive_conn_lock
		_recursive_conn_lock = True

		try:
			msg = self.conn.recv()
			if isinstance(msg, RemoteMethodCall) \
			and msg.obj == self.remoteobject:
				re = msg.call(self.obj)
				if not msg.async:
					self.conn.send(re)
			elif isinstance(msg, RemoteSignal):
				_recursive_conn_lock = False # unblock since server is not waiting
				if msg.name in self._listento:
					methodname = 'on_' + msg.name.replace('-', '_')
					func = getattr(self.obj, methodname)
					func(*msg.args)
			else:
				raise AssertionError, 'Invalid message to child %s (%i): %s' % (self.remoteobject, os.getpid(), msg)
		except Exception, err:
			logger.exception('Exception in child handler')
			# would like to send something to let the other side know
			# but could cause hanging on our side if not recieving ...

		_recursive_conn_lock = False


class RemoteObjectProxy(object):
	'''Class for proxy objects that allows calling methods on a
	remote object from the client side of the socket.

	Automatically turns method calls on this object into remote method
	calls over the connection.
	'''

	_client_proxy_authkey = None

	def __init__(self, remoteobject):
		'''Constructor
		@param remoteobject: the L{RemoteObject} we are proxy'ing
		'''
		self._obj = remoteobject

	def __getattr__(self, name):
		def call(*args, **kwargs):
			global _recursive_conn_lock
			if _recursive_conn_lock:
				raise AssertionError, 'BUG: Recursive client connection'
				# Avoid hanging because we call the socket while the
				# server is blocking for our return value on the pipe.
				# If this is an issue blocking functionality,
				# re-route the call to the open pipe for which the
				# server is waiting.

			#~ if self._client_proxy_authkey is None:
				#~ self._client_proxy_authkey = AUTHKEY_FILE.raw()

			msg = RemoteMethodCall(self._obj, name, args, kwargs)
			logger.debug('Remote call from %i: %s', os.getpid(), msg)
			#~ print "CLIENT >>%s<<" % self._client_proxy_authkey
			#~ conn = Client(SERVER_ADDRESS, authkey=self._client_proxy_authkey)
			conn = Client(SERVER_ADDRESS, SERVER_ADDRESS_FAMILY)
			conn.send(msg)
			if not msg.async:
				re = conn.recv()
				logger.debug('Remote call returned to %i: %s', os.getpid(), re)
				if isinstance(re, Exception):
					raise re
				else:
					return re

		setattr(self, name, call)
		return call


class ServerProxyClass(RemoteObjectProxy):
	'''Proxy object that represents the server itself.
	This is the primary interface for the client to call the
	background server. As a proxy it can call all methods of
	the L{Server} class.

	Do not construct directly, see L{ServerProxy()} instead.
	'''

	_obj = RemoteObject('zim.ipc.Server')
	_notebookklass = 'zim.gui.GtkInterface' # used for testing

	def __init__(self, ischildprocess=False):
		self._ischildprocess = ischildprocess
		self._adapter = None

	def set_adapter(self, adapter):
		self._adapter = adapter

	def get_proxy(self, remoteobject, open=True):
		'''Get a L{RemoteObjectProxy} for an remote object
		@param remoteobject: a L{RemoteObject} object
		@param open: if C{True} the object will be created on the fly
		when it doesn't exist yet.
		'''
		if not self.has_object(remoteobject):
			if open:
				self.init_object(remoteobject)
			else:
				return None

		proxy = RemoteObjectProxy(remoteobject)
		proxy._client_proxy_authkey = self._client_proxy_authkey
		return proxy

	def get_notebook(self, uri, open=True):
		'''Convenience method to get a proxy for a notebook
		@param uri: the URI for the notebook
		@param open: if C{True} a new window will be opened if this
		notebook was not yet opened
		'''
		if hasattr(uri, 'uri'):
			uri = uri.uri # convert Dir objects

		assert VALID_NOTEBOOK_URI.match(uri), 'Must be real URI'
		return self.get_proxy(RemoteObject(self._notebookklass, uri), open)

	def list_notebooks(self):
		'''Convenience method to get a list of notebook uris for
		open notebooks.
		'''
		uris = []
		for obj in self.list_objects():
			if obj.klassname == self._notebookklass:
				uris.append(obj.id)
		uris.sort()
		return uris

	def connect(self, signal, object):
		'''Connect to a signal
		@param signal: the signal name
		@param object: the object to call back when the signal is emitted
		'''
		# FIXME, should we have same arguments as regular connect() ?
		assert signal in Server._signals
		if not self._ischildprocess:
			raise AssertionError, 'Only child processes can connect to signals'
		elif not self._adapter:
			raise AssertionError, 'Can not connect signals before IPC adpater is initialized'
		self._adapter.listento(signal, object)


def ServerProxy():
	'''Returns an object of class L{ServerProxyClass}'''
	global SERVER_CONTEXT
	if SERVER_CONTEXT:
		return SERVER_CONTEXT
	else:
		return ServerProxyClass()



## Logging classes based on
## http://stackoverflow.com/questions/641420/how-should-i-log-while-using-multiprocessing-in-python
##
## Need to redirect logging of child classes when we are running without terminal output
## and also in case we are running with terminal output, but child process may not inherit
## terminal (e.g. win32)


class QueueHandler(logging.Handler):

	def __init__(self, queue):
		logging.Handler.__init__(self)
		self.queue = queue

	def emit(self, record):
		if record.exc_info:
			# can't pass exc_info across processes so just format now
			record.exc_text = self.formatException(record.exc_info)
			record.exc_info = None
		record.args = tuple(map(self._format, record.args))
			# Make sure all arguments can be pickled..
		self.queue.put(record)

	@staticmethod
	def _format(a):
		if isinstance(a, (basestring, int, float)):
			return a
		else:
			return repr(a)

	def formatException(self, ei):
		s = ''.join(traceback.format_exception(ei[0], ei[1], ei[2]))
		if s[-1] == "\n":
			s = s[:-1]
		return s


class LogQueueReader(threading.Thread):
	"""thread to write subprocesses log records to main process log

	This thread reads the records written by subprocesses and writes them to
	the handlers defined in the main process's handlers.

	"""

	def __init__(self, queue):
		threading.Thread.__init__(self)
		self.queue = queue
		self.daemon = True

	def run(self):
		"""read from the queue and write to the log handlers

		The logging documentation says logging is thread safe, so there
		shouldn't be contention between normal logging (from the main
		process) and this thread.

		Note that we're using the name of the original logger.

		"""
		# Thanks Mike for the error checking code.
		while True:
			try:
				record = self.queue.get()
				# get the logger for this record
				logger = logging.getLogger(record.name)
				logger.callHandlers(record)
			except (KeyboardInterrupt, SystemExit):
				raise
			except EOFError:
				break
			except:
				traceback.print_exc(file=sys.stderr)


def setup_child_logging(loglevel, logqueue):
	logger = logging.getLogger()

	# The only handler desired is the QueueHandler.  If any others
	# exist, remove them. In this case, on Unix and Linux the StreamHandler
	# will be inherited.
	for handler in logger.handlers:
		logger.removeHandler(handler)

	handler = QueueHandler(logqueue)
	logger.addHandler(handler)
	logger.setLevel(int(loglevel))
