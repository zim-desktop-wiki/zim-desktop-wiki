# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

# Operators:
# 	+ -
# 	AND and &&
# 	OR or ||
# Fields:
# 	Content:
# 	Name:
#	Links:		# forward
# 	LinksFrom:	# forward
# 	LinksTo:	# backward

import re

from zim.parsing import split_quoted_strings, unescape_quoted_string, Re
from zim.index import LINK_DIR_BACKWARD


OPERATOR_OR = 1
OPERATOR_AND = 2

operators = {
	'or': OPERATOR_OR,
	'||': OPERATOR_OR,
	'and': OPERATOR_AND,
	'&&': OPERATOR_AND
}

KEYWORDS = ('content', 'name', 'linksfrom', 'linksto')

keyword_re = Re('('+'|'.join(KEYWORDS)+'):(.*)', re.I)


class OrGroup(list):
	pass


class AndGroup(list):
	pass


class Query(object):

	# TODO support + and - operators

	def __init__(self, string):
		self.string = string
		self.root = self._parse_query(string)

	def _parse_query(self, string):
		words = split_quoted_strings(string, unescape=False)
		tokens = []
		while words:
			w = words.pop(0)
			if w.lower() in operators:
				tokens.append(operators[w.lower()])
			elif keyword_re.match(w):
				keyword = keyword_re[1].lower()
				term = keyword_re[2] or words.pop(0)
				term = unescape_quoted_string(term)
				tokens.append((keyword, term))
			else:
				w = unescape_quoted_string(w)
				tokens.append(('content', w)) # default keyword
		#~ print tokens

		root = AndGroup()
		while tokens:
			token = tokens.pop(0)
			if token in (OPERATOR_AND, OPERATOR_OR):
				pass # AND is the default, OR shoulds not appear here, ignore silently
			elif tokens and tokens[0] == OPERATOR_OR:
				# collect terms joined by OR
				assert isinstance(token, tuple)
				group = [token]
				while len(tokens) >= 2 and tokens[0] == OPERATOR_OR \
				and isinstance(tokens[1], tuple):
					tokens.pop(0)
					group.append(tokens.pop(0))
				root.append(OrGroup(group))
			else:
				# simple term in AND group
				assert isinstance(token, tuple)
				root.append(token)

		#~ print root
		return root

	@classmethod
	def regex(klass, text, case=False):
		'''Build a regex for a search term, expands wilcards and sets
		case sensitivity. Tries to guess if we look for whole word or
		not.
		'''
		# Build regex - first expand wildcards
		parts = text.split('*')
		regex = r'\S*'.join(map(re.escape, parts))

		# Next add word delimiters
		if re.search('^[\*\w]', text, re.U): regex = r'\b' + regex
		if re.search('[\*\w]$', text, re.U): regex = regex + r'\b'

		#~ print 'SEARCH REGEX: >>%s<<' % regex
		if case:
			return re.compile(regex)
		else:
			return re.compile(regex, re.I)


class Selection(object):
	pass


class RootSelection(Selection):

	def __init__(self, notebook):
		self.notebook = notebook

	def filter(self, key, word, regex):
		#~ print self.__class__.__name__, 'filter', key, word
		pages = []
		scores = {}
		if key == 'content':
			for store in self.notebook.get_stores():
				# TODO optimise by first checking the source before
				# checking the parsetree
				for page in store.walk():
					tree = page.get_parsetree()
					if tree:
						score = tree.countre(regex)
						if score:
							pages.append(page)
							scores[page] = score
		elif key == 'linksto':
			path = self.notebook.resolve_path(word)
			links = self.notebook.index.list_links(path, LINK_DIR_BACKWARD)
			for link in links:
				page = link.source
				pages.append(page)
				scores[page] = 1
		elif key in ('name', 'linksfrom'):
			pages = []
			print 'TODO: supprot keyword "%s"' % key
		else:
			assert False, 'BUG: unknown keyword: %s' % key

		#~ print '>>', pages
		return ResultsSelection(self.notebook, pages, scores)


class ResultsSelection(Selection):

	def __init__(self, notebook, pages, scores):
		self.notebook = notebook
		self.pages = pages
		self.scores = scores or {}

	def filter(self, key, word, regex):
		#~ print self.__class__.__name__, 'filter', key, word
		pages = []
		scores = {}
		if key == 'content':
			for page in self.pages:
				tree = page.get_parsetree()
				if tree:
					score = tree.countre(regex)
					if score:
						pages.append(page)
						scores[page] = self.scores.get(page, 0) + score
		elif key in ('name', 'linksfrom', 'linksto'):
			pages = []
			print 'TODO: supprot keyword "%s"' % key
		else:
			assert False, 'BUG: unknown keyword: %s' % key
		#~ print '>>>', pages
		return ResultsSelection(self.notebook, pages, scores)


class Searcher(object):

	# TODO - can we get rid of this class in favor of an
	# SearchSelection class that ties together the notebook and the query ?

	def __init__(self, notebook):
		self.notebook = notebook

	def search(self, query):
		return self._filter_and(query, query.root, RootSelection(self.notebook))

	def _filter_and(self, query, group, selection):
		for term in group:
			if isinstance(term, OrGroup):
				selection = self._filter_or(query, term, selection)
			else:
				key, word = term
				regex = query.regex(word)
				selection = selection.filter(key, word, regex)

		return selection

	def _filter_or(self, query, group, selection):
		# TODO support OR operator
		return selection

