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
import re
import xdg.BaseDirectory

import zim

# TODO incorporate BaseDir methods in fs

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

class TemplateError(Exception):
	'''Error class for errors in templates'''

class Template(object):
	'''Template object, maps to a single template file.'''

	def __init__(self, file, format):
		'''FIXME'''
		self.format = format
		if isinstance(file, basestring):
			file = open(file)
		self.count = 0
#		try:
		self._tokenize(file)
#		except TemplateError, error:
#			print error
#			print 'Error at %s line %i\n' % (file, self.count)

	def _tokenize(self, file):
		'''Loops trough lines to break it up in text and tokens.'''
		self.tokens = []
		self.stack = [ self.tokens ]

		def append_text(text):
			if not text: return
			if ( self.stack[-1] and
			     isinstance(self.stack[-1][-1], basestring) ):
				self.stack[-1][-1] += text
			else:
				self.stack[-1].append(text)

		for line in file:
			self.count += 1
			linestart = True

			while line.find('[%') >= 0:
				(pre, sep, line) = line.partition('[%')
				(cmd, sep, line) = line.partition('%]')
				append_text(pre)
				expand = self._append_token(cmd)
				if linestart and not expand:
					 # remove end of line to make blocks look better
					if line.isspace(): line = ''
				linestart = False

			append_text(line)

		if len(self.stack) == 1:
			del self.stack # clean up

	def _append_token(self, string):
		'''Process a single token and put an action in the token list
		Returns True if this token will expand to a value.'''
		string = string.strip()
		if not string: return False

		if string.startswith('SET'):
			(var, sep, val) = string[3:].partition('=')
			var = self._param(var)
			val = self._args(val)
			if len(val) == 1: val = val[0]
			self.stack[-1].append( ('SET', var, val) )
		elif string.startswith('IF'):
			var = self._param(string[2:])
			token = ('IF', var, [], [])
			self.stack[-1].append(token)
			self.stack.append(token[2])
		elif string.startswith('ELSE'):
			self.stack.pop()
			try:
				token = self.stack[-1][-1]
				assert token[0] == 'IF'
			except:
				raise TemplateError, 'ELSE clause outside IF block'
			self.stack.append(token[3])
		elif string.startswith('FOREACH'):
			(var, sep, val) = string[3:].partition('=')
			var = self._param(var)
			val = self._param(val)
			token = ('FOREACH', var, val, [])
			self.stack[-1].append(token)
			self.stack.append(token[-1])
		elif string.startswith('END'):
			self.stack.pop()
		else:
			if string.startswith('GET'): string = string[3:].lstrip()
			if string.find('(') > 0:
				assert False, 'TODO parse function'
			else:
				var = self._param(string)
				self.stack[-1].append( ('GET', var) )
			return True

		return False # SET and all flow control tokens do not expand

	_param_re = re.compile('\A\w[\w\.]*\w\Z')

	def _param(self, string):
		'''Verify string is a valid parameter name'''
		string = string.strip()
		if not self._param_re.match(string):
			raise TemplateError, 'not a valid parameter: %s' % string
		return string

	_args_re = re.compile('''
		^(
			(?P<quot>['"]).*?(?P=quot) |  # quoted string
			\w[\w\.]*\w                   # or param
		)	[\s\,]*                       # followed by seperators
	''', re.X)

	def _args(self, string):
		'''Parse simple list of quoted words and param names'''
		args = []
		def get_arg(match):
			args.append( match.group(0).strip('\'\"') )
			return ''
		string = self._args_re.sub( get_arg, string.strip('() ') )
		if string:
			raise TemplateError, 'invalid syntax: >>%s<<' % string
		return args

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
					if self.get_param(token[1]): # IF
						self._process(token[2], output) #recurs
					elif len(token) > 3: # ELSE
						self._process(token[3], output) #recurs
				elif token[0] == 'FOREACH':
					pass # TODO
				elif token[0] == 'GET':
					val = self.get_param(token[1])
					if val: output.write( val )
				elif token[0] == 'SET':
					self.set_param(token[1], token[2])
			else:
				# If it is not a token, it is a piece of text
				output.write(token)

	def get_param(self, key):
		'''Used during processing to get a template parameter'''
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

	def set_param(self, key, val):
		'''Used during processing to set a parameter'''
		if key.find('.') >= 0 or key == 'page' or key == 'zim':
			# do not allow overwriting defaults or nested keys
			raise TemplateError, 'Could not set parameter: %s' % key
		self.dict[key] = val


class TemplateFunctions(object):
	'''This class contains functions that can be called from a template.'''

	@staticmethod
	def strftime(template, format, timestamp):
		'''FIXME'''
		pass # TODO


class PageProxy(object):
	'''Exposes a single page object to the template.'''

	def __init__(self, page, format):
		'''Constructor takes the page object to expose and a format.'''
		# private attributes should be shielded by the template engine
		self._page = page
		self._format = format

	is_index = False

	@property
	def name(self): return self._page.name

	@property
	def basename(self): return self._page.basename

	@property
	def namespace(self): return self._page.namespace

	@property
	def title(self): return '' # TODO

	@property
	def heading(self): return '' # TODO

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
	def body(self): return self._page.get_text(format=self._format)


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
