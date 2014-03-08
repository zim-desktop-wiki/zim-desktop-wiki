# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>
#
# Inspired by and partially based on code from clac.py,
# Which is copyright 2009 Mark Borgerding and licensed under the GPL version 3

from __future__ import with_statement
from __future__ import division # We are doing math in this module ...


import logging
import re
import math
import cmath

from zim.plugins import PluginClass, extends, WindowExtension
from zim.actions import action
from zim.errors import Error


logger = logging.getLogger('zim.plugins.insertsymbol')


# helper functions
def dip(x):
	'demote, if possible, a complex to scalar'
	if type(x) == complex and x.imag == 0:
		return x.real
	else:
		return x

def which_call(x, mathfunc, cmathfunc, allowNegative=True):
	x=dip(x)
	if type(x) == complex or (allowNegative == False and x<0):
		return cmathfunc(x)
	else:
		return mathfunc(x)

# math functions defined here

def degrees(x):
	return x*180/math.pi

def radians(x):
	return x*math.pi/180

def log(x,b=math.e):
	'log(x[, base]) -> the logarithm of x to the given base.\nIf the base not specified, returns the natural logarithm (base e) of x.'
	if type(x) == complex or x<0:
		return dip( cmath.log(x) / cmath.log(b) )
	else:
		return math.log(x)/math.log(b)

def real(x):
	'return just the real portion'
	if type(x) == complex:
		return x.real
	else:
		return x

def imag(x):
	'return just the imaginary portion'
	if type(x) == complex:
		return x.imag
	else:
		return 0

def sign(x):
	'returns -1,0,1 for negative,zero,positive numbers'
	if x == 0:
		return 0
	elif x > 0:
		return 1
	else:
		return -1

def log2(x):
	'logarithm base 2'
	return log(x,2)

def gcd(x,y):
	'greatest common denominator'
	while x>0:
		(x,y) = (y%x,x) # Guido showed me this one on the geek cruise
	return y

def lcm(x,y):
	'least common multiple'
	return x*y/gcd(x,y)

def phase(z):
	'phase of a complex in radians'
	z=cpx(z)
	return math.atan2( z.imag , z.real )

def cpx(x):
	'convert a number or tuple to a complex'
	if type(x) == tuple:
		return complex( x[0] , x[1] )
	else:
		return complex(x)

def conj( x ):
	'complex conjugate'
	x = cpx( x )
	return complex( x.real , -x.imag )

def complexify(x,func ):
	'call func on the real and imaginary portions, creating a complex from the respective results'
	if type(x) == complex and x.imag != 0:
		return dip( complex( func(x.real) , func(x.imag) ) )
	else:
		return func(x)

# overwrite the built-in math functions that don't handle complex
def round(x):
	'nearest integer'
	if type(x) == complex:
		return complexify( x , round )
	else:
		return math.floor(x+.5)

def floor(x):
	'round towards negative infinity'
	return complexify( x , math.floor )

def ceil(x):
	'round towards positive infinity'
	return complexify( x , math.ceil )


# functions and constants available  within the safe eval construct
GLOBALS = {
	'__builtins__': None, # Don't allow open() etc.
	# builtins we want to keep
	'abs': abs,
	'ord': ord,
	'chr': unichr,
	'hex': hex,
	'oct': oct,
	'int': int,
	# direct imports
	'e': math.e,
	'pi': math.pi,
	'atan2': math.atan2,
	'fmod': math.fmod,
	'frexp': math.frexp,
	'hypot': math.hypot,
	'ldexp': math.ldexp,
	'modf': math.modf,
	# other nice-to-have constants
	'j': cmath.sqrt(-1),
	# marshall between the math and cmath functions automatically
	'acos': lambda x: which_call(x,math.acos,cmath.acos),
	'asin': lambda x: which_call(x,math.asin,cmath.asin),
	'atan': lambda x: which_call(x,math.atan,cmath.atan),
	'cos': lambda x: which_call(x,math.cos,cmath.cos),
	'cosh': lambda x: which_call(x,math.cosh,cmath.cosh),
	'sin': lambda x: which_call(x,math.sin,cmath.sin),
	'sinh': lambda x: which_call(x,math.sinh,cmath.sinh),
	'tan': lambda x: which_call(x,math.tan,cmath.tan),
	'tanh': lambda x: which_call(x,math.tanh,cmath.tanh),
	'exp': lambda x: which_call(x,math.exp,cmath.exp),
	'log10': lambda x: which_call(x,math.log10,cmath.log10,False),
	'sqrt': lambda x: which_call(x,math.sqrt,cmath.sqrt,False),
	# functions defined here
	'degrees': degrees,
	'radians': radians,
	'log': log,
	'real': real,
	'imag': imag,
	'sign': sign,
	'log2': log2,
	'gcd': gcd,
	'lcm': lcm,
	'phase': phase,
	'conj': conj,
	'round': round,
	'floor': floor,
	'ceil': ceil,
	# synonyms
	'mag': abs,
	'angle': phase,
}


