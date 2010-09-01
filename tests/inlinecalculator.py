
# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import tests
from tests import TestCase

import zim.plugins
from zim.config import ConfigDict


class TestPrintToBrowser(TestCase):

	slowTest = True

	def runTest(self):
		'Test InlineCalculator plugin'
		ui = StubUI()
		pluginklass = zim.plugins.get_plugin('inlinecalculator')
		plugin = pluginklass(ui)

		for text, wanted in (
			('3 + 4 =', '3 + 4 = 7'),
			('3 + 4 = 1', '3 + 4 = 7'),
			('3 + 4 = 1 ', '3 + 4 = 7 '),
			('10 / 3 =', '10 / 3 = 3.33333333333'), # divide integers to float !
			('milage: 3 + 4 =', 'milage: 3 + 4 = 7'),
			('3 + 4 = 7 + 0.5 =  ', '3 + 4 = 7 + 0.5 = 7.5'),
			('''\
5.5
 4.3
3.1
--- +
''',

			'''\
5.5
 4.3
3.1
--- +
12.9
'''			),
		):
			result = plugin.process_text(text)
			self.assertEqual(result, wanted)
		

		self.assertRaises(NameError, plugin.process_text, 'open("/etc/passwd")') # global
		self.assertRaises(NameError, plugin.process_text, 'self') # local


class StubUI(object):

	ui_type = 'stub'

	def __init__(self):
		self.notebook = tests.get_test_notebook()		
		self.preferences = ConfigDict()
		self.uistate = ConfigDict()
	
	def connect(*a): pass

	def connect_after(*a): pas
