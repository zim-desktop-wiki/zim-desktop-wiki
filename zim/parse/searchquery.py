# Copyright 2009-2025 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains logic to parse search queries

The main entry point is the function L{parse_search_query()} which takes a string
and definition of supported keywords and returns a L{SearchQuery} object.

Search queries consist of keywords like `content: foo` to search content for `foo`
or `name: foo` to search names matching `foo`.

Search terms without a keyword are mapped to a default keyword.

Search terms can be combined using operators.

Supported operators:
	- "NOT", "not" and "-"
	- "AND", "and", and "+"
	- "OR" or "or"

Order of precedence: AND, OR, NOT
so "foo AND NOT bar OR baz" means AND(foo, OR(NOT(bar), baz))

Explicit groups can be made by "(" and ")"

This module does not implement the search itself, see C{zim.search} for page search.
For other cases, the helper function L{compile_search_query_check_function()} can be used.
'''


import re
import enum
import logging

from functools import partial
from collections.abc import Callable

from .encode import split_quoted_strings, unescape_quoted_string


logger = logging.getLogger('zim.parsing.searchquery')


OPERATOR_OR = 'OR'
OPERATOR_AND = 'AND'
OPERATOR_NOT = 'NOT'
OPERATOR_GROUP_START = '('
OPERATOR_GROUP_END = ')'


_operator_tokens = (OPERATOR_OR, OPERATOR_AND, OPERATOR_NOT, OPERATOR_GROUP_START, OPERATOR_GROUP_END)

_query_operators = {
	'or': OPERATOR_OR,
	'and': OPERATOR_AND,
	'+': OPERATOR_AND,
	'-': OPERATOR_NOT,
	'not': OPERATOR_NOT,
	'(': OPERATOR_GROUP_START,
	')': OPERATOR_GROUP_END,
}
_operators_allowed_in_keyword_group = ('+', '-')
	# 'and' 'or' 'not' will be interpreted as string in keyword group context


OPERATOR_MATCH = 'MATCH'
OPERATOR_EQUAL = '__eq__'
OPERATOR_LESS_THAN = '__lt__'
OPERATOR_GREATER_THAN = '__gt__'
OPERATOR_LESS_EQUAL = '__le__'
OPERATOR_GREATER_EQUAL = '__ge__'


_keyword_operators = {
	':': OPERATOR_MATCH,
	'=': OPERATOR_EQUAL,
	'>': OPERATOR_GREATER_THAN,
	'<': OPERATOR_LESS_THAN,
	'>=': OPERATOR_GREATER_EQUAL,
	'<=': OPERATOR_LESS_EQUAL,
}
_keyword_operators_strings = {v: k for k, v in _keyword_operators.items()}

# Query options
class SearchFlag(enum.Flag):
	CASE_SENSITIVE = 1
	WHOLE_WORD = 2
	REGEX = 4

	def to_letters(self) -> str:
		string = ''
		for k, v in self._letter_codes.items():
			if SearchFlag(k) in self:
				string += v
		return string

	@classmethod
	def from_letters(cls, string: str) -> 'SearchFlag':
		flags = cls(0)
		for k, v in cls._letter_codes.items():
			if v in string:
				flags |= cls(k)
		return flags

# hack to add "nonmember" attributes to enum class
SearchFlag._letter_codes = {
	SearchFlag.CASE_SENSITIVE.value: 'C',
	SearchFlag.WHOLE_WORD.value: 'W',
	SearchFlag.REGEX.value: 'R'
}
SearchFlag.from_letters_re = re.compile('^\\?([%s]+)\\:$' % ''.join(SearchFlag._letter_codes.values()))


SEARCH_CASE_SENSITIVE = SearchFlag.CASE_SENSITIVE #: Constant to find case sensitive
SEARCH_WHOLE_WORD = SearchFlag.WHOLE_WORD #: Constant to find whole words only
SEARCH_REGEX =  SearchFlag.REGEX #: Constant for regex search


class SearchQuery:
	'''Object to represent a search query'''

	def __init__(self, operator=OPERATOR_AND, terms: 'Iterable|None'=None, negate: bool=False, flags: SearchFlag=SearchFlag(0)):
		self.operator = operator
		self.terms = list(terms) if terms else []
		assert all(isinstance(t, (SearchQuery, SearchQueryTerm)) for t in self.terms), self.terms
		self.negate = negate
		self.flags = flags

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			(self.operator, self.negate, self.terms, self.flags) == (other.operator, other.negate, other.terms, self.flags)

	def __repr__(self):
		return '<%s "%s">' % (self.__class__.__name__, str(self))

	def __str__(self):
		sep = " %s " % self.operator
		string = "(%s)" % sep.join(str(t) for t in self.terms)
		if self.flags:
			string = '(?%s: ' % self.flags.to_letters() + string[1:]
		return "NOT " + string if self.negate else string

	def __len__(self):
		return len(self.terms)

	def __iter__(self):
		return iter(self.terms)

	def __getitem__(self, i):
		return self.terms[i]

	def add(self, term):
		self.terms.append(term)

	def remove(self, term):
		i = self.terms.index(term)
		self.terms.pop(i)

	def copy(self):
		'''Shallow copy'''
		return self.__class__(self.operator, list(self.terms), self.negate)


class SearchQueryTerm:
	'''Object to represent a single keyword term in a search query'''

	def __init__(self, keyword: str, value: str, kw_operator=OPERATOR_MATCH, negate: bool=False):
		self.keyword = keyword.lower()
		self.value = value
		self.kw_operator = kw_operator
		self.negate = negate

	def copy(self, keyword: str|None=None, value: str|None=None, kw_operator=None, negate: bool|None=None):
		'''Create a new instance with only few attribute modified'''
		negate = self.negate if negate is None else negate # distinguish False and None
		return self.__class__(keyword or self.keyword, value or self.value, kw_operator or self.kw_operator, negate)

	def __eq__(self, other):
		# Compare resulting term, not original string information
		return isinstance(other, self.__class__) and \
			(self.keyword, self.value, self.kw_operator, self.negate) == (other.keyword, other.value, self.kw_operator, other.negate)

	def __repr__(self):
		return '<%s "%s">' % (self.__class__.__name__, str(self))

	def __str__(self):
		string = self.keyword + _keyword_operators_strings[self.kw_operator] + '"%s"' % self.value
		return "NOT " + string if self.negate else string


def parse_search_query(string: str, keywords: dict, default_keyword: str='any', flags: SearchFlag=SearchFlag(0)) -> SearchQuery:
	'''Parse a search query string into a L{SearchQuery} object

	Parsing behavior is controlled by the `keywords` dict and the `default_keyword`.
	The `keywords` dict should specify valid keywords as keys, the value should be a dict.
	The following keys are supported:

	  - `implicit_match` defines a regex object to be used to match this keyword implicit,
	     e.g. `search_tag_re` for the `tags` keyword

	For malformed queries warnings are logged while skipping over the errors.

	@param string: the string to be parsed
	@param keywords: dict with supported keywords
	@param default_keyword: keyword for strings without keyword specified
	@param flags: flags to be passed on when handling the query
	'''
	assert isinstance(flags, SearchFlag)
	tokens = _tokenize_search_query(string, keywords, default_keyword)
	tokens = _collect_explicit_groups(tokens)
	query = _process_operators(tokens)
	query.flags = flags
	return query


def _tokenize_search_query(string: str, keywords: dict, default_keyword: str='any') -> list:
	# Split string in words, each word is either a search term or an operator
	# terms without a keyword get the default keyword

	# Bootstrap regexes
	kws = list(keywords)
	kws.append(default_keyword)
	keyword_re = re.compile('(' + '|'.join(kws) + ')(:?[><]=|:?[=><]|:)(.*)', re.I|re.U)
	implicit_keywords = {}
	if isinstance(keywords, dict): # should always be a dict, but in testing we use sets
		for k in keywords:
			if 'implicit_match' in keywords[k]:
				r = keywords[k]['implicit_match']
				implicit_keywords[k] = re.compile(r, re.U) if isinstance(r, str) else r

	def match_implicit_keyword(string):
		for k, r in implicit_keywords.items():
			if r.match(string):
				return k
		else:
			return default_keyword

	# Flat tokenizer
	words = split_quoted_strings(string)
	tokens = []
	while words:
		w = words.pop(0)

		if w[0] in ('(', ')', '+', '-') and len(w) > 1:
			words.insert(0, w[1:])
			w = w[0]

		while w[-1] in ('(', ')') and len(w) > 1:
			words.insert(0, w[-1])
			w = w[:-1]

		m_key = keyword_re.match(w)
		if w.lower() in _query_operators:
			tokens.append(_query_operators[w.lower()])
		elif m_key:
			keyword = m_key.group(1).lower()
			kwop = _keyword_operators.get(m_key.group(2).strip(':'), OPERATOR_MATCH)
			if m_key.group(3) or ( words and not words[0][0] == '(' ):
				string = m_key.group(3) or words.pop(0)
				term = unescape_quoted_string(string)
				tokens.append(SearchQueryTerm(keyword, term, kw_operator=kwop))
			elif words and words[0][0] == '(':
				# special case to support "keyword: (value value value)" as "(keyword:value keyword:value keyword:value)"
				if words[0] == '(':
					words.pop(0)
				else:
					words[0] = words[0][1:]
				tokens.append(OPERATOR_GROUP_START)
				tokens.extend(_tokenize_group_for_term(keyword, words))
			else:
				# no more words - edge case - something ending in ":" but nothing following
				term = m_key.group(1) + m_key.group(2)
				keyword = match_implicit_keyword(term)
				tokens.append(SearchQueryTerm(keyword, term))
		elif tokens and tokens[-1] == '(' and SearchFlag.from_letters_re.match(w):
			tokens.append(SearchFlag.from_letters(w))
		else:
			keyword = match_implicit_keyword(w)
			term = unescape_quoted_string(w)
			tokens.append(SearchQueryTerm(keyword, term))
	return tokens


def _tokenize_group_for_term(keyword, words):
	# Collect all words untill ")" as keyword terms for "keyword"
	tokens = []
	while words and words[0][0] != ')':
		w = words.pop(0)

		if w[0] in ('(', ')', '+', '-') and len(w) > 1:
			words.insert(0, w[1:])
			w = w[0]

		while w[-1] in ('(', ')') and len(w) > 1:
			words.insert(0, w[-1])
			w = w[:-1]

		if w in _operators_allowed_in_keyword_group:
			tokens.append(_query_operators[w])
		elif w == '(':
			logger.warning("Out of place '(' operator in keyword group of search query")
			# skip over this token
		else:
			term = unescape_quoted_string(w)
			tokens.append(SearchQueryTerm(keyword, term))

	return tokens


def _collect_explicit_groups(tokens: list) -> list:
	# Group matched "(" and ")" and raise on unmatched occurences
	stack = [[]]
	for i, t in enumerate(tokens):
		if t == OPERATOR_GROUP_START:
			subgroup = []
			stack[-1].append(subgroup)
			stack.append(subgroup)
		elif t == OPERATOR_GROUP_END:
			if len(stack) > 1:
				stack.pop()
			else:
				logger.warning("Unmatched ')' in search query")
				# skip over this token
		else:
			stack[-1].append(t)

	if len(stack) > 1:
		logger.warning("Unmatched '(' in search query")

	return stack[0]


def _process_operators(tokens: list) -> SearchQuery:
	# Validate out of place operators at start and end
	if not tokens or all(t in _operator_tokens for t in tokens):
		logger.warning('Empty search query')
		return SearchQuery()

	# Turn sub groups into queries - depth first
	for i in range(0, len(tokens)):
		if isinstance(tokens[i], list):
			tokens[i] = _process_operators(tokens[i]) # recurs

	# Check for flags
	flags = tokens.pop(0) if isinstance(tokens[0], SearchFlag) else SearchFlag(0)

	# Remove out of place AND / OR operators
	if tokens[0] == OPERATOR_AND:
		# Allow for one stray AND operator, to get over "+foo +bar"
		tokens.pop(0)

	while tokens[0] in (OPERATOR_AND, OPERATOR_OR):
		logger.warning("Out of place operator at start of query: %s" % tokens[0])
		tokens.pop(0)

	while tokens[-1] in (OPERATOR_AND, OPERATOR_OR, OPERATOR_NOT):
		logger.warning("Out of place operator at end of query: %s" % tokens[-1])
		tokens.pop()

	# Process operators
	for i in range(0, len(tokens)-1):
		if tokens[i] == OPERATOR_NOT:
			tokens[i] = None
			if isinstance(tokens[i+1], (SearchQuery, SearchQueryTerm)):
				tokens[i+1].negate = True
			else:
				logger.warning("Out of place NOT operator in search query")
		elif tokens[i] in (OPERATOR_OR, OPERATOR_AND):
			if tokens[i+1] in (OPERATOR_OR, OPERATOR_AND):
				logger.warning("Out of place operator in query: %s" % tokens[i])
				tokens[i] = None
			elif tokens[i] == OPERATOR_AND:
				# implicit deafult, so remove already
				tokens[i] = None
			else:
				pass
		elif tokens[i] in (OPERATOR_GROUP_START, OPERATOR_GROUP_END):
			logger.warning('Bug: all operators should be removed at this point, found %s' % tokens[i])
			tokens[i] = None
		
	tokens = [t for t in tokens if t is not None]

	# Check for implicit sub-groups, and return top level group as query
	while OPERATOR_OR in tokens:
		i = tokens.index(OPERATOR_OR) # position first OR
		j = i # position last OR
		while j < len(tokens) and tokens[j] == OPERATOR_OR:
			j += 2

		group = [t for t in tokens[i-1:j] if t != OPERATOR_OR]
		if i == 1 and j == len(tokens):
			# We consumed the whole token list
			return SearchQuery(OPERATOR_OR, group, flags=flags)
		else:
			# Splice subgroup in list
			tokens = tokens[:i-1] + [SearchQuery(OPERATOR_OR, group)] + tokens[j:]
	else:
		# Final group is implicit AND group
		if len(tokens) == 1 and isinstance(tokens[0], SearchQuery):
			if not tokens[0].flags:
				tokens[0].flags = flags 
			return tokens[0]
		else:
			return SearchQuery(OPERATOR_AND, tokens, flags=flags)


def find_string_to_regex(string: str, flags: SearchFlag = SearchFlag(0)) -> re.Pattern|None:
	'''Returns a regex object for a string match for in page find
	
	Applies the same rules as L{search_query_term_to_regex()} with additional support for
	regex searches and supports the pipe caharacter (`|`) as inline "OR"
	'''
	if SEARCH_REGEX in flags:
		regex = string

		if SEARCH_WHOLE_WORD in flags:
			if re.match(r'^\s*\w', string, re.U):
				regex = r'\b' + regex

			if re.search(r'(?<!\\)\w\s*$', string, re.U): # match ending in char, but not in escape char
				regex = regex + r'\b'
	else:
		parts = [
			_search_query_term_to_regex(SearchQueryTerm('text', p), flags, capture_glob=True)
				for p in string.split('|') 
		]
		regex = '|'.join(p for p in parts if p)

	return re.compile(regex, re.U) if SEARCH_CASE_SENSITIVE in flags else re.compile(regex, re.U | re.I)


def search_query_term_to_regex(term: SearchQueryTerm, flags: SearchFlag = SearchFlag(0)) -> re.Pattern|None:
	'''Returns a regex object for a simple string match of a L{SearchQueryTerm}

	The following rules are applied:
	  - a "*" optionally matches any non-whitespace character
	  - a space " " matches any combination of whitespace, or begin or end of the string
	  - by default, matches anywhere in the text, so implying "*" at the start and end of the word
	  - however, if a "*" is used, begin and end will automatically match word boundaries, unless the search term starts or ends with "*"
	  - a space " " at the start or the end forces a word bounderay, " word " only matches the whole word
	  - if the option "Whole Word" is set, word boundaries are always added automatically, and a "*" is required to match elsewhere
	  - by default matches case insensitive, unless the "equal" operator is used or the "Match case" option is set

	@param term: a L{SearchQueryTerm}
	@param flags: a SearchFlag enum
	@param returns: a C{re.Pattern} object or C{None} if the pattern is invalid
	'''
	# NOTE: changes in above rules also need to be updated in the manual
	regex = _search_query_term_to_regex(term, flags)
	if not regex:
		return None
	elif term.kw_operator == OPERATOR_EQUAL or SEARCH_CASE_SENSITIVE in flags:
		# OPERATOR_EQUAL is interpreted as exact match, so case sensitive
		return re.compile(regex, re.U)
	else:
		return re.compile(regex, re.U | re.I)


def _search_query_term_to_regex(term: SearchQueryTerm, flags: SearchFlag = SearchFlag(0), capture_glob=False) -> str:
	# Inner logic for search_query_term_to_regex() and related functions

	if not term.value.replace('*', '').strip():
		return None # nothing to match

	# Globs to regex
	parts = []
	for p in term.value.strip().strip('*').split('*'):
		sub_parts = re.split('\\s+', p)
		parts.append(r'\W+'.join(map(re.escape, sub_parts)))
	regex = r'\S*'.join(parts)

	# Add word delimiters to regex
	if SEARCH_WHOLE_WORD in flags:
		# Default is word boundaries, unless explicit glob or non-alpha char
		if re.match(r'^\s*\w', term.value, re.U):
			regex = r'\b' + regex

		if re.search(r'\w\s*$', term.value, re.U):
			regex = regex + r'\b'
	elif '*' in term.value:
		# Implicit word boundaries, like above but with exception for chinese
		if re.match(r'^\s*\w', term.value, re.U) and not '\u4e00' <= term.value[0] <= '\u9fff':
			regex = r'\b' + regex

		if re.search(r'\w\s*$', term.value, re.U) and not '\u4e00' <= term.value[-1] <= '\u9fff':
			regex = regex + r'\b'
	else:
		# Explicit word boundaries by whitespace, default is anywhere
		if re.match(r'^\s+\w', term.value, re.U):
			regex = r'\b' + regex

		if re.search(r'\w\s+$', term.value, re.U):
			regex = regex + r'\b'

	if capture_glob:
		if term.value.startswith('*'):
			regex = r'\S*' + regex

		if term.value.endswith('*'):
			regex += r'\S*'

	return regex


def search_query_pagename_term_to_regex(term: SearchQueryTerm, flags: SearchFlag = SearchFlag(0)) -> re.Pattern|None:
	'''Returns a regex object for a page name match of a L{SearchQueryTerm}

	Behavior is equal to L{search_query_term_to_regex()} with these additional rules:
	  - a "*" glob does not cross name segments, it does stop at the ":" separator
	  - a ":" matches the start or end of a name segment
	  - a "::" at the start matches start at the top-level of the notebook
	  - a "::" at the end excludes sub-pages
	  - a ":+" at the end gives sub-pages put excludes the parent page

	@param term: a L{SearchQueryTerm}
	@param returns: a C{re.Pattern} object or C{None} if the pattern is invalid
	'''
	# NOTE: changes in above rules also need to be updated in the manual
	regex = _search_query_term_to_regex(term, flags)
	if not regex:
		return None

	regex = regex.replace(r'\S*', r'[^\s:]*') # "*" should exclude ":" as well as whitespace

	if regex.startswith('::'):
		regex = '^:?' + regex[2:]
	elif regex.startswith(':'):
		regex = '(^:?|:)' + regex[1:]

	if regex.endswith('::'):
		regex = regex[:-2] + ':?$'
	elif term.value.endswith(':+'):
		regex = regex[:-3] + ':.+'
	elif regex.endswith(':'):
		regex = regex[:-1] + '(:|:?$)'

	if term.kw_operator == OPERATOR_EQUAL or SEARCH_CASE_SENSITIVE in flags:
		# OPERATOR_EQUAL is interpreted as exact match, so case sensitive
		return re.compile(regex, re.U)
	else:
		return re.compile(regex, re.U | re.I)


search_tag_re = re.compile(r'^@[\w*]+@?$', re.U) #: Inteded to be used for implicit keyword parsing


def search_query_tags_term_to_regex(term: SearchQueryTerm, flags: SearchFlag = SearchFlag(0)) -> re.Pattern|None:
	'''Return a regex object for a tag name

	Behavior is equal to L{search_query_term_to_regex()} with these additional rules:
	  - if the term starts with a "@" it will only match from the start of the name
	  - if the term ends with a "@" it will only match from the end of the name
	  - tags are always case in-sensitive, so the "Match case" option does nothing

	@param term: a L{SearchQueryTerm}
	@param returns: a C{re.Pattern} object or C{None} if the pattern is invalid
	'''
	regex = _search_query_term_to_regex(term, flags)
	if not regex:
		return None

	if regex.startswith('@'):
		regex = '\\b' + regex[1:]

	if regex.endswith('@'):
		regex = regex[:-1] + '\\b'

	return re.compile(regex, re.U | re.I) # Tags are always case in-sensitive


def check_func_constructor(term: SearchQueryTerm, keywords: dict) -> Callable[[object], bool]:
	'''To be used as a constructor with L{compile_search_query_check_function}
	The resulting check function does by default a string match based on C{search_query_term_to_regex}
	on the value of the given key in the object.
	Requires the C{key} to be specified in the keywords dict.
	If a c{regex_constructor} function is given in the keyword dict, this is used instead
	of C{search_query_term_to_regex}
	'''
	if 'regex_constructor' in keywords[term.keyword]:
		regex_constructor = keywords[term.keyword]['regex_constructor']
	else:
		regex_constructor = search_query_term_to_regex

	pattern = regex_constructor(term)
	key = keywords[term.keyword]['key']

	def mychecker(record):
		return bool(pattern.search(record[key]))

	return mychecker


def check_func_constructor_any_keyword(term: SearchQueryTerm, keywords: dict) -> Callable[[object], bool]:
	'''To be used as a constructor with L{compile_search_query_check_function}
	Intended for the default keyword. It effectively constructs an "or" function over multiple fields
	in the record. The C{'include'} value in the keywords dict should provide a list
	of keywords to include.
	'''

	check_functions = []
	for keyword in keywords[term.keyword]['include']:
		constructor = keywords[keyword].get('check_func_constructor', check_func_constructor)
		myterm = term.copy(keyword=keyword)
		checker = constructor(myterm, keywords)
		check_functions.append(checker)

	def mychecker(record):
		for checker in check_functions:
			if checker(record):
				return True
		else:
			return False

	return mychecker


def check_comparison_func_constructor(term: SearchQueryTerm, keywords: dict) -> Callable[[object], bool]:
	'''To be used as a constructor with L{compile_search_query_check_function}
	The resulting function uses the comparison functions `<`, `>`, `=`, `<=`, `>=`, where `:` is interpreted
	as `=`. The c{'comparison'} value in the keywords dict should provide a type (e.g. `str` or `int`)
	that is used for the comparison
	'''
	key = keywords[term.keyword]['key']
	ctype = keywords[term.keyword]['comparison']
	try:
		ref = ctype(term.value) # e.g. str -> int
	except ValueError:
		logger.warning('Invalid value for type \'%s\': %s' % ctype.__name__, term.value)
		return lambda r: False

	op = ctype.__eq__ if term.kw_operator == OPERATOR_MATCH else getattr(ctype, term.kw_operator)
	return lambda r: op(r[key], ref)


def _negate_checker(checker, *a):
	return not checker(*a)


def _and_checker(checkers, record):
	return all(c(record) for c in checkers)


def _or_checker(checkers, record):
	return any(c(record) for c in checkers)


def compile_search_query_check_function(query: SearchQuery, keywords: dict) -> Callable[[object], bool]:
	'''Compile a query to a function that checks whather a given object matches the query

	This function compiles a function that matches the rules of the given C{query} such that it
	returns boolean when called with an "record" to be checked. This "record" is an object which
	has an C{__getitem__} method and be iterable. Typical usage is checking tuples or dicts
	as records.

	The C{keywords} dict should contain definitions of the keywords supported in the query.
	It is intended to be the same dict as provided to C{parse_search_query()}.

	By default each term is interpretad as a string match against a given field in the "record".
	The C{keywords} dict should have a key C{'key'} which gives the mapping into the record.

	To change the default behavior, a key C{'check_func_constructor'} can be given in the keywords
	dict. This should have a functions as value that constructs the final check function. 
	The constructors should have the signature:

			constructor(term: SearchQueryTerm, keywords: dict) -> Callable[[object], bool]

	And result in a check function

			check(record: Sequence|Mapping) -> bool

	These check functions only need to check for a positive match, the wrapper takes care of
	operators and negation.

	Check function constructors included here are L{check_func_constructor_pagename},
	L{check_comparison_func_constructor}, L{check_func_constructor_any_keyword}.

	@param keywords: dict with keywords as keys and a dict with attributes (e.g. the type) as values
	@returns: a check function for the whole query C{check(record: Mapping) -> bool}
	'''
	members = []
	for term in query.terms:
		if isinstance(term, SearchQuery):
			members.append(compile_search_query_check_function(term, keywords)) # recurs
		else:
			constructor = keywords[term.keyword].get('check_func_constructor', check_func_constructor)
			checker = constructor(term, keywords)
			if term.negate:
				members.append(partial(_negate_checker, checker))
			else:
				members.append(checker)

	if len(members) == 1:
		# optimize for simple case by loosing group wrapper
		if query.negate:
			return partial(_negate_checker, members[0])
		else:
			return members[0]
	else:
		op_func = _or_checker if query.operator == OPERATOR_OR else _and_checker
		if query.negate:
			return partial(_negate_checker, op_func, members)
		else:
			return partial(op_func, members)