class ExpressionError(Error):

	description = _(
		'The inline calculator plugin was not able\n'
		'to evaluate the expression at the cursor.' )
		# T: error description


_multiline_re = re.compile('--+\s+[+-]')
	# for multiline summation with "--- +" and similar


class InlineCalculatorPlugin(PluginClass):

	plugin_info = {
		'name': _('Inline Calculator'), # T: plugin name
		'description': _('''\
This plugin allows you to quickly evaluate simple
mathematical expressions in zim.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Inline Calculator',
	}

	#~ plugin_preferences = (
		# key, type, label, default
	#~ )


	def process_text(self, text):
		'''Takes a piece of text and parses it for expressions
		to evaluate. Returns the text with result inserted or replaced.
		Will raise an exception on errors.
		'''
		# This method is separated from eval_math() for easy testing

		if '\n' in text:
			return self._process_multiline(text)
		else:
			return self._process_line(text)

	def _process_line(self, line):
		# Check for non-math prefix
		prefix = ''
		if ':' in line:
			i = line.rindex(':') + 1
			prefix = line[:i]
			line = line[i:]

		# Allow for chaining like "1 + 2 = 3 + 0.5 = 3.5" etc.
		if line.count('=') > 1:
			parts = line.split('=')
			prefix += '='.join(parts[:-2]) + '='
			line = '='.join(parts[-2:])

		# Check for whitespace postfix after previous answer
		postfix = ''
		stripped = line.rstrip()
		if '=' in line \
		and stripped != line and not stripped.endswith('='):
			i = len(line) - len(stripped)
			postfix = line[-i:]
			line = stripped

		# Strip previous answer and '='
		if '=' in line:
			i = line.index('=')
			line = line[:i]

		result = self.safe_eval(line)

		return prefix + line + '= ' + str(result) + postfix

	def _process_multiline(self, text):
		lines = text.splitlines()
		for i, line in enumerate(lines):
			if _multiline_re.match(line):
				operator = line.strip()[-1]
				break
		else:
			raise ExpressionError, _('Could not parse expression')
				# T: error message

		sep = ' %s ' % operator
		expression = sep.join('(%s)' % l for l in lines[:i])
		result = self.safe_eval(expression)

		lines = lines[:i+1] + [str(result)]
		return '\n'.join(lines) + '\n'


	def safe_eval(self, expression):
		'''Safe evaluation of a python expression'''
		try:
			return eval(expression, GLOBALS, {})
		except Exception, error:
			msg = '%s: %s' % (error.__class__.__name__, error)
			raise ExpressionError, msg


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
		<ui>
		<menubar name='menubar'>
			<menu action='tools_menu'>
				<placeholder name='plugin_items'>
					<menuitem action='eval_math'/>
				</placeholder>
			</menu>
		</menubar>
		</ui>
	'''

	@action(_('Evaluate _Math')) # T: menu item
	def eval_math(self):
		'''Action called by the menu item or key binding,
		will look at the cursor for an expression to evaluate.
		'''
		buffer = self.window.pageview.view.get_buffer()
			# XXX- way to long chain of objects here

		# FIXME: what do we do for selections ?

		cursor = buffer.get_iter_at_mark(buffer.get_insert())
		start, end = buffer.get_line_bounds(cursor.get_line())
		line = buffer.get_text(start, end)

		if not line or line.isspace():
			# Empty line, look at previous line
			if cursor.get_line() > 1:
				start, end = buffer.get_line_bounds(cursor.get_line() - 1)
				cursor = end.copy()
				cursor.backward_char()
				line = buffer.get_text(start, end)
			else:
				return # silent fail

		if _multiline_re.match(line):
			# Search for start of block - iterate back to empty line
			lineno = cursor.get_line()
			while lineno > 1:
				mystart, myend = buffer.get_line_bounds(lineno)
				myline = buffer.get_text(mystart, myend)
				if not myline or myline.isspace():
					break
				else:
					start = mystart
					lineno -= 1
		else:
			# One line expression, just pass it on
			# FIXME skip forward past next word if any if last char is '='
			end = cursor

		orig = buffer.get_text(start, end)
		new = self.plugin.process_text(orig)
		with buffer.user_action:
			buffer.delete(start, end)
			buffer.insert_at_cursor(new)


