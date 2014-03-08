# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO merge classes include here back into parser.py

# TODO Split out in sub modules
#	templates/__init__.py		# Template & build_template()
#	templates/parser.py			# TemplateParser and TemplateTreeBuilder
#	templates/expressionparser.py
#	templates/expression.py		# TemplateExpression, param dict etc.
#	templates/functions.py		# strftime etc.

# TODO for properties dict, translate keys into valid param names (replace('-', '_'))
#      need PageProxy for those kind of things

# TODO for "days" property in calendar plugin, add arguments to set
# first and last day -- allow selecting work week only etc.

# TODO specific exception classes for errors in template parsing
#      and execution + report line & char in errors

# TODO add "DEFAULT" and "CALL" directives

# TODO add "and" and "or" keywords for expression
#      allow e.g. "IF loop.first and loop.last" to detect single page

########

import re
import collections

from zim.parser import Parser, Rule, SimpleTreeBuilder


# Supported sytax
#   [% .. %] and <!--[% .. %]-->
#
# Instructions:
#   GET
#   SET
#   IF expr EL(S)IF expr .. ELSE .. END
#   FOR var IN expr .. END
#   FOREACH var = expr ... END
#   FOREACH var IN expr ... END
#   BLOCK name .. END
#   INCLUDE name or expr -- block or file
#
# Expressions can be:
#	True, False, None
#   "string", 'string', 5, 5.0
#   [.., .., ..]
#	parameter.name, mylist.0
#	function(.., ..)
#	.. operator ..
#
# Operators can be:
#	==, !=, >, >=, <, <=
#
# Note that BLOCKS are always defined in the top level scope
# so you not have them e.g. in an IF clause to define alternative versions.
# BLOCKS may be defined after the location where they are used.
#
# Within a loop, special parameter "loop" is defined with following
# attributes:
# 	loop.first		True / False
# 	loop.last		True / False
# 	loop.parity		"even" or "odd"
# 	loop.even		True / False
# 	loop.odd		True / False
#	loop.size		n
#	loop.max		n-1
#	loop.index		0 .. n-1
# 	loop.count		1 .. n
# 	loop.outer		outer "loop" or None
#	loop.prev		previous item or None
#	loop.next		next item or None

# Document:
# * all of the above
# * that we follow template toolkit syntax, but not full implementation
#   and especially not perl style implicite behavior
#   e.g. calling methods without ()
#   or calling methods by assigning with "="
# * valid param names
# * internal functions - TODO strftime / html_encode / url_encode / ...
# * methods callable on string / dict / list


################# BUILDER ###################################

class SimpleTreeElement(list):

	# Not unlike the Element class of xml.etree, but without the
	# "text" and "tail" attributes - text is just part of the list.
	# This makes processing so much easier...

	__slots__ = ('tag', 'attrib')

	def __init__(self, tag, attrib=None, children=None):
		self.tag = tag
		self.attrib = attrib
		if children:
			self.extend(children)

	def get(self, attr, default=None):
		if self.attrib:
			return self.attrib.get(attr, default)
		else:
			return None

	def __eq__(self, other):
		if self.tag == other.tag \
		and self.attrib == other.attrib \
		and len(self) == len(other):
			return all(s == o for s, o in zip(self, other))
		else:
			return False

	def __repr__(self):
		if len(self) > 0:
			return '<%s:\n%s>' % (self.__class__.__name__, self.pprint(level=1))
		else:
			return '<%s: %s>' % (self.__class__.__name__, self.pprint(level=0).strip())

	def __str__(self):
		return self.__repr__()

	def pprint(self, level=0):
		prefix = '  ' * level
		if len(self) > 0:
			lines = [prefix + '%s %r [\n' % (self.tag, self.attrib)]
			for item in self:
				if isinstance(item, SimpleTreeElement):
					lines.append(item.pprint(level=level+1))
				elif isinstance(item, basestring):
					for line in item.splitlines(True):
						lines.append(prefix + '  %r\n' % line)
				else:
					lines.append(prefix + '  %r\n' % item)
			lines.append(prefix + ']\n')
			return ''.join(lines)
		else:
			return prefix + '%s %r []\n' % (self.tag, self.attrib)


# TODO move this class to parser, and remove merging from SimpleTreeBuilder
from zim.parser import Builder
class BuilderTextBuffer(Builder):
	'''Wrapper that buffers text going to a L{Builder} object
	such that last piece of text remains accesible and can be modified.
	'''

	def __init__(self, builder):
		self.builder = builder
		self.buffer = []

	def get_text(self):
		return u''.join(self.buffer)

	def set_text(self, text):
		self.buffer = [text]

	def clear_text(self):
		self.buffer = []

	def flush(self):
		text = u''.join(self.buffer)
		if text:
			self.builder.text(text)
		self.buffer = []

	def start(self, tag, attrib=None):
		if self.buffer:
			self.flush()
		self.builder.start(tag, attrib)

	def end(self, tag):
		if self.buffer:
			self.flush()
		self.builder.end(tag)

	def text(self, text):
		self.buffer.append(text)

	def append(self, tag, attrib=None, text=None):
		if self.buffer:
			self.flush()
		self.builder.append(tag, attrib, text)


## TODO replace SimpleTreeBuilder with this implementation
class MySimpleTreeBuilder(Builder):
	'''Like L{SimpleTreeBuilder} but uses L{TempalteElement} instead
	of plain tuple
	'''

	def __init__(self, elementfactory=SimpleTreeElement):
		self.elementfactory = elementfactory
		self.root = []
		self.stack = [self.root]
		self.merge_text = False

	def get_root(self):
		if not len(self.stack) == 1:
			raise AssertionError('Did not finish processing')
		return self.root

	def start(self, tag, attrib=None):
		element = self.elementfactory(tag, attrib)
		self.stack[-1].append(element)
		self.stack.append(element)

	def end(self, tag):
		element = self.stack.pop()
		if element.tag != tag:
			raise AssertionError, 'Expected %s got %s' % (element.tag, tag)

	def text(self, text):
		self.stack[-1].append(text)

	def append(self, tag, attrib=None, text=None):
		element = self.elementfactory(tag, attrib)
		if text:
			element.append(text)
		self.stack[-1].append(element)



######################## EXPRESSION ######################


