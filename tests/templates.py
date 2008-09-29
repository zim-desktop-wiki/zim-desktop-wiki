# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.templates module.'''

import unittest
from StringIO import StringIO

import zim
from zim import templates

class TestTemplate(unittest.TestCase):

#	def setUp(self):
#		self.template = ...

	def testSyntax(self):
		'''Test Template processing simple statements without page'''
		file = StringIO('''
[% SET test  = "foo"  %]
[% SET true  = "true" %]
[% SET false = ""     %]
---
<b>[% test %]</b>
---
[% IF true %]OK[% ELSE %]NOK[% END %]
[% IF false %]
OK
[% ELSE %]
NOK
[% END %]
---
[% zim.version %]
---
[% FOREACH name = [ 'foo', 'bar', 'baz' ] -%]
	NAME = [% GET name %]
[%- END %]
---
[% numbers = ['1', '2', '3'] %]
[% FOREACH n IN numbers %][% n %]...[% END %]
---
''')

		result = '''
---
<b>foo</b>
---
OK
NOK
---
%s
---
	NAME = foo
	NAME = bar
	NAME = baz
---
1...2...3...
---
''' % zim.__version__
		test = StringIO()
		tmpl = templates.Template(file, 'html')
		#~ import pprint
		#~ pprint.pprint( tmpl.tokens )
		tmpl.process(None, test)
		#~ print test.getvalue()
		self.assertEqual(test.getvalue(), result)

	def testRaise(self):
		'''Test Template invalid syntax raises TemplateError'''
		file = StringIO('foo[% ELSE %]bar')
		self.assertRaises(templates.TemplateSyntaxError,
								templates.Template, file, 'html')
		file = StringIO('foo[% FOREACH foo = ("1", "2", "3") %]bar')
		self.assertRaises(templates.TemplateSyntaxError,
								templates.Template, file, 'html')
		file = StringIO('foo[% `echo /etc/passwd` %]bar')
		self.assertRaises(templates.TemplateSyntaxError,
								templates.Template, file, 'html')
