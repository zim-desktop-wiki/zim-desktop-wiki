
# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests
from tests import TestCase

from datetime import date as dateclass

import zim.plugins
from zim.notebook import Path
from zim.config import ConfigDict


class TestCalendarPlugin(TestCase):

	slowTest = True

	def runTest(self):
		'Test Calendar plugin'
		ui = StubUI()
		pluginklass = zim.plugins.get_plugin('calendar')
		plugin = pluginklass(ui)
		today = dateclass.today()
		for namespace in (Path('Calendar'), Path(':')):
			plugin.preferences['namespace'] = namespace.name
			path = plugin.path_from_date(today)
			self.assertTrue(isinstance(path, Path))
			self.assertTrue(path.ischild(namespace))
			date = plugin.date_from_path(path)
			self.assertTrue(isinstance(date, dateclass))
			self.assertEqual(date, today)


class StubUI(object):

	ui_type = 'stub'

	def __init__(self):
		self.notebook = tests.get_test_notebook()
		self.page = self.notebook.get_page(Path('Test:foo'))
		self.preferences = ConfigDict()
		self.uistate = ConfigDict()
	
	def connect(*a): pass

	def connect_after(*a): pass
