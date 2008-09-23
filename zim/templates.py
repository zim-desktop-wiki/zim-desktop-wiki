# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains classes for template processing.

The main class is Template, which wraps and pre-compiles a template file. Each
page that can be dumped using the template is wrapped with a PageProxy object,
which exposes attributes and functions to be used in the template. This module
is most efficient when you want to dump many pages with one template.

Usage:
	import zim.templates
	tmpl = zim.templates.get_template('html', 'Default')
	for page in notebook.get_root():
		tmpl.process(page, sys.stdout)

Template files are expected to be in a path XDG_DATA/zim/templates/FORMAT/

The following syntax is supported:

	[% GET page.name %] or just [% page.name %]
	[% SET foo %]
	[% IF param %] ... [% ELSE %] ... [% END %]
	[% FOREACH name = param %] ... [% name %] ... [% END %]
	[% strftime('%c', param) %]

Available parameters are 'zim.version' and 'page', all available attributes
for 'page' are defined in the PageProxy class.
'''

import os
import xdg.BaseDirectory

import zim


def list_templates(format):
	'''FIXME'''
	templates = []
	for dir in xdg.BaseDirectory.load_data_paths('zim', 'templates', format):
		if not os.path.isdir(dir): continue
		templates.extend( os.listdir(dir) )
	# TODO: remove extension
	return templates


def get_template(format, name):
	'''FIXME'''
	for dir in xdg.BaseDirectory.load_data_paths('zim', 'templates', format):
		if not os.path.isdir(dir): continue
		path = os.path.join(dir, name)
		if os.path.exists(path):
			# TODO: add extension
			return Template(path, format)

class TemplateError:
	'''Error class for errors in templates'''

class Template(object):
	'''Template object, maps to a single template file.'''

	def __init__(self, file, format):
		'''FIXME'''
		self.format = format
		if isinstance(file, basestring):
			file = open(file)
		self.count = 0
		try:
			self._tokenize(file)
		except Exception, error:
#		except TemplateError, error:
			print error, 'Error at %s line %i\n' % (file, self.count)

	def _tokenize(self, file):
		'''Loops trough lines to break it up in text and tokens.'''
		self.tokens = []
		self.stack = [ self.tokens ]

		def append_text(text):
			if not text: return
			if self.stack[-1] and isinstance(self.stack[-1][-1], basestring):
				self.stack[-1][-1] += text
			else:
				self.stack[-1].append(text)

		for line in file:
			self.count += 1

			while line.find('[%') >= 0:
				(pre, sep, line) = line.partition('[%')
				(cmd, sep, line) = line.partition('%]')
				append_text(pre)
				self._append_token(cmd)

			append_text(line)

		if len(self.stack) == 1:
			del self.stack # clean up

	def _append_token(self, string):
		'''Process a single token and put an action in the token list'''
		string = string.strip()
		if not string: return
		if string.startswith('SET'):
			string = string[3:].lstrip()
			# TODO check valid param
			self.stack[-1].append( ('SET', string) )
		elif string.startswith('IF'):
			string = string[2:].lstrip()
			# TODO check valid param
			token = ('IF', string, [], [])
			self.stack[-1].append(token)
			self.stack.append(token[2])
		elif string.startswith('ELSE'):
			self.stack.pop()
			token = self.stack[-1][-1]
			if token[0] != 'IF':
				raise TemplateError, 'ELSE clause outside IF block'
			self.stack.append(token[3])
		elif string.startswith('FOREACH'):
			string = string[7:].lstrip()
			# TODO check param assignment
			token = ('FOREACH', string, [])
			self.stack[-1].append(token)
			self.stack.append(token[2])
		elif string.startswith('END'):
			self.stack.pop()
		else:
			if string.startswith('GET'):
				string = string[3:].lstrip()
				string.lstrip()
			# check string is param or function
			# check valid syntax
			self.stack[-1].append( ('GET', string) )

	def process(self, page, output):
		'''FIXME'''
		self.dict = { 'zim': { 'version': zim.__version__ } }
		self.dict['page'] = PageProxy(page, self.format)
		self._process(self.tokens, output)
		del self.dict # cleanup

	def _process(self, tree, output):
		'''FIXME'''
		for token in tree:
			if isinstance(token, tuple):
				if token[0] == 'IF':
					if self._get_param(token[1]): # IF
						self._process(token[2], output) #recurs
					elif len(token) > 3: # ELSE
						self._process(token[3], output) #recurs
				elif token[0] == 'FOREACH':
					pass # TODO
				elif token[0] == 'GET':
					output.write( self._get_param(token[1]) )
				elif token[0] == 'SET':
					pass
					#self._set_param(token[1], token[2])
			else:
				# If it is not a token, it is a piece of text
				output.write(token)

	def _get_param(self, key):
		val = self.dict
		for k in key.split('.'):
			if k.startswith('_'):
				# shield private attributes
				raise TemplateError, 'No such parameter: %s' % key
			elif isinstance(val, PageProxy):
				if hasattr(val, k):
					val = getattr(val, k)
				else:
					raise TemplateError, 'No such parameter: %s' % key
			elif isinstance(val, dict):
				val = val.get(k, '')
			else:
				raise TemplateError, 'No such parameter: %s' % key
		return val

	def _set_param(self, key, val):
		if key.find('.') >= 0 or key == 'page' or key == 'zim':
			# do not allow overwriting defaults or nested keys
			raise TemplateError, 'Could not set parameter: %s' % key
		self.dict[key] = val


class TemplateFunctions(object):
	'''This class contains functions that can be called from a template.'''

	@staticmethod
	def strftime(format, timestamp):
		'''FIXME'''
		pass # TODO


class PageProxy(object):
	'''Exposes a single page object to the template.'''

	def __init__(self, page, format):
		'''Constructor takes the page object to expose and a format.'''
		# private attributes should be shielded by the template engine
		self._page = page
		self._format = format

	@property
	def name(self): self._page.name

	@property
	def basename(self): self._page.basename

	@property
	def namespace(self): self._page.namespace

	@property
	def title(self): pass # TODO

	@property
	def heading(self): pass # TODO

	@property
	def links(self): pass # TODO

	@property
	def backlinks(self): pass # TODO

	@property
	def prev(self): pass # TODO

	@property
	def next(self): pass # TODO

	@property
	def index(self): pass # TODO

	@property
	def body(self): self._page.get_text(format=self._format)


if __name__ == '__main__':
	# Some debug code to list and dump templates
	import sys
	import pprint
	if len(sys.argv) == 3:
		(format, template) = sys.argv[1:3]
		tmpl = get_template(format, template)
		pprint.pprint( tmpl.tokens )
	elif len(sys.argv) == 2:
		format = sys.argv[1]
		pprint.pprint( list_templates(format) )
	else:
		print 'usage: %s FORMAT [TEMPLATE]' % __file__
