# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.templates module.'''

import tests

import os

import zim
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

		self.assertRaises(TemplateSyntaxError, TemplateParam, '_settings.foo')
		self.assertRaises(TemplateSyntaxError, TemplateParam, 'xxx._yyy.zzz')
		self.assertRaises(TemplateSyntaxError, TemplateParam, 'xxx.y-y.zzz')


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
<h1>[% notebook.name %]: [% page.name %]</h1>
<h2>[% page.heading %]</h2>
[% page.body %]
'''
		wantedresult = u'''\
Version %s
<title>Page Heading</title>
<h1>Unnamed Notebook: FooBar</h1>
<h2>Page Heading</h2>
<p>
<strong>foo bar !</strong><br>
</p>

''' % zim.__version__
		notebook = tests.new_notebook()
		page = notebook.get_page(Path('FooBar'))
		page.parse('wiki', '''\
====== Page Heading ======
**foo bar !**
''')
		self.assertTrue(len(page.dump('html', linker=StubLinker())) > 0)
		result = Template(input, 'html', linker=StubLinker()).process(Notebook(), page)
		self.assertEqual(result, wantedresult.splitlines(True))

		# Check new page template
		notebook = tests.new_notebook()
		page = notebook.get_page(Path('Some New None existing page'))
		template = notebook.get_template(page)
		tree = template.process_to_parsetree(notebook, page) # No linker !
		self.assertEqual(tree.find('h').text, u'Some New None existing page')

class TestTemplatePageMenu(tests.TestCase):
	def runTest(self):
		# menu(root, collapse, ignore_empty)
		data = (
# Test default settings
(u"[% menu() %]", '''\
<ul>
<li><a href="page://Parent" title="Parent">Parent</a></li>
<ul>
<li><strong>Daughter</strong></li>
<ul>
<li><a href="page://Parent:Daughter:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Daughter:Grandson" title="Grandson">Grandson</a></li>
</ul>
<li><a href="page://Parent:Son" title="Son">Son</a></li>
</ul>
<li><a href="page://roundtrip" title="roundtrip">roundtrip</a></li>
<li><a href="page://TODOList" title="TODOList">TODOList</a></li>
<li><a href="page://TrashMe" title="TrashMe">TrashMe</a></li>
</ul>
'''),
# Collapsing turned off
(u"[% menu(':', FALSE, TRUE) %]", '''\
<ul>
<li><a href="page://Parent" title="Parent">Parent</a></li>
<ul>
<li><strong>Daughter</strong></li>
<ul>
<li><a href="page://Parent:Daughter:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Daughter:Grandson" title="Grandson">Grandson</a></li>
</ul>
<li><a href="page://Parent:Son" title="Son">Son</a></li>
<ul>
<li><a href="page://Parent:Son:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Son:Grandson" title="Grandson">Grandson</a></li>
</ul>
</ul>
<li><a href="page://roundtrip" title="roundtrip">roundtrip</a></li>
<li><a href="page://TODOList" title="TODOList">TODOList</a></li>
<ul>
<li><a href="page://TODOList:bar" title="bar">bar</a></li>
<li><a href="page://TODOList:foo" title="foo">foo</a></li>
</ul>
<li><a href="page://TrashMe" title="TrashMe">TrashMe</a></li>
<ul>
<li><a href="page://TrashMe:sub page 1" title="sub page 1">sub page 1</a></li>
<li><a href="page://TrashMe:sub page 2" title="sub page 2">sub page 2</a></li>
</ul>
</ul>
'''),
# Empty pages are not ignored
(u"[% menu(':', TRUE, FALSE) %]", '''\
<ul>
<li><a href="page://Bar" title="Bar">Bar</a></li>
<li><a href="page://foo" title="foo">foo</a></li>
<li><a href="page://Linking" title="Linking">Linking</a></li>
<li><a href="page://Parent" title="Parent">Parent</a></li>
<ul>
<li><a href="page://Parent:Child" title="Child">Child</a></li>
<li><strong>Daughter</strong></li>
<ul>
<li><a href="page://Parent:Daughter:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Daughter:Grandson" title="Grandson">Grandson</a></li>
<li><a href="page://Parent:Daughter:SomeOne" title="SomeOne">SomeOne</a></li>
</ul>
<li><a href="page://Parent:Son" title="Son">Son</a></li>
</ul>
<li><a href="page://roundtrip" title="roundtrip">roundtrip</a></li>
<li><a href="page://Test" title="Test">Test</a></li>
<li><a href="page://TODOList" title="TODOList">TODOList</a></li>
<li><a href="page://TrashMe" title="TrashMe">TrashMe</a></li>
<li><a href="page://utf8" title="utf8">utf8</a></li>
</ul>
'''),
# Both
(u"[% menu(':', FALSE, FALSE) %]", '''\
<ul>
<li><a href="page://Bar" title="Bar">Bar</a></li>
<li><a href="page://foo" title="foo">foo</a></li>
<ul>
<li><a href="page://foo:bar" title="bar">bar</a></li>
</ul>
<li><a href="page://Linking" title="Linking">Linking</a></li>
<ul>
<li><a href="page://Linking:Dus" title="Dus">Dus</a></li>
<ul>
<li><a href="page://Linking:Dus:Ja" title="Ja">Ja</a></li>
</ul>
<li><a href="page://Linking:Foo" title="Foo">Foo</a></li>
<ul>
<li><a href="page://Linking:Foo:Bar" title="Bar">Bar</a></li>
<ul>
<li><a href="page://Linking:Foo:Bar:Baz" title="Baz">Baz</a></li>
</ul>
</ul>
</ul>
<li><a href="page://Parent" title="Parent">Parent</a></li>
<ul>
<li><a href="page://Parent:Child" title="Child">Child</a></li>
<ul>
<li><a href="page://Parent:Child:Grandchild" title="Grandchild">Grandchild</a></li>
</ul>
<li><strong>Daughter</strong></li>
<ul>
<li><a href="page://Parent:Daughter:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Daughter:Grandson" title="Grandson">Grandson</a></li>
<li><a href="page://Parent:Daughter:SomeOne" title="SomeOne">SomeOne</a></li>
<ul>
<li><a href="page://Parent:Daughter:SomeOne:Bar" title="Bar">Bar</a></li>
<li><a href="page://Parent:Daughter:SomeOne:Foo" title="Foo">Foo</a></li>
</ul>
</ul>
<li><a href="page://Parent:Son" title="Son">Son</a></li>
<ul>
<li><a href="page://Parent:Son:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Son:Grandson" title="Grandson">Grandson</a></li>
</ul>
</ul>
<li><a href="page://roundtrip" title="roundtrip">roundtrip</a></li>
<li><a href="page://Test" title="Test">Test</a></li>
<ul>
<li><a href="page://Test:foo" title="foo">foo</a></li>
<ul>
<li><a href="page://Test:foo:bar" title="bar">bar</a></li>
</ul>
<li><a href="page://Test:Foo Bar" title="Foo Bar">Foo Bar</a></li>
<ul>
<li><a href="page://Test:Foo Bar:Dus Ja Hmm" title="Dus Ja Hmm">Dus Ja Hmm</a></li>
</ul>
<li><a href="page://Test:tags" title="tags">tags</a></li>
<li><a href="page://Test:wiki" title="wiki">wiki</a></li>
</ul>
<li><a href="page://TODOList" title="TODOList">TODOList</a></li>
<ul>
<li><a href="page://TODOList:bar" title="bar">bar</a></li>
<li><a href="page://TODOList:foo" title="foo">foo</a></li>
</ul>
<li><a href="page://TrashMe" title="TrashMe">TrashMe</a></li>
<ul>
<li><a href="page://TrashMe:sub page 1" title="sub page 1">sub page 1</a></li>
<li><a href="page://TrashMe:sub page 2" title="sub page 2">sub page 2</a></li>
</ul>
<li><a href="page://utf8" title="utf8">utf8</a></li>
<ul>
<li><a href="page://utf8:αβγ" title="αβγ">αβγ</a></li>
<li><a href="page://utf8:בדיקה" title="בדיקה">בדיקה</a></li>
<ul>
<li><a href="page://utf8:בדיקה:טכניון" title="טכניון">טכניון</a></li>
<ul>
<li><a href="page://utf8:בדיקה:טכניון:הנדסת מכונות" title="הנדסת מכונות">הנדסת מכונות</a></li>
<li><a href="page://utf8:בדיקה:טכניון:מדעי המחשב" title="מדעי המחשב">מדעי המחשב</a></li>
</ul>
</ul>
<li><a href="page://utf8:中文" title="中文">中文</a></li>
</ul>
</ul>
'''),
# Let's chenge the root
(u"[% menu(page, FALSE) %]", '''\
<ul>
<li><a href="page://Parent:Daughter:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Daughter:Grandson" title="Grandson">Grandson</a></li>
</ul>
'''),
(u"[% menu(page.name, FALSE, FALSE) %]", '''\
<ul>
<li><a href="page://Parent:Daughter:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Daughter:Grandson" title="Grandson">Grandson</a></li>
<li><a href="page://Parent:Daughter:SomeOne" title="SomeOne">SomeOne</a></li>
<ul>
<li><a href="page://Parent:Daughter:SomeOne:Bar" title="Bar">Bar</a></li>
<li><a href="page://Parent:Daughter:SomeOne:Foo" title="Foo">Foo</a></li>
</ul>
</ul>
'''),
(u"[% menu(page.namespace, FALSE, FALSE) %]", '''\
<ul>
<li><a href="page://Parent:Child" title="Child">Child</a></li>
<ul>
<li><a href="page://Parent:Child:Grandchild" title="Grandchild">Grandchild</a></li>
</ul>
<li><strong>Daughter</strong></li>
<ul>
<li><a href="page://Parent:Daughter:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Daughter:Grandson" title="Grandson">Grandson</a></li>
<li><a href="page://Parent:Daughter:SomeOne" title="SomeOne">SomeOne</a></li>
<ul>
<li><a href="page://Parent:Daughter:SomeOne:Bar" title="Bar">Bar</a></li>
<li><a href="page://Parent:Daughter:SomeOne:Foo" title="Foo">Foo</a></li>
</ul>
</ul>
<li><a href="page://Parent:Son" title="Son">Son</a></li>
<ul>
<li><a href="page://Parent:Son:Granddaughter" title="Granddaughter">Granddaughter</a></li>
<li><a href="page://Parent:Son:Grandson" title="Grandson">Grandson</a></li>
</ul>
</ul>
'''),
)

		notebook = notebook = tests.new_notebook()
		page = notebook.get_page(Path(':Parent:Daughter'))
		for input, wantedresult in data:
			result = Template(input, 'html', linker=StubLinker()).process(notebook, page)
			self.assertEqual(result, wantedresult.splitlines(True))

		

class StubLinker(object):

	def set_usebase(self, usebase): pass

	def set_path(self, path): pass

	def link(self, link): return '%s://%s' % (link_type(link), link)

	def img(self, src): return 'img://' + src

	def icon(self, name): return 'icon://' + name
