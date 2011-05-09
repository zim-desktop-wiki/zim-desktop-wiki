# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

from tests import TestCase, LoggingFilter, get_test_notebook
from zim.fs import File
import sys
from cStringIO import StringIO
import logging
import wsgiref.validate
import wsgiref.handlers

from zim.www import WWWInterface

# TODO how to test fetching from a socket while mainloop is running ?


class Filter404(LoggingFilter):

	logger = 'zim.www'
	message = '404 Not Found'



class TestWWWInterface(TestCase):

	slowTest = True

	def assertResponseWellFormed(self, response, expectbody=True):
		body = response.splitlines()
		header = []
		while body:
			line = body.pop(0)
			if line == '':
				break
			else:
				header.append(line)
		self.assertTrue(header[0].startswith('HTTP/1.0 '))
		self.assertTrue(len([l for l in header if l.startswith('Content-Type: ')]) == 1, 'Content-Type header present')
		self.assertTrue(len([l for l in header if l.startswith('Date: ')]) == 1, 'Date header present')
		if expectbody:
			text = '\n'.join(body)
			self.assertTrue(text and not text.isspace(), 'Repsonse has a body')

		return header, body

	def assertResponseOK(self, response, expectbody=True):
		header, body = self.assertResponseWellFormed(response, expectbody)
		self.assertEqual(header[0], 'HTTP/1.0 200 OK')
		self.assertTrue('Content-Type: text/html; charset="utf-8"' in header)
		return header, body

	def setUp(self):
		self.template = None
		self.not_found_paths = ['/Test', '/nonexistingpage.html', '/nonexisting/']
		self.file_paths = ['/favicon.ico', '/+icons/checked-box.png']

	def runTest(self):
		'Test WWW interface'
		notebook = get_test_notebook()
		notebook.index.update()
		interface = WWWInterface(notebook, template=self.template)
		validator = wsgiref.validate.validator(interface)

		def call(command, path):
			environ = {
				'REQUEST_METHOD': command,
				'SCRIPT_NAME': '',
				'PATH_INFO': path,
				'QUERY_STRING': '',
				'SERVER_NAME': 'localhost',
				'SERVER_PORT': '80',
				'SERVER_PROTOCOL': '1.0'
			}
			rfile = StringIO('')
			wfile = StringIO()
			handler = wsgiref.handlers.SimpleHandler(rfile, wfile, sys.stderr, environ)
			handler.run(validator)
			#~ print '>>>>\n', wfile.getvalue(), '<<<<'
			return wfile.getvalue()

		# index
		for path in ('/', '/Test/'):
			response = call('HEAD', path)
			self.assertResponseOK(response, expectbody=False)
			response = call('GET', path)
			#~ print '>'*80, '\n', response, '<'*80
			self.assertResponseOK(response)
			self.assertTrue('<li><a href="/Test/foo.html" title="foo">foo</a></li>' in response)

		# page
		response = call('GET', '/Test/foo.html')
		self.assertResponseOK(response)
		self.assertTrue('<h1>Foo</h1>' in response)
		
		
		# page not found

		with Filter404():
			for path in self.not_found_paths:
				response = call('GET', path)
				header, body = self.assertResponseWellFormed(response)
				self.assertEqual(header[0], 'HTTP/1.0 404 Not Found')

		# favicon and other files
		for path in self.file_paths:
			response = call('GET', path)
			header, body = self.assertResponseWellFormed(response)
			self.assertEqual(header[0], 'HTTP/1.0 200 OK')


class TestWWWInterfaceTemplate(TestWWWInterface):

	def assertResponseOK(self, response, expectbody=True):
		header, body = TestWWWInterface.assertResponseOK(self, response, expectbody)
		if expectbody:
			self.assertTrue('<!-- Wiki content -->' in body, 'Template is used')

	def setUp(self):
		TestWWWInterface.setUp(self)
		self.template = 'Default'
		self.not_found_paths.append('/+template/favicon/zim.png')

	def runTest(self):
		'Test WWW interface with a template. "ERROR: No such file: ..." message expected'
		TestWWWInterface.runTest(self)

class TestWWWInterfaceTemplateResources(TestWWWInterface):

	def assertResponseOK(self, response, expectbody=True):
		header, body = TestWWWInterface.assertResponseOK(self, response, expectbody)
		if expectbody:
			self.assertTrue('src="/%2Btemplate/favicon/zim.png"' ''.join(body), 'Template is used')

	def setUp(self):
		TestWWWInterface.setUp(self)
		self.file = File('tests/data/template-resources/Default.html')
		self.template = self.file.path
		self.file_paths.append('/+template/favicon/zim.png')

	def runTest(self):
		'Test WWW interface with a template with resources.'
		TestWWWInterface.runTest(self)
