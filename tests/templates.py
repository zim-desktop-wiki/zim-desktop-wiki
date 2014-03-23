# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.templates module.'''

import tests


from zim.templates import *

from zim.templates.parser import *
from zim.templates.expression import *
from zim.templates.expressionparser import *

from zim.parser import SimpleTreeElement, SimpleTreeBuilder, BuilderTextBuffer


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




class TestTemplateBuilderTextBuffer(tests.TestCase):

	def runTest(self):
		builder = SimpleTreeBuilder()
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
		file = File('./tests/data/TestTemplate.html')

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