# Expression evaluation is done without using a real python eval to
# keep it safe from arbitrary code execution
#
# Both parameter values and functions are stored in a dict that is
# passed to the Expression object when it is executed. The expressions
# should not allow access to anything outside this dict, and only
# sane access to objects reachable from this dict.
#
# Parameter lookup gets list and dict items as well as object attributes.
# It does not allow accessing private attributes (starting with "_")
# or or code objects (object method of function) - callable objects on
# the other hand can be accessed.
#
# We control execution by only executing functions that are specifically
# whitelisted as being an ExpressionFunction (can be used as decorator).
# The expression classes have builtin support for some builtin methods
# on strings, lists and dicts (see L{ExpressionString},
# L{ExpressionDict} and L{ExpressionList} respectively), other functions
# can be supplied in the context dict or as object attributes.
#
# The biggest risks would be to put objects in the dict that allow
# access to dangerous methods or private data. Or to have functions
# that e.g. eval one of their arguments or take a callable argument
#
# The idea is that objects in the expression dict are proxies that
# expose a sub set of the full object API and template friendly methods.
# These restrictions hsould help to minimize risk of arbitrary code
# execution in expressions.

import inspect
import operator
import ast


class ExpressionSyntaxError(Exception):
	pass


class ExpressionParser(object):

	# This parser does not use the Parser / Builder architecture
	# as the expression format is not really suited for this kind
	# of block parser
	# Instead it is a simple parser that first splits text in tokens
	# and then consumes those tokens left-to-right while building
	# an object tree.

	# TODO keep character count to raise meaninful errors

	# Operator precedence: or -- and -- not -- <, <=, >, >=, <>, !=, ==
	operators = {
		'==':	operator.eq,
		'!=':	operator.ne,
		'>':	operator.gt,
		'>=':	operator.ge,
		'<':	operator.lt,
		'<=':	operator.le,
		'and':	operator.and_,
		'or':	operator.or_,
		'not':	operator.not_, # special case - unary operator
	}

	tokens = [',', '[', ']', '(', ')'] \
		+ [k for k in operators.keys() if not k.isalnum()]
		# Only inluding NON-alphanumeric operators here

	_param_re = re.compile(r'^[^\W\d_]\w*(\.[^\W_]\w*)*$')
		# like "name.name" but first char can not be "_"
		# digits are allowed after dot, since template assumes dot notation for list index as well..
		# FIXME for generic use make this configurable / subclass template specific version

	def __init__(self):
		tokens = map(re.escape, self.tokens)
		self._word_re = re.compile(
			r'''(
				'(\\'|[^'])*' |  # single quoted word
				"(\\"|[^"])*" |  # double quoted word
				[^\s'"%s]+    |  # word without spaces and token chars
				%s               # tokens are a word on their own
			)''' % (''.join(tokens), '|'.join(tokens)), re.X
		)

	def parse(self, string):
		tokens = self._tokenize(string)
		expr = self._parse(tokens)
		if tokens: # trailing stuff remaining
			raise ExpressionSyntaxError, 'Unexpected text after expression: %s' % tokens
		return expr

	def _tokenize(self, string):
		# custom version of split_quoted_strings
		string = string.strip()
		words = []
		m = self._word_re.match(string)
		while m:
			words.append(m.group(0))
			i = m.end()
			string = string[i:].lstrip()
			m = self._word_re.match(string)

		assert not string, '>> %s' % string
		return words

	def _parse(self, tokens):
		# Operator precedence: or, and, not, <, <=, >, >=, <>, !=, ==
		# so we start with parsing " ... or .. or .." and decent from there
		lexpr = self._parse_and(tokens)
		if tokens and tokens[0] == 'or':
			tokens.pop(0)
			rexpr = self._parse(tokens) # recurs
			return ExpressionOperator(operator.or_, lexpr, rexpr)
		else:
			return lexpr

	def _parse_and(self, tokens):
		# Handle "... and ... and ..."
		lexpr = self._parse_not(tokens)
		if tokens and tokens[0] == 'and':
			tokens.pop(0)
			rexpr = self._parse_and(tokens) # recurs
			return ExpressionOperator(operator.and_, lexpr, rexpr)
		else:
			return lexpr

	def _parse_not(self, tokens):
		# Handle "not ..."
		if not tokens:
			raise ExpressionSyntaxError, 'Unexpected end of expression'
		if tokens[0] == 'not':
			tokens.pop(0)
			rexpr = self._parse_comparison(tokens)
			return ExpressionUnaryOperator(operator.not_, rexpr)
		else:
			return self._parse_comparison(tokens)

	def _parse_comparison(self, tokens):
		# Handle "... op ..." where op is: <, <=, >, >=, <>, !=, ==
		lexpr = self._parse_statement(tokens)
		if tokens and tokens[0] in self.operators \
		and tokens[0] not in ('or', 'and', 'not'):
			op = tokens.pop(0)
			rexpr = self._parse_statement(tokens)
			return ExpressionOperator(self.operators[op], lexpr, rexpr)
		else:
			return lexpr

	def _parse_statement(self, tokens):
		# Handle: param, func call or literal
		if not tokens:
			raise ExpressionSyntaxError, 'Unexpected end of expression'
		if tokens[0] == '[':
			return self._parse_list(tokens)
		elif tokens[0] in self.tokens \
		or tokens[0] in ('or', 'and', 'not'):
			raise ExpressionSyntaxError, 'Unexpected token: "%s"' % tokens[0]
		elif self._param_re.match(tokens[0]) \
		and not tokens[0] in ('True', 'False', 'None'):
			param = ExpressionParameter(tokens.pop(0))
			if tokens and tokens[0] == '(':
				args = self._parse_list(tokens)
				return ExpressionFunctionCall(param, args)
			else:
				return param
		else:
			text = tokens.pop(0)
			try:
				value = ast.literal_eval(text)
			except SyntaxError:
				raise ExpressionSyntaxError, 'Invalid literal: %s' % text
			else:
				return ExpressionLiteral(value)

	def _parse_list(self, tokens):
		# Process left to right, allow descending in sub lists
		assert tokens[0] in ('[', '(')
		delim = ']' if tokens.pop(0) == '[' else ')'
		expr = ExpressionList()
		while tokens and tokens[0] != delim:
			item = self._parse(tokens)
			if tokens and tokens[0] != delim:
				if tokens.pop(0) != ',':
					raise ExpressionSyntaxError, 'Expected: ","'
			expr.append(item)

		if not tokens or tokens[0] != delim:
			raise ExpressionSyntaxError, 'Missing: "%s"' % delim
		else:
			tokens.pop(0)

		return expr


class Expression(object):

	__slots__ = ()

	def __call__(self, dict):
		raise NotImplementedError

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.pprint())

	def __str__(self):
		return self.pprint()

	def pprint(self):
		raise NotImplemented


class ExpressionLiteral(Expression):

	__slots__ = ('value',)

	def __init__(self, value):
		self.value = value

	def __eq__(self, other):
		return self.value == other.value

	def __call__(self, dict):
		return self.value

	def pprint(self):
		return repr(self.value)


