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


MAX_HISTORY = 25


class HistoryRecord(Path):
	'''Path withsome additional info from the history'''

	__slots__ = ('history', 'i')

	def __init__(self, history, i):
		Path.__init__(self, history.history[i])
		self.history = history
		self.i = i

	@property
	def valid(self):
		return self.history.history[self.i] == self.name

	@property
	def is_first(self): return self.i == 0

	@property
	def is_last(self): return self.i == len(self.history.history) - 1

	def get_cursor(self):
		if self.name in self.history.pages:
			return self.history.pages[self.name][0]
		else:
			return None

	def set_cursor(self, value):
		self.history.pages[self.name] = (value, self.scroll)

	cursor = property(get_cursor, set_cursor)

	def get_scroll(self):
		if self.name in self.history.pages:
			return self.history.pages[self.name][1]
		else:
			return None

	def set_scroll(self, value):
		self.history.pages[self.name] = (self.cursor, value)

	scroll = property(get_scroll, set_scroll)


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

		self.uistate.setdefault('pages', {})
		self.uistate.setdefault('history', [])
		self.uistate.setdefault('current', len(self.history)-1)

	current = property(
		lambda self: self.uistate['current'],
		lambda self, value: self.uistate.__setitem__('current', value) )

	history = property(
		lambda self: self.uistate['history'],
		lambda self, value: self.uistate.__setitem__('history', value) )

	@property
	def pages(self): return self.uistate['pages']

	def append(self, page):
		if self.current != -1:
			self.history = self.history[:self.current+1] # drop forward stack

		while len(self.history) >= MAX_HISTORY:
			n = self.history.pop(0)
			if not n in self.history: # name can appear multipel times
				self.pages.pop(n)

		if self.history and self.history[-1] == page.name:
			pass
		else:
			self.history.append(page.name)
		self.current = -1
			# this assignment always triggers "modified" on the ListDict

		self.emit('changed')

	def get_current(self):
		if self.history:
			if self.current < 0:
				self.current = len(self.history) + self.current
			return HistoryRecord(self, self.current)
		else:
			return None

	def set_current(self, record):
		assert record.valid
		self.current = record.i

	def get_previous(self, step=1):
		if self.history:
			if self.current < 0:
				self.current = len(self.history) + self.current

			if self.current == 0:
				return None
			else:
				return HistoryRecord(self, self.current-1)
		else:
			return None

	def get_next(self, step=1):
		if self.history:
			if self.current == -1 or self.current+1 == len(self.history):
				return None
			else:
				return HistoryRecord(self, self.current+1)
		else:
			return None

	def get_child(self, path):
		'''Returns a path for a direct child of path or None'''
		namespace = path.name + ':'
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i].startswith(namespace):
				name = self.history[i]
				parts = name[len(namespace):].split(':')
				return Path(namespace+parts[0])
		else:
			return None

	def get_grandchild(self, path):
		'''Returns a path for the deepest child of path that could be found or None'''
		namespace = path.name + ':'
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i].startswith(namespace):
				namespace = self.history[i] + ':'

		child = Path(namespace)
		if child == path: return None
		else: return child

	def get_history(self):
		'''Generator function that yields history records, latest first'''
		for i in range(len(self.history)-1, -1, -1):
			yield HistoryRecord(self, i)

	def get_unique(self):
		'''Generator function that yields unique records'''
		seen = set()
		for i in range(len(self.history)-1, -1, -1):
			if not self.history[i] in seen:
				seen.add(self.history[i])
				yield HistoryRecord(self, i)


gobject.type_register(History)
