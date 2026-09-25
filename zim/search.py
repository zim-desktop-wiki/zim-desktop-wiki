
# Copyright 2009-2026 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This module contains the logic for searching in a notebook.

The main class to use page search is L{PageSearch}. See the manual for
documentation of the supported query language.

Also see L{zim.parse.searchquery} for generic parsing of the query language
'''

# One design objective here is to minimize the number of files being read
# from disk for full content search. To achieve this the following logic
# is imployed:
# 
# - in execution of the query, index terms are prioritized before content
#   terms to reduce the selection of pages
# - the execution processes pages linearly, so once a page is read, it 
#   gets filtered through all remaining query terms while keeping the
#   content in memory
# - finally in reading a page, we first read the source text, and if there
#   is no match there, we skip parsing the text


import re
import logging
import itertools

from collections.abc import Iterable, Callable
from typing import Optional

from zim.notebook import IndexNotFoundError, LINK_DIR_BACKWARD, LINK_DIR_FORWARD

from zim.plugins import extendable, ExtensionBase

from zim.parse.searchquery import *
from zim.parse.tokenlist import tokens_to_text


logger = logging.getLogger('zim.search')


class PageSearchResult:
	'''Object to combine notebook path with text snippets and search score
	It can also hold a reference to a C{Page} object for efficient caching
	during execution of a query.
	'''

	# Choosen to not make this a subclass of Path in order to preserve IndexPaths
	# this could improve lookup speed for index terms

	__slots__ = ('path', '_page', 'search_snippets', 'search_score')

	def __init__(self, path: 'Path', score: int = 1, snippets: Optional[list] = None):
		self.path = path
		self._page = None
		self.search_score = score # deafult is 1 as any succesfull result has at least score 1
		self.search_snippets = snippets

	def get_page(self, notebook: 'Notebook') -> 'Page':
		'''Proxy for C{notebook.get_page()} that caches result'''
		if not self._page:
			self._page = notebook.get_page(self.path)
		return self._page

	def add_search_snippet(self, snippet: str, score: int = 1):
		'''Add a text snippet to the result and update the score
		@param snippet: text fragment showing the match
		@param score: add this count to the result score
		'''
		if not self.search_snippets:
			self.search_snippets = []
		self.search_snippets.append(snippet)
		self.search_score += score


class SearchCancelledException(Exception):
	'''Exception to raise from ui callback to cancel the search'''
	pass


EXECUTION_PRIO_INDEX = 10 #: Search based on database index
EXECUTION_PRIO_MIXED = 20 #: Nested group that has both index and content terms
EXECUTION_PRIO_CONTENT = 30 #: Requires reading page content
EXECUTION_PRIO_OFFSET_NEGATE = 5 #: Negation wrapper is less efficient, so gets offset

UI_CALLBACK_RATE_FOR_CONTENT = 5 #: if set, call the callback for every n pages being read
UI_CALLBACK_RATE_INDEX = 20 #: if set, call the callback for every n pages being yielded

SCORE_PAGENAME_TAG = 10 #: score awarded for a pagename or tag match


class PageSearchProvider():
	'''Base class for "search providers"

	These classes implement the search functionality for a single keyword term.
	Depending on the place of the term in the query either C{generate()},
	C{filter()}, or C{checker()} will be called.

	The provider deals with L{PageSearchResult} objects which are notebook
	paths. The provider can choose to add snippets to the result and/or change
	the score.

	See L{IndexSearchProvider} and L{ContentSearchProvider} for specific
	optimizations.
	'''

	SUPPORTS_NEGATE = False #: flag whether providers supports negation (NOT) or needs a wrapper
	EXECUTION_PRIO = EXECUTION_PRIO_CONTENT # conservative default

	def __init__(self, notebook: 'Notebook', term: SearchQueryTerm, flags: SearchFlag=SearchFlag(0), ui_callback: Optional[Callable]=None):
		'''Constructor
		@param notebook: the C{Notebook} object to search
		@param term: a L{SearchQueryTerm} to search
		@param flags: optional SEARCH_CASE_SENSITIVE and SEARCH_WHOLE_WORD options
		@param ui_callback: an optional callback function that should be called once in a while for longer running operations
		'''
		assert isinstance(flags, SearchFlag)
		self.notebook = notebook
		self.term = term
		self.ui_callback = ui_callback
		self.flags = flags

	@classmethod
	def get_find_string(cls, term: SearchQueryTerm) -> str|None:
		'''Get a string to match this term in content or C{None}, only applicable for content terms
		Used to translate a query to a string for the findbar in the textview
		Since this method does not get the SEARCH_CASE_SENSITIVE or SEARCH_WHOLE_WORD flags, assume standard behavior.
		The flags are applied in the wrapper.
		'''
		return None

	def walk_notebook(self) -> Iterable[PageSearchResult]:
		'''Generator for all pages, yields L{PageSearchResult}s'''
		for p in self.notebook.pages.walk():
			yield PageSearchResult(p)

	def generate(self) -> Iterable[PageSearchResult]:
		'''Generate results
		This means searching the whole notebook and either yielding results
		or returning an iterable for the results
		The results should be L{PageSearchResult} objects
		'''
		raise NotImplementedError('generate in %s' % self.__class__.__name__)

	def filter(self, source: Iterable[PageSearchResult]) -> Iterable[PageSearchResult]:
		'''Filter results
		Filtering results from a different source and either yielding results
		or returning an iterable for the results
		While filtering the search result can be updated with snippets and/or score
		@param source: iterable of L{PageSearchResult}s
		@returns: iterator of filtered results
		'''
		raise NotImplementedError('filter in %s' % self.__class__.__name__)

	def checker(self) -> Callable[[PageSearchResult], bool]:
		'''Create a check function
		The check function can "freeze" state, link intermediate cached
		results, and will have a shorter lifetime than the provider itself
		Although the check function returns boolean, it may also update the search result
		with snippets and/or score
		@returns: a function with the spec: C{check(result: PageSearchResult) -> bool}
		'''
		raise NotImplementedError('checker in %s' % self.__class__.__name__)


class IndexedSearchProvider(PageSearchProvider):
	'''Base class for "search providers" that are based on the index
	Assumption is that these are optimized for fast lookup in the C{generate()}
	function.
	'''

	EXECUTION_PRIO = EXECUTION_PRIO_INDEX

	def filter(self, source):
		'''Filter implementation based on caching the results from generate'''
		mymatches = set(r.path.name for r in self.generate())
		for r in source:
			if r.path.name in mymatches:
				r.search_score += 1
				yield r

	def checker(self):
		'''Check function implementation based on caching the results from generate'''
		mymatches = set(r.path.name for r in self.generate())

		def check(r):
			if r.path.name in mymatches:
				r.search_score += 1
				return True
			else:
				return False

		return check


class ContentSearchProvider(PageSearchProvider):
	'''Base class for "search providers" that need to do a content check
	per page.
	Assumption is that these are based on a check function created by
	C{checker()} that needs to visit each page and read content.

	When reading files from disk, the provider should call the 
	c{ui_callback} function once in a while, if it is set.
	'''

	EXECUTION_PRIO = EXECUTION_PRIO_CONTENT

	def generate(self):
		'''Generate implementation based on filtering the notebook'''
		return self.filter(self.walk_notebook())

	def filter(self, source):
		'''Filter implementation based on the check function'''
		check = self.checker()
		for r in source:
			if check(r):
				yield r

	@classmethod
	def get_find_string(cls, term):
		return term.value


class PageNameProvider(IndexedSearchProvider):
	'''Provider for the keywords `name`, `section` and `namespace`'''

	SUPPORTS_NEGATE = True
	EXECUTION_PRIO = EXECUTION_PRIO_INDEX + 1
		# In comparison to other index providers this one also does optimized check and filter
		# --> raise prio, let other index provider do generation if possible in query

	def __init__(self, notebook, term, flags=SearchFlag(0), ui_callback=None):
		super().__init__(notebook, term, flags, ui_callback)
		if term.keyword in ('namespace', 'section'):
			term = term.copy(value= '::' + term.value.strip(':') + ':') # force absolute lookup
		self.regex = search_query_pagename_term_to_regex(term, self.flags)

	def generate(self):
		if self.term.negate:
			return self.filter(self.walk_notebook())
		else:
			# We generate candidates by lookup of pages by longest word in query
			words = re.findall('\\w+', self.term.value, re.U)
			if not words:
				return [] # no valid pagename without any alphanumerics

			words.sort(key=lambda w: len(w))
			longest = words[-1]
			return self.filter(self._generate(longest))

	def _generate(self, text):
			# Walk part of notebook that matches text
			for p in self.notebook.pages.match_all_pages(text, limit=100_000): # arbitrairy high limit
				yield PageSearchResult(p)
				for c in self.notebook.pages.walk(p):
					yield PageSearchResult(c)

	def filter(self, source):
		check = self.checker()
		for r in source:
			if check(r):
				yield r

	def checker(self):
		if not self.regex:
			return lambda r: False
		elif self.term.negate:
			return lambda r: not self.regex.search(r.path.name)
		else:
			def check(r):
				if self.regex.search(r.path.name):
					r.search_score += SCORE_PAGENAME_TAG
					return True
				else:
					return False
			return check


class LinksProvider(IndexedSearchProvider):
	'''Provider for the keywords `links`, `linksfrom` and `linksto`'''

	def __init__(self, notebook, term, flags=SearchFlag(0), ui_callback=None):
		super().__init__(notebook, term, flags, ui_callback)
		self.link_dir = LINK_DIR_FORWARD if term.keyword in ('links', 'linksfrom') else LINK_DIR_BACKWARD
		self.inner = PageNameProvider(notebook, term, flags=flags, ui_callback=ui_callback)

	def generate(self):
		for pagename_result in self.inner.generate():
			# FUTURE: could optimize for pagename queries ending in ":+" to use list_links_section()
			# but currently list_links_section() is also not really optimized
			links = self.notebook.links.list_links(pagename_result.path, self.link_dir)
			if self.link_dir == LINK_DIR_FORWARD:
				yield from [PageSearchResult(link.target) for link in links]
			else:
				yield from [PageSearchResult(link.source) for link in links]


class TagsProvider(IndexedSearchProvider):
	'''Provider for the `tags` keyword'''

	def __init__(self, notebook, term, flags=SearchFlag(0), ui_callback=None):
		super().__init__(notebook, term, flags, ui_callback)
		if term.keyword == 'tag' or re.match('^@\\w+@$', term.value):
			# Backward compatible exact match
			# Or optimized for direct match
			self.regex = None
			self.generate = self.generate_exact
		else:
			self.regex = search_query_tags_term_to_regex(term, self.flags)
			if self.regex:
				self.generate = self.generate_glob
			else:
				self.generate = lambda: [] # do nothing

	@classmethod
	def get_find_string(cls, term):
		if term.keyword == 'tag' or re.match('^@\\w+@$', term.value):
			return '@%s ' % term.value.strip('@')
		else:
			return '@' + term.value.strip('@')

	def generate_exact(self):
		tag = self.term.value.strip('@')
		try:
			return [PageSearchResult(p, score=SCORE_PAGENAME_TAG) for p in self.notebook.tags.list_pages(tag)]
		except IndexNotFoundError:
			return []

	def generate_glob(self):
		words = re.findall('\\w+', self.term.value, re.U)
		if not words:
			return [] # no valid pagename without any alphanumerics

		words.sort(key=lambda w: len(w))
		longest = words[-1]

		for tag in self.notebook.tags.match_tags(longest):
			if self.regex.search(tag.name):
				for p in self.notebook.tags.list_pages(tag):
					yield PageSearchResult(p, score=SCORE_PAGENAME_TAG)


class TextProvider(ContentSearchProvider):
	'''Provider for the `text` or `content` keyword'''

	SUPPORTS_NEGATE = True

	def __init__(self, notebook, term, flags=SearchFlag(0), ui_callback=None):
		super().__init__(notebook, term, flags, ui_callback)
		self.regex = search_query_term_to_regex(term, self.flags)
		self.ui_callback_counter = 0

	def checker(self):
		return self.check_content

	def check_content(self, result):
		if not self.regex:
			return False

		try:
			page = result.get_page(self.notebook)
			if page.peek_has_parsetree():
				tree = page.get_parsetree()
			else:
				# Prevent parsing the tree unless there is a match with the source code
				source = page.peek_get_source()

				if self.ui_callback:
					# Make sure ui remains responsive
					if self.ui_callback_counter == UI_CALLBACK_RATE_FOR_CONTENT:
						self.ui_callback_counter = 0
						self.ui_callback()
					else:
						self.ui_callback_counter += 1

				if source and self.regex.search(source):
					tree = page.get_parsetree()
				else:
					return self.term.negate
		except SearchCancelledException:
			raise
		except:
			logger.exception('Exception searching content: %s', result.path)
			return False

		if tree:
			if not hasattr(tree, '__search_text'):
				# Hack to buffer content
				tree.__search_text = tokens_to_text(tree.iter_tokens())
			count = len(self.regex.findall(tree.__search_text))
			if count:
				result.search_score += count
			return bool(count) != self.term.negate
		else:
			return self.term.negate


class GroupProvider(PageSearchProvider):

	def __init__(self, notebook, members):
		super().__init__(notebook, None)

		# Determine group execution prio
		members.sort(key=lambda p: p.EXECUTION_PRIO)
		if members[0].EXECUTION_PRIO < EXECUTION_PRIO_CONTENT \
			and members[-1].EXECUTION_PRIO >= EXECUTION_PRIO_CONTENT:
				self.EXECUTION_PRIO = EXECUTION_PRIO_MIXED
		else:
			self.EXECUTION_PRIO = members[-1].EXECUTION_PRIO # Take max

		self.members = members


class AndGroup(GroupProvider):
	'''Provider for `(a AND b)`'''

	def generate(self):
		source = self.members[0].generate()
		return self._filter(source, self.members[1:])

	def filter(self, source):
		return self._filter(source, self.members)

	def _filter(self, source, members):
		# Create pipeline of filters, yield results
		# surviving all steps
		it = members[0].filter(source)
		for p in members[1:]:
			it = p.filter(it)

		yield from it

	def checker(self):
		checkers = [p.checker() for p in self.members]
		return lambda r: all(c(r) for c in checkers)


class OrGroup(GroupProvider):
	'''Provider for `(a OR b)`'''

	# To ensure only yielding once, we buffer results we have seen
	# this gives penalty in memory usage for queries with many results

	def generate(self):
		# Used for top level query group, optimize between index lookup and 1-by-1 content checks
		indexed = [p for p in self.members if isinstance(p, IndexedSearchProvider)]
		content = [p for p in self.members if p not in indexed]

		seen = set()
		for p in indexed:
			for r in p.generate():
				if r.path.name not in seen:
					seen.add(r.path.name)
					# FUTURE: check remaining terms in the OR for text matches?
					yield r

		if content:
			source = self.walk_notebook()
			yield from self._filter(source, content, seen)

	def filter(self, source):
		return self._filter(source, self.members, set())

	def _filter(self, source, providers, seen):
		checks = [p.checker() for p in providers]
		for r in source:
			for check in checks:
				if check(r):
					if r.path.name not in seen:
						seen.add(r.path.name)
						# FUTURE: check remaining terms in the OR for text matches?
						yield r

	def checker(self):
		checkers = [p.checker() for p in self.members]
		return lambda r: any(c(r) for c in checkers)


class NegateOperator():
	'''Negate a SearchProvider'''

	# Uses `itertools.tee` to duplicate source and compare results of wrapped
	# provider versus source. Results that are not matched by the inner
	# function are buffered in memory. These are the results we want after
	# negation, so we assume these are limitted in number

	def __init__(self, inner: PageSearchProvider):
		self.inner = inner
		self.EXECUTION_PRIO = inner.EXECUTION_PRIO + EXECUTION_PRIO_OFFSET_NEGATE

	def walk_notebook(self):
		return self.inner.walk_notebook()

	def generate(self):
		source = self.inner.walk_notebook()
		return self.filter(source)

	def filter(self, source):
		it, ref = itertools.tee(source, 2)
		for r in self.inner.filter(it):
			for c in ref:
				if c.path != r.path:
					yield c
				else:
					break # pass over this item
		else:
			yield from ref # remainder did not match inner

	def checker(self):
		check = self.inner.checker()
		return lambda r: not check(r)


class PageSearchExtension(ExtensionBase):
	'''Base class for extensing search functionality'''

	def __init__(self, plugin, page_search: 'PageSearch'):
		super().__init__(plugin, page_search)
		self.page_search = page_search

	def add_keyword(self, keyword: str, **attributes):
		'''Add custom search keyword or overload default keyword implementation

		Overwrites existing keywords, so be carefull to merge attributes where needed
		before calling this method

		@param **attributes: keywords attributes used in page search, these include attributes
		for search quary parsing and for execution. At minimum a "provider" attributes should be
		specified, giving a L{PageSearchProvider} sub-class or a constructor function, 
		or the "expand_terms" attribute should be specified.
		'''
		if 'provider' in attributes:
			assert isinstance(attributes['provider'], Callable) \
				or issubclass(attributes['provider'], PageSearchProvider)
		else:
			assert 'expand_terms' in attributes, 'Attributes should contain either "provider", or "expand_terms"'

		self.page_search.KEYWORDS[keyword] = attributes


@extendable(PageSearchExtension)
class PageSearch(object):
	'''Object to handle page search
	Can be extended by plugins to modify search behavior
	'''

	_KEYWORDS = {
		'text': {'provider': TextProvider},
		'content': {'provider': TextProvider},
		'name': {'provider': PageNameProvider},
		'namespace': {'provider': PageNameProvider},
		'section': {'provider': PageNameProvider},
		'links': {'provider': LinksProvider},
		'linksfrom': {'provider': LinksProvider},
		'linksto': {'provider': LinksProvider},
		'tag': {'provider': TagsProvider},
		'tags': {'implicit_match': search_tag_re, 'provider': TagsProvider},
		'any': {'expand_terms': ['name', 'tags', 'linksfrom', 'text']},
		'contentorname': {'expand_terms': ['name', 'content']}, # for backward compatibility, undocumented
	}

	_DEFAULT_KEYWORD = 'any'

	def __init__(self, notebook: 'Notebook', ui_callback: Optional[Callable[[],None]]=None):
		'''Constructor
		@param notebook: a L{Notebook} object
		@param ui_callback: optional function that is called during longer operations to keep
		the ui responsive. Can raise L{SearchCancelledException} to break the search loop
		'''
		self.notebook = notebook
		self.KEYWORDS = dict((k, dict(v)) for k, v in self._KEYWORDS.items()) # copy defaults
		self.DEFAULT_KEYWORD = self._DEFAULT_KEYWORD
		self.ui_callback = ui_callback
		self.ui_callback_counter = 0

	def parse_page_search_query(self, string: str, flags: SearchFlag=SearchFlag(0)) -> SearchQuery:
		'''Parse string into L{SearchQuery} object'''
		return parse_search_query(string, self.KEYWORDS, default_keyword=self.DEFAULT_KEYWORD, flags=flags)

	def search_pages(self, query: SearchQuery) -> Iterable[PageSearchResult]:
		'''Generator for page search results

		@param query: L{SearchQuery} object created by L{parse_page_search_query()}
		@returns: yields sets with results
		'''
		provider = self._compile_page_search(query, query.flags)
		try:
			for r in provider.generate():
				r._page = None # avoid leaking lots of Page references, keeping content in memory
				if self.ui_callback:
						# Make sure ui remains responsive
						if self.ui_callback_counter == UI_CALLBACK_RATE_INDEX:
							self.ui_callback_counter = 0
							self.ui_callback()
						else:
							self.ui_callback_counter += 1
				yield r
		except SearchCancelledException:
			pass

	def _compile_page_search(self, query, flags):
		assert isinstance(query, SearchQuery)
		flags = query.flags if query.flags else flags # can be overruled, else take parent flags (enum, do not use "or" here)

		if query.operator == OPERATOR_OR and query.negate:
			# Optimize for equivalence NOT(a OR b) = (NOT a AND NOT b) since AND is more efficiently implemented
			query = self._transform_not_or_group(query)

		members = []
		for term in query.terms:
			if isinstance(term, SearchQuery):
				provider = self._compile_page_search(term, flags) # recurs for nested group
			elif 'expand_terms' in self.KEYWORDS[term.keyword]:
				provider = self._compile_expand_terms(term, flags)
			else:
				cls = self.KEYWORDS[term.keyword]['provider']
				provider = cls(self.notebook, term, flags, self.ui_callback)
				if term.negate and not provider.SUPPORTS_NEGATE:
					provider = NegateOperator(provider)

			members.append(provider)

		if len(members) == 1:
			return members[0]
		else:
			group = AndGroup(self.notebook, members) if query.operator == OPERATOR_AND else OrGroup(self.notebook, members)
			if query.negate:
				group = NegateOperator(group)
			return group

	def _transform_not_or_group(self, query):
		# Transform `NOT (a OR b)` to `NOT a AND NOT b`
		group = SearchQuery(OPERATOR_AND)
		for t in query:
			t = t.copy()
			t.negate = t.negate != True # XOR
			group.add(t)

		return group

	def _compile_expand_terms(self, term, flags):
		# Expand terms of an "any" keyword
		# Either `a (a OR b)`` or a `NOT a AND NOT b` group
		query = SearchQuery(OPERATOR_AND if term.negate else OPERATOR_OR)
		for keyword in self.KEYWORDS[term.keyword]['expand_terms']:
			t = term.copy(keyword=keyword)
			query.terms.append(t)

		return self._compile_page_search(query, flags) # indirect recurs

	def find_query_from_search_query(self, query: SearchQuery) -> 'FindQuery|None':
		'''Turn a C{SearchQuery} into a C{FindQuery}
		All positive terms that match content are taken into account
		'''
		from zim.gui.pageview.find import FindQuery

		seen = set()
		def is_double(r):
			if r in seen:
				return True
			else:
				seen.add(r)
				return False

		strings = list(r for r in self._walk_search_query_for_find(query) if not is_double(r))
		if strings:
			return FindQuery('|'.join(strings), query.flags)
		else:
			return None

	def _walk_search_query_for_find(self, query):
		for term in query:
			if term.negate:
				continue # skip negated content (and ignore double negated...)

			if isinstance(term, SearchQuery):
				yield from self._walk_search_query_for_find(term) # recurs
			else: # SearchQueryTerm
				if 'expand_terms' in self.KEYWORDS[term.keyword]:
					## HACK to prevent a big ..|..|.. match, just do content matching for "any" term ##

					#q = SearchQuery(OPERATOR_OR)
					#for keyword in self.KEYWORDS[term.keyword]['expand_terms']:
					#	t = term.copy(keyword=keyword)
					#	q.add(t)
					#yield from self._walk_search_query_for_find(q) # recurs

					yield TextProvider.get_find_string(term)
				else:
					cls = self.KEYWORDS[term.keyword]['provider']
					string = cls.get_find_string(term)
					if string:
						yield string
