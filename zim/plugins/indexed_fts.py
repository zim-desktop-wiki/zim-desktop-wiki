# coding=utf-8

'''Plugin for indexing page contents using sqlite's FTS5 module
It borrows a lot from the task list plugin which also needs to index all
page contents.
'''

import contextlib
import sqlite3
import logging
import json

from zim.plugins import PluginClass
from zim.notebook import NotebookExtension, Path
from zim.notebook.index.base import IndexerBase
from zim.parse.tokenlist import tokens_to_text
from zim.parse.searchquery import search_query_term_to_regex, SearchFlag
from zim.search import PageSearchExtension, \
	IndexedSearchProvider, PageSearchResult, TextProvider, \
	EXECUTION_PRIO_MIXED, OPERATOR_EQUAL, SEARCH_WHOLE_WORD, SEARCH_CASE_SENSITIVE


logger = logging.getLogger("zim.plugins.indexed_fts")


def compare_version(curv, minv):
	'''Check if a passed tuple of version numbers curv is equal or higher
	than the version tuple passed in minv
	Most significant digits come first, all should be integers.
	'''
	for i, j in zip(curv, minv):
		if i > j:
			return True

		elif i == j:
			continue

		else:
			return False

	# Coming here means we have the minimum working version.
	return True


class IndexedFTSPlugin(PluginClass):

	plugin_info = {
		'name': _('Indexed Full-Text Search'), # T: plugin name
		'description': _('''\
This plugin provides full-text indexing of
page contents for fast full-text search,
based on the FTS5 virtual table module of
sqlite.
'''), # T: plugin description
		'author': 'Nimrod Maclomhair',
		'help': 'Plugins:Indexed Full Text Search'
	}

	plugin_preferences = (
		# key, type, label, default
		('remove_diacritics', 'bool', _('Remove diacritics before indexing'), False), # T: plugin preference for indexed search
		('tokenchars', 'string', _('Additional token characters'), ''), # T: plugin preference for indexed search
	)

	@classmethod
	def check_dependencies(klass):
		with contextlib.closing(sqlite3.connect(':memory:')) as connection:
			with connection:
				try:
					with contextlib.closing(connection.cursor()) as cursor:
						cursor.execute('SELECT name FROM pragma_module_list() WHERE name = ?;', ('fts5',))
						data = cursor.fetchall()
						has_fts5 = ('fts5',) in data
				except sqlite3.Error:
					with contextlib.closing(connection.cursor()) as cursor:
						cursor.execute('pragma compile_options;')
						data = cursor.fetchall()
						has_fts5 = ('ENABLE_FTS5',) in data

		# this is the smallest version with available feature ``contentless-delete tables``
		has_min_version = compare_version(
			sqlite3.sqlite_version_info, (3, 43, 0)
		)

		return (has_fts5 and has_min_version), [
			('sqlite FTS5 module', has_fts5, True),
			('sqlite version 3.43.0 or higher', has_min_version, True)
		]


class FTSSearchExtension(PageSearchExtension):

	def __init__(self, plugin, page_search):
		super().__init__(plugin, page_search)
		self.add_keyword('text', provider=FTSSearchProvider)
		self.add_keyword('content', provider=FTSSearchProvider)


def quote_for_fts(keyword):
	return '"' + keyword.replace('"', '""') + '"'


def escape_for_glob(keyword):
	# quote glob operators not supported by zim search syntax
	return keyword.translate({
		"?": "%?",
		"%": "%%"
	})


