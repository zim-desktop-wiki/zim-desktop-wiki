# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.templates module.'''

import tests
from tests import TestCase

import os

import zim
from zim.templates import *
from zim.templates import GenericTemplate, \
	TemplateParam, TemplateDict, TemplateFunction, PageProxy
from zim.notebook import Notebook
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
		self.assertEqualDiff(result, wantedresult.splitlines(True))

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


class TestTemplateSet(TestCase):

	def runTest(self):
		'''Load all shipped templates for syntax check'''
		for dir, dirs, files in os.walk('./data/templates'):
			format = os.path.basename(dir)
			if format == 'templates':
				continue # skip top level dir
			files = [f for f in files if not f.startswith('.') and not '~' in f]
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
		notebook, page = tests.get_test_page('FooBar')
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

class TestTemplate(TestCase):

	def runTest(self):
		input = u'''\
Version [% zim.version %]
<title>[% page.title %]</title>
<h1>[% page.name %]</h1>
<h2>[% page.heading %]</h2>
[% page.body %]
'''
		wantedresult = u'''\
Version %s
<title>Page Heading</title>
<h1>FooBar</h1>
<h2>Page Heading</h2>
<p>
<strong>foo bar !</strong><br>
</p>

''' % zim.__version__
		notebook, page = tests.get_test_page('FooBar')
		page.parse('wiki', '''\
====== Page Heading ======
**foo bar !**
''')
		self.assertTrue(len(page.dump('html', linker=StubLinker())) > 0)
		result = Template(input, 'html', linker=StubLinker()).process(Notebook(), page)
		self.assertEqualDiff(result, wantedresult.splitlines(True))

		# Check new page template
		notebook, page = tests.get_test_page('Some New None existing page')
		template = notebook.get_template(page)
		tree = template.process_to_parsetree(notebook, page) # No linker !
		self.assertEqualDiff(tree.find('/h').text, u'Some New None existing page')

		

class StubLinker(object):

	def set_usebase(self, usebase): pass

	def set_path(self, path): pass

	def link(self, link): return '%s://%s' % (link_type(link), link)

	def img(self, src): return 'img://' + src

	def icon(self, name): return 'icon://' + name
