# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

logger = logging.getLogger('zim.notebook.index')


class IndexNotFoundError(ValueError):
	'''Error used when lookup fails because a pagename does not appear
	in the index.
	'''
	pass


class IndexConsistencyError(AssertionError):
	'''Error used when a lookup fails while expected to succeed'''
	pass


class IndexView(object):
	'''Base class for "index view" objects'''

	@classmethod
	def new_from_index(cls, index):
		return cls(index.db)

	def __init__(self, db):
		self.db = db


class ContentIndexer(object):
	'''Base class for "content indexer" objects.
	It defines the callback functions that are calls from L{PagesIndexer}
	'''

	def __init__(self, db, signal_queue):
		self.db = db
		self.signals = signal_queue

	def on_db_init(self):
		'''Callback that is called when a database is initialized.
		@implementation: must be overloaded by subclass
		'''
		raise NotImplementedError

	def on_db_start_update(self, pages_indexer):
		'''Callback that is called when an update is started
		@param pages_indexer: a L{PagesIndexer}
		@implementation: can be overloaded, default does nothing
		'''
		pass

	def on_db_finish_update(self, pages_indexer):
		'''Callback that is called when an update finished
		@param pages_indexer: a L{PagesIndexer}
		@implementation: can be overloaded, default does nothing
		'''
		pass

	def on_db_added_page(self, pages_indexer, page_id, pagename):
		'''Callback that is called after a new page is added to the
		database.
		@param pages_indexer: a L{PagesIndexer}
		@param page_id: the id of the page in the C{pages} table
		@param pagename: a L{Path} object
		@implementation: can be overloaded by subclass, default does nothing
		'''
		pass

	def on_db_index_page(self, pages_indexer, page_id, pagename, doc):
		'''Callback that is called when the content of a page is indexed.
		@param pages_indexer: a L{PagesIndexer}
		@param page_id: the id of the page in the C{pages} table
		@param pagename: a L{Path} object
		@param doc: a token iterator of page contents
		@implementation: can be overloaded by subclass, default does nothing
		'''
		pass

	def on_db_delete_page(self, pages_indexer, page_id, pagename):
		'''Callback that is called before a page is deleted from the
		database.
		@param pages_indexer: a L{PagesIndexer}
		@param page_id: the id of the page in the C{pages} table
		@param pagename: a L{Path} object
		@implementation: can be overloaded by subclass, default does nothing
		'''
		pass


class PluginIndexerBase(ContentIndexer):
	'''Base class for indexers defined in plugins. These need some
	additional logic to allow them to be added and removed flexibly.
	See L{Index.add_plugin_indexer()} and L{Index.remove_plugin_indexer()}.

	Additional behavior required for plugin indexers:

	  - PLUGIN_NAME and PLUGIN_DB_FORMAT must be defined
	  - on_db_init() must be robust against data from
	    an older verion of the plugin being present. E.g. by first dropping
	    the plugin table and then initializing it again.
	  - on_db_teardown() needs to be implemented

	'''

	PLUGIN_NAME = None #: plugin name as string
	PLUGIN_DB_FORMAT = None #: version of the db scheme for this plugin as string

	def on_db_teardown(self):
		'''Callback that is called when the plugin is removed. Will not be
		called when the application exits.
		@implementation: must be overloaded by subclass
		'''
		raise NotImplementedError