class FTSSearchProvider(IndexedSearchProvider):
	# Provider for content search using this plugin

	# NOTE: depending on the query there are several ways to query the database
	#
	#   1. MATCH statement works for words and phrases but only supports glob at the end.
	#      Found this also slows down for large notebooks.
	#   2. GLOB in the Vocab table allows globs anywhere in the word, but does not support
	#      phrases
	#   3. Therefore phrases with globs in it, we are out of luck and need to combine 
	#      querying the index for one of the words (assume longest is most significant)
	#      and post-filter to do regex match on the content for the exact phrase. Slower
	#      than direct database query, but faster than searching all content without index
	#
	# This class dynamicly combines strategy 2 and 3
	#
	# Since the FTS table is case-insensitive, strategy 3 is also required for case-sensitive queries

	# FUTURE: use BM25 ranking to set matching score ?

	def __init__(self, notebook, term, flags=SearchFlag(0), ui_callback=None):
		super().__init__(notebook, term, flags, ui_callback)
		if flags or term.kw_operator == OPERATOR_EQUAL or any(c.isspace() for c in term.value):
			# flags and equal operator are handled by filter through TextProvider check
			# and OPERATOR_EQUAL is also interpreted as exact match, so case sensitive
			self.EXECUTION_PRIO = EXECUTION_PRIO_MIXED
			self.generate = self.generate_phrase
		else:
			self.generate = self.generate_word

		self.glob = self._get_glob(term)

	def _get_glob(self, term):
		glob = term.value.lower().strip()
		if not glob.replace('*', '').strip():
			return None
		elif not "*" in glob and not SEARCH_WHOLE_WORD in self.flags:
			# If glob is used in the term already, assume automatic start/end of the word
			if not term.value[0].isspace() and not glob[0] == '*':
				glob = '*' + glob # default glob word start

			if not term.value[-1].isspace() and not glob[-1] == '*':
				glob += '*' # default glob word ending
		# else keep start/end as is

		return glob.strip()

	@classmethod
	def get_find_string(cls, term):
		return term.value

	def generate_word(self):
		if not self.glob:
			# Protect against a possibly long-running query if accidentally searching for "*"
			return []

		for row in self.generate_inner(self.glob):
			yield PageSearchResult(Path(row["name"]), score=row["score"])

	def generate_phrase(self):
		if not self.glob:
			# Protect against a possibly long-running query if accidentally searching for "*"
			return []

		tokens = self.glob.split()
		tokens.sort(key=lambda w: len(w))
		longest = tokens[-1]

		textprovider = TextProvider(self.notebook, self.term, self.flags, self.ui_callback)
		check = textprovider.checker()
		for row in self.generate_inner(longest):
			result = PageSearchResult(Path(row["name"]), 0)
			if check(result):
				yield result

	def generate_inner(self, glob):
		#print(">>GLOB>>", glob)
		return self.notebook.index._db.execute(
			"SELECT p.name AS name, count(v.offset) AS score "
			"FROM pages_fts as f "
			"JOIN keys_pages_fts as k ON f.rowid = k.fts_id "
			"JOIN pages AS p ON k.page_id = p.id "
			"JOIN pages_ftsv AS v ON f.rowid = v.doc "
			"WHERE v.term GLOB ? "
			"GROUP BY p.name;",
			(escape_for_glob(glob),)
		)