class ExpressionParameter(Expression):

	__slots__ = ('name', 'parts', 'key')

	def __init__(self, name):
		self.name = name
		self.parts = name.split('.')
		if any(n.startswith('_') for n in self.parts):
			raise ValueError, 'Invalid parameter name: %s' % name

		for i in range(len(self.parts)):
			try:
				self.parts[i] = int(self.parts[i])
			except ValueError:
				pass

		self.key = self.parts[-1]

	def __eq__(self, other):
		return isinstance(other, ExpressionParameter) \
				and self.name == other.name

	def __call__(self, context):
		value = context
		for i, p in enumerate(self.parts):
			try:
				try:
					value = value[p]
				except TypeError:
					# not indexable, or wrong key type - try getattr
					value = getattr(value, p)
			except (IndexError, KeyError, AttributeError):
				# We got right type, but data is not there
				raise AssertionError, 'No such parameter: %s' % '.'.join(map(str, self.parts[:i+1]))

			if inspect.ismethod(value) \
			or inspect.isfunction(value) \
			or inspect.isbuiltin(value):
				raise AssertionError, 'Can not access parameter: %s' % self.name

		return value

	@property
	def parent(self):
		'''Returns a C{ExpressionParameter} for the parent object.
		Used e.g. to find the parent scope for assignment.
		'''
		if len(self.parts) > 1:
			return ExpressionParameter('.'.join(map(str, self.parts[:-1])))
		else:
			return lambda d: d # HACK - define proper class for root namespace

	def pprint(self):
		return 'PARAM(%s)' % self.name


class ExpressionList(Expression):

	__slots__ = ('items',)

	def __init__(self, items=None):
		if items:
			self.items = list(items)
			assert all(isinstance(item, Expression) for item in self.items)
		else:
			self.items = []

	def __eq__(self, other):
		return self.items == other.items

	def __call__(self, dict):
		return [item(dict) for item in self.items]

	def append(self, item):
		assert isinstance(item, Expression)
		self.items.append(item)

	def pprint(self):
		return '[' + ', '.join(map(str, self.items)) + ']'


class ExpressionOperator(Expression):

	__slots__ = ('operator', 'lexpr', 'rexpr')

	def __init__(self, operator, lexpr, rexpr):
		assert isinstance(lexpr, Expression)
		assert isinstance(rexpr, Expression)
		self.operator = operator
		self.lexpr = lexpr
		self.rexpr = rexpr

	def __eq__(self, other):
		return (self.operator, self.lexpr, self.rexpr) == (other.operator, other.lexpr, other.rexpr)

	def __call__(self, dict):
		lvalue = self.lexpr(dict)
		rvalue = self.rexpr(dict)
		return self.operator(lvalue, rvalue)

	def pprint(self):
		return 'OP(%s, %s, %s)' % (self.operator.__name__, self.lexpr, self.rexpr)


class ExpressionUnaryOperator(Expression):

	__slots__ = ('operator', 'rexpr')

	def __init__(self, operator, rexpr):
		assert isinstance(rexpr, Expression)
		self.operator = operator
		self.rexpr = rexpr

	def __eq__(self, other):
		return (self.operator, self.rexpr) == (other.operator, other.rexpr)

	def __call__(self, dict):
		rvalue = self.rexpr(dict)
		return self.operator(rvalue)

	def pprint(self):
		return 'OP(%s, %s)' % (self.operator.__name__, self.rexpr)


class ExpressionFunctionCall(Expression):

	__slots__ = ('param', 'args')

	def __init__(self, param, args):
		assert isinstance(param, ExpressionParameter)
		assert isinstance(args, ExpressionList)
		self.param = param
		self.args = args

	def __eq__(self, other):
		return (self.param, self.args) == (other.param, other.args)

	def __call__(self, context):
		## Lookup function:
		## getitem dict / getattr objects / getattr on wrapper
		obj = self.param.parent(context)
		name = self.param.key
		try:
			function = obj[name]
			if not isinstance(function, ExpressionFunction):
				raise KeyError
		except (TypeError, KeyError):
			if hasattr(obj, name) \
			and isinstance(getattr(obj, name), ExpressionFunction):
				function = getattr(obj, name)
			else:
				wrapper = self.wrap_object(obj)
				if wrapper is not None \
				and hasattr(wrapper, name) \
				and isinstance(getattr(wrapper, name), ExpressionFunction):
					function = getattr(wrapper, name)
				else:
					raise AssertionError, 'parameter is not a valid function: %s' % self.param.name

		## Execute function
		if not isinstance(function, ExpressionFunction):
			# Just being paranoid here, but leave it in to block any mistakes in above lookup
			raise AssertionError, 'parameter is not a valid function: %s' % self.param.name

		args = self.args(context)
		return function(*args)

	def wrap_object(self, obj):
		'''Find a suitable wrapper that exposes safe methods for
		a given object
		'''
		if isinstance(obj, basestring):
			return ExpressionStringObject(obj)
		elif isinstance(obj, (dict, collections.Mapping)):
			return ExpressionDictObject(obj)
		elif isinstance(obj, list):
			return ExpressionListObject(obj)
		else:
			return None

	def pprint(self):
		return 'CALL(%s: %s)' % (self.param.name, self.args.pprint())


class ExpressionFunction(object):
	'''Wrapper for methods and functions that whitelists
	functions to be called from expressions
	'''

	def __init__(self, func):
		self._func = func

	def __get__(self, instance, owner):
		# This allows using this object as a decorator as well
		if instance is None:
			return self
		else:
			return BoundExpressionFunction(instance, self._func)

	def __eq__(self, other):
		return self._func == other._func

	def __call__(self, *a):
		return self._func(*a)

	def __repr__(self):
		# Also shows up when function parameter is used, but not called
		# (TemplateToolkit allow implicit call - we don't !)
		return "<%s: %s()>" % (self.__class__.__name__, self._func.__name__)


class BoundExpressionFunction(ExpressionFunction):

	def __init__(self, obj, func):
		self._obj = obj
		self._func = func

	def __call__(self, *a):
		return self._func(self._obj, *a)


class ExpressionObjectBase(object):

	_fmethods = ()

	def __init__(self, obj):
		self._obj = obj

	def __getattr__(self, name):
		if name in self._fmethods:
			func = ExpressionFunction(getattr(self._obj, name))
			#~ setattr(self, name, func)
			return func
		else:
			raise AttributeError

	def __getitem__(self, k):
		return self._obj[k]

	def __iter__(self):
		return iter(self._obj)

	def __len__(self):
		return len(self._obj)

	def __str__(self):
		return str(self._obj)

	def __repr__(self):
		return '<%s: %r>' % (self.__class__.__name__, self._obj)

	@ExpressionFunction
	def len(self):
		return len(self)

	@ExpressionFunction
	def sorted(self):
		return sorted(self)

	@ExpressionFunction
	def reversed(self):
		return list(reversed(self))



