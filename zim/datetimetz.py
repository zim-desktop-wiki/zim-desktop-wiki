# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# Thin wrapper for standard library datetime, provides current timezone info
# Based on example code from standard library datetime documentation.

from datetime import *

def now():
	'''Like standard datetime.now() but with local timezone info'''
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



if __name__ == '__main__':
	print 'NOW:', now().isoformat()
