# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains generic template functions.

In addition to the functions defined here, L{zim.export.template}
defines functions like C{resource()} and C{uri()} which require
knowledge about the templates destination file structure.
'''


import locale

import logging

logger = logging.getLogger('zim.templates')

from functools import partial

import zim.datetimetz as datetime

from zim.templates.expression import ExpressionFunction

from zim.formats.html import html_encode
from zim.parsing import url_encode, URL_ENCODE_DATA


def build_template_functions():
	return {
		'len': ExpressionFunction(len),
		'sorted': ExpressionFunction(sorted),
		'reversed': ExpressionFunction(lambda i: list(reversed(i))),
		'range': ExpressionFunction(range),
		'strftime': template_strftime,
		'strfcal': template_strfcal,
		'html_encode': ExpressionFunction(html_encode),
		'url_encode': ExpressionFunction(partial(url_encode, mode=URL_ENCODE_DATA)),
	}


@ExpressionFunction
def template_strftime(format, date=None):
	'''Template function wrapper for strftime'''
	format = str(format) # Needed to please datetime.strftime()
	try:
		if date is None:
			string = datetime.now().strftime(format)
		elif isinstance(date, (datetime.date, datetime.datetime)):
			string = date.strftime(format)
		else:
			raise Error, 'Not a datetime object: %s' % date

		return string.decode(locale.getpreferredencoding())
			# strftime returns locale as understood by the C api
			# unfortunately there is no guarantee we can actually
			# decode it ...
	except:
		logger.exception('Error in strftime "%s"', format)


@ExpressionFunction
def template_strfcal(format, date=None):
	'''Template function wrapper for strfcal'''
	format = str(format) # Needed to please datetime.strftime()
	try:
		if date is None:
			date = datetime.now()
		return datetime.strfcal(format, date)
	except:
		logger.exception('Error in strftime "%s"', format)
