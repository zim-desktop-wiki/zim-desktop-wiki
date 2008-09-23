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
		file = StringIO('''
[% SET test  = "foo"  %]
[% SET true  = "true" %]
[% SET false = ""     %]
<b>[% test %]</b>
[% IF true %]OK[% ELSE %]NOK[% END %]
''')
		result = '''
<b>foo</b>
OK
'''
		test = StringIO()
		tmpl = templates.Template(file, 'html')
		tmpl.process(None, test)
		self.assertEqual(test.getvalue(), result)

	def testraise(self):
		file = StringIO('foo[% ELSE %]bar')
		self.assertRaises(templates.TemplateError,
								templates.Template, file, 'html')

if __name__ == '__main__':
	unittest.main()


