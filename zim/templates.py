# -*- coding: utf-8 -*-

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
		sys.stdout.writelines( tmpl.process(page) )

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

One crucial difference with most template imlpementations is that we do
not trust our templates - it should be possible for non-programmers
to download that template for a fancy presentations from the internet
without worrying whether it may delete his or her notes.
Therefore we try to minimize to possibilities to actually execute
arbitrary code from templates.

* We only allow strings as function arguments from the tempalte,
  no arbitrary expressions
* Functions that are allowed to be called from the template need to be
  flagged explicitely by wrapping them in a TemplateFunction object.
* There is no directive to evaluate code, like EVAL, PERL or PYTHON
'''

# TODO pages.previous, pages.next, pages.home and pages.index
# TODO add a directive [% INCLUDE template_name %]
# TODO put token classes in a dict to allow extension by subclasses
# TODO give plugins a way to access the TemplateDict before processing a page

import re
import logging
from time import strftime, strptime

import zim
import zim.formats
from zim.errors import Error
from zim.fs import File
from zim.config import data_dirs
from zim.parsing import Re, TextBuffer, split_quoted_strings, unescape_quoted_string, is_path_re
from zim.formats import ParseTree, Element
from zim.index import LINK_DIR_BACKWARD

logger = logging.getLogger('zim.templates')

__all__ = [
	'list_templates', 'get_template', 'Template',
	'TemplateError', 'TemplateSyntaxError', 'TemplateProcessError'
]


def list_templates(format):
	'''Returns a dict mapping template names to file paths.'''
	format = format.lower()
	templates = {}
	path = list(data_dirs(('templates', format)))
	path.reverse()
	for dir in path:
		for file in dir.list():
			i = file.rfind('.') # match begin of file extension
			if i >= 0:
				#~ templates[file[0:i]] = dir.file(file) FIXME
				import os
				templates[file[0:i]] = os.path.join(dir.path, file)
	return templates


def get_template(format, name):
	'''Returns a Template object for a tempalte name or a file path'''
	if is_path_re.match(name):
		file = File(name)
	else:
		templates = list_templates(format)
		#~ if not name in templates: FIXME exception type
			#~ raise
		file = File(templates[name])
	logger.info('Loading template from: %s', file)
	return Template(file.readlines(), format, name=file)


class TemplateError(Error):
	pass


class TemplateSyntaxError(TemplateError):

	description = '''\
An error occcured while parsing a template.
It seems the template contains some invalid syntax.
'''


	def __init__(self, msg):
		self._msg = msg
		self.file = '<unknown file>'
		self.line = 0

	@property
	def msg(self):
		return 'Syntax error at "%s" line %i: %s' % \
						(self.file, self.line, self.msg)


class TemplateProcessError(TemplateError):

	description = '''
