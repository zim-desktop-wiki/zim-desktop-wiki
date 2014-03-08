# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO internal functions: strftime / strfcal / html_encode / url_encode / ...

from zim.templates.expression import ExpressionFunction

def build_template_functions():
	return {
		'len': ExpressionFunction(len),
		'sorted': ExpressionFunction(sorted),
		'reversed': ExpressionFunction(lambda i: list(reversed(i))),
		'range': ExpressionFunction(range),
		# TODO strftime, strfcal
	}
