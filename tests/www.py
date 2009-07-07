# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from tests import TestCase, get_test_notebook

import sys
from cStringIO import StringIO
import logging
import wsgiref.validate
import wsgiref.handlers

from zim.www import WWWInterface

# TODO how to test fetching from a socket while mainloop is running ?

class Filter404(object):

	def filter(self, record):
		return not record.getMessage().startswith('404 Not Found')



class testWWWInterface(TestCase):

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
		if expectbody:
			self.assertTrue('<!-- Wiki content -->' in body, 'Template is used')

	def runTest(self):
		'Test WWW interface'
		notebook = get_test_notebook()
		notebook.index.update()
		interface = WWWInterface(notebook, template='Default')
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
			return wfile.getvalue()

		# index
		for path in ('/', '/Test/'):
			response = call('HEAD', path)
			self.assertResponseOK(response, expectbody=False)
			response = call('GET', path)
			#~ print '>'*80, '\n', response, '<'*80
			self.assertResponseOK(response)
			self.assertTrue('<li><a href="/Test/foo.html">foo</a></li>' in response)

		# page
		response = call('GET', '/Test/foo.html')
		self.assertResponseOK(response)
		self.assertTrue('<h1>Foo</h1>' in response)

		# page not found
		logger = logging.getLogger('zim.www')
		filter = Filter404()
		logger.addFilter(filter)
		try:
			for path in ('/Test', '/nonexistingpage.html', '/nonexisting/'):
				response = call('GET', path)
				header, body = self.assertResponseWellFormed(response)
				self.assertEqual(header[0], 'HTTP/1.0 404 Not Found')
		except:
			logger.removeFilter(filter)
			raise
		else:
			logger.removeFilter(filter)

