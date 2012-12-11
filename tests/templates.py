# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
			self.assertEqual([t[1] for t in templates], files)
			for file in files:
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
<strong>foo bar !</strong><br>
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
		self.assertEqual(tree.find('h').text, u'Some New None existing page')

class TestTemplatePageIndexFuntion(tests.TestCase):

	def runTest(self):
		# pageindex(root, collapse, ignore_empty)
		self.maxDiff = None

		data = (
('Parent:Daughter', u"[% pageindex('Parent') %]", '''\
<ul>
<li><a href="page://:Parent:Child" title="Child" class="page">Child</a></li>
<li><strong class="activepage">Daughter</strong></li>
<ul>
<li><a href="page://:Parent:Daughter:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Daughter:Grandson" title="Grandson" class="page">Grandson</a></li>
<li><a href="page://:Parent:Daughter:SomeOne" title="SomeOne" class="page">SomeOne</a></li>
</ul>
<li><a href="page://:Parent:Son" title="Son" class="page">Son</a></li>
</ul>
'''),

('Parent:Daughter:SomeOne', u"[% pageindex('Parent') %]", '''\
<ul>
<li><a href="page://:Parent:Child" title="Child" class="page">Child</a></li>
<li><a href="page://:Parent:Daughter" title="Daughter" class="page">Daughter</a></li>
<ul>
<li><a href="page://:Parent:Daughter:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Daughter:Grandson" title="Grandson" class="page">Grandson</a></li>
<li><strong class="activepage">SomeOne</strong></li>
<ul>
<li><a href="page://:Parent:Daughter:SomeOne:Bar" title="Bar" class="page">Bar</a></li>
<li><a href="page://:Parent:Daughter:SomeOne:Foo" title="Foo" class="page">Foo</a></li>
</ul>
</ul>
<li><a href="page://:Parent:Son" title="Son" class="page">Son</a></li>
</ul>
'''),

('Parent:Daughter:SomeOne', u"[% pageindex('Parent', FALSE, FALSE) %]", '''\
<ul>
<li><a href="page://:Parent:Child" title="Child" class="page">Child</a></li>
<ul>
<li><a href="page://:Parent:Child:Grandchild" title="Grandchild" class="page">Grandchild</a></li>
</ul>
<li><a href="page://:Parent:Daughter" title="Daughter" class="page">Daughter</a></li>
<ul>
<li><a href="page://:Parent:Daughter:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Daughter:Grandson" title="Grandson" class="page">Grandson</a></li>
<li><strong class="activepage">SomeOne</strong></li>
<ul>
<li><a href="page://:Parent:Daughter:SomeOne:Bar" title="Bar" class="page">Bar</a></li>
<li><a href="page://:Parent:Daughter:SomeOne:Foo" title="Foo" class="page">Foo</a></li>
</ul>
</ul>
<li><a href="page://:Parent:Son" title="Son" class="page">Son</a></li>
<ul>
<li><a href="page://:Parent:Son:Granddaughter" title="Granddaughter" class="page">Granddaughter</a></li>
<li><a href="page://:Parent:Son:Grandson" title="Grandson" class="page">Grandson</a></li>
</ul>
</ul>
'''),
		)

		notebook = tests.new_notebook()
		for path, input, wantedresult in data:
			page = notebook.get_page(Path(path))
			result = Template(input, 'html', linker=StubLinker()).process(notebook, page)
			self.assertEqual(result, wantedresult.splitlines(True))


class StubLinker(object):

	def set_usebase(self, usebase): pass

	def set_path(self, path): pass

	def link(self, link): return '%s://%s' % (link_type(link), link)

	def img(self, src): return 'img://' + src

	def icon(self, name): return 'icon://' + name
