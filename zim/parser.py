# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
and a literal space need to be written as "C{\ }". In general you need
to use the "r" string prefix to ensure those backslashes make it
through to the final expression.
'''

import re

import xml.etree.cElementTree as ElementTree


from zim.errors import Error


def prepare_text(text, tabstop=4):
	'''Ensures text is properly formatted.
	  - Fixes missing line end
	  - Expands spaces to tabs
	@param text: the intput text
	@param tabstop: the number of spaces to represent a tab
	@returns: the fixed text
	'''
	# HACK this char is recognized as line end by splitlines()
	# but not matched by \n in a regex. Hope there are no other
	# exceptions like it (crosses fingers)
	text = text.replace(u'\u2028', '\n')

	# Fix line end
	if not text.endswith('\n'):
		text = text + '\n'

	# Fix tabs
	spaces = ' ' * tabstop
	pattern = '(?m)^(\t*)((?:%s)+)' % spaces
	text = re.sub(
		pattern,
		lambda m: m.group(1) + '\t' * (len(m.group(2)) / tabstop),
		text
	)
	# Specify "(?m)" instead of re.M since "flags" keyword is not
	# supported in python 2.6

	return text


class Builder(object):
	'''This class defines a 'builder' interface for parse trees. It is
	used by the parser to construct the parse tree while keeping the
	parser objects agnostic of how the resulting parse tree objects
	look.
	'''

	def start(self, tag, attrib=None):
		'''Start formatted region
		@param tag: the tag name
		@param attrib: optional dict with attributes
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplemented

	def text(self, text):
		'''Append text
		@param text: text to be appended as string
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplemented

	def end(self, tag):
		'''End formatted region
		@param tag: the tag name
		@raises XXX: when tag does not match current state
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplemented

	def append(self, tag, attrib=None, text=None):
		'''Convenience function to open a tag, append text and close
		it immediatly. Only used for formatted text that has no
		sub-processing done.
		@param tag: the tag name
		@param attrib: optional dict with attributes
		@param text: formatted text
		@implementation: optional for subclasses, default implementation
		calls L{start()}, L{text()}, and L{end()}
		'''
		self.start(tag, attrib)
		if not text is None:
			self.text(text)
		self.end(tag)


class BuilderTextBuffer(Builder):
	'''Wrapper that buffers text going to a L{Builder} object
	such that the last piece of text remains accessible for inspection
	and can be modified.
	'''

	def __init__(self, builder):
		self.builder = builder
		self.buffer = []

	# Interface to handle text buffer

	def get_text(self):
		return u''.join(self.buffer)

	def set_text(self, text):
		self.buffer = [text]

	def clear_text(self):
		self.buffer = []

	def flush(self):
		text = u''.join(self.buffer)
		if text:
			self.builder.text(text)
		self.buffer = []

	# Builder interface

	def start(self, tag, attrib=None):
		if self.buffer:
			self.flush()
		self.builder.start(tag, attrib)

	def end(self, tag):
		if self.buffer:
			self.flush()
		self.builder.end(tag)

	def text(self, text):
		self.buffer.append(text)

	def append(self, tag, attrib=None, text=None):
		if self.buffer:
			self.flush()
		self.builder.append(tag, attrib, text)


class SimpleTreeElement(list):

	# Not unlike the Element class of xml.etree, but without the
	# "text" and "tail" attributes - text is just part of the list.
	# This makes processing so much easier...

	__slots__ = ('tag', 'attrib')

	def __init__(self, tag, attrib=None, children=None):
		self.tag = tag
		self.attrib = attrib
		if children:
			self.extend(children)

	def get(self, attr, default=None):
		if self.attrib:
			return self.attrib.get(attr, default)
		else:
			return None

	def __eq__(self, other):
		if self.tag == other.tag \
		and self.attrib == other.attrib \
		and len(self) == len(other):
			return all(s == o for s, o in zip(self, other))
		else:
			return False

	def __repr__(self):
		if len(self) > 0:
			return '<%s:\n%s>' % (self.__class__.__name__, self.pprint(level=1))
		else:
			return '<%s: %s>' % (self.__class__.__name__, self.pprint(level=0).strip())

	def __str__(self):
		return self.__repr__()

	def pprint(self, level=0):
		'''Returns pretty-printed text representation'''
		prefix = '  ' * level
		if len(self) > 0:
			lines = [prefix + '%s %r [\n' % (self.tag, self.attrib)]
			for item in self:
				if isinstance(item, SimpleTreeElement):
					lines.append(item.pprint(level=level+1))
				elif isinstance(item, basestring):
					for line in item.splitlines(True):
						lines.append(prefix + '  %r\n' % line)
				else:
					lines.append(prefix + '  %r\n' % item)
			lines.append(prefix + ']\n')
			return ''.join(lines)
		else:
			return prefix + '%s %r []\n' % (self.tag, self.attrib)


