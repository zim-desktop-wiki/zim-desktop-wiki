# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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

from functools import partial

from wsgiref.headers import Headers
import urllib

from zim.errors import Error
from zim.notebook import Notebook, Path, Page, IndexPage, PageNameError
from zim.fs import File, Dir, FileNotFoundError
from zim.config import data_file, ConfigManager
from zim.plugins import PluginManager
from zim.stores import encode_filename
from zim.parsing import url_encode

from zim.export.linker import ExportLinker, StubLayout
from zim.export.template import ExportTemplateContext

from zim.formats import get_format

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


class WWWInterface(object):
	'''Class to handle the WWW interface for zim notebooks.

	Objects of this class are callable, so they can be used as application
	objects within a WSGI compatible framework. See PEP 333 for details
	(U{http://www.python.org/dev/peps/pep-0333/}).

	For basic handlers to run this interface see the "wsgiref" package
	in the standard library for python.
	'''

	def __init__(self, notebook, config=None, template='Default'):
		'''Constructor
		@param notebook: a L{Notebook} object
		@param config: optional C{ConfigManager} object
		@param template: html template for zim pages
		'''
		assert isinstance(notebook, Notebook)
		self.notebook = notebook
		self.config = config or ConfigManager(profile=notebook.profile)

		self.output = None

		if template is None:
			template = 'Default'

		if isinstance(template, basestring):
			from zim.templates import get_template
			self.template = get_template('html', template)
			if not self.template:
				raise AssertionError, 'Could not find html template: %s' % template
		else:
			self.template = template

		self.linker_factory = partial(WWWLinker, self.notebook, self.template.resources_dir)
		self.dumper_factory = get_format('html').Dumper # XXX

		self.plugins = PluginManager(self.config)
		self.plugins.extend(notebook.index)
		self.plugins.extend(notebook)
		self.plugins.extend(self)

		#~ self.notebook.index.update()

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

			if path == '/':
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
				if self.template.resources_dir:
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
		lines = []

		context = ExportTemplateContext(
			self.notebook,
			self.linker_factory,
			self.dumper_factory,
			title=page.get_title(),
			content=[page],
			home=self.notebook.get_home_page(),
			up=page.parent if page.parent and not page.parent.isroot else None,
			prevpage=self.notebook.index.get_previous(page),
			nextpage=self.notebook.index.get_next(page),
			links={'index': '/'},
			index_generator=self.notebook.index.walk,
			index_page=page,
		)
		self.template.process(lines, context)
		return lines


class WWWLinker(ExportLinker):
	'''Implements a linker that returns the correct
	links for the way the server handles URLs.
	'''

	def __init__(self, notebook, resources_dir=None, source=None):
		layout = StubLayout(notebook, resources_dir)
		ExportLinker.__init__(self, notebook, layout, source=source)

	def icon(self, name):
		return url_encode('/+resources/%s.png' % name)

	def resource(self, path):
		return url_encode('/+resources/%s' % path)

	def resolve_source_file(self, link):
		return None # not used by HTML anyway

	def page_object(self, path):
		'''Turn a L{Path} object in a relative link or URI'''
		return url_encode('/' + encode_filename(path.name) + '.html')
			# TODO use script location as root for cgi-bin

	def file_object(self, file):
		'''Turn a L{File} object in a relative link or URI'''
		if file.ischild(self.notebook.dir):
			# attachment
			relpath = file.relpath(self.notebook.dir)
			return url_encode('/+file/' + relpath)
		elif self.notebook.document_root \
		and file.ischild(self.notebook.document_root):
			# document root
			relpath = file.relpath(self.notebook.document_root)
			return url_encode('/+docs/' + relpath)
			# TODO use script location as root for cgi-bin
			# TODO allow alternative document root for cgi-bin
		else:
			# external file -> file://
			return file.uri


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
