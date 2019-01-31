
# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

import sys
import os
from io import BytesIO
import logging
import wsgiref.validate
import wsgiref.handlers

from zim.fs import File
from zim.www import WWWInterface
from zim.notebook import Path

# TODO how to test fetching from a socket while mainloop is running ?


class Filter404(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self, 'zim.www', '404 Not Found')


@tests.slowTest
class TestWWWInterface(tests.TestCase):

	def assertResponseWellFormed(self, response, expectbody=True):
		lines = response.split(b'\r\n')
		header = []
		while lines:
			line = lines.pop(0)
			if line == b'':
				break
			else:
				header.append(line.decode('UTF-8'))
		body = b'\r\n'.join(lines)

		self.assertTrue(header[0].startswith('HTTP/1.0 '))
		self.assertTrue(len([l for l in header if l.startswith('Content-Type: ')]) == 1, 'Content-Type header present')
		self.assertTrue(len([l for l in header if l.startswith('Date: ')]) == 1, 'Date header present')
		if expectbody:
			self.assertTrue(body and not body.isspace(), 'Repsonse has a body')

		return header, body

	def assertResponseOK(self, response, expectbody=True):
		header, body = self.assertResponseWellFormed(response, expectbody)
		self.assertEqual(header[0], 'HTTP/1.0 200 OK')
		self.assertTrue('Content-Type: text/html; charset="utf-8"' in header)
		return header, body

	def setUp(self):
		self.template = 'Default'
		self.file_not_found_paths = ['/Test', '/nonexistingpage.html', '/nonexisting/']
		self.file_found_paths = ['/favicon.ico', '/+resources/checked-box.png']

	def runTest(self):
		'Test WWW interface'
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		notebook.index.check_and_update()
		interface = WWWInterface(notebook, template=self.template)
		validator = wsgiref.validate.validator(interface)

		def call(command, path):
			#print("CALL:", command, path)
			environ = {
				'REQUEST_METHOD': command,
				'SCRIPT_NAME': '',
				'PATH_INFO': path,
				'QUERY_STRING': '',
				'SERVER_NAME': 'localhost',
				'SERVER_PORT': '80',
				'SERVER_PROTOCOL': '1.0'
			}
			rfile = BytesIO(b'')
			wfile = BytesIO()
			handler = wsgiref.handlers.SimpleHandler(rfile, wfile, sys.stderr, environ)
			handler.run(validator)
			return wfile.getvalue()

		# index
		for path in ('/', '/Test/'):
			response = call('HEAD', path)
			self.assertResponseOK(response, expectbody=False)
			response = call('GET', path)
			#print('>'*80, '\n', response, '<'*80)
			header, body = self.assertResponseOK(response)
			self.assertIn(b'<li><a href="/Test/foo.html" title="foo" class="page">foo</a>', body)

		# page
		afolder = notebook.get_attachments_dir(Path('Test:foo'))
		afile = afolder.file('attachment.pdf')
		afile.touch()

		response = call('GET', '/Test/foo.html')
		header, body = self.assertResponseOK(response)
		self.assertIn(b'<h1>Foo <a name=\'Test:foo\'></a></h1>', body)

		# - ensure page link works
		self.assertIn(b'<a href="/Test/foo/bar.html"', body)

		# - ensure attachment link works
		self.assertIn(b"<td><a href='/%2Bfile/Test/foo/attachment.pdf'>attachment.pdf</a></td>", body)

		# - ensure sub page does not show up as attachment
		self.assertNotIn(b'bar.txt', body)


		# page not found
		with Filter404():
			for path in self.file_not_found_paths:
				response = call('GET', path)
				header, body = self.assertResponseWellFormed(response)
				self.assertEqual(header[0], 'HTTP/1.0 404 Not Found')

		# favicon and other files
		for path in self.file_found_paths:
			response = call('GET', path)
			header, body = self.assertResponseWellFormed(response)
			self.assertEqual(header[0], 'HTTP/1.0 200 OK')


#~ class TestWWWInterfaceTemplate(TestWWWInterface):
#~
	#~ def assertResponseOK(self, response, expectbody=True):
		#~ header, body = TestWWWInterface.assertResponseOK(self, response, expectbody)
		#~ if expectbody:
			#~ self.assertTrue('<!-- Wiki content -->' in body, 'Template is used')
#~
	#~ def setUp(self):
		#~ TestWWWInterface.setUp(self)
		#~ self.template = 'Default'
		#~ self.file_not_found_paths.append('/+resources/foo/bar.png')
#~
	#~ def runTest(self):
		#~ 'Test WWW interface with a template.'
		#~ TestWWWInterface.runTest(self)


class TestWWWInterfaceTemplateResources(TestWWWInterface):

	def assertResponseOK(self, response, expectbody=True):
		header, body = TestWWWInterface.assertResponseOK(self, response, expectbody)
		if expectbody:
			self.assertIn(b'<!-- Wiki content -->', body, 'Template is used')
		return header, body

	def setUp(self):
		TestWWWInterface.setUp(self)
		self.file = File('tests/data/templates/html/Default.html')
		self.template = self.file.path
		self.file_found_paths.append('/+resources/foo/bar.png')

	def runTest(self):
		'Test WWW interface with a template with resources.'
		TestWWWInterface.runTest(self)