class ExpressionStringObject(ExpressionObjectBase):
	'''Proxy for string objects that gives safe methods for use in
	expressions.
	'''

	_fmethods = (
		'capitalize', 'center', 'count', 'endswith', 'expandtabs',
		'ljust', 'lower', 'lstrip', 'replace', 'rjust', 'rsplit',
		'rstrip', 'split', 'splitlines', 'startswith', 'title',
		'upper',
	)


class ExpressionDictObject(ExpressionObjectBase):
	'''Proxy for dict objects that gives safe methods for use in
	expressions.
	'''

	_fmethods = (
		'get', 'keys', 'values', 'items',
		'len', 'reversed', 'sorted'
	)
	# only functions for non-mutuable mapping here !

	def __setitem__(self, k, v):
		self._obj[k] = v

	def __delitem__(self, k):
		del self._obj[k]



class ExpressionListObject(ExpressionObjectBase):
	'''Proxy for list objects that gives safe methods for use in
	expressions.
	'''

	_fmethods = ('get', 'len', 'reversed', 'sorted')

	@ExpressionFunction
	def get(self, i, default=None):
		try:
			return self._obj[i]
		except IndexError:
			return default


############ TEMPLATE PARSER ################

class TemplateBuilderTextBuffer(BuilderTextBuffer):
	'''Sub class of L{BuilderTextBuffer} that is used to strip text
	around template instructions.
	'''

	_rstrip_re = re.compile(r'\n?[ \t]*$')
	_lstrip_re = re.compile(r'^[ \t]*\n?')

	def __init__(self, builder):
		BuilderTextBuffer.__init__(self, builder)
		self._lstrip_pending = False

	def text(self, text):
		BuilderTextBuffer.text(self, text)

	def flush(self):
		text = u''.join(self.buffer)

		if text and self._lstrip_pending:
			text = self._lstrip(text)

		if text:
			self.builder.text(text)

		self._lstrip_pending = False
		self.buffer = []

	def rstrip(self):
		'''Do an rstrip on last piece of text up to and including
		newline
		'''
		text = u''.join(self.buffer)
		if text:
			self.buffer = [self._rstrip(text)]

	def _rstrip(self, text):
		if text.endswith('\n'):
			return text[:-1]
		else:
			return self._rstrip_re.sub('', text)

	def lstrip(self):
		'''Flag that next piece of text needs to be lstripped up to
		and including newline
		'''
		self._lstrip_pending = True

	def _lstrip(self, text):
		return self._lstrip_re.sub('', text)


class TemplateTreeBuilder(MySimpleTreeBuilder):

	def __init__(self):
		MySimpleTreeBuilder.__init__(self)

	def start(self, tag, attrib=None):
		# Special case for blocks - put them outside hierarchy
		if tag == 'BLOCK':
			element = self.elementfactory(tag, attrib, [])
			self.root.append(element)
			self.stack.append(element)
		else:
			# Check IF / ELIF / ELSE occur in right sequence
			if tag in ('ELIF', 'ELSE'):
				prev = self.stack[-1][-1]
				if not hasattr(prev, 'tag') \
				and prev.tag in ('IF', 'ELIF'):
					raise '%s block out of place' % tag

			MySimpleTreeBuilder.start(self, tag, attrib)


