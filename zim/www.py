# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

# TODO needs more options like
#		-p --port INT	set port number
#		-P --public 	allow connections from outside
# TODO need template class
# TODO check client host for security
# TODO wrap all calls to notebook in try: except: blocks

class WWW(object):
	'''Object to handle the WWW interface for zim notebooks'''

	def href(self, page):
		'''Returns the url to page'''
		path = page.name.replace(':', '/')
		if not path.startswith('/'): path = '/'+path
		# "href", page.name, '>', path
		return self.url + path

	def do_GET_index(self, namespace=None):
		'''Serve the index page'''
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
		self.reply(200, html)


	def do_GET_page(self, pagename):
		'''Serve a single page from the notebook'''
		page = self.notebook.get_page(pagename)
		if page.isempty():
			if page.children:
				return self.do_GET_index(page.name)
			else:
				# TODO raise error 404
				self.reply(200, 'Page not found: %s' % pagename)
				return
		else:
			from StringIO import StringIO
			if self.template:
				output = StringIO()
				self.template.process(page, output)
				html = output.getvalue()
			else:
				html = page.get_text(format='html')
			self.reply(200, html)


	def reply(self, response, html):
		'''Send a piece of html to the browser'''
		#print 'sending\n'+html
		self.send_response(response)
		self.send_header('Content-Type', 'text/html')
		self.send_header('Content-Length', str(len(html)))
		# Last-Modified
		# etc.
		self.end_headers()

		html = html.encode('utf8')
		for line in html.splitlines():
			self.wfile.write(line+'\n')


def serve(port, notebook=None, template=None):
	'''Run a server based on BaseHTTPServer'''
	import BaseHTTPServer

	class Handler(BaseHTTPServer.BaseHTTPRequestHandler, WWW):

		def do_GET(self):
			if self.path == '/':
				self.do_GET_index()
			else:
				page = self.path.replace('/', ':')
				self.do_GET_page(page)

	if not template is None:
		import zim.templates
		template = zim.templates.get_template('html', template)

	# start the server
	Handler.notebook = notebook # FIXME using class attribute here
	Handler.url = 'http://localhost:%d' % port # FIXME using class attribute here
	Handler.template = template # FIXME using class attribute here
	server_address = ('', port)
	httpd = BaseHTTPServer.HTTPServer(server_address, Handler)
	sa = httpd.socket.getsockname()
	print "Serving HTTP on", sa[0], "port", sa[1], "..."
	httpd.serve_forever()

def cgi():
	'''Run as a cgi script'''
	pass
