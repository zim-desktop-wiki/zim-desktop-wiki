# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

# TODO needs more options like
#		-p --port INT	set port number
#		-P --public 	allow connections from outside
# TODO check client host for security
# TODO setting for doc_root_url when running in CGI mode

'''FIXME'''

import sys
import socket
import logging
import glib
import gobject

from zim import NotebookInterface
from zim.notebook import Page
from zim.fs import *
from zim.formats import ParseTree, TreeBuilder


logger = logging.getLogger('zim.www')


class WWWError(Exception):
	'''FIXME'''

	statusstring = {
		'404': 'Not Found',
		'405': 'Method Not Allowed',
		'500': 'Internal Server Error',
	}

	def __init__(self, status='500', headers=None, msg=None):
		'''FIXME'''
		self.status = '%s %s' % (status, self.statusstring[status])
		self.headers = headers
		self.msg = msg
		self.logmsg = self.status + ' - ' + self.msg


class NoConfigError(WWWError):

	def __init__(self):
		WWWError.__init__(self, msg='Server was not configured properly, please provide a notebook first.')


class PageNotFoundError(WWWError):

	def __init__(self, page):
		if not isinstance(page, basestring):
			page = page.name
		WWWError.__init__(self, '404', msg='No such page: %s' % page)


class WWWInterface(NotebookInterface):
	'''Class to handle the WWW interface for zim notebooks.

	Objects of this class are callable, so they can be used as application
	objects within a WSGI compatible framework. See PEP 333 for details
	( http://www.python.org/dev/peps/pep-0333/ ).

	For basic handlers to run this interface see the wsgiref package that comes
	with python.
	'''

	ui_type = 'html'

	def __init__(self, notebook=None, template='Default', **opts):
		NotebookInterface.__init__(self, **opts)
		self.output = None
		if isinstance(template, basestring):
			from zim.templates import get_template
			template = get_template('html', template)
		self.template = template
		self.load_config()
		self.load_plugins()
		if not notebook is None:
			self.open_notebook(notebook)

	def __call__(self, environ, start_response):
		'''Main function for handling a single request. Arguments are the file
		handle to write the output to and the path to serve. Any exceptions
		will result in a error response being written.

		First argument is a dictionary with environment variables and some special
		variables. See the PEP for expected variables. The second argument is a
		function that can be called for example like:

			start_response(200, [('Content-Type', 'text/plain')])

		This method is supposed to take care of sending the response line and
		the headers.

		The return value of this call is a list of lines with the content to
		be served.
		'''
		path = environ.get('PATH_INFO', '/')
		try:
			methods = ('GET', 'HEAD')
			if not environ['REQUEST_METHOD'] in methods:
				raise WWWError('405', headers=[('Allow', ', '.join(methods))])

			if self.notebook is None:
				raise NoConfigError
			elif path == '' or path == '/':
				content = self.render_index()
			elif path.startswith('/+docs/'):
				pass # TODO document root
			elif path.startswith('/+file/'):
				pass # TODO attachment or raw source
			else:
				# Must be a page or a namespace (html file or directory path)
				if path.endswith('.html'):
					pagename = path[:-5].replace('/', ':')
				elif path.endswith('/'):
					pagename = path[:-1].replace('/', ':')
				else:
					raise PageNotFoundError(path)

				page = self.notebook.get_page(pagename)
				if page.isempty():
					if page.children:
						content = self.render_index(pagename)
					else:
						raise PageNotFoundError(page)
				else:
					content = self.render_page(pagename)
		except WWWError, error:
			logger.error(error.logmsg)
			header = [('Content-Type', 'text/plain')]
			if error.headers:
				header.extend(error.headers)
			start_response(error.status, header)
			if environ['REQUEST_METHOD'] == 'HEAD':
				return []
			else:
				return error.msg
		# TODO also handle template errors as special here
		except Exception, error:
			# Unexpected error - maybe a bug, do not expose output on bugs
			# to the outside world
			logger.error("%s: %s", error.__class__.__name__, str(error))
			sys.excepthook(*sys.exc_info())
			start_response('500 Internal Server Error', [])
			return []
		else:
			header = [('Content-Type', 'text/html;charset=utf-8')]
			start_response('200 OK', header)
			if environ['REQUEST_METHOD'] == 'HEAD':
				return []
			else:
				return [string.encode('utf8') for string in content]

	def render_index(self, namespace=None):
		'''Serve an index page'''
		if namespace is None:
			namespace = self.notebook.get_root()
		elif isinstance(namespace, basestring):
			namespace = self.notebook.get_namespace(namespace)

		page = IndexPage(namespace)
		return self.render_page(page)

	def render_page(self, page):
		'''Serve a single page from the notebook'''
		if isinstance(page, basestring):
			page = self.notebook.get_page(page)

		if self.template:
			output = Buffer()
			self.template.process(page, output)
			html = output.getvalue()
		else:
			html = page.get_text(format='html')

		return [html]


