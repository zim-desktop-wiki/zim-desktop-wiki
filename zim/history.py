# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME

The history can be represented as a list of pages with extra columns for the
cursor and scroll positions. One additional setting is used to give the current
page in that list. All entries before the current position can be accessed by
navigating backward, all entries ahead of the current position can be accessed
by navigating forward. The same page can occur multiple times in the list, each
of these occurences should be a reference to the same record to keep
the cursor and scroll position in sync.

The history does not use the same database files as used by the index because
there could be multiple histories for on the same notebook, e.g. for multiple
users.
'''

import gobject

from zim.notebook import Path

PAGE_COL = 0
CURSOR_COL = 1
SCROLL_COL = 2


class HistoryRecord(Path):
	'''This class functions as an iterator for the history list'''

	__slots__ = ('history', 'i')

	def __init__(self, history, i):
		Path.__init__(self, history[i][PAGE_COL])
		self.history = history
		self.i = i

	@property
	def cursor(self):
		return self.history[self.i][CURSOR_COL]

	@property
	def scroll(self):
		return self.history[self.i][SCROLL_COL]

	def is_first(self):
		return self.i == 0

	def is_last(self):
		return self.i == len(self.history)-1


class History(gobject.GObject):
	'''FIXME

	Signals:
		* changed - emitted whenever something changes
	'''
	# TODO should inherit from the selection object
	# TODO max length for list (?)
	# TODO connect to notebook signals to stay in sync

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_LAST, None, tuple())
	}

	def __init__(self, notebook):
		gobject.GObject.__init__(self)
		self.history = []
		self.current = None

	def append(self, page):
		if not self.current is None:
			self.history = self.history[:self.current+1] # drop forward stack

		for item in self.history:
			if item[PAGE_COL] == page.name:
				self.history.append(item) # copy reference
				break
		else:
			item = [page.name, None, None] # PAGE_COL, CURSOR_COL, SCROLL_COL
			self.history.append(item)

		self.current = len(self.history)-1

		self.emit('changed')

	def get_current(self):
		if not self.current is None:
			return HistoryRecord(self.history, self.current)
		else:
			return None

	def set_current(self, record):
		self.current = record.i

	def get_previous(self, step=1):
		if not self.current is None and self.current > 0:
			return HistoryRecord(self.history, self.current-1)
		else:
			return None

	def get_next(self, step=1):
		if not self.current is None and self.current+1 < len(self.history):
			return HistoryRecord(self.history, self.current+1)
		else:
			return None

	def get_child(self, path):
		'''Returns a path for a direct child of path or None'''
		namespace = path.name + ':'
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i][PAGE_COL].startswith(namespace):
				name = self.history[i][PAGE_COL]
				parts = name[len(namespace):].split(':')
				return Path(namespace+parts[0])
		else:
			return None

	def get_grandchild(self, path):
		'''Returns a path for the deepest child of path that could be found or None'''
		namespace = path.name + ':'
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i][PAGE_COL].startswith(namespace):
				namespace = self.history[i][PAGE_COL] + ':'

		if len(namespace) == len(path.name) + 1:
			return None
		else:
			return Path(namespace)

	def get_history(self):
		'''Generator function that yields history records, latest first'''
		for i in range(len(self.history)-1, -1, -1):
			yield HistoryRecord(self.history, i)

	def get_unique(self, max=None):
		'''Generator function that yields unique records'''
		seen = set()
		for i in range(len(self.history)-1, -1, -1):
			if not self.history[i][PAGE_COL] in seen:
				seen.add(self.history[i][PAGE_COL])
				yield HistoryRecord(self.history, i)


gobject.type_register(History)
