# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

import sys
import os
from cStringIO import StringIO
import logging
import wsgiref.validate
import wsgiref.handlers

from zim.fs import File
from zim.www import WWWInterface
from zim.config import VirtualConfigManager

# TODO how to test fetching from a socket while mainloop is running ?


class Filter404(tests.LoggingFilter):

	logger = 'zim.www'
	message = '404 Not Found'


@tests.slowTest
class TestWWWInterface(tests.TestCase):

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
		self.template = 'Default'
		self.file_not_found_paths = ['/Test', '/nonexistingpage.html', '/nonexisting/']
		self.file_found_paths = ['/favicon.ico', '/+resources/checked-box.png']

	def runTest(self):
		'Test WWW interface'
		config = VirtualConfigManager()
		notebook = tests.new_notebook(fakedir=self.get_tmp_name())
		notebook.index.update()
		interface = WWWInterface(notebook, config=config, template=self.template)
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
			if os.name == 'nt':
				# HACK: on windows we have no file system encoding,
				# but use unicode instead for os API.
				# However wsgiref.validate fails on unicode param
				# in environmnet.
				for k, v in handler.os_environ.items():
					if isinstance(v, unicode):
						handler.os_environ[k] = v.encode('utf-8')

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
			self.assertTrue('<li><a href="/Test/foo.html" title="foo" class="page">foo</a>' in response)

		# page
		response = call('GET', '/Test/foo.html')
		self.assertResponseOK(response)
		self.assertTrue('<h1>Foo <a name=\'Test:foo\'></a></h1>' in response)

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
			self.assertTrue('<!-- Wiki content -->' in body, 'Template is used')
			self.assertTrue('src="/%2Bresrouces/foo/bar.png"' ''.join(body), 'Template is used')

	def setUp(self):
		TestWWWInterface.setUp(self)
		self.file = File('tests/data/templates/html/Default.html')
		self.template = self.file.path
		self.file_found_paths.append('/+resources/foo/bar.png')

	def runTest(self):
		'Test WWW interface with a template with resources.'
		TestWWWInterface.runTest(self)
