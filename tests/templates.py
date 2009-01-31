# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.templates module.'''

import tests
from tests import TestCase

import os

from zim.fs import *
from zim.templates import *
from zim.templates import GenericTemplate, \
	TemplateParam, TemplateDict, TemplateFunction, PageProxy
import zim.formats

class TestTemplateParam(TestCase):

	def runTest(self):
		param = TemplateParam('xxx.yyy.zzz')
		self.assertEquals(param.path, ['xxx', 'yyy'])
		self.assertEquals(param.key, 'zzz')

		self.assertRaises(TemplateSyntaxError, TemplateParam, '_settings.foo')
		self.assertRaises(TemplateSyntaxError, TemplateParam, 'xxx._yyy.zzz')
		self.assertRaises(TemplateSyntaxError, TemplateParam, 'xxx.y-y.zzz')


class TestTemplateDict(TestCase):

	def runTest(self):
		data = {'foo': {'bar': {'baz': '123'}}, 'xyz':'check'}
		dict = TemplateDict(data)

		param = TemplateParam('foo.bar.baz')
		self.assertEquals(dict[param], '123')
		dict[param] = 'FOO'
		self.assertEquals(dict[param], 'FOO')
		self.assertEquals(data['foo']['bar']['baz'], '123')


class TestGenericTemplate(TestCase):

#	def setUp(self):
#		self.template = ...

	def testSyntax(self):
		'''Test Template processing simple statements without page'''
		file = Buffer('''
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
''')

		result = u'''\
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
		test = Buffer()
		tmpl = GenericTemplate(file)
		#~ import pprint
		#~ pprint.pprint( tmpl.tokens )
		dict = { 'upper': TemplateFunction(lambda d, *a: a[0].upper()) }
		tmpl.process(dict, test)
		#~ print test.getvalue()
		self.assertEqualDiff(test.getvalue(), result)

	def testRaise(self):
		'''Test Template invalid syntax raises TemplateError'''
		#~ file = Buffer('foo[% ELSE %]bar')
		#~ try: Template(file, 'html')
		#~ except TemplateSyntaxError, error: print error
		file = Buffer('foo[% ELSE %]bar')
		self.assertRaises(TemplateSyntaxError, GenericTemplate, file)

		file = Buffer('foo[% FOREACH foo = ("1", "2", "3") %]bar')
		self.assertRaises(TemplateSyntaxError, GenericTemplate, file)

		file = Buffer('foo[% `echo /etc/passwd` %]bar')
		self.assertRaises(TemplateSyntaxError, GenericTemplate, file)

		file = Buffer('foo[% duss("ja") %]bar')
		templ = GenericTemplate(file)
		self.assertRaises(TemplateProcessError, templ.process, {}, Buffer())


class TestTemplateSet(TestCase):

	def runTest(self):
		'''Load all shipped templates for syntax check'''
		for dir, dirs, files in os.walk('./data/templates'):
			format = os.path.basename(dir)
			if format == 'templates':
				continue # skip top level dir
			files = [f for f in files if not f.startswith('.')]
			templates = list_templates(format)
			self.assertTrue(len(files) > 0)
			self.assertEqual(len(templates), len(files))
			for file in templates.values():
				#~ print files
				file = os.path.join(dir, file)
				tmpl = Template(file, format)
				# Syntax errors will be raised during init
				# TODO parameter check for these templates
				#      ... run them with raise instead of param = None


class TestPageProxy(TestCase):

	def runTest(self):
		page = tests.get_test_page(':FooBar')
		page.set_text('wiki', '''\
====== Page Heading ======
**foo bar !**
''')
		self.assertTrue(len(page.get_text('html')) > 0)
		proxy = PageProxy(page, zim.formats.get_format('html'))
		self.assertEqual(proxy.name, page.name)
		self.assertEqual(proxy.namespace, page.namespace)
		self.assertEqual(proxy.basename, page.basename)
		self.assertTrue(isinstance(proxy.properties, dict))
		self.assertTrue(len(proxy.body) > 0)
		# TODO add othermethods

class TestTemplate(TestCase):

	def runTest(self):
		file = Buffer(u'''\
<title>[% page.title %]</title> FIXME
<h1>[% page.name %]</h1>
<h2>[% page.heading %]</h2> FIXME
[% page.body %]
''' )
		result = u'''\
<title>FooBar</title> FIXME
<h1>FooBar</h1>
<h2></h2> FIXME
<h1>Page Heading</h1>
<p>
<strong>foo bar !</strong>
</p>

'''
		page = tests.get_test_page(':FooBar')
		page.set_text('wiki', '''\
====== Page Heading ======
**foo bar !**
''')
		self.assertTrue(len(page.get_text('html')) > 0)
		output = Buffer()
		Template(file, 'html').process(page, output)
		self.assertEqualDiff(output.getvalue(), result)
