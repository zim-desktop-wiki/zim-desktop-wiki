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
import os
import socket
import logging
import glib

from zim import Interface
from zim.utils import rfc822headers
from zim.fs import *

class Error(Exception):
	'''FIXME'''

	def __init__(self, code, msg):
		'''FIXME'''
		self.code = code
		self.msg = msg


class WWWInterface(Interface):
	'''Class to handle the WWW interface for zim notebooks'''

	ui_type = 'html'

	def __init__(self, notebook=None, template='Default', **opts):
		Interface.__init__(self, **opts)
		assert not notebook is None, 'Need to specify a notebook'
		self.output = None
		if isinstance(template, basestring):
			from zim.templates import get_template
			template = get_template('html', template)
		self.template = template
		self.load_config()
		self.load_plugins()
		self.open_notebook(notebook)

	def serve(self, path, file):
		'''Main function for handling a single request. Arguments are the file
		handle to write the output to and the path to serve. Any exceptions
		will result in a error response being written.
		'''
		# TODO: add argument post=None for handling posted forms
		# TODO: first path element could be notebook name
		assert self.output is None
		self.output = file
		try:
			if path == '/':
				self.serve_index()
			elif path.startswith('/+docs/'):
				pass # TODO document root
			elif path.startswith('/+file/'):
				pass # TODO attachment or raw source
			else:
				pagename = path.replace('/', ':')
				self.serve_page(pagename)
		except Exception, error:
			self.write_error(error)

		self.output = None

	def serve_index(self, namespace=None):
		'''Serve the index page'''
		# TODO wrap index into a page so we can use the same template
		html = '''
<html>
<head>
	<title>Notebook index - zim</title>
</head>
<body>
'''
		if namespace:
			html += '<h1>%s</h1>' % namespace
		else:
			html += '<h1>Notebook index</h1>'

		html += '<ul>\n'

		def add_page(page):
			href = self.href(page)
			text = page.basename
			myhtml = '<li><a href="%s">%s</a></li>\n' % (href, text)
			if page.children:
				myhtml += '<ul>\n'
				for page in page.children:
					myhtml += add_page(page) # recurs
				myhtml += '</ul>\n'
			return myhtml

		pagelist = self.notebook.get_root()
		if namespace:
			pagelist = self.notebook.get_page(namespace).children

		for page in pagelist:
			html += add_page(page)

		html += '''
</ul>
</body>
</html>
'''
		self.write_headers(200)
		self.output.write(html.encode('utf8'))

	def serve_page(self, pagename):
		'''Serve a single page from the notebook'''
		page = self.notebook.get_page(pagename)
		if page.isempty():
			if page.children:
				return self.serve_index(page.name)
			else:
				raise Error, (404, 'Page not found: %s' % pagename)
		else:
			if self.template:
				output = Buffer()
				self.template.process(page, output)
				html = output.getvalue()
			else:
				html = page.get_text(format='html')
			self.write_headers(200)
			self.output.write(html.encode('utf8'))

	def href(self, page):
		'''Returns the url to page'''
		path = page.name.replace(':', '/')
		if not path.startswith('/'): path = '/'+path
		#~ return self.url + path
		return path

	def write_headers(self, response, headers=None):
		'''FIXME'''
		if headers is None: headers = {}

		# Send HTTP response
		self.output.write("HTTP/1.0 %d\r\n" % response)

  		# Set default headers
		#~ headers['Server'] = 'zim %.2f' % zim.__version__
		#~ headers['Date'] = '1-1-00' # FIXME
		headers.setdefault('Content-Type', 'text/html;charset=utf-8')
		# Last-Modified
		# etc.

		# Write headers
		self.output.write(rfc822headers.format(headers, strict=True))
		self.output.write("\r\n") # end of headers

	def write_error(self, error):
		'''FIXME'''
		if isinstance(error, Error):
			code = error.code
			msg = error.msg
		else:
			code = 500
			msg = error.__str__()
		self.write_headers(code)
		self.output.write(msg.encode('utf8'))


class Handler(object):
	'''FIXME'''

	def __init__(self, notebook=None, **opts):
		self.opts = opts
		if not notebook is None:
			self.notebook = WWWInterface(notebook=notebook, **opts)
		else:
			self.notebook = None
			self.notebooks = {}

	def main(self):
		'''FIXME'''
		path = os.environ['PATH_INFO'] or '/'
		self.serve(path, sys.stdout)

	def serve(self, path, file):
		'''FIXME'''
		# TODO: decode path %xx -> char(xx)
		if self.notebook is None:
			# if not path or path == '/':
			#	serve index page
			# else:
			# 	i = path.find('/')
			#	name = path[:i]
			#	if not name in self.notebooks
			#		self.notebooks[name] = WWWInterface(name, **self.opts)
			#	self.notebooks[notebook].serve(path[i:], file)
			assert False, 'TODO dispatch multiple notebooks'
		else:
			# we only serve a single notebook
			return self.notebook.serve(path, file)

class Server(Handler):
	'''Run a server based on BaseHTTPServer'''

	logger = logging.getLogger('zim.www.server')

	def __init__(self, notebook=None, port=8080, gui=False, **opts):
		'''FIXME'''
		Handler.__init__(self, notebook, **opts)
		assert isinstance(port, int), port
		self.port = port
		#~ self.url = 'http://localhost:%d' % self.port
		self.socket = None
		if gui:
			import zim.gui.server
			self.window = zim.gui.server.ServerWindow()
			self.use_gtk = True
		else:
			self.use_gtk = False

	def bind(self):
		#~ logger.warn('''\
#~ WARNING: Serving zim notes as a webserver. Unless you have some
#~ kind of firewall your notes are now open to the whole wide world.
#~ ''')

		# open sockets for connections
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.bind(("localhost", self.port)) # TODO use socket.gethostname() for public server
		self.socket.listen(5)

		glib.io_add_watch(self.socket, glib.IO_IN,
			lambda *a: self.do_accept_request())

	def main(self):
		if self.socket is None:
			self.bind()
		if self.use_gtk:
			import gtk
			self.window.show_all()
			gtk.main()
		else:
			glib.MainLoop().run()

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
		# assume no body since we do not supprot POST (yet)
		rfile.close()

		wfile = clientsocket.makefile('wb')
		#~ wfile.write("HTTP/1.0 %d\r\n" % 500)
		self.serve(path, wfile)
		wfile.flush()
		wfile.close()
		clientsocket.close()
		return True # else io watch gets deleted
