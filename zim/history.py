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

The list of recent pages is kind of a summary of the last X pages in the
history without doubles.
'''

PAGE_COL = 0
CURSOR_COL = 1
SCROLL_COL = 2


class HistoryRecord(object):
	'''This class functions as an iterator for the history list'''

	def __init__(self, history, i):
		self.history = history
		self.i = i

	@property
	def name(self): return self.history[self.i][PAGE_COL]

	@property
	def cursor(self): return self.history[self.i][CURSOR_COL]

	@property
	def scroll(self): return self.history[self.i][SCROLL_COL]


class History(object):
	'''FIXME'''
	# TODO should inherit from the selection object
	# TODO should use SQL storage
	# TODO max length for list (?)
	# TODO connect to notebook signals to stay in sync

	def __init__(self, notebook):
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

	def get_recent(self):
		'''Generator function that yields unique records'''
		# TODO
