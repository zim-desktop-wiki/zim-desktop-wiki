# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

# TODO needs more options like
#		-p --port INT	set port number
#		-P --public 	allow connections from outside
# TODO check client host for security
# TODO setting for doc_root_url when running in CGI mode

from zim import Application

from zim.fs import *

class Error(Exception):
	'''FIXME'''

	def __init__(self, code, msg):
		'''FIXME'''
		self.code = code
		self.msg = msg


class WWW(Application):
	'''Object to handle the WWW interface for zim notebooks'''

	def __init__(self, **opts):
		Application.__init__(self, **opts)
		self.file = None

	def serve(self, file, path):
		'''Main function for handling a single request. Arguments are the file
		handle to write the output to and the path to serve. Any exceptions
		will result in a error response being written.
		'''
		# TODO: add argument post=None for handling posted forms
		# TODO: first path element could be notebook name
		assert self.file is None
		self.file = file
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

		self.file = None

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
		self.file.write(html.encode('utf8'))

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
			self.file.write(html.encode('utf8'))

	def href(self, page):
		'''Returns the url to page'''
		path = page.name.replace(':', '/')
		if not path.startswith('/'): path = '/'+path
		return self.url + path

	def write_headers(self, response, headers=None):
		'''FIXME'''
		if headers is None: headers = {}

		# Send HTTP response
		self.file.write("HTTP/1.0 %d\r\n" % response)

  		# Set default headers
		#~ headers['Server'] = 'zim %.2f' % zim.__version__
		#~ headers['Date'] = '1-1-00' # FIXME
		headers.setdefault('Content-Type', 'text/html;charset=utf-8')
		# Last-Modified
		# etc.

		# Write headers
		for k, v in headers.items():
			self.file.write("%s: %s\r\n" % (k, v))
		self.file.write("\r\n") # end of headers

	def write_error(self, error):
		'''FIXME'''
		if isinstance(error, Error):
			code = error.code
			msg = error.msg
		else:
			code = 500
			msg = error.__str__()
		self.write_headers(code)
		self.file.write(msg.encode('utf8'))


class Server(WWW):
	'''Run a server based on BaseHTTPServer'''

	def __init__(self, port=8080, template='Default', **opts):
		'''FIXME'''
		WWW.__init__(self, **opts)
		assert isinstance(port, int)
		if isinstance(template, basestring):
			from zim.templates import get_template
			template = get_template('html', template)
		self.template = template
		self.port = port
		self.url = 'http://localhost:%d' % self.port

	def main(self):
		import BaseHTTPServer
		print '''\
WARNING: Serving zim notes as a webserver. Unless you have some
kind of firewall your notes are now open to the whole wide world.
'''
		# Define custom handler class and bind the class to our object.
		# Each request will pop a new instance of this class while we
		# are persistent and all instances should dipatch to us.
		class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):

			protocol_version = 'HTTP/1.0'
			zim_server = self # class attribute

			def do_GET(self):
				self.zim_server.serve(self.wfile, self.path)

			def do_HEAD(self):
				pass # TODO

			def do_POST(self):
				pass # TODO

		# start the server
		server_address = ('', self.port)
		server = BaseHTTPServer.HTTPServer(server_address, MyHandler)
		sa = server.socket.getsockname()
		print "Serving HTTP on", sa[0], "port", sa[1], "..."
		server.serve_forever()


class CGI(object):
	'''FIXME'''

	def main():
		'''FIXME'''
		import sys
		path = foo # TODO: get pathinfo
		self.serve(sys.stdout, path)
