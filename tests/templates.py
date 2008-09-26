# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for the zim.templates module.'''

import unittest

from StringIO import StringIO
from zim import templates

class TestTemplate(unittest.TestCase):

#	def setUp(self):
#		self.template = ...

	def testprocess(self):
		'''Test Template processing simple statements without page'''
		file = StringIO('''
[% SET test  = "foo"  %]
[% SET true  = "true" %]
[% SET false = ""     %]
<b>[% test %]</b>
[% IF true %]OK[% ELSE %]NOK[% END %]
---
[% IF false %]
OK
[% ELSE %]
NOK
[% END %]
''')
		result = '''
<b>foo</b>
OK
---
NOK
'''
		test = StringIO()
		tmpl = templates.Template(file, 'html')
		#import pprint
		#pprint.pprint( tmpl.tokens )
		tmpl.process(None, test)
		self.assertEqual(test.getvalue(), result)

	def testraise(self):
		'''Test Template invalid syntax raises TemplateError'''
		file = StringIO('foo[% ELSE %]bar')
		self.assertRaises(templates.TemplateError,
								templates.Template, file, 'html')

if __name__ == '__main__':
	unittest.main()


