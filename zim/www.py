# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO check client host for security
# TODO setting for doc_root_url when running in CGI mode
# TODO support "etg" and "if-none-match' headers at least for icons

'''This module contains a web interface for zim. This is an alternative to
the GUI application. It can be run either as a stand-alone web server or
embedded in another server using cgi-bin or one of the python web frameworks.
'''

import sys
import socket
import logging
import gobject

from wsgiref.headers import Headers
import urllib

from zim import NotebookInterface
from zim.errors import Error
from zim.notebook import Path, Page, IndexPage, PageNameError
from zim.fs import File, Dir, FileNotFoundError
from zim.formats import ParseTree, TreeBuilder, BaseLinker
from zim.config import data_file
from zim.stores import encode_filename
from zim.parsing import url_encode


logger = logging.getLogger('zim.www')


class WWWError(Error):

	statusstring = {
		'403': 'Forbidden',
		'404': 'Not Found',
		'405': 'Method Not Allowed',
		'500': 'Internal Server Error',
	}

	def __init__(self, msg, status='500', headers=None):
		self.status = '%s %s' % (status, self.statusstring[status])
		self.headers = headers
		self.msg = self.status
		if msg:
			self.msg += ' - ' + msg


class NoConfigError(WWWError):

	description = '''\
There was no notebook configured for this zim instance.
This is likely a configuration isue.
'''

	def __init__(self):
		WWWError.__init__(self, 'Notebook not found')


class PageNotFoundError(WWWError):

	description = '''\
You tried to open a page that does not exist.
'''

	def __init__(self, page):
		if not isinstance(page, basestring):
			page = page.name
		WWWError.__init__(self, 'No such page: %s' % page, status='404')


class PathNotValidError(WWWError):

	description = '''\
The requested path is not valid
'''

	def __init__(self):
		WWWError.__init__(self, 'Invalid path', status='403')


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
		self.linker = WWWLinker(self.notebook)
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

			# cleanup path
			#~ print 'INPUT', path
			path = path.replace('\\', '/') # make it windows save
			isdir = path.endswith('/')
			parts = [p for p in path.split('/') if p and not p == '.']
			if [p for p in parts if p.startswith('.')]:
				# exclude .. and all hidden files from possible paths
				raise PathNotValidError()
			path = '/' + '/'.join(parts)
			if isdir and not path == '/': path += '/'
			#~ print 'PATH', path

			if not path:
				path = '/'
			elif path == '/favicon.ico':
				path = '/+icons/favicon.ico'
			else:
			    path = urllib.unquote(path)

			if self.notebook is None:
				raise NoConfigError
			elif path == '/':
				headers.add_header('Content-Type', 'text/html', charset='utf-8')
				content = self.render_index()
			elif path.startswith('/+docs/'):
				dir = self.notebook.document_root
				if not dir:
					raise PageNotFoundError(path)
				file = dir.file(path[7:])
				content = [file.raw()]
					# Will raise FileNotFound when file does not exist
				headers['Content-Type'] = file.get_mimetype()
 			elif path.startswith('/+file/'):
				file = self.notebook.dir.file(path[7:])
					# TODO: need abstraction for getting file from top level dir ?
				content = [file.raw()]
					# Will raise FileNotFound when file does not exist
				headers['Content-Type'] = file.get_mimetype()
 			elif path.startswith('/+icons/'):
 				# TODO check if favicon is overridden or something
 				file = data_file('pixmaps/%s' % path[8:])
				content = [file.raw()]
					# Will raise FileNotFound when file does not exist
 				if path.endswith('.png'):
 					headers['Content-Type'] = 'image/png'
 				elif path.endswith('.ico'):
 					headers['Content-Type'] = 'image/vnd.microsoft.icon'
 				else:
					raise PathNotValidError()
			else:
				# Must be a page or a namespace (html file or directory path)
				headers.add_header('Content-Type', 'text/html', charset='utf-8')
				if path.endswith('.html'):
					pagename = path[:-5].replace('/', ':')
				elif path.endswith('/'):
					pagename = path[:-1].replace('/', ':')
				else:
					raise PageNotFoundError(path)

				path = self.notebook.resolve_path(pagename)
				page = self.notebook.get_page(path)
				if page.hascontent:
					content = self.render_page(page)
				elif page.haschildren:
					content = self.render_index(page)
				else:
					raise PageNotFoundError(page)
		except Exception, error:
			headerlist = []
			headers = Headers(headerlist)
			headers.add_header('Content-Type', 'text/plain', charset='utf-8')
			if isinstance(error, (WWWError, FileNotFoundError)):
				logger.error(error.msg)
				if isinstance(error, FileNotFoundError):
					error = PageNotFoundError(path)
					# show url path instead of file path
				if error.headers:
					header.extend(error.headers)
				start_response(error.status, headerlist)
				content = unicode(error).splitlines(True)
			# TODO also handle template errors as special here
			else:
				# Unexpected error - maybe a bug, do not expose output on bugs
				# to the outside world
				logger.exception('Unexpected error:')
				start_response('500 Internal Server Error', headerlist)
				content = ['Internal Server Error']
			if environ['REQUEST_METHOD'] == 'HEAD':
				return []
			else:
				return [string.encode('utf-8') for string in content]
		else:
			start_response('200 OK', headerlist)
			if environ['REQUEST_METHOD'] == 'HEAD':
				return []
			elif 'utf-8' in headers['Content-Type']:
				return [string.encode('utf-8') for string in content]
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

	def __init__(self, notebook=None, port=8080, gui=False, public=True, **opts):
		gobject.GObject.__init__(self)
		self.socket = None
		self.running = False
		self.set_port(port)
		self.public = public
		self._io_event = None

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
		hostname = '' # means all interfaces
		if not self.public:
			hostname = 'localhost'
		self.socket.bind((hostname, self.port))
		self.socket.listen(5)

		self._io_event = gobject.io_add_watch(
			self.socket, gobject.IO_IN,
			lambda *a: self.do_accept_request())

		self.running = True
		self.emit('started')

	def stop(self):
		'''Close the socket and stop listening, emits the 'stopped' signal'''
		if not self.running:
			return # ignore silently

		if self._io_event:
			gobject.source_remove(self._io_event)
			self._io_event = None

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

	def __init__(self, notebook, path=None):
		BaseLinker.__init__(self)
		self.notebook = notebook
		self.path = path

	def icon(self, name):
		return url_encode('/+icons/%s.png' % name)

	def link_page(self, link):
		try:
			page = self.notebook.resolve_path(link, source=self.path)
		except PageNameError:
			return ''
		else:
			return url_encode('/' + encode_filename(page.name) + '.html')
			# TODO use script location as root for cgi-bin

	def link_file(self, link):
		# cleanup the path
		isabs = link.startswith('/')
		isdir = link.endswith('/')
		link = link.replace('\\', '/')
		parts = [p for p in link.split('/') if p and not p == '.']
		# TODO fold '..'
		link = '/'.join(parts)
		if isabs and link != '/': link = '/' + link
		if isdir and link != '/': link += '/'

		if link.startswith('/'):
			# document root
			return url_encode('/+docs/' + link.lstrip('/'))
			# TODO use script location as root for cgi-bin
			# TODO allow alternative document root for cgi-bin
		else:
			# attachment or external file
			try:
				file = self.notebook.resolve_file(link, self.path)
				if file.ischild(self.notebook.dir):
					# attachment
					relpath = file.relpath(self.notebook.dir)
						# TODO: need abstract interface for this
					return url_encode('/+file/' + relpath)
				else:
					# external file -> file://
					return file.uri
			except:
				# typical error is a non-local file:// uri
				return link
