# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module implements the history for navigating pages in the
notebook.

The main class is L{History}. Also there is a specialized class
L{HistoryPath} which extends L{Path} with history information.
'''

import gobject
import logging

from zim.notebook import Path
from zim.config import json

MAX_HISTORY = 25
MAX_RECENT = 10

logger = logging.getLogger('zim.history')


class HistoryPath(Path):
	'''Path with some additional info from the history.

	@ivar cursor: cursor position as integer offset from start of the
	text buffer
	@ivar scroll: scroll position of the text view as integer
	@ivar is_first: C{True} when this is the first path in the history
	@ivar is_last: C{True} when this is the last path in the history
	'''

	__slots__ = ('cursor', 'scroll', 'is_first', 'is_last')

	def __init__(self, name, cursor=None, scroll=None):
		Path.__init__(self, name)
		self.scroll = scroll
		self.cursor = cursor
		self.is_first = False
		self.is_last = False


class RecentPath(Path):
	pass


class HistoryList(list):
	'''A list of L{HistoryPath}s which takes care of serialization
	when saving in a config file, and de-serialization on construction.
	'''

	def __init__(self, list):
		'''Constructor
		@param list: a list of 3-tuples giving path name, cursor
		position and scroll position. Will be converted in a list with
		L{HistoryPath}s
		'''
		try:
			for name, cursor, scroll in list:
				self.append(HistoryPath(name, cursor, scroll))
		except:
			logger.exception('Could not parse history list:')

	def __getitem__(self, i):
		path = list.__getitem__(self, i)
		if i == 0:
			path.is_first = True
			path.is_last = False
		elif i == len(self) - 1:
			path.is_first = False
			path.is_last = True
		else:
			path.is_first = False
			path.is_last = False
		return path

	def index(self, path):
		ids = [id(p) for p in self]
		return ids.index(id(path))

	def serialize_zim_config(self):
		'''Serialize to string
		@returns: the list content as a json formatted string
		'''
		data = [(path.name, path.cursor, path.scroll) for path in self]
		return json.dumps(data, separators=(',',':'))


class History(gobject.GObject):
	'''History class, keeps track of a list of L{HistoryPath} objects.
	Also has a 'current' page which should match the current page in the
	interface. The current page normally is the latest page in the list,
	but when the user navigates back in the history it can be another
	position.

	@ivar notebook: the L{Notebook}
	@ivar uistate: the L{ConfigDict} used to store the history

	@signal: C{changed ()}: emitted when the path list changed
	'''

	# We keep two stacks:
	#    _history (== uistate['list'])
	#    _recent (== uistate['recent'])
	#
	# The first is a list of pages as they were accesed in time,
	# the second is a list of recent pages that were seen in order they
	# were seen. Most of the time these two lists are duplicate, but if
	# the user navigates back and then clicks a link part of the _history
	# stack is dropped. In that case the _recent stack has pages that are
	# not in the history.
	# Both stacks keep history objects that have a cursor position etc.
	# and methods like get_child() and get_path() use data in both stacks.
	#
	# The prorperty _current holds an index of the _history stack pointing
	# to the current page.
	#
	# Note that the cursor position is set directly into the HistoryPath object
	# in the GtkInterface do_close_page event
	#
	# FIXME: if we also store the cursor in the recent pages it gets
	# remembered longer

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_LAST, None, tuple())
	}

	def __init__(self, notebook, uistate=None):
		'''Constructor
		@param notebook: a L{Notebook} object
		@param uistate: L{SectionedConfigDict} to store the history (history
		will use the 'History' section in ConfigDict)
		'''
		gobject.GObject.__init__(self)
		self.notebook = notebook
		if uistate is None:
			self.uistate = {}
		else:
			self.uistate = uistate['History']

		# Initialize history list and ensure current is within range
		# previous version (<= 0.49) used attributes 'pages' and 'history'
		# so we can not use those without breaking backward compatibility
		self.uistate.setdefault('list', [])
		self.uistate.setdefault('recent', [])
		self.uistate.setdefault('current', len(self._history)-1)

		self.uistate['list'] = HistoryList(self.uistate['list'])
		self.uistate['recent'] = HistoryList(self.uistate['recent'])

		if self._current < 0 or self._current > len(self._history) - 1:
			self._current = len(self._history)-1

		# Initialize recent if it didn;t exist (was introduced version 0.55)
		# Add all items, then go back to last position
		if self._history and not self._recent:
			for p in self._history:
				self._update_recent(p)

			for i in range(len(self._history)-1, self._current-1, -1):
				p = self._history[i]
				self._update_recent(p)

		# Connect to notebook
		self.notebook.connect('moved-page', self._on_page_moved)
		self.notebook.connect('deleted-page', self._on_page_deleted)

	# read / write property
	_current = property(
		lambda self: self.uistate['current'],
		lambda self, value: self.uistate.__setitem__('current', value) )

	@property
	def _history(self):
		return self.uistate['list']

	@property
	def _recent(self):
		return self.uistate['recent']

	def _on_page_deleted(self, nb, page):
		# Remove deleted pages from recent
		f = lambda p: p == page or p.ischild(page)

		changed = False
		for path in filter(f, self._recent):
			self._recent.remove(path)
			changed = True

		if changed:
			self.emit('changed')

	def _on_page_moved(self, nb, oldpath, newpath, update_links):
		# Update paths to reflect new position while keeping other data
		changed = False
		for list in (self._history, self._recent):
			for path in list:
				if path == oldpath:
					path.name = newpath.name
					changed = True
				elif path.ischild(oldpath):
					newchild = newpath + path.relname(oldpath)
					path.name = newchild.name
					changed = True

		if changed:
			self.emit('changed')

	def append(self, path):
		'''Append a new page to the history. Will drop the forward
		stack and make this page the latest page.
		@param path: L{Path} for the current page
		@emits: changed
		'''
		if self._history and self._history[self._current] == path:
			pass # prevent duplicate entries in a row
		else:
			# drop forward stack
			while len(self._history) - 1 > self._current:
				self._history.pop()

			# purge old entries
			while len(self._history) >= MAX_HISTORY:
				self._history.pop(0)

			# append new page
			historypath = HistoryPath(path.name)
			self._history.append(historypath)
			self._current = len(self._history) - 1
			# this assignment always triggers "modified" on the ControlledDict

			if not isinstance(path, RecentPath):
				self._update_recent(historypath)

			self.emit('changed')

	def _update_recent(self, path):
		# Make sure current page is on top of recent stack
		if self._recent and path == self._recent[-1]:
			return False

		if path in self._recent:
			self._recent.remove(path)

		while len(self._recent) >= MAX_RECENT:
			self._recent.pop(0)

		self._recent.append(path)
		return True

	def get_current(self):
		'''Get current path
		@returns: a L{HistoryPath} object
		'''
		if self._history:
			return self._history[self._current]
		else:
			return None

	def set_current(self, path):
		'''Set current path (changes the pointer, does not change
		the list of pages)
		@param path: a L{HistoryPath} object
		@raises ValueError:  when the path is not in the history list
		'''
		assert isinstance(path, HistoryPath)
		self._current = self._history.index(path)
			# fails if path not in history
		if not isinstance(path, RecentPath) \
		and self._update_recent(path):
			self.emit('changed')

	def get_previous(self):
		'''Get the previous path
		@returns: a L{HistoryPath} object or C{None} if current is
		already the first path in the list
		'''
		if len(self._history) > 1 and self._current > 0:
			return self._history[self._current - 1]
		else:
			return None

	def get_next(self):
		'''Get the next path
		@returns: a L{HistoryPath} object or C{None} if current is
		already the last path in the list
		'''
		if self._current < len(self._history) - 1:
			return self._history[self._current + 1]
		else:
			return None

	def get_child(self, path):
		'''Get the most recent path that is a direct child of the
		given path. If there is a recent grand-child of the given path
		in the history, that will be used as a bases to get a new
		L{Path} object. Used by the keybinding for navigating to child
		pages.
		@param path: a L{Path} object
		@returns: a L{HistoryPath} or L{Path} object or C{None}
		'''
		for list in (self._history, self._recent):
			for p in reversed(list):
				if p.ischild(path):
					relname = p.relname(path)
					if ':' in relname:
						basename = relname.split(':')[0]
						return path + basename
					else:
						return path + relname
		else:
			return None

	def get_grandchild(self, path):
		'''Get the deepest nested grand-child of a given path. Used
		for the 'namespace' pathbar to keep showing child pages when
		the user navigates up.
		@param path: a L{Path} object
		@returns: a L{HistoryPath} object or C{None}
		'''
		child = path
		for list in (self._history, self._recent):
			for p in reversed(list):
				if p.ischild(child):
					child = p

		if child == path: return None
		else: return Path(child.name) # Force normal Path

	def get_state(self, path):
		'''Looks through the history and recent pages to the last
		known cursor position for a page.
		@param path: a L{Path} object
		@returns: a tuple of cursor and scroll position for C{path}
		or C{(None, None)}
		'''
		for list in (self._history, self._recent):
			for record in reversed(list):
				if record == path \
				and not record.cursor is None:
					return record.cursor, record.scroll
		else:
			return None, None

	def get_history(self):
		'''Generator function that yields history records, latest first
		@returns: yields L{HistoryPath} objects
		'''
		# Generator to avoid external acces to the list
		for p in reversed(self._history):
			yield p

	def get_recent(self):
		'''Generator function that yields recent pages
		@returns: yields L{RecentPath} objects
		'''
		# Generator to avoid external acces to the list
		for p in reversed(self._recent):
			yield RecentPath(p.name)
			# yield Path instead of HistoryPath because that
			# would make the applciation think we are opening
			# from history. Opening from recent pages should
			# be like normal navigation instead.


gobject.type_register(History)
