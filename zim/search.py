# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This module contains the logic for searching in a notebook.

Supported operators:
 	NOT not -
 	AND and + &&
 	OR or ||

Order of precedence: AND, OR, NOT
so "foo AND NOT bar OR baz" means AND(foo, OR(NOT(bar), baz))

Supported keywords:
 	Content:
 	Name:
	Namespace:	# alias for Name XXX or Name: XXX:*
	Links:		# forward - alias for linksfrom
 	LinksFrom:	# forward
 	LinksTo:	# backward
 	ContentOrName: # the default, like Name: *X* or Content: X
 	Tag:		# look for a single tag

For the Content field we need to request the actual page contents,
all other fields we get from the index and are more efficient to
query.

For link keywords only a '*' at the right side is allowed
For the name keyword a '*' is allowed on both sides
For content '*' can occur on both sides, but does not match withspace
'''

# TODO keyword for deadlinks, keyword for pages with no content

# Queries are parsed into trees of groups of search terms
# Terms have a keyword and a string to look for
# When we start searching we walks through this tree and assemble the
# results. In theory we fully support nested groups, but the current
# query syntax doesn't allow them. So for now trees will only consist
# of a toplevel AND group possibly with nested OR groups one level
# below it.


import re

from zim.parsing import split_quoted_strings, unescape_quoted_string, Re
from zim.notebook import Path, PageNameError
from zim.index import LINK_DIR_BACKWARD, LINK_DIR_FORWARD


OPERATOR_OR = 1
OPERATOR_AND = 2
OPERATOR_NOT = 3

operators = {
	'or': OPERATOR_OR,
	'||': OPERATOR_OR,
	'and': OPERATOR_AND,
	'&&': OPERATOR_AND,
	'+': OPERATOR_AND,
	'-': OPERATOR_NOT,
	'not': OPERATOR_NOT,
}

KEYWORDS = (
	'content', 'name', 'namespace', 'contentorname',
	'links', 'linksfrom', 'linksto', 'tag'
)

keyword_re = Re('('+'|'.join(KEYWORDS)+'):(.*)', re.I)
operators_re = Re(r'^(\|\||\&\&|\+|\-)')
tag_re = Re(r'^\@(\w+)$', re.U)

class QueryTerm(object):
	'''Wrapper for a single term in a query. Consists of a keyword,
	a string and a flag for inverse (NOT operator).
	'''

	def __init__(self, keyword, string, inverse=False):
		self.keyword = keyword
		self.string = string
		self.inverse = inverse

	def __eq__(self, other):
		if isinstance(other, QueryTerm):
			return self.keyword == other.keyword \
			and self.string == other.string \
			and self.inverse == other.inverse
		else:
			return False

	def __repr__(self):
		if self.inverse:
			return '<NOT %s: "%s">' % (self.keyword, self.string)
		else:
			return '<%s: "%s">' % (self.keyword, self.string)


class QueryGroup(list):
	'''Wrapper for a sub group of a query. Just a list of QueryTerms
	with an asociated operator (either AND or OR).
	'''

	def __init__(self, operator, terms=None):
		assert operator in (OPERATOR_AND, OPERATOR_OR)
		self.operator = operator
		if terms:
			self[:] = terms


class Query(object):
	'''This class wraps a query as typed by the user. It parses the
	query into a tree of QueryGroup and QueryTerm objects. The 'root'
	attribute contains the top of the tree, while the 'string' attribute
	contains the original query.
	'''

	def __init__(self, string):
		self.string = string
		self.root = self._parse_query(string)

	def _parse_query(self, string):
		# First do a raw tokenizer
		words = split_quoted_strings(string, unescape=False)
		tokens = []
		while words:
			if operators_re.match(words[0]):
				w = operators_re[0]
				words[0] = words[0][len(w):]
			else:
				w = words.pop(0)

			if w.lower() in operators:
				tokens.append(operators[w.lower()])
			elif keyword_re.match(w):
				keyword = keyword_re[1].lower()
				string = keyword_re[2] or words.pop(0)
				string = unescape_quoted_string(string)
				if keyword == 'links':
					keyword = 'linksfrom'
				tokens.append(QueryTerm(keyword, string))
			elif tag_re.match(w):
				tokens.append(QueryTerm('tag', w[1:]))
			else:
				w = unescape_quoted_string(w)
				tokens.append(QueryTerm('contentorname', w)) # default keyword
		#~ print tokens

		# Then parse NOT operator out
		tokens, mytokens = [], tokens
		while mytokens:
			token = mytokens.pop(0)
			if token == OPERATOR_NOT:
				if mytokens and isinstance(mytokens[0], QueryTerm):
					token = mytokens.pop(0)
					token.inverse = True
					tokens.append(token)
				else:
					pass # ignore
			else:
				tokens.append(token)
		#~ print tokens

		# Finally group in AND and OR groups
		root = QueryGroup(OPERATOR_AND)
		while tokens:
			token = tokens.pop(0)
			if isinstance(token, QueryTerm):
				if tokens and tokens[0] == OPERATOR_OR:
					# collect terms joined by OR
					assert isinstance(token, QueryTerm)
					group = QueryGroup(OPERATOR_OR)
					group.append(token)
					while len(tokens) >= 2 and tokens[0] == OPERATOR_OR \
					and isinstance(tokens[1], QueryTerm):
						tokens.pop(0)
						group.append(tokens.pop(0))
					root.append(group)
				else:
					# simple term in AND group
					root.append(token)
			else:
				assert token in (OPERATOR_AND, OPERATOR_OR)
				pass # AND is the default, OR shoulds not appear here, ignore silently

		#~ print root
		return root

	@property
	def simple_match(self):
		'''Used to determine a simple matching string to be used
		in the find method in the pageview. Used in SearchDialog.
		'''
		# TODO make this return a list with positive terms for content
		# if find supports an OR operator, highlight them all
		if len(self.root) == 1 and isinstance(self.root[0], QueryTerm) \
		and self.root[0].keyword in ('content', 'contentorname'):
			return self.root[0].string
		else:
			return None


class PageSelection(set):
	'''This class is just a container of path objects'''

	pass


class SearchSelection(PageSelection):
	'''This class wraps a set of Page or ResultPath objects which result
	from processing a search query. The atribute 'scores' gives a dict
	with an arbitrary integer for each path in this set to rank how well
	they match the query.
	'''

	def __init__(self, notebook):
		self.notebook = notebook
		self.query = None
		self.scores = {}

	def search(self, query, selection=None):
		'''Populate this SearchSelection with results for a query.
		If a selection is given this should be a subset to search
		within. This method flushes any previous results in this set.
		'''
		# TODO support callback

		# Clear state
		self.query = query
		self.clear()
		self.scores = {}

		# Actual search
		self.update(self._process_group(query.root, selection))

		# Clean up results
		scored = set(self.scores.keys())
		for path in scored - self:
			self.scores.pop(path)

	def _process_group(self, group, scope):
		# Decide what operator to use
		if group.operator == OPERATOR_AND:
			# For AND scope is always latest results
			def op_func(results, scope, newresults):
				#~ print '!! AND', results, newresults
				if results is None:
					return newresults, newresults
				else:
					results &= newresults
					return results, results
		else: # OPERATOR_OR
			# For OR we always keep the original scope
			def op_func(results, scope, newresults):
				#~ print '!! OR', results, newresults
				if results is None:
					return newresults, scope
				else:
					results |= newresults
					return results, scope

		# For optimization we sort the terms in the group based  on how
		# easy we can get them. Anything that needs content is last.
		indexterms = []
		subgroups = []
		contentterms = []
		for term in group:
			if isinstance(term, QueryGroup):
				subgroups.append(term)
			else:
				assert isinstance(term, QueryTerm)
				if term.keyword in ('content', 'contentorname'):
					contentterms.append(term)
				else:
					indexterms.append(term)

		# First process index terms
		results = None
		for term in indexterms:
			results, scope = op_func(results, scope,
				self._process_from_index(term, scope) )

		# Next we process subgroups - recursing
		for term in subgroups:
			results, scope = op_func(results, scope,
				self._process_group(term, scope) )

		# Now do the content terms all at once
		if contentterms:
			results, scope = op_func(results, scope,
				self._process_content(contentterms, scope, group.operator))

		# And return our results as summed by the operator
		return results or set()

	def _count_score(self, path, score):
		self.scores[path] = self.scores.get(path, 0) + score

	def _process_from_index(self, term, scope):
		# Process keywords we can get from the index, just one term at
		# a time. Scope is used to limit the search when practical, but
		# no guarantee for following it.
		results = set()
		index = self.notebook.index

		if term.keyword in ('name', 'namespace'):
			if scope:
				generator = iter(scope)
			else:
				generator = index.walk()

			if term.keyword == 'namespace':
				regex = self._namespace_regex(term.string)
			else:
				regex = self._name_regex(term.string)

			#~ print '!! REGEX: ' + regex.pattern
			for path in generator:
				if regex.match(path.name):
					results.add(path)

		elif term.keyword in ('linksfrom', 'linksto'):
			if term.keyword == 'linksfrom': dir = LINK_DIR_FORWARD
			else: dir = LINK_DIR_BACKWARD

			if term.string.endswith('*'):
				recurs = True
				string = term.string.rstrip('*')
			else:
				recurs = False
				string = term.string

			try:
				path = self.notebook.resolve_path(string)
			except PageNameError:
				return results

			if recurs:
				links = index.list_links_to_tree(path, dir)
			else:
				links = index.list_links(path, dir)

			if dir == LINK_DIR_FORWARD:
				for link in links:
					results.add(link.href)
			else:
				for link in links:
					results.add(link.source)

		elif term.keyword == 'tag':
			tag = index.lookup_tag(term.string)
			if tag:
				for path in index.list_tagged_pages(tag):
					results.add(path)

		else:
			assert False, 'BUG: unknown keyword: %s' % term.keyword

		# Inverse selection
		if term.inverse:
			if not scope:
				scope = set()
				for p in index.walk():
					scope.add(p)
			results = scope - results

		for path in results:
			self._count_score(path, 1)

		return results

	def _process_content(self, terms, scope, operator):
		# Process terms for content, process many at once in order to
		# only open the page once and allow for a linear behavior of the
		# callback function. (We could also have relied on page objects
		# caching the parsetree, but then there is no way to support a
		# useful callback method.)
		results = set()

		for term in terms:
			term.content_regex = self._content_regex(term.string)
			term.name_regex = self._name_regex('*'+term.string.strip('*')+'*')

		if scope:
			def page_generator():
				for path in scope:
					yield self.notebook.get_page(path)
			generator = page_generator()
		else:
			generator = self.notebook.walk()

		for page in generator:
			#~ print '!! Search content', page
			tree = page.get_parsetree()
			if tree is None:
				continue # Assume need to have content even for negative query

			path = Path(page.name)
			if operator == OPERATOR_AND:
				score = 0
				for term in terms:
					#~ print '!! Count AND %s' % term
					myscore = tree.countre(term.content_regex)
					if term.keyword == 'contentorname' \
					and term.name_regex.search(page.name):
						myscore += 10

					if bool(myscore) != term.inverse: # implicite XOR
						score += myscore or 1
					else:
						score = 0
						break

				if score:
					results.add(path)
					self._count_score(path, score)
			else: # OPERATOR_OR
				for term in terms:
					#~ print '!! Count OR %s' % term
					score = tree.countre(term.content_regex)
					if term.keyword == 'contentorname' \
					and term.name_regex.search(page.name):
						score += 10

					if bool(score) != term.inverse: # implicite XOR
						results.add(path)
						self._count_score(path, score or 1)

		return results

	def _name_regex(self, string, case=False):
		# Build a regex for matching a glob against a page name
		# Don't use word delimiters here, since page names could be in
		# camelcase. User should include ":" if they want to match
		# whole namespace.
		if string.startswith('*'):
			prefix = r'.*'
			string = string.lstrip('*')
		else:
			prefix = r'^'
			string = string.lstrip(':')

		if string.endswith('*'):
			postfix = r''
			string = string.rstrip('*')
		else:
			postfix = r'$'

		regex = prefix + re.escape(string) + postfix

		if case:
			return re.compile(regex)
		else:
			return re.compile(regex, re.I)

	def _namespace_regex(self, string, case=False):
		# like _name_regex but adds recursive descent below the page
		namespace = re.escape( string.strip('*:') )
		regex = r'^(' + namespace + '$|' + namespace + ':)'
		if case:
			return re.compile(regex)
		else:
			return re.compile(regex, re.I)

	def _content_regex(self, string, case=False):
		# Build a regex for a content search term, expands wildcards
		# and sets case sensitivity. Tries to guess if we look for
		# whole word or not.

		# Build regex - first expand wildcards
		parts = string.split('*')
		regex = r'\S*'.join(map(re.escape, parts))

		# Next add word delimiters
		if re.search(r'^[\*\w]', string, re.U): regex = r'\b' + regex
		if re.search(r'[\*\w]$', string, re.U): regex = regex + r'\b'

		#~ print 'SEARCH REGEX: >>%s<<' % regex
		if case:
			return re.compile(regex, re.U)
		else:
			return re.compile(regex, re.U | re.I)
