# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
Module that contains the logic for evaluating expressions in the
template.

Expression evaluation is done without using a real python eval to
keep it safe from arbitrary code execution

Both parameter values and functions are stored in a dict that is
passed to the Expression object when it is executed. The expressions
should not allow access to anything outside this dict, and only
sane access to objects reachable from this dict.

Parameter lookup gets list and dict items as well as object attributes.
It does not allow accessing private attributes (starting with "_")
or or code objects (object method of function) - callable objects on
the other hand can be accessed.

We control execution by only executing functions that are specifically
whitelisted as being an ExpressionFunction (can be used as decorator).
The expression classes have builtin support for some builtin methods
on strings, lists and dicts (see L{ExpressionString},
L{ExpressionDict} and L{ExpressionList} respectively), other functions
can be supplied in the context dict or as object attributes.

The biggest risks would be to put objects in the dict that allow
access to dangerous methods or private data. Or to have functions
that e.g. eval one of their arguments or take a callable argument

The idea is that objects in the expression dict are proxies that
expose a sub set of the full object API and template friendly methods.
These restrictions hsould help to minimize risk of arbitrary code
execution in expressions.
'''


import collections
import inspect
import logging

logger = logging.getLogger('zim.templates')


class Expression(object):
	'''Base class for all expressions'''

	__slots__ = ()

	def __call__(self, dict):
		'''Evaluate the expression
		@param dict: the context with parameter values
		'''
		raise NotImplementedError

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.pprint())

	def __str__(self):
		return self.pprint()

	def pprint(self):
		'''Print the expression hierarchy'''
		raise NotImplemented


class ExpressionLiteral(Expression):
	'''Expression with a literal value'''

	__slots__ = ('value',)

	def __init__(self, value):
		'''Constructor
		@param value: the expression value (string, int, float, ...)
		'''
		self.value = value

	def __eq__(self, other):
		return self.value == other.value

	def __call__(self, dict):
		return self.value

	def pprint(self):
		return repr(self.value)


class ExpressionParameter(Expression):
	'''Expression with a parameter name, evaluates the parameter value'''

	__slots__ = ('name', 'parts', 'key')

	def __init__(self, name):
		'''Constructor
		@param name: the parameter name
		'''
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
				logger.warning('No such parameter: %s', '.'.join(map(str, self.parts[:i+1])))
				return None

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
	'''Expression for a list of expressions, recurses over all items
	when evaluated
	'''

	__slots__ = ('items',)

	def __init__(self, items=None):
		'''Constructor
		@param items: iterable with L{Expression} objects
		'''
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
	'''Expression for an operator statement (e.g. "AND", "OR", "<"),
	recurses for left and right side of the expression.
	'''

	__slots__ = ('operator', 'lexpr', 'rexpr')

	def __init__(self, operator, lexpr, rexpr):
		'''Constructor
		@param operator: an operator function
		@param lexpr: left hand L{Expression} object
		@param rexpr: right hand L{Expression} object
		'''
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
	'''Expression with a unary operator (e.g. "NOT") that recurses
	for the right hand side of the statement.
	'''

	__slots__ = ('operator', 'rexpr')

	def __init__(self, operator, rexpr):
		'''Constructor
		@param operator: an operator function
		@param rexpr: right hand L{Expression} object
		'''
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
	'''Expression with a function name and arguments, recurses for
	the arguments and evaluates the function.
	'''

	__slots__ = ('param', 'args')

	def __init__(self, param, args):
		'''Constuctor
		@param param: an L{ExpressionParameter} that refers the function
		@param args: an L{ExpressionList} with arguments
		'''
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
					raise AssertionError, 'Not a valid function: %s' % self.param.name

		## Execute function
		if not isinstance(function, ExpressionFunction):
			# Just being paranoid here, but leave it in to block any mistakes in above lookup
			raise AssertionError, 'Not a valid function: %s' % self.param.name

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

	Can be used as a decorator.
	'''

	def __init__(self, func):
		'''Constructor
		@param func: the actual function
		'''
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
	'''Wrapper used by L{ExpressionFunction} when used as a decorator
	for object methods.
	'''

	def __init__(self, obj, func):
		self._obj = obj
		self._func = func

	def __call__(self, *a):
		return self._func(self._obj, *a)


class ExpressionObjectBase(object):
	'''Base method for wrapper objects that are used to determine the
	safe functions to call on objects in the parameter dict.

	The attribute C{_fmethods()} lists methods that can be called
	safely on the wrapped objects.
	'''

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