class TemplateParser(object):

	# Build parse tree like:
	#  - text
	#  - IF expr=...
	#    - text
	#    - GET expr=...
	#    - text
	#  - ELIF expr= ..
	#    - text
	#  - text
	#
	# So:
	#   GET token: append
	#   IF token: start IF
	#   ELIF token: end IF (error if unmatched), start ELIF
	#   END token: end whatever is on the stack
	#
	# Keywords are case sensitive: must be upper case

	_set_token_re = re.compile(r'^([\w\.]+)\s*=\s*(.*)$') # var = expr

	_token_with_expr_re = re.compile(r'^(\w+)\s+(.*)$') # TOKEN expr

	_for_in_token_re = re.compile(r'^(\w+)\s+IN\s+(.*)$') # name IN expr

	_for_is_token_re = re.compile(r'^(\w+)\s*=\s*(.*)$') # name = expr

	_block_token_re = re.compile(r'^\w+$') # name

	_tokens_with_expr = (
		'GET', 'SET',
		'IF', 'ELIF', 'ELSIF', 'ELSE',
		'FOR', 'FOREACH',
		'BLOCK', 'INCLUDE',
		'END'
	)	# These tokens take an argument

	_tokens_without_expr = ('ELSE', 'END')
		# These tokens do not take an argument

	_tokens_with_end = (
		'IF', 'ELIF', 'ELSIF', 'ELSE',
		'FOR', 'FOREACH', 'BLOCK',
	)	# These tokens start a block that is delimited by END

	_tokens_with_line_chomp = _tokens_with_end + (
		'END', 'INCLUDE'
	)	# For these tokens strip whitespace of token is on it's own line

	_tokens_with_default_chomp = ('SET',)
		# For these tokens always strip whitespace left and right

	def __init__(self):
		self.text_parser = self.build_text_parser()
		self.expr_parser = ExpressionParser()
		self._stack = []

	def parse(self, text):
		builder = TemplateTreeBuilder()
		self.__call__(builder, text)
		return builder.get_root()

	def __call__(self, builder, text):
		wrapper = TemplateBuilderTextBuffer(builder)
		wrapper.start('TEMPLATE')
		self.text_parser(wrapper, text)
		wrapper.end('TEMPLATE')

	def build_text_parser(self):
		# Rules capture [% .. %] and <!--[% ... %]--> including "chomp" flags
		# First two rules block level instruction on it's own line
		# next two rules are embdedded in content
		line_tokens = '|'.join(map(re.escape, self._tokens_with_line_chomp))
		text_parser = (
			Rule('X-XML-Token', r'''
				^[^\S\n]*			# whitespace at line start
				\<\!--\[%%			# start of instruction
				(
					-?				# rchomp
					\s+
					(?:%s)			# line tokens
					(?:\s[^%%]*?)?	# optional expression -- the [^%%] os a bit of a hack here..
					\s
					-?				# lchomp
				)
				%%\]--\>			# end of instruction
				[^\S\n]*\n			# whitespace and end of line
				''' % line_tokens,
				process=self._process_token )
			| Rule('X-Text-Token', r'''
				^[^\S\n]*			# whitespace at line start
				\[%%				# start of instruction
				(
					-?				# rchomp
					\s+
					(?:%s)			# line tokens
					(?:\s[^%%]*?)?	# optional expression -- the [^%%] os a bit of a hack here..
					\s
					-?				# lchomp
				)
				%%\]				# end of instruction
				[^\S\n]*\n			# whitespace and end of line
				''' % line_tokens,
				process=self._process_token )
			| Rule('X-Inline-XML-Token',
				r'\<\!--\[%(-?\s.*?\s-?)%\]--\>',
				process=self._process_token )
			| Rule('X-Inline-Text-Token',
				r'\[%(-?\s.*?\s-?)%\]?',
				process=self._process_token )
		)
		return text_parser

	def _process_token(self, builder, text):
		rchomp = text.startswith('-') # rstrip prev text
		lchomp = text.endswith('-') # lstrip next text
		text = text.strip('-').strip()

		m = self._token_with_expr_re.match(text)
		if m and m.group(1) in self._tokens_with_expr:
			token = m.group(1)
			expr = m.group(2).strip()
			if not expr:
				raise AssertionError # TODO better error
		elif text in self._tokens_without_expr:
			token = text
			expr = None
		else:
			m = self._set_token_re.match(text)
			if m:
				token = 'SET'
			else:
				token = 'GET'
			expr = text

		if token in self._tokens_with_default_chomp:
			rchomp = True
			lchomp = True

		if rchomp:
			builder.rstrip()

		method = getattr(self, '_process_token_' + token.lower())
		method(builder, token, expr)

		if lchomp:
			builder.lstrip()

	def _process_append_token(self, b, t, e):
		e = self.expr_parser.parse(e)
		b.append(t, {'expr': e})

	_process_token_get = _process_append_token
	_process_token_include = _process_append_token

	def _process_token_set(self, b, t, e):
		m = self._set_token_re.match(e)
		if m:
			v = ExpressionParameter(m.group(1))
			e = self.expr_parser.parse(m.group(2))
			b.append(t, {'var': v, 'expr': e})
		else:
			raise AssertionError # TODO better error

	def _process_token_if(self, b, t, e):
		e = self.expr_parser.parse(e)
		b.start('IF', {'expr': e})
		self._stack.append('IF')

	def _process_token_elif(self, b, t, e):
		b.end(self._stack.pop()) # raises if unmatched - TODO explicit error
		e = self.expr_parser.parse(e)
		b.start('ELIF', {'expr': e})
		self._stack.append('ELIF')

	_process_token_elsif = _process_token_elif

	def _process_token_else(self, b, t, e):
		b.end(self._stack.pop()) # raises if unmatched - TODO explicit error
		b.start('ELSE')
		self._stack.append('ELSE')

	def _process_token_for(self, b, t, e):
		m = self._for_in_token_re.match(e)
		if t == 'FOREACH' and not m:
			m = self._for_is_token_re.match(e)

		if m:
			v = ExpressionParameter(m.group(1))
			e = self.expr_parser.parse(m.group(2))
			b.start('FOR', {'var': v, 'expr': e})
			self._stack.append('FOR')
		else:
			raise AssertionError, '>> %s, expected "=" or "IN"' % e # TODO better error

	_process_token_foreach = _process_token_for

	def _process_token_block(self, b, t, e):
		if not self._block_token_re.match(e):
			raise AssertionError # TODO better error
		b.start('BLOCK', {'name': e})
		self._stack.append('BLOCK')

	def _process_token_end(self, b, t, e):
		b.end(self._stack.pop()) # raises if unmatched - TODO explicit error



################### UTILS ################

class MovingWindowIter(object):
	'''Iterator yields a 3-tuple of the previous item, the current item
	and the next item while iterating a give iterator.
	Previous or next item will be C{None} if not available.
	Use as:

		for prev, current, next in MovingWindowIter(mylist):
			....

	@ivar items: current 3-tuple
	@ivar last: C{True} if we are at the last item
	'''

	def __init__(self, iterable):
		self._iter = iter(iterable)
		try:
			first = self._iter.next()
		except StopIteration:
			# empty list
			self.last = True
			self.last = (None, None, None)
		else:
			self.last = False
			self.items = (None, None, first)

	def __iter__(self):
		return self

	def next(self):
		if self.last:
			raise StopIteration

		discard, prev, current = self.items
		try:
			next = self._iter.next()
		except StopIteration:
			self.last = True
			self.items = (prev, current, None)
		else:
			self.items = (prev, current, next)

		return self.items


##################### TEMPLATE EVAL ######################

import logging

logger = logging.getLogger('zim.template.eval')


class TemplateContextDict(ExpressionDictObject):

	_fmethods = ExpressionDictObject._fmethods + (
		'pop', 'clear', 'update', 'setdefault'
	) # adding methods for mutuable mapping here



class TemplateLoopState(object):

	def __init__(self, size=None, outer=None):
		if size is None:
			self.size = None
			self.max = None
		else:
			self.size = size
			self.max = size - 1

		self.outer = outer

		self.prev = None
		self.current = None
		self.next = None
		self.index = None
		self.count = None
		self.first = None
		self.last = None
		self.parity	= None
		self.even = None
		self.odd = None

	def _update(self, i, movingwindowiter):
		self.prev = movingwindowiter.items[0]
		self.current = movingwindowiter.items[1]
		self.next = movingwindowiter.items[2]

		self.first = i == 0
		self.last = movingwindowiter.last

		self.index = i
		self.count = i + 1
		self.parity	= 'even' if i % 2 == 0 else 'odd'
		self.even = self.parity == 'even'
		self.odd = self.parity == 'odd'


