# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import re

from zim.parser import Parser, Rule, SimpleTreeBuilder, BuilderTextBuffer

from zim.templates.expressionparser import ExpressionParser, ExpressionParameter

class TemplateBuilderTextBuffer(BuilderTextBuffer):
	'''Sub class of L{BuilderTextBuffer} that is used to strip text
	around template instructions.
	'''

	_rstrip_re = re.compile(r'\n?[ \t]*$')
	_lstrip_re = re.compile(r'^[ \t]*\n?')

	def __init__(self, builder):
		BuilderTextBuffer.__init__(self, builder)
		self._lstrip_pending = False

	def text(self, text):
		BuilderTextBuffer.text(self, text)

	def flush(self):
		text = u''.join(self.buffer)

		if text and self._lstrip_pending:
			text = self._lstrip(text)

		if text:
			self.builder.text(text)

		self._lstrip_pending = False
		self.buffer = []

	def rstrip(self):
		'''Do an rstrip on last piece of text up to and including
		newline
		'''
		text = u''.join(self.buffer)
		if text:
			self.buffer = [self._rstrip(text)]

	def _rstrip(self, text):
		if text.endswith('\n'):
			return text[:-1]
		else:
			return self._rstrip_re.sub('', text)

	def lstrip(self):
		'''Flag that next piece of text needs to be lstripped up to
		and including newline
		'''
		self._lstrip_pending = True

	def _lstrip(self, text):
		return self._lstrip_re.sub('', text)


class TemplateTreeBuilder(SimpleTreeBuilder):

	def __init__(self):
		SimpleTreeBuilder.__init__(self)

	def start(self, tag, attrib=None):
		# Special case for blocks - put them outside hierarchy
		if tag == 'BLOCK':
			element = self.elementfactory(tag, attrib, [])
			self.root.append(element)
			self.stack.append(element)
		else:
			# Check IF / ELIF / ELSE occur in right sequence
			if tag in ('ELIF', 'ELSE'):
				prev = self.stack[-1][-1]
				if not hasattr(prev, 'tag') \
				and prev.tag in ('IF', 'ELIF'):
					raise '%s block out of place' % tag

			SimpleTreeBuilder.start(self, tag, attrib)


