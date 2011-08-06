# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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


logger = logging.getLogger('zim.history')


class HistoryPath(Path):
	'''Path with some additional info from the history.

	@ivar cursor: cursor position as integer offset from start of the
	text buffer
	@ivar scroll: scroll position of the text view as integer
	@ivar is_first: C{True} when this is the first path in the history
	@ivar is_last: C{True} when this is the last path in the history
	'''

	__slots__ = ('cursor', 'scroll', 'deleted', 'is_first', 'is_last')

	def __init__(self, name, cursor=None, scroll=None):
		Path.__init__(self, name)
		self.scroll = scroll
		self.cursor = cursor
		self.deleted = False
		self.is_first = False
		self.is_last = False

	def exists(self):
		'''Returns whether the history thinks this page still exists or
		not. Soft test, for hard test need to get the real page itself.
		'''
		return not self.deleted


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

	@ivar current: list index for the current page
	@ivar history: the L{HistoryList}
	@ivar notebook: the L{Notebook}
	@ivar uistate: the L{ConfigDict} used to store the history

	@signal: C{changed ()}: emitted when the path list changed
	'''
	# TODO should inherit from the selection object ?

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_LAST, None, tuple())
	}

	def __init__(self, notebook, uistate=None):
		'''Constructor
		@param notebook: a L{Notebook} object
		@param uistate: L{ConfigDict} to store the history (history
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
		self.uistate.setdefault('current', len(self.history)-1)

		self.uistate['list'] = HistoryList(self.uistate['list'])

		if self.current < 0 or self.current > len(self.history) - 1:
			self.current = len(self.history)-1

		# Check pages exist
		index = self.notebook.index
		seen = {}
		for path in self.history:
			if not path.name in seen:
				indexpath = index.lookup_path(path)
				if indexpath is None:
					exists = False
				else:
					exists = indexpath.exists()
				seen[path.name] = exists

			path.deleted = not seen[path.name]

		# Connect to notebook
		self.notebook.connect('moved-page', lambda o, a, b, c: self._on_page_moved(a,b,c))
		self.notebook.connect('deleted-page', lambda o, a: self._on_page_deleted(a))
		self.notebook.connect('stored-page', lambda o, a: self._on_page_stored(a))

	# read / write property
	current = property(
		lambda self: self.uistate['current'],
		lambda self, value: self.uistate.__setitem__('current', value) )

	@property
	def history(self):
		return self.uistate['list']

	def _on_page_deleted(self, page):
		# Flag page and children as deleted
		changed = False
		for path in self.history:
			if path == page or path.ischild(page):
				path.deleted = True
				changed = True

		if changed:
			self.emit('changed')

	def _on_page_stored(self, page):
		# Flag page exists
		changed = False
		for path in self.history:
			if path == page:
				path.deleted = False
				changed = True

		if changed:
			self.emit('changed')

	def _on_page_moved(self, oldpath, newpath, update_links):
		# Update paths to reflect new position while keeping other data
		changed = False
		for path in self.history:
			if path == oldpath:
				path.name = newpath.name
				changed = True
			elif path.ischild(oldpath):
				newchild = newpath + path.relname(oldpath)
				path.name = newchild.name
				changed = True

		if changed:
			self.emit('changed')

	def append(self, page):
		'''Append a new page to the history. Will drop the forward
		stack and make this page the latest page.
		@param page: L{Path} for the current page
		@emits: changed
		'''
		# drop forward stack
		while len(self.history) - 1 > self.current:
			self.history.pop()

		# purge old entries
		while len(self.history) >= MAX_HISTORY:
			self.history.pop(0)

		if self.history and self.history[-1] == page:
			pass
		else:
			path = HistoryPath(page.name)
			path.deleted = not page.exists()
			self.history.append(path)

		self.current = len(self.history) - 1
			# this assignment always triggers "modified" on the ListDict

		self.emit('changed')

	def get_current(self):
		'''Get current path
		@returns: a L{HistoryPath} object
		'''
		if self.history:
			return self.history[self.current]
		else:
			return None

	def set_current(self, path):
		'''Set current path (changes the pointer, does not change
		the list of pages)
		@param path: a L{HistoryPath} object
		@raises ValueError:  when the path is not in the history list
		'''
		assert isinstance(path, HistoryPath)
		self.current = self.history.index(path)
			# fails if path not in history

	def get_previous(self):
		'''Get the previous path
		@returns: a L{HistoryPath} object or C{None} if current is
		already the first path in the list
		'''
		if len(self.history) > 1 and self.current > 0:
			return self.history[self.current - 1]
		else:
			return None

	def get_next(self):
		'''Get the next path
		@returns: a L{HistoryPath} object or C{None} if current is
		already the last path in the list
		'''
		if self.current < len(self.history) - 1:
			return self.history[self.current + 1]
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
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i].ischild(path):
				relname = self.history[i].relname(path)
				if ':' in relname:
					basename = relname.split(':')[0]
					return path + basename
				else:
					return self.history[i]
		else:
			return None

	def get_grandchild(self, path):
		'''Get the deepest nested gran-child of a given path. Used
		for the 'namepsace' pathbar to keep showing child pages when
		the user navigates up.
		@param path: a L{Path} object
		@returns: a L{HistoryPath} object or C{None}
		'''
		child = path
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i].ischild(child):
				child = self.history[i]

		if child == path: return None
		else: return child

	def get_path(self, path, need_cursor=False):
		'''Get a L{HistoryPath} for a given path. Just looks for the
		first occurence of the path in the history list and returns
		the corresponding L{HistoryPath}. Used e.g. by the interface to
		find out the latest cursor position for a page.

		@param path: a L{Path} object
		@param need_cursor: if C{True} only history records are
		returned that have a value for the cursor that is not C{None}

		@returns: a L{HistoryPath} object or None
		'''
		for record in self.get_history():
			if record == path:
				if need_cursor:
					if not record.cursor is None:
						return record
					else:
						continue
				else:
					return record

	def get_history(self):
		'''Generator function that yields history records, latest first
		@returns: yields L{HistoryPath} objects
		'''
		for i in range(len(self.history)-1, -1, -1):
			yield self.history[i]

	def get_unique(self):
		'''Generator function that yields unique pages in the history
		@returns: yields L{HistoryPath} objects
		'''
		seen = set()
		for i in range(len(self.history)-1, -1, -1):
			path = self.history[i]
			if not path in seen and not path.deleted:
				seen.add(path)
				yield path


gobject.type_register(History)