A run-time error occured while processing a template.
This can be due to the template calling functions that are
not availabel, or it can be a glitch in the program.
'''


class GenericTemplate(object):
	'''Base template class'''

	def __init__(self, input, name=None):
		'''Constuctor takes a file path or an opened file handle'''
		if isinstance(input, basestring):
			input = input.splitlines(True)
		self.name = name or '<open file>'
		self.lineno = 0
		self.tokens = TemplateTokenList()
		self.stack = [ self.tokens ]
		self._parse(input)

	def process(self, dict):
		'''Processes the template and returns a list of lines.
		The dict is used to get / set template parameters.
		'''
		if not isinstance(dict, TemplateDict):
			dict = TemplateDict(dict)

		output = TextBuffer(self.tokens.process(dict))
		return output.get_lines()

	_token_re = Re(r'^([A-Z]+)(\s|$)')

	def _parse(self, input):
		'''Read the template and build a list with tokens'''

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
				elif self._token_re.match(string):
					raise TemplateSyntaxError, 'Unknown directive: %s' % self._token_re[1]
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
			if len(self.stack) > 1:
				raise TemplateSyntaxError, 'open block at end of input - forgot END ?'
		except TemplateSyntaxError, error:
			error.file = self.name
			error.line = self.lineno
			raise error


class Template(GenericTemplate):
	'''Template class that can process a zim Page object'''

	def __init__(self, input, format, linker=None, name=None):
		if isinstance(format, basestring):
			format = zim.formats.get_format(format)
		self.format = format
		self.linker = linker
		GenericTemplate.__init__(self, input, name)

	def set_linker(self, linker):
		self.linker = linker

	def process(self, notebook, page):
		'''Processes the template with a dict giving a set a standard
		parameters for 'page' and returns a list of lines.
		'''
		dict = {
			'zim': { 'version': zim.__version__ },
			'page': PageProxy(notebook, page, self.format, self.linker),
			'strftime': TemplateFunction(self.strftime),
			'url': TemplateFunction(self.url)
		}
		output = GenericTemplate.process(self, dict)

		# Caching last processed dict because any pages in the dict
		# will be cached using a weakref dict. Assuming we process multiple
		# pages after each other, and they share links like home / previous /
		# next etc. this will is a cheap optimization.
		self._last_dict = dict
		return output

	def process_to_parsetree(self, notebook, page):
		'''Like process, but returns a parse tree instead of text'''
		lines = self.process(notebook, page)
		return self.format.Parser().parse(lines)

	@staticmethod
	def strftime(dict, format, timestamp=None):
		'''Static method callable from the template, returns a string'''
		if timestamp is None:
			return strftime(format)
		elif isinstance(timestamp, basestring):
			# TODO generalize this - now hardcoded for Calendar plugin
			match = re.search(r'\d{4}:\d{2}:\d{2}', timestamp)
			if match:
				timestamp = strptime(match.group(0), '%Y:%m:%d')
				return strftime(format, timestamp)
			else:
				return None
		else:
			return strftime(format, timestamp)

	@staticmethod
	def url(dict, pagename):
		'''Static method callable from the template, returns a string'''
		return pagename # FIXME page to url function


class TemplateTokenList(list):
	'''This class contains a list of TemplateToken objects and strings'''

	def process(self, dict):
		'''Recursively calls "process()" on the TemplateToken objects
		and prints out any strings in the list.
		'''
		output = []
		for token in self:
			if isinstance(token, TemplateToken):
				output.extend(token.process(dict))
			else:
				output.append(token)

		return output


class TemplateToken(object):

	def parse_expr(self, string):
		'''This method parses an expression and returns an object of either
		class TemplateParam, TemplateParamList or TemplateFuntionParam or
		a simple string. (All these classes have a method "evaluate()" which
		takes an TemplateDict as argument and returns a value for the result
		of the expression.)
		'''
		string = string.strip()

		def parse_list(string):
			list = TemplateParamList()
			for i, w in enumerate(
				split_quoted_strings(string, unescape=False) ):
				if i % 2:
					if w != ',':
						raise TemplateSyntaxError, string
				elif w.startswith('"') or w.startswith("'"):
					list.append(TemplateLiteral(unescape_quoted_string(w)))
				else:
					list.append(TemplateParam(w))
			return list

		if string.startswith('[') and string.endswith(']'):
			# list like ['foo', 'bar', page.title]
			return parse_list(string[1:-1])
		elif string.startswith('"') or string.startswith("'"):
			# quoted string
			return TemplateLiteral(unescape_quoted_string(string))
		elif string.find('(') > 0:
			# function like foo('bar', page.title)
			i = string.find('(')
			name = string[:i]
			args = parse_list(string[i+1:-1])
			return TemplateFunctionParam(name, args)
		else:
			return TemplateParam(string)


class GETToken(TemplateToken):

	def __init__(self, string):
		self.expr = self.parse_expr(string)

	def process(self, dict):
		value = self.expr.evaluate(dict)
		if value:
			return [unicode(value).encode('utf-8')]
		else:
			return []


class SETToken(TemplateToken):

	def __init__(self, string):
		(var, sep, val) = string.partition('=')
		if not sep:
			raise TemplateSyntaxError, string
		self.param = TemplateParam(var.strip())
		self.expr = self.parse_expr(val)

	def process(self, dict):
		dict[self.param] = self.expr.evaluate(dict)
		return []


class IFToken(TemplateToken):

	def __init__(self, string):
		(var, sep, val) = string.partition('==')
		self.expr = self.parse_expr(var)
		if sep:
			self.val = self.parse_expr(val)
		else:
			self.val = None
		self.if_block = TemplateTokenList()
		self.else_block = TemplateTokenList()

	def process(self, dict):
		var = self.expr.evaluate(dict)
		if not self.val is None:
			val = self.val.evaluate(dict)
			bool = var == val
		else:
			bool = var

		if bool:
			return self.if_block.process(dict)
		else:
			return self.else_block.process(dict)


class FOREACHToken(TemplateToken):

	def __init__(self, string):
		(var, sep, val) = string.partition('=')
		if not sep:
			(var, sep, val) = string.partition('IN')
		if not sep:
			raise TemplateSyntaxError, string
		self.param = TemplateParam(var.strip())
		self.expr = self.parse_expr(val)
		self.foreach_block = TemplateTokenList()

	def process(self, dict):
		values = self.expr.evaluate(dict)
		# FIXME how to check if values is iterable ?
		output = []
		for value in values:
			dict[self.param] = value
			output.extend(self.foreach_block.process(dict))

		return output

class TemplateLiteral(unicode):

	def evaluate(self, dict):
		return self


class TemplateParam(object):
	'''Template params are namespaces using '.' as separator. This class maps
	a parameter name to a tuple reflecting this namespace path. Used in
	combination with TemplateDict to do get / set parameters from the
	template. This class also enforces that parameter names only contain
	alphanumeric characters and none of the path elements starts with a "_".
	'''

	# Tried to subclass directly from tuple, but seems it is not
	# possible to set the value of the tuple from __init__, see used
	# the 'path' attribute instead

	_param_re = re.compile('\A[^_\W][\w]*\Z')
		# matches names that do not start with '_'

	def __init__(self, name):
		self.name = name
		parts = name.split('.')
		for n in parts:
			if not self._param_re.match(n):
				raise TemplateSyntaxError, 'invalid parameter: %s' % name
		self.path = parts[:-1]
		self.key = parts[-1]

	def __str__(self):
		return self.name

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.name)

	def evaluate(self, dict):
		return dict[self]


class TemplateFunctionParam(TemplateParam):

	def __init__(self, name, args):
		TemplateParam.__init__(self, name)
		assert isinstance(args, TemplateParamList)
		self.args = args

	def evaluate(self, dict):
		func = dict[self]
		args = self.args.evaluate(dict)
		if not isinstance(func, TemplateFunction):
			raise TemplateProcessError, 'No such function: %s' % self.name
		return func(dict, *args)


class TemplateParamList(list):

	def evaluate(self, dict):
		values = []
		for item in self:
			if isinstance(item, (TemplateParam, TemplateParamList)):
				values.append(item.evaluate(dict))
			else: # simple string
				values.append(item)
		return values


class TemplateFunction(object):
	'''Wrapper for a callable, all functions stored in the template dict
	need to be stored wrapped in this class. This prevents the template
	from executing functions that are not explicitly cleared as being
	callable from the template. Template functions are called with the
	TemplateDict as first argument, followed by whatever arguments were
	given in the template.
	'''

	def __init__(self, function):
		self.function = function

	def __call__(self, *args):
		return self.function(*args)


class TemplateDict(object):
	'''Object behaving like a dict for storing values of template parameters.
	It is initialized with a nested structure of dicts and objects which
	contains the data used to fill in the template. When a lookup is done
	using a TemplateParam object as key it uses the path to lookup the value
	by going recursively through the nested data structures.
	When a value is assigned to this dict it is stored in a separate data
	structure, so the initial data structure is never overwritten. For
	subsequent lookups the both data structures are checked so they look like
	a single structure. This behavior should shield any internal structures
	from being overwritten from a template.
	'''

	def __init__(self, defaults=None):
		self._default = defaults or {}
		self._user = {}

	def _lookup_branch(self, root, param, vivicate=False):
		# recursive lookup a dict or object
		branch = root
		for name in param.path:
			if isinstance(branch, dict):
				if name in branch:
					branch = branch[name]
				elif vivicate:
					branch[name] = {}
					branch = branch[name]
				else:
					return None
			elif isinstance(branch, object):
				# do not use hasattr here - it silences exceptions
				try:
					branch = getattr(branch, name)
				except AttributeError:
					return None
			else:
				return None
		return branch

	def _lookup_key(self, root, param):
		branch = self._lookup_branch(root, param)
		if branch is None:
			return None
		elif isinstance(branch, dict):
			if param.key in branch:
				return branch[param.key]
		elif isinstance(branch, object):
			# do not use hasattr here - it silences exceptions
			try:
				return getattr(branch, param.key)
			except AttributeError:
				pass
		return None

	def __getitem__(self, param):
		assert isinstance(param, TemplateParam)
		item = self._lookup_key(self._user, param)
		if item is None:
			item = self._lookup_key(self._default, param)
		return item

	def __setitem__(self, param, value):
		assert isinstance(param, TemplateParam)
		user = self._lookup_branch(self._user, param, vivicate=True)
		user[param.key] = value


class PageProxy(object):
	'''Exposes a single page object to the template.'''

	def __init__(self, notebook, page, format, linker):
		'''Constructor takes the page object to expose and a format.'''
		# private attributes should be shielded by the template engine
		self._page = page
		self._notebook = notebook
		self._format = format
		self._linker = linker
		self._treeproxy_obj = None

	def _treeproxy(self):
		if self._treeproxy_obj is None:
			self._treeproxy_obj = \
				ParseTreeProxy(self._page.get_parsetree(), self)
		return self._treeproxy_obj

	@property
	def properties(self): return self._page.properties

	@property
	def name(self): return self._page.name

	@property
	def basename(self): return self._page.basename

	@property
	def namespace(self): return self._page.namespace

	@property
	def title(self): return self.heading or self._page.basename

	@property
	def heading(self): return self._treeproxy().heading

	@property
	def body(self):	return self._treeproxy().body

	@property
	def parts(self): return None # TODO split in parts and return ParseTreeProxy obejcts

	@property
	def links(self):
		for type, name, _ in self._page.get_links():
			if type == 'page':
				page = self._notebook.get_page(name)
				yield PageProxy(self._notebook, page, self._format, self._linker)

	@property
	def backlinks(self):
		blinks = self._notebook.index.list_links(self._page, LINK_DIR_BACKWARD)
		#~ for link in blinks:
		#~	page = self._notebook.get_page(link.href)
		#~	yield PageProxy(self._notebook, page)


class ParseTreeProxy(object):

	def __init__(self, tree, pageproxy):
		self._tree = tree
		self._pageproxy = pageproxy

	@property
	def heading(self):
		if not self._tree:
			return None
		else:
			head, body = self._split_head(self._tree)
			return head

	@property
	def body(self):
		if not self._tree:
			return None
		else:
			head, body = self._split_head(self._tree)
			format = self._pageproxy._format
			linker = self._pageproxy._linker
			linker.set_path(self._pageproxy._page)
			return ''.join(format.Dumper(linker=linker).dump(body))

	def _split_head(self, tree):
		if not hasattr(self, '_servered_head'):
			elements = tree.getroot().getchildren()
			if elements[0].tag == 'h':
				root = Element('zim-tree')
				for element in elements[1:]:
					root.append(element)
				body = ParseTree(root)
				self._servered_head = (elements[0].text, body)
			else:
				self._servered_head = (None, tree)

		return self._servered_head
