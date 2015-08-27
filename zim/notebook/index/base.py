# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

logger = logging.getLogger('zim.notebook.index')


from zim.signals import SIGNAL_BEFORE, SIGNAL_AFTER


class IndexNotFoundError(ValueError):
	pass


class IndexConsistencyError(ValueError):
	pass


class IndexViewBase(object):
	'''Base class for "IndexView" objects'''

	@classmethod
	def new_from_index(klass, index, *args, **kwargs):
		return klass(index.db_conn.db_context(), *args, **kwargs)

	def __init__(self, db_context):
		self._db = db_context


class IndexerBase(object):
	'''Base class for "Indexer" objects.
	The methods in this class all take the "db" as the first argument
	because they can be used with a db onnection in a separate thread.
	'''

	def __init__(self):
		self._signal_handlers = {}
		self._signal_queue = []

	def connect(self, signal, handler, userdata=None):
		assert signal in self.__signals__
		if not signal in self._signal_handlers:
			self._signal_handlers[signal] = []
		if userdata is not None:
			inner = handler
			def wrapper(*a):
				a = a + (userdata,)
				inner(*a)
			handler = wrapper
		myhandler = (handler,) # new tuple to ensure unique object
		self._signal_handlers[signal].append(myhandler)
		return id(myhandler)

	def disconnect(self, handlerid):
		for signal in self._signal_handlers:
			for handler in self._signal_handlers[signal]:
				if id(handler) == handlerid:
					self._signal_handlers[signal].remove(handler)
					if not self._signal_handlers[signal]:
						self._signal_handlers.pop(signal)
					return

	def emit(self, signal, *args):
		if signal in self._signal_handlers:
			if self.__signals__[signal][1] == SIGNAL_BEFORE:
				self._emit(signal, args)
			else:
				self._signal_queue.append((signal, args))

	def emit_queued_signals(self):
		for signal, args in self._signal_queue:
			self._emit(signal, args)
		self._signal_queue = []

	def _emit(self, signal, args):
		for myhandler in self._signal_handlers[signal]:
			try:
				myhandler[0](self, *args)
			except:
				logger.exception('Exception in signal emit %s %r', signal, args)

	def on_db_init(self, index, db):
		'''Callback that is called when a database is initialized.
		Default implementation executes the C{INIT_SCRIPT} attribute.
		@param index: an L{IndexInternal} instance for the calling index
		@param db: a C{sqlite3.Connection} object
		@implementation: can be overloaded by subclass
		'''
		if hasattr(self, 'INIT_SCRIPT'):
			db.executescript(self.INIT_SCRIPT)
		else:
			raise NotImplementedError

	def on_new_page(self, index, db, indexpath):
		'''Callback that is called after a new page is added to the
		database.
		@param index: an L{IndexInternal} instance for the calling index
		@param db: a C{sqlite3.Connection} object
		@param indexpath: an L{IndexPath} object
		@implementation: can be overloaded by subclass, default does nothing
		'''
		pass

	def on_index_page(self, index, db, indexpath, parsetree):
		'''Callback that is called when the content of a page is indexed.
		@param index: an L{IndexInternal} instance for the calling index
		@param db: a C{sqlite3.Connection} object
		@param indexpath: an L{IndexPath} object
		@param parsetree: a L{ParseTree} object
		@implementation: can be overloaded by subclass, default does nothing
		'''
		pass

	def on_delete_page(self, index, db, indexpath):
		'''Callback that is called before a page is deleted from the
		database.
		@param index: an L{IndexInternal} instance for the calling index
		@param db: a C{sqlite3.Connection} object
		@param indexpath: an L{IndexPath} object
		@implementation: can be overloaded by subclass, default does nothing
		'''
		pass

	def on_deleted_page(self, index, db, parent, basename):
		'''Callback that is called after a page is deleted from the
		database.
		@param index: an L{IndexInternal} instance for the calling index
		@param db: a C{sqlite3.Connection} object
		@param parent: an L{IndexPath} object
		@param basename: a string
		@implementation: can be overloaded by subclass, default does nothing
		'''
		pass


class PluginIndexerBase(IndexerBase):
	'''Base class for indexers defined in plugins. These need some
	additional logic to allow them to be added and removed flexibly.
	See L{Index.add_plugin_indexer()} and L{Index.remove_plugin_indexer()}.

	Additional behavior required for plugin indexers:

	  - PLUGIN_NAME and PLUGIN_DB_FORMAT must be defined
	  - INIT_SCRIPT or on_db_init() must be robust against data from
	    an older verion of the plugin being present. E.g. by first dropping
	    the plugin table and then initializing it again.
	  - TEARDOWN_SCRIPT needs to be defined, or on_teardown() implemented

	'''

	PLUGIN_NAME = None #: plugin name as string
	PLUGIN_DB_FORMAT = None #: version of the db scheme for this plugin as string

	def on_teardown(self, index, db):
		'''Callback that is called when the plugin is removed. Will not be
		called when the application exits.
		Default implementation executes the C{TEARDOWN_SCRIPT} attribute.
		@param index: an L{IndexInternal} instance for the calling index
		@param db: a C{sqlite3.Connection} object
		@implementation: can be overloaded by subclass
		'''
		if hasattr(self, 'TEARDOWN_SCRIPT'):
			db.executescript(self.TEARDOWN_SCRIPT)
		else:
			raise NotImplementedError
