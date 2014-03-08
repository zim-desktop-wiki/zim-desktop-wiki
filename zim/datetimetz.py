# -*- coding: utf-8 -*-

# Copyright 2010-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Thin wrapper for 'datetime' module from the standard library.
Provides timezone info for the local time. Based on example code
from standard library datetime documentation.

Main usage of this module is the function L{now()}. It imports all
from the standard datetime, so it can be used as a transparant
replacement.

Also adds a L{strfcal()} method and extends L{strftime()} to deal
with weeknumbers correctly.
'''

import re

from datetime import *

import logging

logger = logging.getLogger('zim')


def now():
	'''Like C{datetime.now()} but with local timezone info'''
	# Also setting microsecond to zero, to give isoformat() a nicer look
	return datetime.now(LocalTimezone()).replace(microsecond=0)


# A class capturing the platform's idea of local time.

import time as _time

ZERO = timedelta(0)
STDOFFSET = timedelta(seconds = -_time.timezone)
if _time.daylight:
	DSTOFFSET = timedelta(seconds = -_time.altzone)
else:
	DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET

class LocalTimezone(tzinfo):
	'''Implementation of tzinfo with the current time zone, based on
	the platform's idea of local time
	'''

	def utcoffset(self, dt):
		if self._isdst(dt):
			return DSTOFFSET
		else:
			return STDOFFSET

	def dst(self, dt):
		if self._isdst(dt):
			return DSTDIFF
		else:
			return ZERO

	def tzname(self, dt):
		return _time.tzname[self._isdst(dt)]

	def _isdst(self, dt):
		tt = (dt.year, dt.month, dt.day,
			  dt.hour, dt.minute, dt.second,
			  dt.weekday(), 0, -1)
		stamp = _time.mktime(tt)
		tt = _time.localtime(stamp)
		return tt.tm_isdst > 0



# Initialize setting for first day of the week. This is locale
# dependent, and the gtk.Calendar widget already has good code to find it out.
# Unfortunately, the widget keeps that data private *%#*$()()*) !

MONDAY = 0 # iso calendar starts week at Monday
SUNDAY = 6
FIRST_DAY_OF_WEEK = None
def init_first_day_of_week():
	global FIRST_DAY_OF_WEEK
	try:
		import babel
		import locale
		mylocale = babel.Locale(locale.getdefaultlocale()[0])
		if mylocale.first_week_day == 0:
			FIRST_DAY_OF_WEEK = MONDAY
		else:
			FIRST_DAY_OF_WEEK = SUNDAY
		logger.debug('According to babel first day of week is %i', FIRST_DAY_OF_WEEK)
	except ImportError:
		# Fallback gleaned from gtkcalendar.c - hence the inconsistency
		# with weekday numbers in iso calendar...
		t = _("calendar:week_start:0")
		# T: Translate to "calendar:week_start:0" if you want Sunday to be the first day of the week or to "calendar:week_start:1" if you want Monday to be the first day of the week
		if t[-1] == '0':
			FIRST_DAY_OF_WEEK = SUNDAY
		elif t[-1] == '1':
			FIRST_DAY_OF_WEEK = MONDAY
		else:
			logger.warn("Whoever translated 'calendar:week_start:0' did so wrongly.")
			FIRST_DAY_OF_WEEK = SUNDAY


def dates_for_week(year, week):
	'''Returns the first and last day of the week for a given
	week number of a given year.
	@param year: year as int (e.g. 2012)
	@param week: week number as int (0 .. 53)
	@returns: a 2-tuple of:
	  - a C{datetime.date} object for the start date of the week
	  - a C{datetime.date} object for the end dateof the week

	@note: first day of the week can be either C{MONDAY} or C{SUNDAY},
	this is configured in C{FIRST_DAY_OF_WEEK} based on the locale.
	'''
	# Note that the weeknumber in the isocalendar does NOT depend on the
	# first day being Sunday or Monday, but on the first Thursday in the
	# new year. See datetime.isocalendar() for details.
	# If the year starts with e.g. a Friday, January 1st still belongs
	# to week 53 of the previous year.
	# Day of week in isocalendar starts with 1 for Mon and is 7 for Sun,
	# and week starts on Monday.
	if FIRST_DAY_OF_WEEK is None:
		init_first_day_of_week()

	jan1 = date(year, 1, 1)
	_, jan1_week, jan1_weekday = jan1.isocalendar()

	if FIRST_DAY_OF_WEEK == MONDAY:
		days = jan1_weekday - 1
		# if Jan 1 is a Monday, days is 0
	else:
		days = jan1_weekday
		# if Jan 1 is a Monday, days is 1
		# for Sunday it becomes 7 (or -1 week)

	if jan1_week == 1:
		weeks = week - 1
	else:
		# Jan 1st is still wk53 of the previous year
		weeks = week

	start = jan1 + timedelta(days=-days, weeks=weeks)
	end = start + timedelta(days=6)
	return start, end


def weekcalendar(date):
	'''Get the year, week number and week day for a specific date.
	Like C{datetime.date.isocalendar()} but takes into account
	C{FIRST_DAY_OF_WEEK} correctly.
	@param date: a C{datetime.date} or C{datetime.datetime} object
	@returns: a year, a week number and a weekday as integers
	The weekday numbering depends on locale, 1 is always first day
	of the week, either a Sunday or a Monday.
	'''
	# Both strftime %W and %U are not correct, they use differnt
	# week number count than the isocalendar. See datetime
	# module for details.
	# In short Jan 1st can still be week 53 of the previous year
	# So we can use isocalendar(), however this does not take
	# into accout FIRST_DAY_OF_WEEK, see comment in dates_for_week()
	if FIRST_DAY_OF_WEEK is None:
		init_first_day_of_week()

	year, week, weekday = date.isocalendar()

	if FIRST_DAY_OF_WEEK == SUNDAY and weekday == 7:
		# iso calendar gives us the week ending this sunday,
		# we want the next week
		monday = date + timedelta(days=1)
		year, week, weekday = monday.isocalendar()
	elif FIRST_DAY_OF_WEEK == SUNDAY:
		weekday += 1

	return year, week, weekday


def strfcal(format, date):
	'''Method similar to strftime, but dealing with the weeknumber,
	day of the week and the year of that week.

	Week 1 is the first week where the Thursday is in the new year. So e.g. the
	last day of 2012 is a Monday. And therefore the calendar week for 31 Dec 2012
	is already week 1 2013.

	The locale decides whether a week starts on Monday (as the ISO standard would have
	it) or on Sunday. So depending on your locale Sun 6 Jan 2013 is either still week
	1 or already the first day of week 2.

	Codes supported by this method:

	  - C{%w} is replaced by the weekday as a decimal number [1,7], with 1 representing
	    either Monday or Sunday depending on the locale
	  - C{%W} is replaced by the weeknumber depending on the locale
	  - C{%Y} is replaced by the year with century as a decimal number, the year depends
	    on the weeknumber depending on the locale
	  - C{%%} is replaced by %

	Difference between this method and strftime is that:

	  1. It uses locale to determine the first day of the week
	  2. It returns the year that goes with the weeknumber
	'''
	# TODO: may want to add version of the codes that allow forcing
	#       Monday or Sunday as first day, e.g. using %u %U %X and %v %V %Z

	year, week, weekday = weekcalendar(date)

	def replacefunc(matchobj):
		code = matchobj.group(0)
		if code == '%w':
			return str(weekday)
		elif code == '%W':
			return '%02d' % week
		elif code == '%Y':
			return str(year)
		elif code == '%%':
			return '%'
		else:
			return code # ignore unsupported codes

	return re.sub(r'\%.', replacefunc, format)


def strftime(format, date):
	'''Extended version of strftime that adds a few POSIX codes

	  - C{%u} is replaced by the weekday as a decimal number [1,7], with 1 representing Monday.
	  - C{%V} is replaced by the week number of the year (Monday as the first day of the week)
	    as a decimal number [01,53]. If the week containing 1 January has four or more days in
	    the new year, then it is considered week 1. Otherwise, it is the last week of the
	    previous year, and the next week is week 1.
	'''
	year, week, weekday = date.isocalendar()

	def replacefunc(matchobj):
		code = matchobj.group(0)
		if code == '%u':
			return str(weekday)
		elif code == '%V':
			return str(week)
		else:
			return code # ignore unsupported codes

	format = re.sub(r'\%.', replacefunc, format)
	return date.strftime(format)


if __name__ == '__main__': #pragma: no cover
	import gettext
	gettext.install('zim', None, unicode=True, names=('_', 'gettext', 'ngettext'))
	init_first_day_of_week()

	if FIRST_DAY_OF_WEEK == SUNDAY:
		print 'First day of week: Sunday'
	else:
		print 'First day of week: Monday'
	print 'Now:', now().isoformat(), strftime("%z, %Z", now())
	print 'Calendar:', strfcal('day %w of week %W %Y', now())