class FTSIndexer(IndexerBase):
	'''Indexer for adding page content to the FTS index table, to keep
	the FTS index up-to-date.
	'''
	PLUGIN_NAME = "IndexedFTS"
	PLUGIN_CONFIG_KEY = "IndexedFTS_configuration"
	PLUGIN_DB_FORMAT = "0.2"
	_TABLE_DROP_STATEMENTS = """
		DROP TABLE IF EXISTS pages_fts;
		DROP TABLE IF EXISTS pages_ftsv;
		DROP TABLE IF EXISTS keys_pages_fts;
	"""

	__signals__ = {}

	@classmethod
	def teardown(cls, db):
		db.executescript(cls._TABLE_DROP_STATEMENTS)
		db.execute("DELETE FROM zim_index WHERE key = ?;", (cls.PLUGIN_NAME,))
		db.execute("DELETE FROM zim_index WHERE key = ?;", (cls.PLUGIN_CONFIG_KEY,))

	def __init__(self, db, pages_indexer, plugin_preferences):
		IndexerBase.__init__(self, db)
		self.db = db

		# Version checks are performed by IndexedFTSNotebookExtension
		# before we are instantiated (it's easier there)

		self.db.executescript('''
			CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
				page_content,
				tokenize = "unicode61 remove_diacritics {0} tokenchars '{1}'",
				content = '',
				contentless_delete = 1
			);
			CREATE VIRTUAL TABLE IF NOT EXISTS pages_ftsv
			USING fts5vocab(pages_fts, instance);

			CREATE TABLE IF NOT EXISTS keys_pages_fts (
				page_id INTEGER PRIMARY KEY,
				fts_id INTEGER REFERENCES pages_fts(rowid)
			);
			CREATE INDEX IF NOT EXISTS keys_pages_fts_rowid ON keys_pages_fts(fts_id);
		'''.format(
			'2' if plugin_preferences['remove_diacritics'] else '0',

			plugin_preferences['tokenchars'].replace('"', '""')
				if plugin_preferences['tokenchars'] is not None else ''
		))
		self.db.execute(
			"INSERT OR REPLACE INTO zim_index VALUES (?, ?), (?, ?);",
			(self.PLUGIN_NAME, self.PLUGIN_DB_FORMAT,
			self.PLUGIN_CONFIG_KEY, json.dumps(plugin_preferences),)
		)

		self.connectto_all(pages_indexer, (
			'page-changed', 'page-row-deleted'
		))

	def get_fts_id(self, page_id):
		fts_id = self.db.execute("SELECT fts_id FROM keys_pages_fts WHERE page_id = ?;", (page_id,)).fetchone()
		return fts_id[0] if fts_id is not None else None

	def on_page_changed(self, o, row, content_tree):
		'''
		This is the centerpiece of the plugin: FTS-index all text in the
		document and store the newly created row.
		'''
		logger.debug("Indexing full text of page %s", row["name"])

		allcont_str = tokens_to_text(content_tree.iter_tokens())
		fts_id = self.get_fts_id(row["id"])
		if fts_id is not None:
			# Page was searched before, we can update
			self.db.execute("UPDATE pages_fts SET page_content = ? WHERE rowid = ?;",
				(allcont_str, fts_id)
			)
		else:
			cur = self.db.execute(
				"INSERT INTO pages_fts (page_content) VALUES (?);",
				(allcont_str,))
			cur.execute(
				"INSERT OR REPLACE INTO keys_pages_fts (page_id, fts_id) VALUES (?, ?);",
				(row["id"], cur.lastrowid,))

	def on_page_row_deleted(self, o, row):
		fts_id = self.get_fts_id(row["id"])
		if fts_id is not None:
			self.db.execute("DELETE FROM pages_fts WHERE rowid = ?;",
				(fts_id,)
			)
			self.db.execute("DELETE FROM keys_pages_fts WHERE fts_id = ?;",
				(fts_id,)
			)


class IndexedFTSNotebookExtension(NotebookExtension):
	'''Extend notebook by adding special hooks when pages in the index
	are added or changed or deleted, so these changes can be reflected
	in the FTS index.

	Additionally, we flag all pages with content for re-indexing so that
	we get a full FTS index.
	'''

	def __init__(self, plugin, notebook):
		NotebookExtension.__init__(self, plugin, notebook)

		self.index = notebook.index

		# Check if the current index contains the latest version of the
		# FTS index table (if any at all):
		if self.index.get_property(FTSIndexer.PLUGIN_NAME) \
			!= FTSIndexer.PLUGIN_DB_FORMAT:

			FTSIndexer.teardown(self.index._db)
			self.index.flag_reindex()

		self.indexer = None
		self.setup_indexer()
		self.index.connect('new-update-iter', self.setup_indexer)

		self.plugin.preferences.connect('changed', self.on_preferences_changed)


	def setup_indexer(self):
		if self.indexer is not None:
			self.indexer.disconnect_all()

		self.indexer = FTSIndexer(self.index._db,
			self.index.update_iter.pages, self.plugin.preferences)

		self.index.update_iter.add_indexer(self.indexer)

	def on_preferences_changed(self, preferences):
		"""Callback to update index when plugin preferences are changed
		This method assumes self.plugin.preferences is up-to-date anyway
		"""
		stored_prefs = self.index.get_property(FTSIndexer.PLUGIN_CONFIG_KEY)
		if stored_prefs is None:
			FTSIndexer.teardown(self.index._db)
			self.index.flag_reindex()
			self.setup_indexer()
			return

		stored_prefs = json.loads(stored_prefs)

		for key, value in preferences.items():
			if stored_prefs[key] != value:
				FTSIndexer.teardown(self.index._db)
				self.index.flag_reindex()
				self.setup_indexer()
				return

	def teardown(self):
		'''This should be called when the plugin is disabled.
		It will not, however, remove the plugins data from the index
		because this might be tedious to restore and only be called on
		the open notebooks anyway - closed notebooks will remain with
		their FTS index as well.
		'''
		self.indexer.disconnect_all()
		self.index.update_iter.remove_indexer(self.indexer)