class TemplateProcessor(object):

	# See Expression for remarks on safe eval of expressions.
	#
	# In addition here we set also parameters in the context rather
	# then just retrieving them. To make this safe we only allow
	# modification of C{TemplateContextDict} dicts and do not allow
	# any assignment to other dicts or objects.

	# Instructions supported here:
	#
	# 	'GET', 'SET',
	# 	'IF', 'ELIF', 'ELSE',
	# 	'FOR'
	# 	'INCLUDE',

	def __init__(self, parts):
		self.main = None
		self.blocks = {}
		for item in parts:
			if item.tag == 'TEMPLATE':
				self.main = item
			elif item.tag == 'BLOCK':
				self.blocks[item.get('name')] = item
			else:
				raise AssertionError, 'Unknown tag: %s' % item.tag

		if self.main is None:
			raise AssertionError, 'Missing main part of template'

	def process(self, output, context):
		assert isinstance(context, TemplateContextDict)
		self.__call__(output, self.main, context)

	@staticmethod
	def _set(context, var, value):
		# We only allow setting in pre-defined TemplateContextDict's
		namespace = context
		for name in var.parts[:-1]:
			if namespace \
			and isinstance(namespace, TemplateContextDict):
				namespace = namespace.get(name)
			else:
				raise AssertionError, 'Can not assign: %s' % var.name

		if namespace \
		and isinstance(namespace, TemplateContextDict):
			namespace[var.key] = value
		else:
			raise AssertionError, 'Can not assign: %s' % var.name

	def __call__(self, output, elements, context):
		n = len(elements)
		i = 0
		while i < n:
			try:
				element = elements[i]
				i += 1
				if isinstance(element, basestring):
					output.append(element)
				elif element.tag == 'GET':
					expr = element.attrib['expr']
					value = expr(context)
					output.append(unicode(value))
				elif element.tag == 'SET':
					var = element.attrib['var']
					expr = element.attrib['expr']
					value = expr(context)
					self._set(context, var, value)
				elif element.tag in ('IF', 'ELIF'):
					expr = element.attrib['expr']
					if bool(expr(context)):
						self.__call__(output, element, context) # recurs
						while i < n \
						and isinstance(elements[i], SimpleTreeElement) \
						and elements[i].tag in ('ELIF', 'ELSE'):
							# Skip subsequent ELIF / ELSE clauses
							i += 1
				elif element.tag == 'ELSE':
					self.__call__(output, element, context) # recurs
				elif element.tag == 'FOR':
					self._loop(output, element, context)
				elif element.tag == 'INCLUDE':
					expr = element.attrib['expr']
					if isinstance(expr, ExpressionParameter):
						name = expr.name
						if name in self.blocks:
							self.__call__(output, self.blocks[name], context) # recurs
						else:
							raise AssertionError, 'No such block defined: %s' % name
					else:
						raise AssertionError, 'TODO also allow files from template resources'
				else:
					raise AssertionError, 'Unknown instruction: %s' % element.tag
			except:
				#~ logger.exception('Exception in template')
				raise

	def _loop(self, output, element, context):
		var = element.attrib['var']
		expr = element.attrib['expr']
		items = expr(context)
		if not isinstance(items, collections.Iterable):
			raise TypeError, 'Can not iterate over: %s' % items
		elif not isinstance(items, collections.Sized):
			# cast to list to ensure we have a len()
			items = list(items)

		# set "loop"
		outer = context.get('loop')
		if isinstance(outer, TemplateLoopState):
			loop = TemplateLoopState(len(items), outer)
		else:
			loop = TemplateLoopState(len(items), None)
		context['loop'] = loop

		# do the iterations
		myiter = MovingWindowIter(items)
		for i, items in enumerate(myiter):
			loop._update(i, myiter)
			self._set(context, var, items[1]) # set var
			self.__call__(output, element, context) # recurs

		# restore "loop"
		context['loop'] = outer


class Template(object):

	# On purpose a very thin class, allow to test all steps of parsing
	# and processing as individual classes

	# For templates that we define inline, use a file-like text buffer

	template_functions = {
		'len': ExpressionFunction(len),
		'sorted': ExpressionFunction(sorted),
		'reversed': ExpressionFunction(lambda i: list(reversed(i))),
		'range': ExpressionFunction(range),
		# TODO strftime, strfcal
	}

	def __init__(self, file):
		self.filename = file.path
		self.parts = TemplateParser().parse(file.read())
		rdir = file.dir.subdir(file.basename[:-5]) # XXX strip extension, .html here
		if rdir.exists():
			self.resources_dir = rdir
		else:
			self.resources_dir = None

	def process(self, output, context):
		context = TemplateContextDict(dict(context)) # COPY to keep changes local
		context.update(self.template_functions) # set builtins
		#~ import pprint; pprint.pprint(context)
		processor = TemplateProcessor(self.parts)
		processor.process(output, context)




################### TESTS ####################

import unittest as tests


class TestExpressionParser(tests.TestCase):

	def runTest(self):
		## Test atoms
		p = ExpressionParser()
		for text, wanted in (
			('True', ExpressionLiteral(True)),
			('False', ExpressionLiteral(False)),
			('None', ExpressionLiteral(None)),
			('"foo\\tbar"', ExpressionLiteral("foo\tbar")),
			('123', ExpressionLiteral(123)),
			('1.2', ExpressionLiteral(1.2)),
			('1E+3', ExpressionLiteral(1E+3)),
			('x', ExpressionParameter('x')),
			('foo.bar', ExpressionParameter('foo.bar')),
		):
			self.assertEqual(p.parse(text), wanted)

		## Test compound expressions
		p = ExpressionParser()
		for text, wanted in (
			('x or y', ExpressionOperator(
				operator.or_,
				ExpressionParameter('x'),
				ExpressionParameter('y')
			)),
			('x == y', ExpressionOperator(
				operator.eq,
				ExpressionParameter('x'),
				ExpressionParameter('y')
			)),
			('not x', ExpressionUnaryOperator(
				operator.not_,
				ExpressionParameter('x')
			)),
			('[1, a, True]', ExpressionList([
				ExpressionLiteral(1),
				ExpressionParameter('a'),
				ExpressionLiteral(True),
			])),
			('[[1, a], [True, False]]', ExpressionList([
				ExpressionList([
					ExpressionLiteral(1),
					ExpressionParameter('a'),
				]),
				ExpressionList([
					ExpressionLiteral(True),
					ExpressionLiteral(False),
				])
			])),
			('func(1, a)', ExpressionFunctionCall(
				ExpressionParameter('func'),
				ExpressionList([
					ExpressionLiteral(1),
					ExpressionParameter('a'),
				])
			)),
			('func([1, a])', ExpressionFunctionCall(
				ExpressionParameter('func'),
				ExpressionList([
					ExpressionList([
						ExpressionLiteral(1),
						ExpressionParameter('a'),
					])
				])
			)),
			('func(1, func(a))', ExpressionFunctionCall(
				ExpressionParameter('func'),
				ExpressionList([
					ExpressionLiteral(1),
					ExpressionFunctionCall(
						ExpressionParameter('func'),
						ExpressionList([
							ExpressionParameter('a'),
						])
					)
				])
			)),
			('[func(1, a), x == y]', ExpressionList([
				ExpressionFunctionCall(
					ExpressionParameter('func'),
					ExpressionList([
						ExpressionLiteral(1),
						ExpressionParameter('a'),
					])
				),
				ExpressionOperator(
					operator.eq,
					ExpressionParameter('x'),
					ExpressionParameter('y')
				)
			])),
		):
			self.assertEqual(p.parse(text), wanted)


		## Test operator precedence
		expr = ExpressionParser().parse('a or b and not c < d and f or x')
			# Read as: '(a or ((b and ((not (c < d)) and f)) or x))'
		wanted = ExpressionOperator(
			operator.or_,
			ExpressionParameter('a'),
			ExpressionOperator(
				operator.or_,
				ExpressionOperator(
					operator.and_,
					ExpressionParameter('b'),
					ExpressionOperator(
						operator.and_,
						ExpressionUnaryOperator(
							operator.not_,
							ExpressionOperator(
								operator.lt,
								ExpressionParameter('c'),
								ExpressionParameter('d')
							)
						),
						ExpressionParameter('f')
					)
				),
				ExpressionParameter('x')
			)
		)
		#~ print '\nEXPRESSION:', expr
		self.assertEqual(expr, wanted)

		## Invalid syntaxes
		p = ExpressionParser()
		for t in (
			'x > y > z',	# chaining comparison operators not allowed
			'x > not y',	# 'not' has higher precendence, can not appear here
			'not not x',	# double operator
			'x and and y',	# double operator
			'[x,,y]',		# double "," - missing element
			'(1,2)',		# Tuple not supported
			'1 2',			# Two expressions, instead of one
			'1, 2',			# Two expressions, instead of one
			'1.2.3',		# Invalid literal
			'<>',			# just an operator
			'',				# empty expression has no meaning
		):
			self.assertRaises(ExpressionSyntaxError, p.parse, t)
				# TODO check for meaningfull error messages for these

		# TODO any edge cases ?


