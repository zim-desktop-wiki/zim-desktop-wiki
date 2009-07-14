# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains the history class.

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

MAX_HISTORY = 25


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
	'''History class.

	Signals:
		* changed - emitted whenever something changes
	'''
	# TODO should inherit from the selection object ?
	# TODO connect to notebook signals to stay in sync

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_LAST, None, tuple())
	}

	def __init__(self, notebook, uistate=None):
		gobject.GObject.__init__(self)
		if uistate is None:
			self.uistate = {}
		else:
			self.uistate = uistate['History']

		self.uistate.setdefault('pages', [])
		self.uistate.setdefault('current', len(self.history)-1)

	# reference to whatever integer is stored in the dict
	current = property(
		lambda self: self.uistate.__getitem__('current'),
		lambda self, value: self.uistate.__setitem__('current', value) )

	# reference to the list with pages
	history = property(
		lambda self: self.uistate.__getitem__('pages'),
		lambda self, value: self.uistate.__setitem__('pages', value) )

	def append(self, page):
		if self.current != -1:
			self.history = self.history[:self.current+1] # drop forward stack

		while len(self.history) >= MAX_HISTORY:
			self.history.pop(0)

		if self.history and page.name == self.history[-1][PAGE_COL]:
			pass
		else:
			item = [page.name, None, None] # PAGE_COL, CURSOR_COL, SCROLL_COL
			self.history.append(item)
		self.current = -1
			# this assignment always triggers "modified" on the ListDict

		self.emit('changed')

	def get_current(self):
		if self.history:
			if self.current < 0:
				self.current = len(self.history) + self.current
			return HistoryRecord(self.history, self.current)
		else:
			return None

	def set_current(self, record):
		self.current = record.i

	def get_previous(self, step=1):
		if self.history:
			if self.current < 0:
				self.current = len(self.history) + self.current

			if self.current == 0:
				return None
			else:
				return HistoryRecord(self.history, self.current-1)
		else:
			return None

	def get_next(self, step=1):
		if self.history:
			if self.current == -1 or self.current+1 == len(self.history):
				return None
			else:
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

		child = Path(namespace)
		if child == path: return None
		else: return child

	def get_history(self):
		'''Generator function that yields history records, latest first'''
		for i in range(len(self.history)-1, -1, -1):
			yield HistoryRecord(self.history, i)

	def get_unique(self):
		'''Generator function that yields unique records'''
		seen = set()
		for i in range(len(self.history)-1, -1, -1):
			if not self.history[i][PAGE_COL] in seen:
				seen.add(self.history[i][PAGE_COL])
				yield HistoryRecord(self.history, i)


gobject.type_register(History)
