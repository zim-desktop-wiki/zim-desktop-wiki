
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

logger = logging.getLogger('zim.notebook.index')

from zim.signals import SignalEmitter, ConnectorMixin


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
		return cls(index._db)

	def __init__(self, db):
		self.db = db


class IndexerBase(SignalEmitter, ConnectorMixin):
	'''Base class for "content indexer" objects.
	It defines the callback functions that are calls from L{PagesIndexer}
	'''

	__signals__ = {}

	def __init__(self, db):
		self.db = db

	def is_uptodate(self):
		return True

	def update(self):
		for i in self.update_iter():
			pass

	def update_iter(self):
		return iter([])


class MyTreeIter(object):
	__slots__ = ('treepath', 'row', 'n_children', 'hint')

	def __init__(self, treepath, row, n_children, hint=None):
		self.treepath = treepath
		self.row = row
		self.n_children = n_children
		self.hint = hint


class TreeModelMixinBase(ConnectorMixin):
	'''This class can be used as mixin class for C{Gtk.TreeModel}
	implementations that use data from the index.

	Treepaths are simply tuples with integers. This Mixin assumes L{MyTreeIter}
	objects for iters. (Which should not be confused with C{Gtk.TreeIter} as
	used by the interface!)
	'''

	def __init__(self, index):
		self.index = index
		self.db = index._db
		self.cache = {}
		self.connect_to_updateiter(index, index.update_iter)
		self.connectto(index, 'new-update-iter', self.connect_to_updateiter)

	def connect_to_updateiter(self, update_iter):
		'''Connect to a new L{IndexUpdateIter}

		The following signals must be implemented:

		  - row-inserted (treepath, treeiter)
		  - row-changed (treepath, treeiter)
		  - row-has-child-toggled (treepath, treeiter)
		  - row-deleted (treepath)

		Typically each signal should also flush the cache using
		C{self.cache.clear()}.

		@implementation: must be implemented by a subclass
		'''
		raise NotImplementedError

	def teardown(self):
		self.flush_cache()
		self.disconnect_all()

	def n_children_top(self):
		'''Return the number of items in the top level of the model'''
		raise NotImplementedError

	def get_mytreeiter(self, treepath):
		'''Returns a C{treeiter} object for C{treepath} or C{None}
		@implementation: must be implemented by a subclass
		'''
		raise NotImplementedError

	def find(self, obj):
		'''Return the treepath for a index object like a L{Path} or L{IndexTag}
		@raises IndexNotFoundError: if C{indexpath} is not found
		@implementation: must be implemented by a subclass
		'''
		raise NotImplementedError

	def find_all(self, obj):
		'''Like L{find()} but can return multiple results
		@implementation: must be implemented by subclasses that have mutiple
		entries for the same object. Default falls back to result of L{find()}.
		'''
		return [self.find(obj)]