class TemplateParser(object):

	# Build parse tree like:
	#  - text
	#  - IF expr=...
	#    - text
	#    - GET expr=...
	#    - text
	#  - ELIF expr= ..
	#    - text
	#  - text
	#
	# So:
	#   GET token: append
	#   IF token: start IF
	#   ELIF token: end IF (error if unmatched), start ELIF
	#   END token: end whatever is on the stack
	#
	# Keywords are case sensitive: must be upper case

	_set_token_re = re.compile(r'^([\w\.]+)\s*=\s*(.*)$') # var = expr

	_token_with_expr_re = re.compile(r'^(\w+)\s+(.*)$') # TOKEN expr

	_for_in_token_re = re.compile(r'^(\w+)\s+IN\s+(.*)$') # name IN expr

	_for_is_token_re = re.compile(r'^(\w+)\s*=\s*(.*)$') # name = expr

	_block_token_re = re.compile(r'^\w+$') # name

	_tokens_with_expr = (
		'GET', 'SET',
		'IF', 'ELIF', 'ELSIF', 'ELSE',
		'FOR', 'FOREACH',
		'BLOCK', 'INCLUDE',
		'END'
	)	# These tokens take an argument

	_tokens_without_expr = ('ELSE', 'END')
		# These tokens do not take an argument

	_tokens_with_end = (
		'IF', 'ELIF', 'ELSIF', 'ELSE',
		'FOR', 'FOREACH', 'BLOCK',
	)	# These tokens start a block that is delimited by END

	_tokens_with_line_chomp = _tokens_with_end + (
		'END', 'INCLUDE'
	)	# For these tokens strip whitespace of token is on it's own line

	_tokens_with_default_chomp = ('SET',)
		# For these tokens always strip whitespace left and right

	def __init__(self):
		self.text_parser = self.build_text_parser()
		self.expr_parser = ExpressionParser()
		self._stack = []

	def parse(self, text):
		builder = TemplateTreeBuilder()
		self.__call__(builder, text)
		return builder.get_root()

	def __call__(self, builder, text):
		wrapper = TemplateBuilderTextBuffer(builder)
		wrapper.start('TEMPLATE')
		self.text_parser(wrapper, text)
		wrapper.end('TEMPLATE')

	def build_text_parser(self):
		# Rules capture [% .. %] and <!--[% ... %]--> including "chomp" flags
		# First two rules block level instruction on it's own line
		# next two rules are embdedded in content
		line_tokens = '|'.join(map(re.escape, self._tokens_with_line_chomp))
		text_parser = (
			Rule('X-XML-Token', r'''
				^[^\S\n]*			# whitespace at line start
				\<\!--\[%%			# start of instruction
				(
					-?				# rchomp
					\s+
					(?:%s)			# line tokens
					(?:\s[^%%]*?)?	# optional expression -- the [^%%] os a bit of a hack here..
					\s
					-?				# lchomp
				)
				%%\]--\>			# end of instruction
				[^\S\n]*\n			# whitespace and end of line
				''' % line_tokens,
				process=self._process_token )
			| Rule('X-Text-Token', r'''
				^[^\S\n]*			# whitespace at line start
				\[%%				# start of instruction
				(
					-?				# rchomp
					\s+
					(?:%s)			# line tokens
					(?:\s[^%%]*?)?	# optional expression -- the [^%%] os a bit of a hack here..
					\s
					-?				# lchomp
				)
				%%\]				# end of instruction
				[^\S\n]*\n			# whitespace and end of line
				''' % line_tokens,
				process=self._process_token )
			| Rule('X-Inline-XML-Token',
				r'\<\!--\[%(-?\s.*?\s-?)%\]--\>',
				process=self._process_token )
			| Rule('X-Inline-Text-Token',
				r'\[%(-?\s.*?\s-?)%\]?',
				process=self._process_token )
		)
		return text_parser

	def _process_token(self, builder, text):
		rchomp = text.startswith('-') # rstrip prev text
		lchomp = text.endswith('-') # lstrip next text
		text = text.strip('-').strip()

		m = self._token_with_expr_re.match(text)
		if m and m.group(1) in self._tokens_with_expr:
			token = m.group(1)
			expr = m.group(2).strip()
			if not expr:
				raise AssertionError # TODO better error
		elif text in self._tokens_without_expr:
			token = text
			expr = None
		else:
			m = self._set_token_re.match(text)
			if m:
				token = 'SET'
			else:
				token = 'GET'
			expr = text

		if token in self._tokens_with_default_chomp:
			rchomp = True
			lchomp = True

		if rchomp:
			builder.rstrip()

		method = getattr(self, '_process_token_' + token.lower())
		method(builder, token, expr)

		if lchomp:
			builder.lstrip()

	def _process_append_token(self, b, t, e):
		e = self.expr_parser.parse(e)
		b.append(t, {'expr': e})

	_process_token_get = _process_append_token
	_process_token_include = _process_append_token

	def _process_token_set(self, b, t, e):
		m = self._set_token_re.match(e)
		if m:
			v = ExpressionParameter(m.group(1))
			e = self.expr_parser.parse(m.group(2))
			b.append(t, {'var': v, 'expr': e})
		else:
			raise AssertionError # TODO better error

	def _process_token_if(self, b, t, e):
		e = self.expr_parser.parse(e)
		b.start('IF', {'expr': e})
		self._stack.append('IF')

	def _process_token_elif(self, b, t, e):
		b.end(self._stack.pop()) # raises if unmatched - TODO explicit error
		e = self.expr_parser.parse(e)
		b.start('ELIF', {'expr': e})
		self._stack.append('ELIF')

	_process_token_elsif = _process_token_elif

	def _process_token_else(self, b, t, e):
		b.end(self._stack.pop()) # raises if unmatched - TODO explicit error
		b.start('ELSE')
		self._stack.append('ELSE')

	def _process_token_for(self, b, t, e):
		m = self._for_in_token_re.match(e)
		if t == 'FOREACH' and not m:
			m = self._for_is_token_re.match(e)

		if m:
			v = ExpressionParameter(m.group(1))
			e = self.expr_parser.parse(m.group(2))
			b.start('FOR', {'var': v, 'expr': e})
			self._stack.append('FOR')
		else:
			raise AssertionError, '>> %s, expected "=" or "IN"' % e # TODO better error

	_process_token_foreach = _process_token_for

	def _process_token_block(self, b, t, e):
		if not self._block_token_re.match(e):
			raise AssertionError # TODO better error
		b.start('BLOCK', {'name': e})
		self._stack.append('BLOCK')

	def _process_token_end(self, b, t, e):
		b.end(self._stack.pop()) # raises if unmatched - TODO explicit error