class TestExpression(tests.TestCase):

	def runTest(self):
		expr = ExpressionList([
			ExpressionLiteral('foooo'),
			ExpressionParameter('foo'),
			ExpressionParameter('a.b'),
			ExpressionOperator(
				operator.le,
				ExpressionParameter('n'),
				ExpressionLiteral(2)
			),
			ExpressionFunctionCall(
				ExpressionParameter('addone'),
				ExpressionList([
					ExpressionParameter('n')
				])
			),
		])

		result = expr( {
			'foo': 'FOO',
			'a': {
				'b': 'BAR'
			},
			'n': 1,
			'addone': ExpressionFunction(lambda a: a+1)
		} )

		wanted = ['foooo', 'FOO', 'BAR', True, 2]
		self.assertEqual(result, wanted)


class TestExpressionFunctionCall(tests.TestCase):

	def runTest(self):
		class Foo(object):

			def __init__(self, prefix):
				self.prefix = prefix

			@ExpressionFunction
			def string(self, string):
				return self.prefix + string

		# Test ExpressionFunction works as decorator (bound method)
		foo = Foo('FOO')
		self.assertIsInstance(foo.string, ExpressionFunction)
		self.assertEqual(foo.string('bar'), 'FOObar')

		# Test get builtin from dict
		mydict = {
			'len': ExpressionFunction(lambda o: len(o)),
			'mylist': ['a', 'b', 'c'],
		}
		args = ExpressionList([ExpressionParameter('mylist')])
		var = ExpressionParameter('len')
		func = ExpressionFunctionCall(var, args)
		self.assertEqual(func(mydict), 3)

		# Test get object method from attr
		mydict = {'foo': foo}
		args = ExpressionList([ExpressionLiteral('BAR')])
		var = ExpressionParameter('foo.string')
		func = ExpressionFunctionCall(var, args)
		self.assertEqual(func(mydict), 'FOOBAR')

		# Test implicit types
		mydict = {
			'somedict': {'a': 'AAA', 'b': 'BBB', 'c': 'CCC'},
			'somelist': ['x', 'y', 'z'],
			'somestring': 'FOOBAR',
		}
		args = ExpressionList() # empty args
		for name, wanted in (
			('somedict.sorted', ['a', 'b', 'c']),
			('somelist.len', 3),
			('somestring.lower', 'foobar'),
			('somedict.b.lower', 'bbb'),
			('somelist.1.upper', 'Y'),
		):
			var = ExpressionParameter(name)
			func = ExpressionFunctionCall(var, args)
			self.assertEqual(func(mydict), wanted)


class TestExpressionObjects(tests.TestCase):

	def runTest(self):
		# Test proper object type for attributes
		for obj in (
			ExpressionStringObject('foo'),
			ExpressionDictObject({'foo': 'bar'}),
			ExpressionListObject(['a', 'b', 'c']),
		):
			for name in obj._fmethods:
				self.assertTrue(hasattr(obj, name))
				function = getattr(obj, name)
				self.assertIsInstance(function, ExpressionFunction)

		# Test getitem, iter, len, str
		# and one or two functions of each type
		data = {'a': 'b', 'c': 'd', 'e': 'f'}
		mydict = ExpressionDictObject(data)
		self.assertEqual(mydict['c'], data['c'])
		self.assertEqual(list(mydict), list(data))
		self.assertEqual(len(mydict), len(data))
		self.assertEqual(str(mydict), str(data))
		self.assertEqual(mydict.get('c'), data.get('c'))

		mylist = ExpressionListObject(['a', 'b', 'c'])
		self.assertEqual(mylist[1], 'b')
		self.assertEqual(mylist.get(1), 'b')
		self.assertIsNone(mylist.get(5))

		mystring = ExpressionStringObject('foo')
		self.assertEqual(mystring.upper(), "FOO")


class TestMovingWindowIterBuffer(tests.TestCase):

	def runTest(self):
		mylist = ['a', 'b', 'c', 'd']
		myiter = MovingWindowIter(mylist)

		self.assertEqual(iter(myiter), myiter, 'MovingWindowIter should be an iter, not an iterable')

		seen = []
		n = len(mylist)
		for i, t in enumerate(myiter):
			seen.append(t[1])
			if i == 0:
				self.assertEqual(t, (None, mylist[0], mylist[1]))
				self.assertFalse(myiter.last)
			elif i == n-1:
				self.assertEqual(t, (mylist[-2], mylist[-1], None))
				self.assertTrue(myiter.last)
			else:
				self.assertEqual(t, (mylist[i-1], mylist[i], mylist[i+1]))
				self.assertFalse(myiter.last)

		self.assertEqual(seen, mylist)



class TestBuilderTextBuffer(tests.TestCase):

	def runTest(self):
		builder = MySimpleTreeBuilder()
		buffer = BuilderTextBuffer(builder)

		buffer.start('FOO')
		buffer.text('aaa\n')
		buffer.text('bbb\n')
		buffer.text('ccc\n')
		self.assertEqual(buffer.get_text(), 'aaa\nbbb\nccc\n')

		buffer.append('BAR')
		self.assertEqual(buffer.get_text(), '')

		buffer.text('qqq\n')
		self.assertEqual(buffer.get_text(), 'qqq\n')
		buffer.clear_text()

		buffer.text('qqq\n')
		self.assertEqual(buffer.get_text(), 'qqq\n')
		buffer.set_text('ddd\n')
		self.assertEqual(buffer.get_text(), 'ddd\n')

		buffer.text('')
		buffer.text('eee')
		buffer.end('FOO')

		E = SimpleTreeElement
		self.assertEqual(builder.get_root(), [
			E('FOO', None, [
				u'aaa\nbbb\nccc\n',
				E('BAR', None, []),
				u'ddd\neee',
			])
		])