class IndexPage(Page):
	'''Page displaying a Namespace index'''

	def __init__(self, namespace, recurs=True):
		'''Constructor takes a namespace object'''
		Page.__init__(self, namespace.name or '<root>', namespace.store)
		self._index_namespace = namespace
		self._index_recurs = recurs
		self.properties['readonly'] = True
		self.properties['type'] = 'namespace-index'

	def isempty(self): return False

	def get_parsetree(self):
		builder = TreeBuilder()

		def add_namespace(namespace):
			builder.start('ul')
			for page in namespace:
				builder.start('li')
				builder.start('link', {'type': 'page', 'href': page.name})
				builder.data(page.basename)
				builder.end('link')
				builder.end('li')
				if page.children and self._index_recurs:
					add_namespace(page.children) # recurs
			builder.end('ul')

		builder.start('page')
		builder.start('h', {'level':1})
		builder.data('Index of %s' % self.name)
		builder.end('h')
		add_namespace(self._index_namespace)
		builder.end('page')
		return ParseTree(builder.close())


class Server(gobject.GObject):
	'''Webserver based on glib'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'started': (gobject.SIGNAL_RUN_LAST, None, []),
		'stopped': (gobject.SIGNAL_RUN_LAST, None, [])
	}

	def __init__(self, notebook=None, port=8080, gui=False, **opts):
		'''FIXME'''
		gobject.GObject.__init__(self)
		self.socket = None
		self.running = False
		self.set_port(port)

		import wsgiref.handlers
		self.handlerclass = wsgiref.handlers.SimpleHandler
		self.interface = WWWInterface(notebook, **opts)

		if gui:
			import zim.gui.server
			self.window = zim.gui.server.ServerWindow(self)
			self.use_gtk = True
		else:
			self.use_gtk = False

	def set_port(self, port):
		assert not self.running
		assert isinstance(port, int), port
		self.port = port

	def main(self):
		if self.use_gtk:
			import gtk
			self.window.show_all()
			gtk.main()
		else:
			if not self.running:
				self.start()
			glib.MainLoop().run()
		self.stop()

	def start(self):
		'''Open a socket and start listening. If we are running already, first
		calls stop() to close the old socket, causing a restart. Emits the
		'started' signal upon success.
		'''
		if self.running:
			self.stop()

		logger.info('Server starting at port %i', self.port)

		# open sockets for connections
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.bind(("localhost", self.port)) # TODO use socket.gethostname() for public server
		self.socket.listen(5)

		glib.io_add_watch(self.socket, glib.IO_IN,
			lambda *a: self.do_accept_request())

		self.running = True
		self.emit('started')

	def stop(self):
		'''Close the socket and stop listening, emits the 'stopped' signal'''
		if not self.running:
			return # ignore silently

		try:
			self.socket.close()
		except Exception, error:
			logger.error(error)
		self.socket = None

		logger.info('Server stopped')
		self.running = False
		self.emit('stopped')

	def do_accept_request(self):
		# set up handler for new connection
		clientsocket, clientaddress = self.socket.accept() # TODO timeout ?

		# read data
		rfile = clientsocket.makefile('rb')
		requestline = rfile.readline()
		command, path, version = requestline.split()
		if version[5:] != 0.9: # HTTP/0.9 does not do headers
			headerlines = []
			while True:
				line = rfile.readline()
				if not line or line.isspace():
					break
				else:
					headerlines.append(line)
			#~ headers = HeadersDict(''.join(headerlines))
		#~ else:
			#~ headers = {}
		logger.info('%s %s %s', clientaddress[0], command, path)

		wfile = clientsocket.makefile('wb')
		environ = {
			'REQUEST_METHOD': command,
			'SCRIPT_NAME': '',
			'PATH_INFO': path,
			'QUERY_STRING': '',
			'SERVER_NAME': 'localhost',
			'SERVER_PORT': str(self.port),
			'SERVER_PROTOCOL': version
		}
		handler = self.handlerclass(rfile, wfile, sys.stderr, environ)
		handler.run(self.interface)
		rfile.close()
		wfile.flush()
		wfile.close()
		clientsocket.close()
		return True # else io watch gets deleted


# Need to register classes defining gobject signals
gobject.type_register(Server)
