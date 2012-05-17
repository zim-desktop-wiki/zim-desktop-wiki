# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests


from datetime import date as dateclass

import zim.plugins
from zim.notebook import Path
from zim.config import ConfigDict


class TestCalendarFunctions(tests.TestCase):

	def testDatesForWeeks(self):
		from zim.plugins.calendar import dates_for_week

		zim.plugins.calendar.FIRST_DAY_OF_WEEK = \
			zim.plugins.calendar.MONDAY
		start, end = dates_for_week(2012, 17)
		self.assertEqual(start, dateclass(2012, 4, 23)) # a monday
		self.assertEqual(end, dateclass(2012, 4, 29)) # a sunday

		zim.plugins.calendar.FIRST_DAY_OF_WEEK = \
			zim.plugins.calendar.SUNDAY
		start, end = dates_for_week(2012, 17)
		self.assertEqual(start, dateclass(2012, 4 ,22)) # a sunday
		self.assertEqual(end, dateclass(2012, 4, 28)) # a saturday

	def testDateRangeFromPath(self):
		from zim.plugins.calendar import daterange_from_path

		# Day
		for path in (Path('Foo:2012:04:27'), Path('Foo:2012:4:27')):
			type, start, end = daterange_from_path(path)
			self.assertEqual(type, 'day')
			self.assertEqual(start, dateclass(2012, 4, 27))
			self.assertEqual(end, dateclass(2012, 4, 27))

		# Week
		zim.plugins.calendar.FIRST_DAY_OF_WEEK = \
			zim.plugins.calendar.MONDAY
		type, start, end = daterange_from_path(Path('Foo:2012:Week 17'))
		self.assertEqual(type, 'week')
		self.assertEqual(start, dateclass(2012, 4, 23)) # a monday
		self.assertEqual(end, dateclass(2012, 4, 29)) # a sunday

		# Month
		for path in (Path('Foo:2012:04'), Path('Foo:2012:4')):
			type, start, end = daterange_from_path(path)
			self.assertEqual(type, 'month')
			self.assertEqual(start, dateclass(2012, 4, 1))
			self.assertEqual(end, dateclass(2012, 4, 30))

		# Year
		type, start, end = daterange_from_path(Path('Foo:2012'))
		self.assertEqual(type, 'year')
		self.assertEqual(start, dateclass(2012, 1, 1))
		self.assertEqual(end, dateclass(2012, 12, 31))


@tests.slowTest
class TestCalendarPlugin(tests.TestCase):

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

		from zim.plugins.calendar import DAY, WEEK, MONTH, YEAR
		zim.plugins.calendar.FIRST_DAY_OF_WEEK = \
			zim.plugins.calendar.MONDAY
		plugin.preferences['namespace'] = 'Calendar'
		date = dateclass(2012, 4, 27)
		for setting, wanted, start in (
			(DAY, 'Calendar:2012:04:27', dateclass(2012, 4, 27)),
			(WEEK, 'Calendar:2012:Week 17', dateclass(2012, 4, 23)),
			(MONTH, 'Calendar:2012:04', dateclass(2012, 4, 1)),
			(YEAR, 'Calendar:2012', dateclass(2012, 1, 1)),
		):
			plugin.preferences['granularity'] = setting
			path = plugin.path_from_date(date)
			self.assertEqual(path.name, wanted)
			self.assertEqual(plugin.date_from_path(path), start)

		path = plugin.path_for_month_from_date(date)
		self.assertEqual(path.name, 'Calendar:2012:04')

# TODO test template function


class StubUI(object):

	ui_type = 'stub'

	def __init__(self):
		self.notebook = tests.new_notebook()
		self.page = self.notebook.get_page(Path('Test:foo'))
		self.preferences = ConfigDict()
		self.uistate = ConfigDict()

	def connect(*a): pass

	def connect_after(*a): pass