class SimpleTreeBuilder(Builder):
	'''Builder class that builds a tree of L{SimpleTreeElement}s'''

	def __init__(self, elementfactory=SimpleTreeElement):
		self.elementfactory = elementfactory
		self.root = []
		self.stack = [self.root]
		self.merge_text = False

	def get_root(self):
		if not len(self.stack) == 1:
			raise AssertionError, 'Did not finish processing'
		return self.root

	# Builder interface

	def start(self, tag, attrib=None):
		element = self.elementfactory(tag, attrib)
		self.stack[-1].append(element)
		self.stack.append(element)

	def end(self, tag):
		element = self.stack.pop()
		if element.tag != tag:
			raise AssertionError, 'Unmatched %s at end of %s' % (element.tag, tag)

	def text(self, text):
		self.stack[-1].append(text)

	def append(self, tag, attrib=None, text=None):
		element = self.elementfactory(tag, attrib)
		if text:
			element.append(text)
		self.stack[-1].append(element)


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
		}
			# T: Extended error message while parsing a file, gives file name, line number and words where error occurred


class Rule(object):
	'''Class that defines a sigle parser rule. Typically used
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
	@ivar decent: optional function (or object) to recursively parse the
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
		self.pattern = pattern
		self.descent = descent
		self.process = process or self._process

	def __repr__(self):
		return '<%s: %s: %s>' % (self.__class__.__name__, self.tag, self.pattern)

	def __or__(self, other):
		'''Allow new parsers to be constructed by combining parser
		objects with the "|" operator.
		'''
		return Parser(self, other)

	def _process(self, builder, text):
		# default action for matched text
		if self.descent:
			builder.start(self.tag)
			self.descent(builder, *text)
			builder.end(self.tag)
		else:
			builder.append(self.tag, None, text)


class Parser(object):
	'''Parser class that matches multiple rules at once. It will
	compile the patterns of various rules into a single regex and
	based on the match call the correct rules for processing.

	@ivar rules: list with L{Rule} objects, can be modified untill the
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
			if isinstance(rule, Parser):
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
		parses the given text and calls the apropriate methods of the
		L{Builder} object to construct the parse results.

		@param builder: a L{Builder} object
		@param text: to be parsed text as string
		'''

		assert text, 'BUG: processing empty string'
		if self._re is None:
			# Generate the regex and cache it for re-use
			self.rules = tuple(self.rules) # freeze list
			pattern = r'|'.join( [
				r"(?P<rule%i>%s)" % (i, r.pattern)
					for i, r in enumerate(self.rules)
			])
			#~ print 'PATTERN:\n', pattern.replace(')|(', ')\t|\n('), '\n...'
			self._re = re.compile(pattern, re.U | re.M | re.X)

		iter = 0
		end = len(text)
		for match in self._re.finditer(text):
			mstart, mend = match.span()
			if mstart > iter:
				try:
					self.process_unmatched(builder, text[iter:mstart])
				except Exception, error:
					self._raise_exception(error, text, iter, mstart, builder)

			name = match.lastgroup # named outer group
			i = int(name[4:]) # name is e.g. "rule1"
			groups = [g for g in match.groups() if g is not None]
			if len(groups) > 1:
				groups.pop(0) # get rid of named outer group if inner groups are defined

			try:
				self.rules[i].process(builder, *groups)
			except Exception, error:
				self._raise_exception(error, text, mstart, mend, builder, self.rules[i])

			iter = mend

		else:
			# no more matches
			if iter < end:
				try:
					self.process_unmatched(builder, text[iter:])
				except Exception, error:
					self._raise_exception(error, text, iter, end, builder)

	parse = __call__

	@staticmethod
	def _raise_exception(error, text, start, end, builder, rule=None):
		# Add parser state, line count etc. to error, then re-raise
		# rule=None means error while processing unmatched text
		if isinstance(error, AssertionError):
			error = ParserError(error.message)
			# Assume any assertion is a parser check

		if hasattr(error, 'parser_offset'):
			offset = start + error.parser_offset
		else:
			offset = start
			error.parser_text = text[start:end]
			error.parser_builder = builder
			error.parser_rule = rule

		error.parser_offset = offset
		error.parser_line_offset = get_line_count(text, offset)

		if isinstance(error, ParserError):
			raise error
		else:
			raise  # original error, do not change stack trace


def get_line_count(text, offset):
	'''Helper function used to report line numbers for exceptions
	that happen during parsing.
	@param text: the text being parsed
	@param offset: character offset in this text
	@returns: a 2-tuple of the line and column that corresponds to this
	offset
	'''
	# line numbers start counting at 1, colums at 0
	if offset == 0:
		return 1, 0
	slice = text[:offset]
	lines = slice.splitlines(1)
	if lines[-1].endswith('\n'):
		return len(lines) + 1, 0
	else:
		return len(lines), len(lines[-1])
