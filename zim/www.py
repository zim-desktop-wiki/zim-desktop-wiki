
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
from gi.repository import GObject

from functools import partial

from wsgiref.headers import Headers
import urllib.request
import urllib.parse
import urllib.error

from zim.errors import Error
from zim.notebook import Notebook, Path, Page, encode_filename, PageNotFoundError
from zim.fs import File, Dir, FileNotFoundError
from zim.config import data_file
from zim.parsing import url_encode

from zim.export.linker import ExportLinker, StubLayout
from zim.export.template import ExportTemplateContext
from zim.export.exporters import createIndexPage

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


class WebPageNotFoundError(WWWError):
	'''Error whan a page is not found (404)'''

	description = '''\
You tried to open a page that does not exist.
'''

	def __init__(self, page):
		if not isinstance(page, str):
			page = page.name
		WWWError.__init__(self, 'No such page: %s' % page, status='404')


class WebPathNotValidError(WWWError):
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

	def __init__(self, notebook, template='Default'):
		'''Constructor
		@param notebook: a L{Notebook} object
		@param template: html template for zim pages
		'''
		assert isinstance(notebook, Notebook)
		self.notebook = notebook

		self.output = None

		if template is None:
			template = 'Default'

		if isinstance(template, str):
			from zim.templates import get_template
			self.template = get_template('html', template)
			if not self.template:
				raise AssertionError('Could not find html template: %s' % template)
		else:
			self.template = template

		self.linker_factory = partial(WWWLinker, self.notebook, self.template.resources_dir)
		self.dumper_factory = get_format('html').Dumper # XXX

		#~ self.notebook.indexer.check_and_update()

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
		path = path.encode('iso-8859-1').decode('UTF-8')
			# The WSGI standard mandates iso-8859-1, but we want UTF-8. See:
			# - https://www.python.org/dev/peps/pep-3333/#unicode-issues
			# - https://code.djangoproject.com/ticket/19468
		try:
			methods = ('GET', 'HEAD', 'POST') ##added POST option to also upload to server
			if not environ['REQUEST_METHOD'] in methods:
				raise WWWError('405', headers=[('Allow', ', '.join(methods))])

			# cleanup path
			path = path.replace('\\', '/') # make it windows save
			isdir = path.endswith('/')
			parts = [p for p in path.split('/') if p and not p == '.']
			if [p for p in parts if p.startswith('.')]:
				# exclude .. and all hidden files from possible paths
				raise WebPathNotValidError()
			path = '/' + '/'.join(parts)
			if isdir and not path == '/':
				path += '/'

			if not path:
				path = '/'
			elif path == '/favicon.ico':
				path = '/+resources/favicon.ico'
			else:
				path = urllib.parse.unquote(path)

			if path == '/':
				headers.add_header('Content-Type', 'text/html', charset='utf-8')
				content = self.render_index()
			elif path.startswith('/+docs/'):
				dir = self.notebook.document_root
				if not dir:
					raise WebPageNotFoundError(path)
				file = dir.file(path[7:])
				content = [file.raw()]
					# Will raise FileNotFound when file does not exist
				headers['Content-Type'] = file.get_mimetype()
			elif path.startswith('/+file/'):
				file = self.notebook.folder.file(path[7:])
					# TODO: need abstraction for getting file from top level dir ?
				content = [file.read_binary()]
					# Will raise FileNotFound when file does not exist
				headers['Content-Type'] = file.mimetype()
			elif path.startswith('/+upload/'): ##added upload option to also upload to server
				logger.debug('Server -  Uploading content')
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
					raise WebPageNotFoundError(path)
			else:
				# Must be a page or a namespace (html file or directory path)
				headers.add_header('Content-Type', 'text/html', charset='utf-8')
				if path.endswith('.html'):
					pagename = path[:-5].replace('/', ':')
				elif path.endswith('/'):
					pagename = path[:-1].replace('/', ':')
				else:
					raise WebPageNotFoundError(path)

				path = self.notebook.pages.lookup_from_user_input(pagename)
				try:
					page = self.notebook.get_page(path)
					if page.hascontent:
						content = self.render_page(page)
					elif page.haschildren:
						content = self.render_index(page)
					else:
						raise WebPageNotFoundError(path)
				except PageNotFoundError:
					raise WebPageNotFoundError(path)
		except Exception as error:
			headerlist = []
			headers = Headers(headerlist)
			headers.add_header('Content-Type', 'text/plain', charset='utf-8')
			if isinstance(error, (WWWError, FileNotFoundError)):
				logger.error(error.msg)
				if isinstance(error, FileNotFoundError):
					error = WebPageNotFoundError(path)
					# show url path instead of file path
				if error.headers:
					for key, value in error.headers:
						headers.add_header(key, value)
				start_response(error.status, headerlist)
				content = str(error).splitlines(True)
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
				return [c.encode('UTF-8') for c in content]
		else:
			start_response('200 OK', headerlist)
			if environ['REQUEST_METHOD'] == 'HEAD':
				return []
			if environ['REQUEST_METHOD'] == 'POST': #upload files or notes
				import cgi, os
				formdata = cgi.FieldStorage(environ=environ, fp=environ['wsgi.input'])
				reply = ['\n<div>']

				pth=self.notebook.layout.root.path
				print(pth)
				dirname = pth+'/Staging/'
				notename = pth+'/Staging.txt'
				filename = formdata['newfile'].filename

				if not os.path.isdir(dirname):
					os.mkdir(dirname)
					os.chmod(dirname, 0o774)

				if not os.path.exists(notename):
					os.umask(0o664)
					f = open(notename,'w+')
					os.chmod(notename,0o664)
					f.write('Staging repository')
					f.close()

				def checkname(tgt): #find next free name
					tgt0, ext = os.path.splitext(tgt)
					tgt1 = tgt0
					k = 0
					while os.path.exists(tgt1+ext):
						tgt1 = tgt0 + str(k)
						k += 1
					return(tgt1+ext)


				#FIXME: refresh page on post
				#Save note to /Staging
				if 'comment' in formdata and len(formdata['comment'].value)>=0:
					fname = formdata['filename'].value if 'filename' in formdata and len(formdata['filename'].value) > 0 else 'note.txt'
					if fname[-4:] != '.txt':
						fname = os.path.splitext(fname)[0]+'.txt'
					fname=fname.replace(' ','_')
					#target = checkname(dirname+fname)
					target = dirname+fname
					logger.debug('Server - target is '+target)
					f = open(target, 'wb')
					os.chmod(target, 0o664)
					f.write(formdata['comment'].value.encode())
					f.close()
					self.notebook.index.update_file(self.notebook.layout.root.file('Staging/'+fname))
					reply.append('File '+str(os.path.basename(target))+' in Staging was written with contents \n\n'+formdata['comment'].value)
					adir, ext = os.path.splitext(fname)

					#Save file to /Staging
					if 'newfile' in formdata and formdata['newfile'].filename != '':
						if not os.path.isdir(dirname+'/'+adir):
							os.mkdir(dirname+'/'+adir)
							os.chmod(dirname, 0o774)
						logger.debug('Server - uploading file')
						target = checkname(os.path.join(dirname+'/'+adir, filename))
						f = open(target, 'wb')
						os.chmod(target, 0o664)
						f.write(formdata['newfile'].file.read())
						f.close()
						reply.append('Upload ready.\nFile stored with name '+filename+' under page Staging')
				#reply.append('</div>\n<a href="/" onclick="history.go(-1)">Go Back</a>')
				#return [''.join(reply).encode()]
				#reply.append('<meta http-equiv="refresh" >')
				reply.append('<meta http-equiv="refresh" content="0; url=/Staging/'+fname.replace('.txt','.html')+'" >')
				return [s.encode() for s in reply]
			elif 'utf-8' in headers['Content-Type']:
				return [string.encode('utf-8') for string in content]
			elif content and isinstance(content[0], str):
				return [c.encode('UTF-8') for c in content]
			else:
				return content

	def render_index(self, namespace=None):
		'''Render an index page
		@param namespace: the namespace L{Path}
		@returns: html as a list of lines
		'''
		path = namespace or Path(':')
		page = createIndexPage(self.notebook, path, namespace)
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
			prevpage=self.notebook.pages.get_previous(page) if not page.isroot else None,
			nextpage=self.notebook.pages.get_next(page) if not page.isroot else None,
			links={'index': '/'},
			index_generator=self.notebook.pages.walk,
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
		if file.ischild(self.notebook.folder):
			# attachment
			relpath = file.relpath(self.notebook.folder)
			print(relpath)
			print(self.notebook.folder)
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
	import os
	app = WWWInterface(notebook, **opts) # FIXME make opts explicit
	#To use authentication install wsgi-basic-auth
	from wsgi_basic_auth import BasicAuth
	if not 'WSGI_AUTH_CREDENTIALS' in os.environ:
		logger.warning('WSGI_AUTH_CREDENTIALS undefined - no authentication enforced. To enable set environment variable WSGI_AUTH_CREDENTIALS="usr1:pwd1|usr2:pwd2"')
	app = BasicAuth(app)
	#app = BasicAuth(app,users={"foo" : "bar", "fig" : "bbb"})
	if public:
		httpd = wsgiref.simple_server.make_server('', port, app)
	else:
		httpd = wsgiref.simple_server.make_server('localhost', port, app)
	return httpd
