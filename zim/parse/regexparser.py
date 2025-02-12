
# Copyright 2011,2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Generic parser for wiki formats

This parser for wiki text (and similar formats) consists of two classes:
the L{Rule} class which defines objects which specify a single parser
rule, and the L{Parser} class which takes a number of rules and
parses a piece of text accordingly. The parser just does a series of
regex matches and calls a method on the specific rule objects to
process the match. Recursion can be achieved by making the rules
process with another L{Parser} object.

All rules have access to a L{Builder} object which is used to construct
the resulting parse tree.

There are several limitation to this parser. Most importantly it does
not have backtracking, so once a rule matches it is not allowed to fail.
But since we are dealing with wiki input it is a good assumption that
the parser should always result in a representation of the text, even
if it is broken according to the grammar. So rules should be made
robust when implementing a wiki parser.

Another limitation comes from the fact that we use regular expressions.
There is a limit on the number of capturing groups you can have in a
single regex (100 on my system), and since all rules in a set are
compiled into one big expression this can become an issue for more
complex parser implementations. However for a typical wiki implementation
this should be sufficient.

Note that the regexes are compiles using the flags C{re.U}, C{re.M},
and C{re.X}. This means any whitespace in the expression is ignored,
and a literal space need to be written as "C{\\ }". In general you need
to use the "r" string prefix to ensure those backslashes make it
through to the final expression.
'''

import re
import logging

from zim.errors import Error

logger = logging.getLogger('zim.parse.regexparser')


def get_line_count(text, offset):
	'''Helper function used to report line numbers for exceptions
	that happen during parsing.
	@param text: the text being parsed
	@param offset: character offset in this text
	@returns: a 2-tuple of the line and column that corresponds to this
	offset
	'''
	# line numbers start counting at 1, columns at 0
	if offset == 0:
		return 1, 0
	slice = text[:offset]
	lines = slice.splitlines(1)
	if lines[-1].endswith('\n'):
		return len(lines) + 1, 0
	else:
		return len(lines), len(lines[-1])


class ParserError(Error):

	def __init__(self, msg):
		Error.__init__(self, msg)

		self.parser_file = _('<Unknown>') # T: placeholder for unknown file name
		self.parser_text = ''
		self.parser_line_offset = (0, 0)

	@property
	def description(self):
		return _('Error in %(file)s at line %(line)i near "%(snippet)s"') % {
			'file': self.parser_file,
			'line': self.parser_line_offset[0],
			'snippet': self.parser_text.strip(),
		} # T: Extended error message while parsing a file, gives file name, line number and words where error occurred


class RegexParser(object):
	'''Parser class that matches multiple rules at once. It will
	compile the patterns of various rules into a single regex and
	based on the match call the correct rules for processing.

	@ivar rules: list with L{Rule} objects, can be modified until the
	parser is used for the first time for parsing (the attribute
	becomes a tuple afterwards)
	@ivar process_unmatched: function (or object) to process un-matched
	text, or C{None}.
	The function should take a L{Builder} object as first argument,
	followed by one or more parameters for matched groups in the
	regular expression.
	'''

	def __init__(self, *rules):
		'''Constructor
		@param rules: list of rules to match (each should derive from
		L{SimpleReParser}, so be either a single rule, or a compound
		rule.)
		'''
		self.rules = [] #: sub rules
		self.process_unmatched = self._process_unmatched
		self._re = None

		for rule in rules:
			if isinstance(rule, RegexParser):
				self.rules.extend(list(rule.rules))
			else:
				assert isinstance(rule, Rule)
				self.rules.append(rule)

		assert self.rules, 'No rules defined for this parser'

	def _process_unmatched(self, builder, text):
		# default action for unmatched text
		builder.text(text)

	def __or__(self, other):
		'''Allow new parsers to be constructed by combining parser
		objects with the "|" operator.
		'''
		return self.__class__(self, other)
			# Return extended copy, not modify self
			# __init__ of new instance will make a copy of our rules

	def __call__(self, builder, text):
		'''Each parser object is callable so it can be used as a
		processing function in any other parser object. This method
		parses the given text and calls the appropriate methods of the
		L{Builder} object to construct the parse results.

		@param builder: a L{Builder} object
		@param text: to be parsed text as string
		'''
		if not text:
			logger.warning('Parser got empty string')
			return

		if self._re is None:
			# Generate the regex and cache it for re-use
			self.rules = tuple(self.rules) # freeze list
			pattern = r'|'.join([
				r"(?P<rule%i>%s)" % (i, r.pattern)
					for i, r in enumerate(self.rules)
			])
			#print('PATTERN:\n', pattern.replace(')|(', ')\t|\n('), '\n...')
			self._re = re.compile(pattern, re.U | re.M | re.X)

		iter = 0
		end = len(text)
		match = self._re.search(text, iter)
		while match:
			mstart, mend = match.span()
			if mstart > iter:
				try:
					self.process_unmatched(builder, text[iter:mstart])
				except Exception as error:
					self._raise_exception(error, text, iter, mstart, builder)

			name = match.lastgroup # named outer group
			i = int(name[4:]) # name is e.g. "rule1"
			groups = [g for g in match.groups() if g is not None]
			if len(groups) > 1:
				groups.pop(0) # get rid of named outer group if inner groups are defined

			self._backup_iter = 0
			try:
				self.rules[i].process(builder, *groups)
			except Exception as error:
				self._raise_exception(error, text, mstart, mend, builder, self.rules[i])

			iter = mend - self._backup_iter
			match = self._re.search(text, iter)
		else:
			# no more matches
			if iter < end:
				try:
					self.process_unmatched(builder, text[iter:])
				except Exception as error:
					self._raise_exception(error, text, iter, end, builder)

	parse = __call__

	def backup_parser_offset(self, i):
		self._backup_iter += i

	@staticmethod
	def _raise_exception(error, text, start, end, builder, rule=None):
		# Add parser state, line count etc. to error, then re-raise
		# rule=None means error while processing unmatched text
		if isinstance(error, AssertionError):
			error = ParserError(str(error))
			# Assume any assertion is a parser check
		elif not isinstance(error, ParserError):
			raise  # original error, do not change stack trace

		if hasattr(error, 'parser_offset'):
			error.parser_offset = offset = start + error.parser_offset
			error.parser_line_offset = get_line_count(text, error.parser_offset)
		else:
			error.parser_offset = start
			error.parser_text = text[start:end]
			error.parser_builder = builder
			error.parser_rule = rule
			error.parser_line_offset = get_line_count(text, error.parser_offset)

		raise error


class Rule(object):
	'''Class that defines a single parser rule. Typically used
	to define a regex pattern for one specific wiki format string
	and the processing to be done when this formatting is encountered
	in the text.

	@ivar tag: L{Builder} tag for result of this rule. Used by the
	default process method.
	@ivar pattern: the regular expression for this parser as string
	@ivar process: function (or object) to process matched text, or C{None}
	The function should take a L{Builder} object as first argument,
	followed by one or more parameters for matched groups in the
	regular expression. If the regex pattern has no capturing groups
	this function is called with the whole match.
	The default function will use the C{tag} and C{descent}
	attributes
	@ivar descent: optional function (or object) to recursively parse the
	text matched by this rule. Called in the same way as C{process}.
	'''

	def __init__(self, tag, pattern, process=None, descent=None):
		'''Constructor
		@param tag: L{Builder} tag for result of this rule. Used by the
		default process method.
		@param pattern: regex pattern as string
		@param process: optional function to process matched text
		@param descent: optional function to recursively parse matched text
		'''
		assert tag is not None or process is not None, 'Need at least a tag or a process method'
		self._re = None
		self.tag = tag
		if isinstance(pattern, str):
			self.pattern = pattern
		else:
			self.pattern = pattern.pattern # Assume compiled regular expression
		self.descent = descent
		self.process = process or self._process

	def __repr__(self):
		return '<%s: %s: %s>' % (self.__class__.__name__, self.tag, self.pattern)

	def __or__(self, other):
		'''Allow new parsers to be constructed by combining parser
		objects with the "|" operator.
		'''
		return RegexParser(self, other)

	def _process(self, builder, text):
		# default action for matched text
		if self.descent:
			builder.start(self.tag)
			self.descent(builder, text)
			builder.end(self.tag)
		else:
			builder.append(self.tag, None, text)
