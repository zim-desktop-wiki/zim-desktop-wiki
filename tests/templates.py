# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.templates module.'''

from tests import TestCase

import os
from StringIO import StringIO

import zim
from zim.templates import *

class TestTemplate(TestCase):

#	def setUp(self):
#		self.template = ...

	def testSyntax(self):
		'''Test Template processing simple statements without page'''
		file = StringIO('''
[%- SET test  = "foo"  -%]
[%- SET true  = "true" -%]
[%- SET false = ""     -%]
---
<b>[% test %]</b>
---
[% IF true %]OK[% ELSE %]NOK[% END %]
[% IF false -%]
OK
[%- ELSE -%]
NOK
[%- END %]
---
[% zim.version %]
---
[% FOREACH name = [ 'foo', 'bar', 'baz' ] -%]
	NAME = [% GET name %]
[% END -%]
---
[% numbers = ['1', '2', '3'] -%]
[% FOREACH n IN numbers %][% n %]...[% END %]
---
''')

		result = '''\
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
		tmpl = Template(file, 'html')
		#~ import pprint
		#~ pprint.pprint( tmpl.tokens )
		tmpl.process(None, test)
		#~ print test.getvalue()
		self.assertEqualDiff(test.getvalue(), result)

	def testRaise(self):
		'''Test Template invalid syntax raises TemplateError'''
		#~ file = StringIO('foo[% ELSE %]bar')
		#~ try: Template(file, 'html')
		#~ except TemplateSyntaxError, error: print error
		file = StringIO('foo[% ELSE %]bar')
		self.assertRaises(TemplateSyntaxError, Template, file, 'html')

		file = StringIO('foo[% FOREACH foo = ("1", "2", "3") %]bar')
		self.assertRaises(TemplateSyntaxError, Template, file, 'html')

		file = StringIO('foo[% `echo /etc/passwd` %]bar')
		self.assertRaises(TemplateSyntaxError, Template, file, 'html')

	def testTemplateSet(self):
		'''Load all shipped templates for syntax check'''
		for dir, dirs, files in os.walk('./data/templates'):
			format = os.path.basename(dir)
			for file in files:
				file = os.path.join(dir, file)
				tmpl = Template(file, format)
				# Syntax errors will be raised during init
				# TODO parameter check for these templates
				#      ... run them with raise instead of param = None
