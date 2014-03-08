# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.templates module.'''

import tests

import os

import zim
from zim.errors import Error
from zim.templates import *
from zim.templates import GenericTemplate, \
	TemplateParam, TemplateDict, TemplateFunction, PageProxy
from zim.notebook import Notebook, Path
import zim.formats
from zim.parsing import link_type


class TestTemplateParam(tests.TestCase):

	def runTest(self):
		param = TemplateParam('xxx.yyy.zzz')
		self.assertEquals(param.path, ['xxx', 'yyy'])
		self.assertEquals(param.key, 'zzz')

		self.assertRaises(Error, TemplateParam, '_settings.foo')
		self.assertRaises(Error, TemplateParam, 'xxx._yyy.zzz')
		self.assertRaises(Error, TemplateParam, 'xxx.y-y.zzz')


class TestTemplateDict(tests.TestCase):

	def runTest(self):
		data = {'foo': {'bar': {'baz': '123'}}, 'xyz':'check'}
		dict = TemplateDict(data)

		param = TemplateParam('foo.bar.baz')
		self.assertEquals(dict[param], '123')
		dict[param] = 'FOO'
		self.assertEquals(dict[param], 'FOO')
		self.assertEquals(data['foo']['bar']['baz'], '123')


class TestGenericTemplate(tests.TestCase):

#	def setUp(self):
#		self.template = ...

	def testSyntax(self):
		'''Test Template processing simple statements without page'''
		input = '''
[%- SET test  = "foo"  -%]
[%- SET true  = "true" -%]
[%- SET false = ""     -%]
---
<b>[% test %]</b>
<i>[% some_none_existing_parameter %]</i>
<u>[% upper('foo') %]</u>
---
[% IF true %]OK[% ELSE %]NOK[% END %]
[% IF false -%]
OK
[%- ELSE -%]
NOK
[%- END %]
---
[% FOREACH name = [ 'foo', 'bar', 'baz' ] -%]
	NAME = [% GET name %]
[% END -%]
---
[% numbers = ['1', '2', '3'] -%]
[% FOREACH n IN numbers %][% n %]...[% END %]
---
'''

		wantedresult = u'''\
---
<b>foo</b>
<i></i>
<u>FOO</u>
---
OK
NOK
---
	NAME = foo
	NAME = bar
	NAME = baz
---
1...2...3...
---
'''
		tmpl = GenericTemplate(input)
		#~ import pprint
		#~ pprint.pprint( tmpl.tokens )
		dict = { 'upper': TemplateFunction(lambda d, *a: a[0].upper()) }
		result = tmpl.process(dict)
		#~ print test.getvalue()
		self.assertEqual(result, wantedresult.splitlines(True))

	def testRaise(self):
		'''Test Template invalid syntax raises TemplateError'''
		input = 'foo[% ELSE %]bar'
		self.assertRaises(TemplateSyntaxError, GenericTemplate, input)

		input = 'foo[% FOREACH foo = ("1", "2", "3") %]bar'
		self.assertRaises(TemplateSyntaxError, GenericTemplate, input)

		input = 'foo[% `echo /etc/passwd` %]bar'
		self.assertRaises(TemplateSyntaxError, GenericTemplate, input)

		input = 'foo[% duss("ja") %]bar'
		templ = GenericTemplate(input)
		self.assertRaises(TemplateProcessError, templ.process, {})


class TestTemplateSet(tests.TestCase):

	def runTest(self):
		'''Load all shipped templates for syntax check'''
		for dir, dirs, files in os.walk('./data/templates'):
			format = os.path.basename(dir)
			if format == 'templates':
				continue # skip top level dir
			files = [f for f in files if not f.startswith('.') and not '~' in f]
			files.sort()
			self.assertTrue(len(files) > 0)
			templates = list_templates(format)
			for file in files:
				self.assertIn(file, [t[1] for t in templates])

				file = os.path.join(dir, file)
				input = open(file).readlines()
				if format == 'plugins':
					tmpl = GenericTemplate(input)
				else:
					tmpl = Template(input, format)
					# Syntax errors will be raised during init
					# TODO parameter check for these templates
					#      ... run them with raise instead of param = None


class TestPageProxy(tests.TestCase):

	def runTest(self):
		notebook = tests.new_notebook()
		page = notebook.get_page(Path('FooBar'))

		page.parse('wiki', '''\
====== Page Heading ======
**foo bar !**
''')
		self.assertTrue(len(page.dump('html', linker=StubLinker())) > 0)
		proxy = PageProxy(Notebook(), page, zim.formats.get_format('html'), StubLinker(), {})
		self.assertEqual(proxy.name, page.name)
		self.assertEqual(proxy.namespace, page.namespace)
		self.assertEqual(proxy.basename, page.basename)
		self.assertTrue(isinstance(proxy.properties, dict))
		self.assertTrue(len(proxy.body) > 0)
		# TODO add othermethods


