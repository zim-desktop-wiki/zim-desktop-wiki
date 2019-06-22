
# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>




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
		self.assertTrue(isinstance(s, str) and len(s) > 0)

		s = dt.strftime("%z")
		self.assertTrue(isinstance(s, str) and len(s) > 0)

		s = dt.strftime("%Z")
		self.assertTrue(isinstance(s, str) and len(s) > 0)

		# strftime
		s = datetime.strftime('%a', dt)
		self.assertTrue(isinstance(s, str) and len(s) > 0)

		s = datetime.strftime('%%', dt)
		self.assertEqual(s, '%')

		# Failed under msys python3.7.2
		#s = datetime.strftime('%u', dt)
		#self.assertTrue(isinstance(s, str) and len(s) > 0)

		#s = datetime.strftime('%V', dt)
		#self.assertTrue(isinstance(s, str) and len(s) > 0)

		# strfcal
		s = datetime.strfcal('%w', dt)
		self.assertTrue(isinstance(s, str) and len(s) > 0)

		s = datetime.strfcal('%W', dt)
		self.assertTrue(isinstance(s, str) and len(s) > 0)

		s = datetime.strfcal('%Y', dt)
		self.assertTrue(isinstance(s, str) and len(s) > 0)

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


from zim.plugins.tasklist.dates import *

class TestDateParsing(tests.TestCase):

	def testParsing(self):
		date = datetime.date(2017, 3, 27)
		for text in (
			'2017-03-27', '2017-03',
			'2017-W13', '2017-W13-1',
			'2017W13', '2017W13-1',
			'2017w13', '2017w13-1',
			'W1713', 'W1713-1', 'W1713.1',
			'Wk1713', 'Wk1713-1', 'Wk1713.1',
			'wk1713', 'wk1713-1', 'wk1713.1',
		):
			m = date_re.match(text)
			self.assertIsNotNone(m, 'Failed to match: %s' % text)
			self.assertEqual(m.group(0), text)
			obj = parse_date(m.group(0))
			self.assertIsInstance(obj, (Day, Week, Month))
			self.assertTrue(obj.first_day <= date <= obj.last_day)

		for text in (
			'foo', '123foo', '2017-03-270',
			'20170317', '17-03-27', '17-03'
			'17W', '2017W131', '2017-W131'
		):
			m = date_re.match(text)
			if m:
				print('>>', m.group(0))
			self.assertIsNone(m, 'Did unexpectedly match: %s' % text)

	def testWeekNumber(self):
		self.assertEqual(
			Day(2017, 3, 27),
			Day.new_from_weeknumber(2017, 13, 1)
		)
		self.assertEqual(
			Day(2017, 3, 27).weekformat(),
			('2017-W13-1')
		)
		self.assertEqual(
			Day.new_from_weeknumber(2017, 13, 7),
			Day.new_from_weeknumber(2017, 14, 0)
		)
