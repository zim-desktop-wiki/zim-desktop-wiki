
# Copyright 2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
Functions to match and parse dates in wiki pages

The following unambigous date forms are supported:
* Day by date using: yyyy-mm-dd  for example 2017-02-16
* Month using: yyyy-mm for example 2017-02
* Week using: (yy)yyWww or (yy)yy-Www, for example 2017W07, 17W07 or 17-W07
* Day by week using  (yy)yyWww(D) or (yy)yy-Www(-D) for example 17-W07-2 for Tuesday
* Week and day by week notation can also use Wkyyww(.D) for example wk1707

To avoid confusion between mm/dd, dd/mm and yy-mm notations neither of
these is supported and the year should always be given in 4 digits.

When the year is shortened to two digits ("yy") it is always prefixed by "20",
so "01" becomes 2001 and "99" becomes 2099. For years starting with 19 (or any
other century) the ful four digit year needs to be used.

Notation is based on https://en.wikipedia.org/wiki/ISO_8601. Truncating the year
is not supported except for the week notation and separators ("-") are required
to avoid matching random other numbers. The "Wkyyww" notation is supported as
non-standard alternative.

Weeknumbers follow the iso calendar. However depending on locale Sunday can
either be the first day of the starting week or the last day of the ending week.
In the weekday notation this is made explicit by using "0" for sunday at the
start of the week and "7" for sunday at the end of the week. Thus the dates
"W1707.7" and "W1708.0" are the same day.
'''

# TODO: add alternative notation using month abbr "16 FEB 2017"


import re
import datetime

from zim.datetimetz import dates_for_week, weekcalendar


__all__ = ('date_re', 'parse_date', 'Month', 'Week', 'Day')


date_re = re.compile(
	'(?:'
	'\d{4}-\d{2}-\d{2}'
	'|\d{4}-\d{2}'
	'|(?:\d{2}|\d{4})-?[Ww][Kk]?\d{2}(?:-\d)?'
	'|[Ww][Kk]?(?:\d{2}|\d{4})\d{2}(?:[.-]\d)?'
	')(?![\w-])'
)


def parse_date(date):
	string = date.upper().replace('-', '').strip()
	if 'W' in string:
		string = string.replace('WK', '').replace('W', '').replace('.', '')
		if len(string) == 4: # yyww
			return Week(int(string[:2]) + 2000, int(string[2:4]))
		elif len(string) == 5: # yywwD
			return Day.new_from_weeknumber(int(string[:2]) + 2000, int(string[2:4]), int(string[4]))
		elif len(string) == 6: # yyyyww
			return Week(int(string[:4]), int(string[4:]))
		elif len(string) == 7: # yyyywwD
			return Day.new_from_weeknumber(int(string[:4]), int(string[4:6]), int(string[6]))
		else:
			raise ValueError('Could not parse: %s' % date)
	elif len(string) == 6: # yyyymm
		return Month(int(string[:4]), int(string[4:]))
	elif len(string) == 8: # yyyymmdd
		return Day(int(string[:4]), int(string[4:6]), int(string[6:]))
	else:
		raise ValueError('Could not parse: %s' % date)


class DateRange(object):

	def __repr__(self):
		return "<%s: %s>" % (self.__class__.__name__, str(self))


class Day(DateRange, datetime.date):

	@classmethod
	def new_from_weeknumber(cls, year, week, weekday):
		if not (isinstance(weekday, int) and 0 <= weekday <= 7):
			raise ValueError('Not a weekday: %i (must be between 0 and 7)' % weekday)

		start, end = dates_for_week(year, week)
		if start.isoweekday() == 1: # monday
			offset = weekday - 1
		else: # sunday
			offset = weekday

		if offset != 0:
			start = start + datetime.timedelta(days=offset)
		return cls(start.year, start.month, start.day)

	@property
	def first_day(self):
		return self

	@property
	def last_day(self):
		return self

	def weekcalendar(self):
		'''Returns (year, week, weekday)'''
		year, week, weekday = weekcalendar(self)
		if weekday == 1 and self.isoweekday() == 7:
			weekday = 0 # See module doc on weekday
		else:
			weekday = self.isoweekday()
		return year, week, weekday

	def weekformat(self):
		'''Format as iso-weeknumber and weekday "YYYY-Www-D"'''
		return '%s-W%s-%s' % self.weekcalendar()


class Week(DateRange):

	def __init__(self, year, week):
		self.year = year
		self.week = week
		self.first_day, self.last_day = dates_for_week(year, week)

	def __str__(self):
		return '%s-W%s' % (self.year, self.week)


class Month(DateRange):

	def __init__(self, year, month):
		self.year = year
		self.month = month
		self.first_day = datetime.date(year, month, 1)
			# ensures year and month are actually valid

	@property
	def last_day(self):
		if self.month < 12:
			return datetime.date(self.year, self.month + 1, 1) - datetime.timedelta(days=1)
		else:
			return datetime.date(self.year + 1, 1, 1) - datetime.timedelta(days=1)

	def __str__(self):
		return '%s-%s' % (self.year, self.month)