class TestTemplateBuilderTextBuffer(tests.TestCase):

	def runTest(self):
		builder = MySimpleTreeBuilder()
		buffer = TemplateBuilderTextBuffer(builder)

		buffer.start('FOO')
		buffer.text('foo\n\t\t')

		buffer.rstrip()
		buffer.append('BAR')
		buffer.lstrip()

		buffer.text('   \n\n\t\tdus\n\n')

		buffer.rstrip()
		buffer.append('BAR')
		buffer.lstrip()
		buffer.text('\n')

		buffer.end('FOO')
		result = builder.get_root()
		#~ print result

		E = SimpleTreeElement
		self.assertEqual(result, [
			E('FOO', None, [
				u'foo',
				E('BAR', None, []),
				u'\n\t\tdus\n',
				E('BAR', None, []),
			])
		])


class TestTemplateParser(tests.TestCase):

	# Include all elements recognized by parser and various forms
	# of whitespace stripping, no need to excersize all expressions
	# - ExpressionParser is tested separately

	TEMPLATE = '''\
[% foo %]
[% GET foo %]

[% bar = "test" %]
[% SET bar = "test" %]

	<!--[% IF foo %]-->
	DO SOMETHING
	<!--[% ELIF foo -%]-->
	SOMETHING ELSE
	[%- ELSE %]
	YET SOMETHING ELSE
	[% END %]

Switch:	[% IF foo %]AAA[% ELSE %]BBB[% END %]

	[% BLOCK bar -%]
	BAR
[% END %]

[% FOR a IN b %]
	AAA
[% END %]

[% FOREACH a IN b %]
	AAA
[% END %]

[% FOREACH a = b %]
	AAA
[% END %]

<!--[% BLOCK foo %]-->
	FOO
<!--[% END %]-->
'''

	E = SimpleTreeElement
	WANTED = [
		E('TEMPLATE', None, [
			E('GET', {'expr': ExpressionParameter('foo')}, []),
			'\n', # whitespace around GET remains intact
			E('GET', {'expr': ExpressionParameter('foo')}, []),
			'\n',
			E('SET', {
				'var': ExpressionParameter('bar'),
				'expr': ExpressionLiteral('test')
			}, []), # no whitespace here - SET chomps
			E('SET', {
				'var': ExpressionParameter('bar'),
				'expr': ExpressionLiteral('test')
			}, []),
			'\n', # only one "\n" here!
			# no indenting before block level items like IF
			E('IF', {'expr': ExpressionParameter('foo')}, [
				'\tDO SOMETHING\n' # indenting intact
			]),
			E('ELIF', {'expr': ExpressionParameter('foo')}, [
				'SOMETHING ELSE' # stripped on both sides
			]),
			E('ELSE', None, [
				'\tYET SOMETHING ELSE\n' # indenting intact
			]),
			'\nSwitch:\t',
			E('IF', {'expr': ExpressionParameter('foo')}, [
				'AAA'
			]),
			E('ELSE', None, [
				'BBB'
			]),
			'\n\n', # two "\n" here because IF .. ELSE is inline
			'\n', # another empty line after block is taken out
			# 3 times same loop by different syntax
			E('FOR', {
				'var': ExpressionParameter('a'),
				'expr': ExpressionParameter('b'),
			}, [
				'\tAAA\n'
			]),
			'\n',
			E('FOR', {
				'var': ExpressionParameter('a'),
				'expr': ExpressionParameter('b'),
			}, [
				'\tAAA\n'
			]),
			'\n',
			E('FOR', {
				'var': ExpressionParameter('a'),
				'expr': ExpressionParameter('b'),
			}, [
				'\tAAA\n'
			]),
			'\n',
		]),
		E('BLOCK', {'name': 'bar'}, ['BAR\n']),
			# indenting before "[% BLOCK .." and before "BAR" both gone
		E('BLOCK', {'name': 'foo'}, ['\tFOO\n']),
			# indenting intact
	]

	def runTest(self):
		parser = TemplateParser()

		root = parser.parse(self.TEMPLATE)
		#~ print root
		self.assertEqual(root, self.WANTED)

		# TODO Test exceptions
		#  - invalid expression
		#  - lower case keyword
		#  - invalide sequence IF / ELSE


class TestTemplateContextDict(tests.TestCase):

	def runTest(self):
		data = {'a': 'AAA', 'b': 'BBB', 'c': 'CCC'}
		context = TemplateContextDict(data)
		for name in context._fmethods:
			func = getattr(context, name)
			self.assertIsInstance(func, ExpressionFunction)

		# make sure we can use as regular dict
		context['d'] = 'DDD'
		self.assertEqual(context.pop('d'), 'DDD')


class TestTemplateProcessor(tests.TestCase):
	pass

	# TODO excersize all instruction types, show loop iterations and if / elsif branches work
	# TODO use loop state parameter
	# TODO test that we really can't set / pop / insert in dicts and lists other than context


class TestTemplate(tests.TestCase):

	def runTest(self):
		from pprint import pprint

		from zim.fs import File
		file = File('./TestTemplate.html')

		templ = Template(file)
		#~ pprint(templ.parts) # parser output

		output = []
		templ.process(output, {
			'title': 'THIS IS THE TITLE',
			'generator': {
				'name': 'ZIM VERSION',
			},
			'navigation': {
				'prev': None,
				'next': None,
			},
			'links': {},
			'pages': [
				{ # page
					'name': 'page',
					'heading': 'HEAD',
					'body': 'BODY',
					'properties': {
						'type': 'PAGE',
					},
					'backlinks': [
						{'name': 'LINK1'},
						{'name': 'LINK2'},
						{'name': 'LINK3'},
					],
					'attachments': [
						{'name': 'FILE1', 'basename': 'FILE1', 'size': '1k'},
						{'name': 'FILE2', 'basename': 'FILE2', 'size': '1k'},
					],
				},
			],
			'uri': ExpressionFunction(lambda l: "URL:%s" % l['name']),
			'anchor': ExpressionFunction(lambda l: "ANCHOR:%s" % l['name']),
		})
		#~ print ''.join(output)

		# TODO assert something



if __name__ == '__main__':
	logging.basicConfig()
	tests.main()
