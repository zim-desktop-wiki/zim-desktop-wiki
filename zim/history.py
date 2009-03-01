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

	def get_child(self, page):
		'''FIXME'''
		namespace = page.name + ':'
		for i in range(self.current):
			j = self.current - i
			if self.history[j][PAGE_COL].startswith(namespace):
				return HistoryRecord(self.history, j)
		else:
			return None

	def get_unique(self, max=None):
		'''Generator function that yields unique records'''
		seen = set()
		for i in range(len(self.history)):
			j = len(self.history) - 1 - i
			if not self.history[j][PAGE_COL] in seen:
				seen.add(self.history[j][PAGE_COL])
				yield HistoryRecord(self.history, j)

	def get_namespace(self):
		'''Generator function that yields records in same namespace path'''
		# TODO get namespace

gobject.type_register(History)
