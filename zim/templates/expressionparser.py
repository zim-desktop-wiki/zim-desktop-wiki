# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the parser to parse expressions in templates
and returns an L{Expression} object.
'''


import re
import operator
import ast


from zim.parser import ParserError

from zim.templates.expression import \
	ExpressionOperator, ExpressionUnaryOperator, \
	ExpressionLiteral, ExpressionParameter, \
	ExpressionList, ExpressionFunctionCall



class ExpressionSyntaxError(ParserError):
	pass


class ExpressionParser(object):
	'''Parser for expressions'''

	# This parser does not use the Parser / Builder architecture
	# as the expression format is not really suited for this kind
	# of block parser
	# Instead it is a simple parser that first splits text in tokens
	# and then consumes those tokens left-to-right while building
	# an object tree.

	# TODO keep character count to raise meaninful errors

	# Operator precedence: or -- and -- not -- <, <=, >, >=, <>, !=, ==
	operators = {
		'==':	operator.eq,
		'!=':	operator.ne,
		'>':	operator.gt,
		'>=':	operator.ge,
		'<':	operator.lt,
		'<=':	operator.le,
		'and':	operator.and_,
		'or':	operator.or_,
		'not':	operator.not_, # special case - unary operator
	}

	tokens = [',', '[', ']', '(', ')'] \
		+ [k for k in operators.keys() if not k.isalnum()]
		# Only inluding NON-alphanumeric operators here

	_param_re = re.compile(r'^[^\W\d_]\w*(\.[^\W_]\w*)*$')
		# like "name.name" but first char can not be "_"
		# digits are allowed after dot, since template assumes dot notation for list index as well..
		# FIXME for generic use make this configurable / subclass template specific version

	def __init__(self):
		tokens = map(re.escape, self.tokens)
		self._word_re = re.compile(
			r'''(
				'(\\'|[^'])*' |  # single quoted word
				"(\\"|[^"])*" |  # double quoted word
				[^\s'"%s]+    |  # word without spaces and token chars
				%s               # tokens are a word on their own
			)''' % (''.join(tokens), '|'.join(tokens)), re.X
		)

	def parse(self, string):
		'''Parse an expression
		@param string: the expression text
		@returns: an L{Expression} object
		'''
		tokens = self._tokenize(string)
		expr = self._parse(tokens)
		if tokens: # trailing stuff remaining
			raise ExpressionSyntaxError, 'Unexpected text after expression: %s' % tokens
		return expr

	def _tokenize(self, string):
		# custom version of split_quoted_strings
		string = string.strip()
		words = []
		m = self._word_re.match(string)
		while m:
			words.append(m.group(0))
			i = m.end()
			string = string[i:].lstrip()
			m = self._word_re.match(string)

		assert not string, '>> %s' % string
		return words

	def _parse(self, tokens):
		# Operator precedence: or, and, not, <, <=, >, >=, <>, !=, ==
		# so we start with parsing " ... or .. or .." and decent from there
		lexpr = self._parse_and(tokens)
		if tokens and tokens[0] == 'or':
			tokens.pop(0)
			rexpr = self._parse(tokens) # recurs
			return ExpressionOperator(operator.or_, lexpr, rexpr)
		else:
			return lexpr

	def _parse_and(self, tokens):
		# Handle "... and ... and ..."
		lexpr = self._parse_not(tokens)
		if tokens and tokens[0] == 'and':
			tokens.pop(0)
			rexpr = self._parse_and(tokens) # recurs
			return ExpressionOperator(operator.and_, lexpr, rexpr)
		else:
			return lexpr

	def _parse_not(self, tokens):
		# Handle "not ..."
		if not tokens:
			raise ExpressionSyntaxError, 'Unexpected end of expression'
		if tokens[0] == 'not':
			tokens.pop(0)
			rexpr = self._parse_comparison(tokens)
			return ExpressionUnaryOperator(operator.not_, rexpr)
		else:
			return self._parse_comparison(tokens)

	def _parse_comparison(self, tokens):
		# Handle "... op ..." where op is: <, <=, >, >=, <>, !=, ==
		lexpr = self._parse_statement(tokens)
		if tokens and tokens[0] in self.operators \
		and tokens[0] not in ('or', 'and', 'not'):
			op = tokens.pop(0)
			rexpr = self._parse_statement(tokens)
			return ExpressionOperator(self.operators[op], lexpr, rexpr)
		else:
			return lexpr

	def _parse_statement(self, tokens):
		# Handle: param, func call or literal
		if not tokens:
			raise ExpressionSyntaxError, 'Unexpected end of expression'
		if tokens[0] == '[':
			return self._parse_list(tokens)
		elif tokens[0] in self.tokens \
		or tokens[0] in ('or', 'and', 'not'):
			raise ExpressionSyntaxError, 'Unexpected token: "%s"' % tokens[0]
		elif self._param_re.match(tokens[0]) \
		and not tokens[0] in ('True', 'False', 'None'):
			param = ExpressionParameter(tokens.pop(0))
			if tokens and tokens[0] == '(':
				args = self._parse_list(tokens)
				return ExpressionFunctionCall(param, args)
			else:
				return param
		else:
			text = tokens.pop(0)
			try:
				value = ast.literal_eval(text)
			except SyntaxError:
				raise ExpressionSyntaxError, 'Invalid literal: %s' % text
			else:
				return ExpressionLiteral(value)

	def _parse_list(self, tokens):
		# Process left to right, allow descending in sub lists
		assert tokens[0] in ('[', '(')
		delim = ']' if tokens.pop(0) == '[' else ')'
		expr = ExpressionList()
		while tokens and tokens[0] != delim:
			item = self._parse(tokens)
			if tokens and tokens[0] != delim:
				if tokens.pop(0) != ',':
					raise ExpressionSyntaxError, 'Expected: ","'
			expr.append(item)

		if not tokens or tokens[0] != delim:
			raise ExpressionSyntaxError, 'Missing: "%s"' % delim
		else:
			tokens.pop(0)

		return expr

