# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains classes for template processing.

The main class is Template, which wraps and pre-compiles a template
file. Each page that can be dumped using the template is wrapped with
a PageProxy object, which exposes attributes and functions to be used
in the template. This module is most efficient when you want to dump
many pages with one template.

Usage:
	import zim.templates
	tmpl = zim.templates.get_template('html', 'Default')
	for page in notebook.get_root():
		tmpl.process(page, sys.stdout)

Template files are expected to be in a path
XDG_DATA/zim/templates/FORMAT/

Syntax is loosely based on the syntax of the perl Template Toolkit
(http://template-toolkit.org). The following syntax is supported:

	[% GET page.name %] or just [% page.name %]
	[% SET foo = 'Foo !' %] or just [ foo = 'Foo !' ]
	[% IF param %] ... [% ELSE %] ... [% END %]
	[% FOREACH name IN param %] ... [% name %] ... [% END %]
	or [% FOREACH name = param %] ...
	or [% FOREACH name IN ['foo', 'bar', 'baz'] %] ...
	[% strftime('%c', param) %]

Available parameters are 'zim.version' and 'page', all available
attributes for 'page' are defined in the PageProxy class.

Syntax errors in the template will cause an exception when the object
is constructed. Errors while processing a template only print warnings
to stderr (e.g. for unknown parameters).

We try to minimize to possibilities to actually execute
arbitrary code from templates. It should be save to download them.

Therefore:
* Function calls are only allowed for functions defined in
  class TemplateFunctions
* It is not allowed to call object methods (use '@property')
* We only allow strings as arguments, no arbitrary expressions
* There is no directive to evaluate code, like EVAL, PERL or PYTHON
'''

import re

import zim
from zim.utils import data_dirs, Re, split_quoted_strings, unescape_quoted_string

# TODO add a directive [% INCLUDE template_name %]

__all__ = ['list_templates', 'get_template', 'Template', 'TemplateSyntaxError']

def list_templates(format):
	'''Returns a dict mapping template names to file paths.'''
	templates = {}
	for dir in data_dirs('templates', format):
		for file in dir.list():
			i = file.rfind('.') # match begin of file extension
			if i >= 0:
				#~ templates[file[0:i]] = dir.file(file) FIXME
				import os
				templates[file[0:i]] = os.path.join(dir.path, file)
	return templates


def get_template(format, name):
	'''Returns a Template object.'''
	templates = list_templates(format)
	#~ if not name in templates: FIXME exception type
		#~ raise
	file = templates[name]
	return Template(file, format)


class TemplateSyntaxError(Exception):
	'''Exception used for syntax errors while parsing templates.
	Will print file path and line number together with the message.
	'''

	def __init__(self, msg):
		self.msg = msg
		self.file = '<unknown file>'
		self.line = 0

	def __str__(self):
		return 'Syntax error at "%s" line %i: %s' % \
						(self.file, self.line, self.msg)


class Template(object):
	'''Template object, maps to a single template file.'''

	def __init__(self, input, format):
		'''Constuctor takes a file path or an opened file handle and format.'''
		self.format = format
		if isinstance(input, basestring):
			self.name = input
			input = open(input)
		else:
			self.name = '<open file>'
		self.lineno = 0
		self.tokens = []
		self.stack = [ self.tokens ]
		self._parse(input)

	def process(self, page, output):
		'''Ouput 'page' to a file path or file handle using this template.'''
		if isinstance(output, basestring):
			output = open(output, 'w')

		dict = TemplateDict();
		dict['zim'] = { 'version': zim.__version__ }
		dict['page'] = PageProxy(page, self.format)

		for token in self.tokens:
			if isinstance(token, TemplateToken):
				token.process(dict, output)
			else:
				output.write(token)

	def _parse(self, input):

		def append_text(text):
			if not text: return
			if ( self.stack[-1] and
			     isinstance(self.stack[-1][-1], basestring) ):
				self.stack[-1][-1] += text
			else:
				self.stack[-1].append(text)

		def append_token(string):
			string = string.strip()
			if not string: return False
			#~ print "TOKEN >>>%s<<<" % string

			if string.startswith('IF'):
				token = IFToken(string[2:])
				self.stack[-1].append(token)
				self.stack.append(token.if_block)
			elif string.startswith('ELSE'):
				self.stack.pop()
				try:
					token = self.stack[-1][-1]
					assert isinstance(token, IFToken)
				except:
					raise TemplateSyntaxError, 'ELSE outside IF block'
				self.stack.append(token.else_block)
			elif string.startswith('FOREACH'):
				token = FOREACHToken(string[7:])
				self.stack[-1].append(token)
				self.stack.append(token.foreach_block)
			elif string.startswith('END'):
				if not len(self.stack) > 1:
					raise TemplateSyntaxError, 'END outside block'
				self.stack.pop()
			else:
				if string.startswith('SET'):
					token = SETToken(string[3:])
				elif string.startswith('GET'):
					token = GETToken(string[3:])
				elif string.find('=') >= 0:	# imlpicite SET
					token = SETToken(string)
				else:  # imlicite GET
					token = GETToken(string)
				self.stack[-1].append(token)

		try:
			for line in input:
				self.lineno += 1

				while line.find('[%') >= 0:
					(pre, sep, line) = line.partition('[%')
					(cmd, sep, line) = line.partition('%]')
					if not sep:
						raise TemplateSyntaxError, "unmatched '[%'"
					append_text(pre)
					if cmd.startswith('-'): # '[%-'
						if isinstance(self.stack[-1][-1], basestring):
							self.stack[-1][-1] = self.stack[-1][-1].rstrip()
					if cmd.endswith('-'): # '-%]'
						line = line.lstrip()
					cmd = cmd.strip('-')
					append_token(cmd)
				append_text(line)
		except TemplateSyntaxError, error:
			error.file = self.name
			error.line = self.lineno
			raise error


# Private Classes

class TemplateToken(object):

	def parse_expr(self, string):
		string = string.strip()

		def parse_list(string):
			list = []
			for i, w in enumerate(
				split_quoted_strings(string, unescape=False) ):
				if i % 2:
					if w != ',':
						raise TemplateSyntaxError, string
				elif w.startswith('"') or w.startswith("'"):
					list.append(unescape_quoted_string(w))
				else:
					list.append(TemplateParam(w))
			return list

		if string.startswith('[') and string.endswith(']'):
			# list like ['foo', 'bar', page.title]
			return parse_list(string[1:-1])
		elif string.startswith('"') or string.startswith("'"):
			# quoted string
			return unescape_quoted_string(string)
		elif string.find('(') > 0:
			# function like foo('bar', page.title)
			i = string.find('(')
			name = string[:i]
			expr = parse_list(string[i+1:-1])
			return TemplateFunction(name, expr)
		else:
			return TemplateParam(string)

	def process_expr(self, expr, dict):
		if isinstance(expr, TemplateParam):
			return dict.get_param(expr)
		elif isinstance(expr, list):
			return [self.process_expr(w, dict) for w in expr] # recurs
		elif isinstance(expr, TemplateFunction):
			args = self.process_expr(expr.expr, dict) # recurs
			return expr(args)
		else: # simple string
			return expr

	def process_block(self, dict, out, tokens):
		for token in tokens:
			if isinstance(token, TemplateToken):
				token.process(dict, out)
			else:
				out.write(token)


class GETToken(TemplateToken):

	def __init__(self, string):
		self.expr = self.parse_expr(string)

	def process(self, dict, out):
		value = self.process_expr(self.expr, dict)
		out.write(value)


class SETToken(TemplateToken):

	def __init__(self, string):
		(var, sep, val) = string.partition('=')
		if not sep:
			raise TemplateSyntaxError, string
		self.param = TemplateParam(var.strip())
		self.expr = self.parse_expr(val)


	def process(self, dict, out):
		value = self.process_expr(self.expr, dict)
		dict.set_param(self.param, value)


class IFToken(TemplateToken):

	def __init__(self, string):
		self.expr = self.parse_expr(string)
		self.if_block = []
		self.else_block = []

	def process(self, dict, out):
		value = self.process_expr(self.expr, dict)
		if value:
			self.process_block(dict, out, self.if_block)
		else:
			self.process_block(dict, out, self.else_block)


class FOREACHToken(TemplateToken):

	def __init__(self, string):
		(var, sep, val) = string.partition('=')
		if not sep:
			(var, sep, val) = string.partition('IN')
		if not sep:
			raise TemplateSyntaxError, string
		self.param = TemplateParam(var.strip())
		self.expr = self.parse_expr(val)
		self.foreach_block = []

	def process(self, dict, out):
		values = self.process_expr(self.expr, dict)
		if not isinstance(values, list):
			return # TODO warn ?
		for value in values:
			dict.set_param(self.param, value)
			self.process_block(dict, out, self.foreach_block)


class TemplateParam(object):

	param_re = re.compile('\A\w[\w]*\Z') # \w includes alnum and "_"

	def __init__(self, name):
		self.keys = name.split('.')
		for k in self.keys:
			if not self.param_re.match(k):
				raise TemplateSyntaxError, 'invalid parameter: '+name


class TemplateDict(dict):

	def get_param(self, param):
		'''Used during processing to get a template parameter'''
		assert isinstance(param, TemplateParam)
		value = self
		for key in param.keys:
			if isinstance(value, dict):
				value = value.get(key, None)
			elif isinstance(value, object):
				if hasattr(value, key):
					val = getattr(val, key)
				else:
					self._warn('No such parameter: %s' % key)
					return None
			else:
				self._warn('No such parameter: %s' % key)
				return None
		return value

	def set_param(self, param, value):
		'''Used during processing to set a parameter'''
		assert isinstance(param, TemplateParam)
		table = self
		for key in param.keys[0:-1]:
			if isinstance(table, dict):
				if not key in table:
					table[key] = {}
				table = table[key]
			else:
				self._warn('Could not set parameter: %s' % key)
				return
		if isinstance(table, dict):
			table[param.keys[-1]] = value
		else:
			self._warn('Could not set parameter: %s' % key)
			return

	def _warn(self, msg):
		import sys
		# TODO add file name and line number
		print >>sys.stderr, 'WARNING: %s' % msg
		#~ from pprint import pprint
		#~ pprint(self)


class TemplateFunction(object):

	def __init__(self, name, expr):
		if not hasattr(TemplateFunctions, name):
			raise TemplateSyntaxError, 'invalid function: '+name
		self.func = getattr(TemplateFunctions, name)
		self.expr = expr

	def __call__(self, args):
		return self.func(*args)


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
	def links(self): return [] # TODO

	@property
	def backlinks(self): return [] # TODO

	@property
	def prev(self): return None # TODO

	@property
	def next(self): return None # TODO

	@property
	def index(self): return None # TODO

	@property
	def body(self): return self._page.get_text(format=self._format)
