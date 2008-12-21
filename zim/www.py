# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

# TODO needs more options like
#		-p --port INT	set port number
#		-P --public 	allow connections from outside
# TODO check client host for security
# TODO setting for doc_root_url when running in CGI mode

'''FIXME

A simple cgi-bin script to serve a zim notebook can look like this:

	#!/usr/bin/python

	import zim.www
	cgi = zim.www.Handler(
		notebook='./foobar/',      # [1]
		template='./mytheme.html'  # [2]
	)
	cgi.main()

[1] If you do not set the notebook the script will be able to serve all
notebooks.
[2] Without template "Default.html" will be used from the zim data directory.
'''

import sys
import socket
import logging
import glib
import gobject

from zim import Interface
from zim.utils import rfc822headers
from zim.fs import *


class WWWError(Exception):
	'''FIXME'''

	def __init__(self, status='500 Internal Server Error', msg='Internal Server Error'):
		'''FIXME'''
		self.status = status
		self.content = msg


class NoConfigError(WWWError):

	def __init__(self):
		WWWError.__init__(self, msg='Server was not configured properly, please provide a notebook first.')


class PageNotFoundError(WWWError):

	def __init__(self, page):
		WWWError.__init__(self, '404 Not Found', msg='No such page: %s' % page.name)


class WWWInterface(Interface):
	'''Class to handle the WWW interface for zim notebooks.

	Objects of this class are callable, so they can be used as application
	objects within a WSGI compatible framework. See PEP 333 for details
	( http://www.python.org/dev/peps/pep-0333/ ).
	'''

	ui_type = 'html'

	def __init__(self, notebook=None, template='Default', **opts):
		Interface.__init__(self, **opts)
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
		'''
		path = environ.get('PATH_INFO', '/')
		try:
			if self.notebook is None:
				raise NoConfigError
			elif len(path) == 0 or path == '/':
				content = self.render_index()
			elif path.startswith('/+docs/'):
				pass # TODO document root
			elif path.startswith('/+file/'):
				pass # TODO attachment or raw source
			else:
				pagename = path.replace('/', ':')
				content = self.render_page(pagename)
		except WWWError, error:
			header = [('Content-Type', 'text/plain')]
			start_response(error.status, header)
			return error.content
		except Exception, error:
			sys.excepthook(*sys.exc_info())
			#~ environ['wsgi.errors'].write(str(error)+'\n') # FIXME also print stack trace
			start_response('500 Internal Server Error', [])
			return []
		else:
			header = [('Content-Type', 'text/html;charset=utf-8')]
			start_response('200 OK', header)
			return [string.encode('utf8') for string in content]

	def render_index(self, namespace=None):
		'''Serve the index page'''
		# TODO wrap index into a page so we can use the same template
		html = ['''\
<html>
<head>
	<title>Notebook index - zim</title>
</head>
<body>
''']
		if namespace:
			html.append('<h1>%s</h1>\n' % namespace)
		else:
			html.append('<h1>Notebook index</h1>\n')

		html.append('<ul>\n')

		def add_page(page):
			href = self.href(page)
			text = page.basename
			myhtml = ['<li><a href="%s">%s</a></li>\n' % (href, text)]
			if page.children:
				myhtml.append('<ul>\n')
				for page in page.children:
					myhtml.extend(add_page(page)) # recurs
				myhtml.append('</ul>\n')
			return myhtml

		if namespace is None:
			pagelist = self.notebook.get_root()
		else:
			pagelist = self.notebook.get_page(namespace).children

		for page in pagelist:
			html.extend(add_page(page))

		html.append('''\
</ul>
</body>
</html>
''')
		return html

	def render_page(self, pagename):
		'''Serve a single page from the notebook'''
		page = self.notebook.get_page(pagename)
		if page.isempty():
			if page.children:
				return self.render_index(page.name)
			else:
				raise PageNotFoundError(page)
		else:
			if self.template:
				output = Buffer()
				self.template.process(page, output)
				html = output.getvalue()
			else:
				html = page.get_text(format='html')
			return [html]

	def href(self, page):
		'''Returns the url to page'''
		path = page.name.replace(':', '/')
		if not path.startswith('/'): path = '/'+path
		#~ return self.url + path
		return path


class Server(gobject.GObject):
	'''Webserver based on glib'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'started': (gobject.SIGNAL_RUN_LAST, None, []),
		'stopped': (gobject.SIGNAL_RUN_LAST, None, [])
	}

	logger = logging.getLogger('zim.www.server')

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

		self.logger.info('Server starting at port %i', self.port)

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
			self.logger.error(error)
		self.socket = None

		self.logger.info('Server stopped')
		self.running = False
		self.emit('stopped')

	def do_accept_request(self):
		# set up handler for new connection
		clientsocket, address = self.socket.accept() # TODO timeout ?
		self.logger.debug('got request from %s', address[0])

		# read data
		rfile = clientsocket.makefile('rb')
		requestline = rfile.readline()
		command, path, version = requestline.split()
		assert version.startswith('HTTP/') # TODO return + log error
		assert command in ('GET', 'HEAD') # TODO return + log error
		if version[5:] != 0.9: # HTTP/0.9 does not do headers
			headerlines = []
			while True:
				line = rfile.readline()
				if not line or line.isspace():
					break
				else:
					headerlines.append(line)
			#~ headers = rfc822headers.parse(''.join(headerlines))
		#~ else:
			#~ headers = {}

		wfile = clientsocket.makefile('wb')
		environ = {
			'REQUEST_METHOD': 'GET',
			'SCRIPT_NAME': '',
			'PATH_INFO': path,
			'QUERY_STRING': '',
			'SERVER_NAME': 'localhost',
			'SERVER_PORT': str(self.port),
			'SERVER_PROTOCOL': version
		}
		handler = self.handlerclass(rfile, wfile, None, environ) # TODO stderr
		handler.run(self.interface)
		rfile.close()
		wfile.flush()
		wfile.close()
		clientsocket.close()
		return True # else io watch gets deleted


# Need to register classes defining gobject signals
gobject.type_register(Server)
