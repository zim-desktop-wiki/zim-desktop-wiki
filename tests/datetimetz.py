# -*- coding: utf-8 -*-

# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement

import tests

import warnings

import zim.datetimetz as datetime


class TestDateTimeZ(tests.TestCase):

	# FIXME would be better to test correctness of results
	#       but first check functions do not give errors

	def setUp(self):
		with warnings.catch_warnings():
			warnings.simplefilter("ignore")
			try:
				import babel
			except ImportError:
				pass

	def runTest(self):
		# now()
		dt = datetime.now()
		s = dt.isoformat()
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		s = dt.strftime("%z")
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		s = dt.strftime("%Z")
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		# strftime
		s = datetime.strftime('%a', dt)
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		s = datetime.strftime('%%', dt)
		self.assertEqual(s, '%')

		s = datetime.strftime('%u', dt)
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		s = datetime.strftime('%V', dt)
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		# strfcal
		s = datetime.strfcal('%w', dt)
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		s = datetime.strfcal('%W', dt)
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		s = datetime.strfcal('%Y', dt)
		self.assertTrue(isinstance(s, basestring) and len(s) > 0)

		s = datetime.strfcal('%%', dt)
		self.assertEqual(s, '%')

		# weekcalendar
		year, week, weekday = datetime.weekcalendar(dt)
		self.assertTrue(isinstance(year, int) and 1900 < year and 3000 > year)
		self.assertTrue(isinstance(week, int) and 1 <= week and 53 >= week)
		self.assertTrue(isinstance(weekday, int) and 1 <= weekday and 7 >= weekday)

		# dates_for_week
		start, end = datetime.dates_for_week(year, week)
		self.assertTrue(isinstance(start, datetime.date))
		self.assertTrue(isinstance(end, datetime.date))
		self.assertTrue(start <= dt.date() and end >= dt.date())
