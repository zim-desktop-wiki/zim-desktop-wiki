# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO merge classes include here back into parser.py

# TODO Split out in sub modules
#	templates/__init__.py		# Template & build_template()
#	templates/parser.py			# TemplateParser and TemplateTreeBuilder
#	templates/expressionparser.py
#	templates/expression.py		# TemplateExpression, param dict etc.
#	templates/functions.py		# strftime etc.

# TODO for properties dict, translate keys into valid param names (replace('-', '_'))
#      need PageProxy for those kind of things

# TODO for "days" property in calendar plugin, add arguments to set
# first and last day -- allow selecting work week only etc.

# TODO specific exception classes for errors in template parsing
#      and execution + report line & char in errors

# TODO add "DEFAULT" and "CALL" directives

# TODO add "and" and "or" keywords for expression
#      allow e.g. "IF loop.first and loop.last" to detect single page

# Supported sytax
#   [% .. %] and <!--[% .. %]-->
#
# Instructions:
#   GET
#   SET
#   IF expr EL(S)IF expr .. ELSE .. END
#   FOR var IN expr .. END
#   FOREACH var = expr ... END
#   FOREACH var IN expr ... END
#   BLOCK name .. END
#   INCLUDE name or expr -- block or file
#
# Expressions can be:
#	True, False, None
#   "string", 'string', 5, 5.0
#   [.., .., ..]
#	parameter.name, mylist.0
#	function(.., ..)
#	.. operator ..
#
# Operators can be:
#	==, !=, >, >=, <, <=
#
# Note that BLOCKS are always defined in the top level scope
# so you not have them e.g. in an IF clause to define alternative versions.
# BLOCKS may be defined after the location where they are used.
#
# Within a loop, special parameter "loop" is defined with following
# attributes:
# 	loop.first		True / False
# 	loop.last		True / False
# 	loop.parity		"even" or "odd"
# 	loop.even		True / False
# 	loop.odd		True / False
#	loop.size		n
#	loop.max		n-1
#	loop.index		0 .. n-1
# 	loop.count		1 .. n
# 	loop.outer		outer "loop" or None
#	loop.prev		previous item or None
#	loop.next		next item or None

# Document:
# * all of the above
# * that we follow template toolkit syntax, but not full implementation
#   and especially not perl style implicite behavior
#   e.g. calling methods without ()
#   or calling methods by assigning with "="
# * valid param names
# * internal functions - TODO strftime / html_encode / url_encode / ...
# * methods callable on string / dict / list


import logging

logger = logging.getLogger('zim.templates')


from zim.templates.parser import TemplateParser
from zim.templates.processor import TemplateProcessor, TemplateContextDict
from zim.templates.functions import build_template_functions


class Template(object):
	'''This class defines the main interface for templates
	It takes care of parsing a template file and allows evaluating
	the template with a given set of template parameters.
	'''

	# On purpose a very thin class, allow to test all steps of parsing
	# and processing as individual classes

	# For templates that we define inline, use a file-like text buffer

	template_functions = build_template_functions()

	def __init__(self, file):
		'''Constructor
		@param file: a L{File} object for the template file
		'''
		self.filename = file.path
		self.parts = TemplateParser().parse(file.read())
		rdir = file.dir.subdir(file.basename[:-5]) # XXX strip extension, .html here
		if rdir.exists():
			self.resources_dir = rdir
		else:
			self.resources_dir = None

	def process(self, output, context):
		'''Evaluate the template
		@param output: an object that has an C{append()} method (e.g. a C{list})
		to receive the output text
		@param context: a C{dict} with a set of template parameters.
		This dict is copied to prevent changes to the original dict when
		processing the template
		'''
		context = TemplateContextDict(dict(context)) # COPY to keep changes local
		context.update(self.template_functions) # set builtins
		#~ import pprint; pprint.pprint(context)
		processor = TemplateProcessor(self.parts)
		processor.process(output, context)

