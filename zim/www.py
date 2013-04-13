# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains a web interface for zim. This is an alternative
to the GUI application.

It can be run either as a stand-alone web server or embedded in another
server as a cgi-bin script or using  one of the python web frameworks
using the "WSGI" API.

The main classes here are L{WWWInterface} which implements the interface
(and is callable as a "WSGI" application) and L{Server} which implements
the standalone server.
'''

# TODO setting for doc_root_url when running in CGI mode
# TODO support "etg" and "if-none-match' headers at least for icons
# TODO: redirect server logging to logging module + set default level to -V in server process


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
	'''Error with http error code'''

	#: mapping of error number to string - extend when needed
	statusstring = {
		'403': 'Forbidden',
		'404': 'Not Found',
		'405': 'Method Not Allowed',
		'500': 'Internal Server Error',
	}

	def __init__(self, msg, status='500', headers=None):
		'''Constructor
		@param msg: specific error message - will be appended after
		the standard error string
		@param status: error code, e.g. '500' for "Internal Server Error"
		or '404' for "Not Found" - see http specifications for valid
		error codes
		@param headers: additional http headers for the error response,
		list of 2-tuples with header name and value
		'''
		self.status = '%s %s' % (status, self.statusstring[status])
		self.headers = headers
		self.msg = self.status
		if msg:
			self.msg += ' - ' + msg


class NoConfigError(WWWError):
	'''Error when configuration is missing what notebook to serve.
	E.g. for cgi-bin script that was copied without modifiction.
	'''

	description = '''\
There was no notebook configured for this zim instance.
This is likely a configuration issue.
'''

	def __init__(self):
		WWWError.__init__(self, 'Notebook not found', status='500')


class PageNotFoundError(WWWError):
	'''Error whan a page is not found (404)'''

	description = '''\
You tried to open a page that does not exist.
'''

	def __init__(self, page):
		if not isinstance(page, basestring):
			page = page.name
		WWWError.__init__(self, 'No such page: %s' % page, status='404')


class PathNotValidError(WWWError):
	'''Error when the url points to an invalid page path'''

	description = '''\
The requested path is not valid
'''

	def __init__(self):
		WWWError.__init__(self, 'Invalid path', status='403')


class WWWInterface(NotebookInterface):
	'''Class to handle the WWW interface for zim notebooks.

	Objects of this class are callable, so they can be used as application
	objects within a WSGI compatible framework. See PEP 333 for details
	(U{http://www.python.org/dev/peps/pep-0333/}).

	For basic handlers to run this interface see the "wsgiref" package
	in the standard library for python.
	'''

	ui_type = 'html'

	def __init__(self, notebook=None, template='Default', **opts):
		'''Constructor
		@param notebook: notebook location
		@param template: html template for zim pages
		@param opts: options for L{NotebookInterface.__init__()}
		'''
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
		'''Main function for handling a single request. Follows the
		WSGI API.

		@param environ: dictionary with environment variables for the
		request and some special variables. See the PEP for expected
		variables.

		@param start_response: a function that can be called to set the
		http response and headers. For example::

			start_response(200, [('Content-Type', 'text/plain')])

		@returns: the html page content as a list of lines
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
				path = '/+resources/favicon.ico'
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
 			elif path.startswith('/+resources/'):
				if self.template and self.template.resources_dir:
					file = self.template.resources_dir.file(path[12:])
					if not file.exists():
						file = data_file('pixmaps/%s' % path[12:])
				else:
					file = data_file('pixmaps/%s' % path[12:])

				if file:
					content = [file.raw()]
						# Will raise FileNotFound when file does not exist
					headers['Content-Type'] = file.get_mimetype()
	 			else:
					raise PageNotFoundError(path)
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
					for key, value in error.headers:
						headers.add_header(key, value)
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
		'''Render an index page
		@param namespace: the namespace L{Path}
		@returns: html as a list of lines
		'''
		page = IndexPage(self.notebook, namespace)
		return self.render_page(page)

	def render_page(self, page):
		'''Render a single page from the notebook
		@param page: a L{Page} object
		@returns: html as a list of lines
		'''
		if self.template:
			return self.template.process(self.notebook, page)
		else:
			return page.dump(format='html', linker=self.linker)


class WWWLinker(BaseLinker):
	'''Implements a L{linker<BaseLinker>} that returns the correct
	links for the way the server handles URLs.
	'''

	def __init__(self, notebook, path=None):
		BaseLinker.__init__(self)
		self.notebook = notebook
		self.path = path

	def resource(self, path):
		return url_encode('/+resources/%s' % path)

	def icon(self, name):
		return url_encode('/+resources/%s.png' % name)

	def resolve_file(self, link):
		try:
			file = self.notebook.resolve_file(link, self.path)
		except:
			# typical error is a non-local file:// uri
			return None
		else:
			return File

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


def main(notebook, port=8080, public=True, **opts):
	httpd = make_server(notebook, port, public, **opts)
	logger.info("Serving HTTP on %s port %i...", httpd.server_name, httpd.server_port)
	httpd.serve_forever()

def make_server(notebook, port=8080, public=True, **opts):
	'''Create a simple http server
	@param notebook: the notebook location
	@param port: the http port to serve on
	@param public: allow connections to the server from other
	computers - if C{False} can only connect from localhost
	@param opts: options for L{WWWInterface.__init__()}
	@returns: a C{WSGIServer} object
	'''
	import wsgiref.simple_server
	app = WWWInterface(notebook, **opts) # FIXME make opts explicit
	if public:
		httpd = wsgiref.simple_server.make_server('', port, app)
	else:
		httpd = wsgiref.simple_server.make_server('localhost', port, app)
	return httpd
