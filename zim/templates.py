# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains classes for template processing.

The main class is Template, which wraps and pre-compiles a template
file. Each page that can be dumped using the template is wrapped with
a PageProxy object, which exposes attributes and functions to be used
in the template. This module is most efficient when you want to dump
many pages with one template.

Usage::

	import zim.templates
	tmpl = zim.templates.get_template('html', 'Default')
	for page in notebook.get_root():
		sys.stdout.writelines( tmpl.process(page) )

Template files are expected to be in a path
XDG_DATA/zim/templates/FORMAT/

Syntax is loosely based on the syntax of the perl Template Toolkit
(U{http://template-toolkit.org}). The following syntax is supported::

	[% GET page.name %] or just [% page.name %]
	[% SET foo = 'Foo !' %] or just [ foo = 'Foo !' ]
	[% IF param %] ... [% ELSE %] ... [% END %]
	[% IF param == value %] ... [% ELSE %] ... [% END %]
	[% IF param %] ... [% ELSIF param %] ... [% ELSE %] ... [% END %]
	[% FOREACH name IN param %] ... [% name %] ... [% END %]
	or [% FOREACH name = param %] ...
	or [% FOREACH name IN ['foo', 'bar', 'baz'] %] ...
	[% strftime('%c', param) %]

Use a "[%-" instead of "[%" or "-%]" instead of "%]" will strip
newlines left or right of the tag.

Available parameters are 'zim.version' and 'page', all available
attributes for 'page' are defined in the PageProxy class.

Syntax errors in the template will cause an exception when the object
is constructed. Errors while processing a template only print warnings
to stderr (e.g. for unknown parameters).

One crucial difference with most template implementations is that we do
not trust our templates - it should be possible for non-programmers
to download that template for a fancy presentations from the Internet
without worrying whether it may delete his or her notes.
Therefore we try to minimize to possibilities to actually execute
arbitrary code from templates.

  - We only allow strings as function arguments from the template,
    no arbitrary expressions
  - Functions that are allowed to be called from the template need to be
    flagged explicitly by wrapping them in a TemplateFunction object.
  - There is no directive to evaluate code, like EVAL, PERL or PYTHON
'''

# TODO add a directive [% INCLUDE template_name %]
# TODO put token classes in a dict to allow extension by subclasses

import re
import logging
import locale

import gobject

import zim
import zim.formats
import zim.datetimetz as datetime
from zim.errors import Error
from zim.fs import File, Dir, format_file_size
from zim.config import data_dirs
from zim.parsing import Re, TextBuffer, split_quoted_strings, unescape_quoted_string, is_path_re
from zim.formats import ParseTree, Element, TreeBuilder
from zim.index import LINK_DIR_BACKWARD
from zim.notebook import Path

logger = logging.getLogger('zim.templates')

__all__ = [
	'list_templates', 'get_template', 'Template',
	'TemplateError', 'TemplateSyntaxError', 'TemplateProcessError'
]


def list_template_categories():
	'''Returns a list of categories (sub folders)'''
	dirs = data_dirs('templates')
	categories = set()
	for dir in dirs:
		for name in dir.list():
			## TODO list_objects would help here + a filter like type=Dir
			if dir.subdir(name).isdir():
				categories.add(name)

	return sorted(categories)


def list_templates(category):
	'''Returns a list of template names
	@param category: a category (sub folder) with tempaltes, e.g. "html"
	@returns: a list of 2-tuples of the template names and the file
	basename for the template file
	'''
	category = category.lower()
	templates = set()
	path = list(data_dirs(('templates', category)))
	path.reverse()
	for dir in path:
		for basename in dir.list():
			if dir.file(basename).exists(): # is a file
				name = basename.rsplit('.', 1)[0] # robust if no '.' in basename
				templates.add((name, basename))
	return sorted(templates)


def get_template(format, template):
	'''Returns a Template object for a template name, file path, or File object'''
	# NOTE: here the "category" needs to be a format at the same time !
	if isinstance(template, File):
		file = template
	else:
		if not is_path_re.match(template):
			file = None
			path = list(data_dirs(('templates', format)))
			path.reverse()
			for dir in path:
				for basename in dir.list():
					name = basename.rsplit('.')[0] # robust if no '.' in basename
					if name == template:
						file = dir.file(basename)
						if file.exists(): # is a file
							break

			if not file:
				file = File(template)
		else:
			file = File(template)

	logger.info('Loading template from: %s', file)
	if not file.exists():
		raise AssertionError, 'No such file: %s' % file

	basename, ext = file.basename.rsplit('.', 1)
	resources = file.dir.subdir(basename)

	return Template(file.readlines(), format, name=file.path, resources_dir=resources)


class TemplateError(Error):

	msg = 'Template Error'

	def __init__(self, token, error):
		self.description = self._description.strip() + '\n\n'
		if token.text:
			self.description += "Error in \"%s\" line \"%i\" at \"%s\":" % (token.file, token.lineno, token.text)
		else:
			self.description += "Error in \"%s\" line \"%i\":" % (token.file, token.lineno)
		self.description += '\n\n' + error.strip()


class TemplateSyntaxError(TemplateError):

	msg = 'Template Syntax Error'

	_description = '''\
An error occurred while parsing a template.
It seems the template contains some invalid syntax.
'''


class TemplateProcessError(TemplateError):

	msg = 'Template Processing Error'

	_description = '''\
A run-time error occurred while processing a template.
This can be e.g. due to the template calling functions that
are not available, or it can be a glitch in the program.
'''


class _TemplateManager(gobject.GObject):
	'''Singleton object used for hooking signals so plugins can be notified
	when a template is used.

	@signal: C{process-page (manager, template, page, dict)}:
	Called just before the page is processed. Plugins can extend functionality
	available to the template by putting parameters or template functions in
	'dict'. Plugins should not modify page!
	'''

	# In theory it would be better to do this without a singleton, but in that
	# case there would need to be an instance of this object per NotebookInterface
	# object. Not impossible, but not needed for now.

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'process-page': (gobject.SIGNAL_RUN_LAST, None, (object, object, object)),
	}

# Need to register classes defining gobject signals
gobject.type_register(_TemplateManager)


TemplateManager = _TemplateManager()


class GenericTemplate(object):
	'''Base template class'''

	def __init__(self, input, name=None):
		'''Constructor takes a file path or an opened file handle'''
		if isinstance(input, basestring):
			input = input.splitlines(True)
		self.file = name or '<open file>'
		self.lineno = 0
		self.text = None # needs to be set to None for use with TemplateError()
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
				token = IFToken(self.file, self.lineno, string[2:])
				self.stack[-1].append(token)
				self.stack.append(token.blocks[0])
			elif string.startswith('ELSIF'):
				self.stack.pop()
				try:
					iftoken = self.stack[-1][-1]
					assert isinstance(iftoken, IFToken)
				except:
					raise TemplateSyntaxError(self, 'ELSIF outside IF block')
				block = iftoken.add_block(string[5:])
				self.stack.append(block)
			elif string.startswith('ELSE'):
				self.stack.pop()
				try:
					iftoken = self.stack[-1][-1]
					assert isinstance(iftoken, IFToken)
				except:
					raise TemplateSyntaxError(self, 'ELSE outside IF block')
				block = iftoken.add_block()
				self.stack.append(block)
			elif string.startswith('FOREACH'):
				token = FOREACHToken(self.file, self.lineno, string[7:])
				self.stack[-1].append(token)
				self.stack.append(token.foreach_block)
			elif string.startswith('END'):
				if not len(self.stack) > 1:
					raise TemplateSyntaxError(self, 'END outside block')
				self.stack.pop()
			else:
				if string.startswith('SET'):
					token = SETToken(self.file, self.lineno, string[3:])
				elif string.startswith('GET'):
					token = GETToken(self.file, self.lineno, string[3:])
				elif self._token_re.match(string):
					raise TemplateSyntaxError(self, 'Unknown directive: %s' % self._token_re[1])
				elif string.find('=') >= 0:	# implicit SET
					token = SETToken(self.file, self.lineno, string)
				else:  # implicit GET
					token = GETToken(self.file, self.lineno, string)
				self.stack[-1].append(token)

		for line in input:
			self.lineno += 1

			while line.find('[%') >= 0:
				(pre, sep, line) = line.partition('[%')
				(cmd, sep, line) = line.partition('%]')
				if not sep:
					raise TemplateSyntaxError(self, "unmatched '[%'")
				append_text(pre)
				if cmd.startswith('-'): # '[%-'
					try:
						if isinstance(self.stack[-1][-1], basestring):
							self.stack[-1][-1] = self.stack[-1][-1].rstrip()
					except IndexError:
						pass
				if cmd.endswith('-'): # '-%]'
					line = line.lstrip()
				cmd = cmd.strip('-')
				append_token(cmd)
			append_text(line)
		if len(self.stack) > 1:
			raise TemplateSyntaxError(self, 'open block at end of input - forgot END ?')


class Template(GenericTemplate):
	'''Template class that can process a zim Page object'''

	def __init__(self, input, format, linker=None, name=None, resources_dir=None):
		if isinstance(format, basestring):
			format = zim.formats.get_format(format)
		self.format = format
		self.linker = linker
		if isinstance(resources_dir, basestring):
			self.resources_dir = Dir(resources_dir)
		else:
			self.resources_dir = resources_dir
		GenericTemplate.__init__(self, input, name)
		self.template_options = None

	def set_linker(self, linker):
		self.linker = linker

	def process(self, notebook, page, pages=None):
		'''Processes the template with a dict giving a set a standard
		parameters for 'page' and returns a list of lines.

		The attribute 'pages' can be used to supply page objects for
		special pages, like 'next', 'previous', 'index' and 'home'.
		'''
		self.template_options = {} # this dict is writable from the template and is
		             # passed on to the format

		if pages:
			mypages = pages
			pages = {}
			for key in mypages.keys():
				if not mypages[key] is None:
					pages[key] = PageProxy(
						notebook, mypages[key],
						self.format, self.linker, self.template_options)
		else:
			pages = {}

		dict = {
			'zim': { 'version': zim.__version__ },
			'notebook': {
				'name' : notebook.name,
				'interwiki': notebook.info.interwiki,
			},
			'page': PageProxy(
				notebook, page,
				self.format, self.linker, self.template_options),
			'pages': pages,
			'strftime': StrftimeFunction(),
			'strfcal': StrfcalFunction(),
			'url': TemplateFunction(self.url),
			'resource': TemplateFunction(self.resource_url),
			'pageindex' : PageIndexFunction(notebook, page, self.format, self.linker, self.template_options),
			'options': self.template_options,
			# helpers that allow to write TRUE instead of 'TRUE' in template functions
			'TRUE' : 'True', 'FALSE' : 'False',
		}

		if self.linker:
			self.linker.set_path(page)
			# this is later reset in body() but we need it here for
			# first part of the template

		TemplateManager.emit('process-page', self, page, dict)

		# Bootstrap options as user modifiable part of dictionary
		# need to assign in TempalteDict, so it goes in _user
		dict = TemplateDict(dict)
		dict[TemplateParam('options')] = self.template_options

		# Finally process the template
		output = GenericTemplate.process(self, dict)

		# Caching last processed dict because any pages in the dict
		# will be cached using a weakref dict. Assuming we process multiple
		# pages after each other, and they share links like home / previous /
		# next etc. this is a cheap optimization.
		self._last_dict = dict
		return output

	def process_to_parsetree(self, notebook, page):
		'''Like process, but returns a parse tree instead of text'''
		lines = self.process(notebook, page)
		return self.format.Parser().parse(lines)

	@staticmethod
	def url(dict, link):
		'''Static method callable from the template, returns a string'''
		if link is None:
			return ''
		elif isinstance(link, FilePathProxy):
			link = link.path
		elif isinstance(link, (File, Dir)):
			link = link.uri
		elif not isinstance(link, basestring): # Path, PageProxy
			link = ':' + link.name
		# else basestring

		linker = dict[TemplateParam('page')]._linker # bit of a hack
		if linker:
			return linker.link(link)
		else:
			return link

	def resource_url(self, dict, path):
		# Don't make the mistake to think we should use the
		# resources_dir here - that dir refers to the source of the
		# resource files, while here we want an URL for the resource
		# file *after* export
		if self.linker:
			return self.linker.resource(path)
		return path


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

	def __init__(self, file, line, text=None):
		self.file = file
		self.lineno = line
		if text is not None:
			self.text = text.strip()
			try:
				self.parse_string(self.text)
			except Error, error:
				raise TemplateSyntaxError(self, error.msg)
		else:
			self.text = None

	def parse_string(self, string):
		raise NotImplemented, 'Class %s does not take string' % self.__class__.__name__

	def parse_expr(self, string):
		'''This method parses an expression and returns an object of either
		class TemplateParam, TemplateParamList or TemplateFuntionParam.

		(All these classes have a method "evaluate()" which
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
						raise TemplateSyntaxError(self, string)
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

	def process(self, dict):
		try:
			re = self.do_process(dict)
		except TemplateError:
			raise
		except Error, error:
			raise TemplateProcessError(self, error.msg)
		except Exception:
			import traceback
			trace = traceback.format_exc()
			raise TemplateProcessError(self, trace)
		return re

	def do_process(self, dict):
		raise NotImplemented


class GETToken(TemplateToken):

	def parse_string(self, string):
		self.expr = self.parse_expr(string)

	def do_process(self, dict):
		value = self.expr.evaluate(dict)
		if value:
			return [value]
		else:
			return []


class SETToken(TemplateToken):

	def parse_string(self, string):
		(var, sep, val) = string.partition('=')
		if not sep:
			raise TemplateSyntaxError(self, string)
		self.param = TemplateParam(var.strip())
		self.expr = self.parse_expr(val)

	def do_process(self, dict):
		dict[self.param] = self.expr.evaluate(dict)
		return []


class IFToken(TemplateToken):

	def parse_string(self, string):
		self.blocks = []
		self.add_block(string)

	def add_block(self, string=None):
		self.blocks.append(TemplateTokenList())
		if not string is None:
			# IF or ELSIF block
			(var, sep, val) = string.partition('==')
			var = self.parse_expr(var)
			if sep:
				val = self.parse_expr(val)
			else:
				val = None

			self.blocks[-1].if_statement = (var, val)
		else:
			# ELSE block
			self.blocks[-1].if_statement = None

		return self.blocks[-1]

	def do_process(self, dict):
		for block in self.blocks:
			if block.if_statement is None:
				# ELSE block
				assert block == self.blocks[-1]
				return block.process(dict)
			else:
				# IF or ELSIF block
				var, val = block.if_statement
				var = var.evaluate(dict)
				if val is None:
					ok = bool(var)
				else:
					val = val.evaluate(dict)
					ok = (var == val)

				if ok:
					return block.process(dict)
				else:
					continue
		else:
			return []


class FOREACHToken(TemplateToken):

	def parse_string(self, string):
		(var, sep, val) = string.partition('=')
		if not sep:
			(var, sep, val) = string.partition('IN')
		if not sep:
			raise TemplateSyntaxError(self, string)
		self.param = TemplateParam(var.strip())
		self.expr = self.parse_expr(val)
		self.foreach_block = TemplateTokenList()

	def do_process(self, dict):
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
		key = parts.pop()
		if '[' in key:
			i = key.index('[')
			parts.append(key[:i])
			key = key[i:]

		for n in parts:
			if not self._param_re.match(n):
				raise Error, 'invalid parameter: %s' % name

		# support param["foo"] syntax for dicts
		if parts and key.startswith('[') and key.endswith(']'):
			key = unescape_quoted_string(key[1:-1])
			if key.startswith('_'):
				raise TemplateSyntaxError(self, 'invalid dictionary key in: %s' % name)
		elif not self._param_re.match(key):
			raise Error, 'invalid parameter: %s' % name
		else:
			pass

		self.path = parts
		self.key = key

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
			raise Error, 'No such function: %s' % self.name
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
		'''Constructor. Base class takes a regular function as argument
		and wraps it to beccome a template functions.
		'''
		self.function = function

	def __call__(self, dict, *args):
		'''Execute the function
		@param dict: the L{TemplateDict} for the page being processed
		@param args: the arguments supplied in the template
		'''
		return self.function(dict, *args)


class StrftimeFunction(TemplateFunction):
	'''Template function wrapper for strftime'''

	def __init__(self):
		pass

	def __call__(self, dict, format, date=None):
		format = str(format) # Needed to please datetime.strftime()
		try:
			if date is None:
				string = datetime.now().strftime(format)
			elif isinstance(date, (datetime.date, datetime.datetime)):
				string = date.strftime(format)
			else:
				raise Error, 'Not a datetime object: %s' % date
			return string.decode(locale.getpreferredencoding())
				# strftime returns locale as understood by the C api
				# unfortunately there is no guarantee we can actually
				# decode it ...
		except:
			logger.exception('Error in strftime "%s"', format)


class StrfcalFunction(TemplateFunction):
	'''Template function wrapper for strfcal'''

	def __init__(self):
		pass

	def __call__(self, dict, format, date=None):
		format = str(format) # Needed to please datetime.strftime()
		try:
			if date is None:
				date = datetime.now()
			return datetime.strfcal(format, date)
		except:
			logger.exception('Error in strftime "%s"', format)



class PageIndexFunction(TemplateFunction):
	'''Template function to build a page menu'''

	def __init__(self, notebook, page, format, linker, options):
		self._notebook = notebook
		self._page = page
		self._format = format
		self._linker = linker
		self._options = options

	def __call__(self, dict, root=':', collapse=True, ignore_empty=True):
		builder = TreeBuilder()

		collapse = bool(collapse) and not collapse == 'False'
		ignore_empty = bool(ignore_empty) and not ignore_empty == 'False'

		if isinstance(root, PageProxy):
			# allow [% menu(page) %] vs [% menu(page.name) %]
			root = root.name

		expanded = [self._page] + list(self._page.parents())

		def add_namespace(path):
			builder.start('ul')

			pagelist = self._notebook.index.list_pages(path)
			for page in pagelist:
				if ignore_empty and not page.exists():
					continue
				builder.start('li')

				if page == self._page:
					# Current page is marked with the strong style
					builder.start('strong', {'_class': 'activepage'}) # HACK - used by Html output
					builder.data(page.basename)
					builder.end('strong')
				else:
					# links to other pages
					builder.start('link', {'type': 'page', 'href': ':'+page.name})
					builder.data(page.basename)
					builder.end('link')

				builder.end('li')
				if page.haschildren:
					if collapse:
						# Only recurs into namespaces that are expanded
						if page in expanded:
							add_namespace(page) # recurs
					else:
						add_namespace(page) # recurs

			builder.end('ul')

		builder.start('page')
		add_namespace(Path(root))
		builder.end('page')

		tree = ParseTree(builder.close())
		if not tree:
			return None

		#~ print "!!!", tree.tostring()

		format = self._format
		linker = self._linker

		dumper = format.Dumper(
			linker=linker,
			template_options=self._options )

		return ''.join(dumper.dump(tree))


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

	def __init__(self, notebook, page, format, linker, options):
		'''Constructor takes the page object to expose and a format.'''
		# private attributes should be shielded by the template engine
		self._page = page
		self._notebook = notebook
		self._format = format
		self._linker = linker
		self._options = options
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
	def content(self): return self._treeproxy().content

	@property
	def parts(self): return None # TODO split in parts and return ParseTreeProxy objects

	@property
	def has_links(self):
		return len(list(self._page.get_links())) > 0

	@property
	def links(self):
		for type, name, _ in self._page.get_links():
			if type == 'page':
				try:
					path = self._notebook.resolve_path(name, self._page)
					if path:
						page = self._notebook.get_page(path)
						yield PageProxy(
							self._notebook, page,
							self._format, self._linker, self._options)
				except:
					logger.exception('Error while exporting')

	@property
	def has_backlinks(self):
		return len(list(self._notebook.index.list_links(self._page, LINK_DIR_BACKWARD))) > 0

	@property
	def backlinks(self):
		blinks = self._notebook.index.list_links(self._page, LINK_DIR_BACKWARD)
		for link in blinks:
			source = self._notebook.get_page(link.source)
			yield PageProxy(self._notebook, source, self._format, self._linker, self._options)

	@property
	def has_attachments(self):
		return len(list(self._notebook.get_attachments_dir(self._page).list())) > 0

	@property
	def attachments(self):
		dir = self._notebook.get_attachments_dir(self._page)
		for basename in dir.list():
			yield FilePathProxy(dir.file(basename), "./"+basename)


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
			if linker:
				linker.set_path(self._pageproxy._page)

			dumper = format.Dumper(
				linker=linker,
				template_options=self._pageproxy._options )

			return ''.join(dumper.dump(body))

	@property
	def content(self):
		if not self._tree:
			return None
		else:
			return self._dump(self._tree)

	def _split_head(self, tree):
		if not hasattr(self, '_servered_head'):
			elements = tree.getroot().getchildren()
			if elements and elements[0].tag == 'h':
				root = Element('zim-tree')
				for element in elements[1:]:
					root.append(element)
				body = ParseTree(root)
				self._servered_head = (elements[0].text, body)
			else:
				self._servered_head = (None, tree)

		return self._servered_head

	def _dump(self, tree):
		format = self._pageproxy._format
		linker = self._pageproxy._linker
		if linker:
			linker.set_path(self._pageproxy._page)

		dumper = format.Dumper(
			linker=linker,
			template_options=self._pageproxy._options )

		return ''.join(dumper.dump(tree))


class FilePathProxy(object):
	'''Proxy for L{File} and L{Dir} objects'''

	# Keep in mind that "path" can refer to attachment in
	# actual notebook, but after export we should refer to
	# new copy of that item.
	# So do not allow "file.uri", but use "url(file)" instead

	def __init__(self, path, href=None):
		self._path = path
		self._href = href

	@property
	def path(self):
		return self._href or self._path.user_path()

	@property
	def basename(self):
		return self._path.basename

	@property
	def mtime(self):
		return datetime.datetime.fromtimestamp(float(self._href.mtime()))

	@property
	def size(self):
		return format_file_size(self._path.size())
