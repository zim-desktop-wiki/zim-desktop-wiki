# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

# TODO needs more options like
#		-p --port INT	set port number
#		-P --public 	allow connections from outside
# TODO check client host for security
# TODO setting for doc_root_url when running in CGI mode
# TODO support "etg" and "if-none-match' headers at least for icons

'''FIXME'''

import sys
import socket
import logging
import gobject

from wsgiref.headers import Headers
import urllib

from zim import NotebookInterface
from zim.notebook import Path, Page, IndexPage
from zim.fs import *
from zim.formats import ParseTree, TreeBuilder
from zim.config import data_file
from zim.exporter import BaseLinker

logger = logging.getLogger('zim.www')

# TODO FIXME HACK - this translation needs to be done when exporting
icons = {}
for icon in ('checked-box.png', 'xchecked-box.png', 'unchecked-box.png'):
	file = data_file('pixmaps/'+icon)
	icons[file.path] = icon

class WWWError(Exception):
	'''FIXME'''

	statusstring = {
		'404': 'Not Found',
		'405': 'Method Not Allowed',
		'500': 'Internal Server Error',
	}

	def __init__(self, status='500', headers=None, msg=''):
		'''FIXME'''
		self.status = '%s %s' % (status, self.statusstring[status])
		self.headers = headers
		self.msg = str(msg)
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
		self.linker = None
		self.load_plugins()
		if not notebook is None:
			self.open_notebook(notebook)

	def open_notebook(self, notebook):
		NotebookInterface.open_notebook(self, notebook)
		#~ self.notebook.index.update()
		self.linker = WWWLinker('html', notebook)
		if self.template:
			self.template.set_linker(self.linker)

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
		headerlist = []
		headers = Headers(headerlist)
		path = environ.get('PATH_INFO', '/')
		try:
			methods = ('GET', 'HEAD')
			if not environ['REQUEST_METHOD'] in methods:
				raise WWWError('405', headers=[('Allow', ', '.join(methods))])

			if not path:
				path = '/'
			elif path == '/favicon.ico':
				path = '/+icons/favicon.ico'
			elif path in icons:
				# TODO FIXME HACK - this translation needs to be done when exporting
				path = '/+icons/' + icons[path]

			if self.notebook is None:
				raise NoConfigError
			elif path == '/':
				headers.add_header('Content-Type', 'text/html', charset='utf-8')
				content = self.render_index()
			elif path.startswith('/+docs/'):
				pass # TODO document root
			elif path.startswith('/+file/'):
				pass # TODO attachment or raw source
			elif path.startswith('/+icons/'):
				# TODO check if favicon is overridden or something
				file = data_file('pixmaps/%s' % path[8:])
				if path.endswith('.png'):
					headers['Content-Type'] = 'image/png'
				elif path.endswith('.ico'):
					headers['Content-Type'] = 'image/vnd.microsoft.icon'
				content = [file.read(encoding=None)]
			else:
				# Must be a page or a namespace (html file or directory path)
				headers.add_header('Content-Type', 'text/html', charset='utf-8')
				if path.endswith('.html'):
					pagename = path[:-5].replace('/', ':')
				elif path.endswith('/'):
					pagename = path[:-1].replace('/', ':')
				else:
					raise PageNotFoundError(path)

				pagename = urllib.unquote(pagename)
				path = self.notebook.resolve_path(pagename)
				page = self.notebook.get_page(path)
				if page.hascontent:
					content = self.render_page(page)
				elif page.haschildren:
					content = self.render_index(page)
				else:
					raise PageNotFoundError(page)
		except WWWError, error:
			logger.error(error.logmsg)
			headerlist = [('Content-Type', 'text/plain')]
			if error.headers:
				header.extend(error.headers)
			start_response(error.status, headerlist)
			if environ['REQUEST_METHOD'] == 'HEAD':
				return []
			else:
				return [error.msg]
		# TODO also handle template errors as special here
		except Exception:
			# Unexpected error - maybe a bug, do not expose output on bugs
			# to the outside world
			logger.exception('Unexpected error:')
			headerlist = [('Content-Type', 'text/plain')]
			start_response('500 Internal Server Error', headerlist)
			return ['Internal Server Error']
		else:
			start_response('200 OK', headerlist)
			if environ['REQUEST_METHOD'] == 'HEAD':
				return []
			elif 'utf-8' in headers['Content-Type']:
				return [string.encode('utf8') for string in content]
			else:
				return content

	def render_index(self, namespace=None):
		'''Serve an index page'''
		page = IndexPage(self.notebook, namespace)
		return self.render_page(page)

	def render_page(self, page):
		'''Serve a single page from the notebook'''
		if self.template:
			return self.template.process(self.notebook, page)
		else:
			return page.dump(format='html', linker=self.linker)


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

	def set_notebook(self, notebook):
		self.stop()
		self.interface = WWWInterface(notebook)

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
			gobject.MainLoop().run()
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

		gobject.io_add_watch(self.socket, gobject.IO_IN,
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


class WWWLinker(BaseLinker):
	pass
