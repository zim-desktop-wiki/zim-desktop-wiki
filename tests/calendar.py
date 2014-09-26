# -*- coding: utf-8 -*-

# Copyright 2008,2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests


from datetime import date as dateclass

import zim.datetimetz

from zim.plugins import PluginManager
from zim.notebook import Path
from zim.templates import get_template
from zim.formats import get_dumper

from zim.plugins.calendar import NotebookExtension, \
	MainWindowExtensionDialog, MainWindowExtensionEmbedded, \
	CalendarDialog

from tests.gui import setupGtkInterface


class TestCalendarFunctions(tests.TestCase):

	def testDatesForWeeks(self):
		from zim.plugins.calendar import dates_for_week

		zim.datetimetz.FIRST_DAY_OF_WEEK = \
			zim.datetimetz.MONDAY
		start, end = dates_for_week(2012, 17)
		self.assertEqual(start, dateclass(2012, 4, 23)) # a monday
		self.assertEqual(end, dateclass(2012, 4, 29)) # a sunday

		zim.datetimetz.FIRST_DAY_OF_WEEK = \
			zim.datetimetz.SUNDAY
		start, end = dates_for_week(2012, 17)
		self.assertEqual(start, dateclass(2012, 4 ,22)) # a sunday
		self.assertEqual(end, dateclass(2012, 4, 28)) # a saturday

		start, end = dates_for_week(2013, 1)
		self.assertEqual(start, dateclass(2012, 12 ,30)) # a sunday
		self.assertEqual(end, dateclass(2013, 1, 5)) # a saturday

		start, end = dates_for_week(2009, 53)
		self.assertEqual(start, dateclass(2009, 12 ,27)) # a sunday
		self.assertEqual(end, dateclass(2010, 1, 2)) # a saturday

	def testWeekCalendar(self):
		from zim.plugins.calendar import weekcalendar
		sunday = dateclass(2012, 4 ,22)
		monday = dateclass(2012, 4, 23)
		nextsunday = dateclass(2012, 4, 29)

		zim.datetimetz.FIRST_DAY_OF_WEEK = \
			zim.datetimetz.MONDAY
		self.assertEqual(weekcalendar(sunday), (2012, 16, 7))
		self.assertEqual(weekcalendar(monday), (2012, 17, 1))
		self.assertEqual(weekcalendar(nextsunday), (2012, 17, 7))

		zim.datetimetz.FIRST_DAY_OF_WEEK = \
			zim.datetimetz.SUNDAY
		self.assertEqual(weekcalendar(sunday), (2012, 17, 1))
		self.assertEqual(weekcalendar(monday), (2012, 17, 2))
		self.assertEqual(weekcalendar(nextsunday), (2012, 18, 1))

		dec31 = dateclass(2012, 12, 31)
		jan1 = dateclass(2013, 1, 1)
		self.assertEqual(weekcalendar(dec31), (2013, 1, 2))
		self.assertEqual(weekcalendar(jan1), (2013, 1, 3))

		dec31 = dateclass(2009, 12, 31)
		jan1 = dateclass(2010, 1, 1)
		self.assertEqual(weekcalendar(dec31), (2009, 53, 5))
		self.assertEqual(weekcalendar(jan1), (2009, 53, 6))


	def testDateRangeFromPath(self):
		from zim.plugins.calendar import daterange_from_path

		# Day
		for path in (Path('Foo:2012:04:27'), Path('Foo:2012:4:27')):
			type, start, end = daterange_from_path(path)
			self.assertEqual(type, 'day')
			self.assertEqual(start, dateclass(2012, 4, 27))
			self.assertEqual(end, dateclass(2012, 4, 27))

		# Week
		zim.datetimetz.FIRST_DAY_OF_WEEK = \
			zim.datetimetz.MONDAY
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

	def testMainWindowExtensions(self):
		pluginklass = PluginManager.get_plugin_class('calendar')
		plugin = pluginklass()

		notebook = tests.new_notebook(self.get_tmp_name())
		ui = setupGtkInterface(self, notebook=notebook)

		plugin.preferences['embedded'] = True
		self.assertEqual(plugin.extension_classes['MainWindow'], MainWindowExtensionEmbedded)
		plugin.extend(ui.mainwindow)

		ext = list(plugin.extensions)
		self.assertEqual(len(ext), 1)
		self.assertIsInstance(ext[0], MainWindowExtensionEmbedded)

		plugin.preferences.changed() # make sure no errors are triggered

		ext[0].go_page_today()
		self.assertTrue(ui.page.name.startswith('Journal:'))

		plugin.preferences['embedded'] = False
		self.assertEqual(plugin.extension_classes['MainWindow'], MainWindowExtensionDialog)
		plugin.extend(ui.mainwindow) # plugin does not remember objects, manager does that

		ext = list(plugin.extensions)
		self.assertEqual(len(ext), 1)
		self.assertIsInstance(ext[0], MainWindowExtensionDialog)

		plugin.preferences.changed() # make sure no errors are triggered

		def test_dialog(dialog):
			self.assertIsInstance(dialog, CalendarDialog)
			dialog.do_today('xxx')
			ui.open_page(Path('foo'))

		with tests.DialogContext(test_dialog):
			ext[0].show_calendar()


		plugin.preferences['embedded'] = True # switch back

	def testNotebookExtension(self):
		pluginklass = PluginManager.get_plugin_class('calendar')
		plugin = pluginklass()

		notebook = tests.new_notebook(self.get_tmp_name())
		plugin.extend(notebook)

		ext = list(plugin.extensions)
		self.assertEqual(len(ext), 1)
		self.assertIsInstance(ext[0], NotebookExtension)

		page = Path('Foo')
		link = notebook.suggest_link(page, '2014-01-06')
		self.assertEqual(link.name, 'Journal:2014:01:06')

		link = notebook.suggest_link(page, 'foo')
		self.assertIsNone(link)

	def testNamespace(self):
		pluginklass = PluginManager.get_plugin_class('calendar')
		plugin = pluginklass()
		today = dateclass.today()
		for namespace in (Path('Calendar'), Path(':')):
			plugin.preferences['namespace'] = namespace
			path = plugin.path_from_date(today)
			self.assertTrue(isinstance(path, Path))
			self.assertTrue(path.ischild(namespace))
			date = plugin.date_from_path(path)
			self.assertTrue(isinstance(date, dateclass))
			self.assertEqual(date, today)

		from zim.plugins.calendar import DAY, WEEK, MONTH, YEAR
		zim.datetimetz.FIRST_DAY_OF_WEEK = \
			zim.datetimetz.MONDAY
		plugin.preferences['namespace'] = Path('Calendar')
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

	def testTemplate(self):
		pluginklass = PluginManager.get_plugin_class('calendar')
		plugin = pluginklass()
		plugin.preferences['namespace'] = Path('Calendar')

		notebook = tests.new_notebook()
		plugin.extend(notebook)

		dumper = get_dumper('wiki')

		zim.datetimetz.FIRST_DAY_OF_WEEK = \
			zim.datetimetz.MONDAY
		for path in (
			Path('Calendar:2012'),
			Path('Calendar:2012:04:27'),
			Path('Calendar:2012:Week 17'),
			Path('Calendar:2012:04'),
		):
			tree = notebook.get_template(path)
			lines = dumper.dump(tree)
			#~ print lines
			self.assertTrue(not 'Created' in ''.join(lines)) # No fall back
			if 'Week' in path.name:
				days = [l for l in lines if l.startswith('=== ')]
				self.assertEqual(len(days), 7)