class TestTemplate(tests.TestCase):

	def runTest(self):
		input = u'''\
Version [% zim.version %]
<title>[% page.title %]</title>
Created [% page.properties['Creation-Date'] %]
<h1>[% notebook.name %]: [% page.name %]</h1>
<h2>[% page.heading %]</h2>
[% options.foo = "bar" %]
[%- page.body -%]
Option: [% options.foo %]
'''
		wantedresult = u'''\
Version %s
<title>Page Heading</title>
Created TODAY
<h1>Unnamed Notebook: FooBar</h1>
<h2>Page Heading</h2>
<p>
<b>foo bar !</b>
</p>
Option: bar
''' % zim.__version__
		notebook = tests.new_notebook()
		page = notebook.get_page(Path('FooBar'))
		page.parse('wiki', '''\
====== Page Heading ======
**foo bar !**
''')
		page.properties['Creation-Date'] = 'TODAY'
		self.assertTrue(len(page.dump('html', linker=StubLinker())) > 0)
		template = Template(input, 'html', linker=StubLinker())
		result = template.process(notebook, page)
		self.assertEqual(''.join(result), wantedresult)
		self.assertEqual(template.template_options['foo'], 'bar')

		# Check new page template
		notebook = tests.new_notebook()
		page = notebook.get_page(Path('Some New None existing page'))
		template = notebook.get_template(page)
		tree = template.process_to_parsetree(notebook, page) # No linker !
		head = tree.find('h').gettext()
		self.assertEqual(head, u'Some New None existing page')

class TestTemplatePageIndexFuntion(tests.TestCase):

	def runTest(self):
		# pageindex(root, collapse, ignore_empty)
		self.maxDiff = None

		data = (
('Parent:Daughter', u"[% pageindex('Parent') %]", '''\
<ul>
<li><a href="page://:Parent:Child" title="Child" class="page">Child</a></li>
<li><b>Daughter</b>
<ul>
<li><a href="page://:Parent:Daughter:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Daughter:Grandson" title="Grandson" class="page">Grandson</a></li>
<li><a href="page://:Parent:Daughter:SomeOne" title="SomeOne" class="page">SomeOne</a></li>
</ul>
</li>
<li><a href="page://:Parent:Son" title="Son" class="page">Son</a></li>
</ul>
'''),

('Parent:Daughter:SomeOne', u"[% pageindex('Parent') %]", '''\
<ul>
<li><a href="page://:Parent:Child" title="Child" class="page">Child</a></li>
<li><a href="page://:Parent:Daughter" title="Daughter" class="page">Daughter</a>
<ul>
<li><a href="page://:Parent:Daughter:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Daughter:Grandson" title="Grandson" class="page">Grandson</a></li>
<li><b>SomeOne</b>
<ul>
<li><a href="page://:Parent:Daughter:SomeOne:Bar" title="Bar" class="page">Bar</a></li>
<li><a href="page://:Parent:Daughter:SomeOne:Foo" title="Foo" class="page">Foo</a></li>
</ul>
</li>
</ul>
</li>
<li><a href="page://:Parent:Son" title="Son" class="page">Son</a></li>
</ul>
'''),

('Parent:Daughter:SomeOne', u"[% pageindex('Parent', FALSE, FALSE) %]", '''\
<ul>
<li><a href="page://:Parent:Child" title="Child" class="page">Child</a>
<ul>
<li><a href="page://:Parent:Child:Grandchild" title="Grandchild" class="page">Grandchild</a></li>
</ul>
</li>
<li><a href="page://:Parent:Daughter" title="Daughter" class="page">Daughter</a>
<ul>
<li><a href="page://:Parent:Daughter:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Daughter:Grandson" title="Grandson" class="page">Grandson</a></li>
<li><b>SomeOne</b>
<ul>
<li><a href="page://:Parent:Daughter:SomeOne:Bar" title="Bar" class="page">Bar</a></li>
<li><a href="page://:Parent:Daughter:SomeOne:Foo" title="Foo" class="page">Foo</a></li>
</ul>
</li>
</ul>
</li>
<li><a href="page://:Parent:Son" title="Son" class="page">Son</a>
<ul>
<li><a href="page://:Parent:Son:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Son:Grandson" title="Grandson" class="page">Grandson</a></li>
</ul>
</li>
</ul>
'''),
		)

		notebook = tests.new_notebook()
		for path, input, wantedresult in data:
			page = notebook.get_page(Path(path))
			result = Template(input, 'html', linker=StubLinker()).process(notebook, page)
			self.assertEqual(''.join(result), wantedresult)


class StubLinker(object):

	def set_usebase(self, usebase): pass

	def set_path(self, path): pass

	def link(self, link): return '%s://%s' % (link_type(link), link)

	def img(self, src): return 'img://' + src

	def icon(self, name): return 'icon://' + name


########################################################################

########################################################################

########################################################################


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
