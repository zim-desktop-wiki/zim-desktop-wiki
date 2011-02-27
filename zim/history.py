# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the history class.

The history can be represented as a list of pages with extra columns for the
cursor and scroll positions. One additional property is used to give the current
page in that list. All entries before the current position can be accessed by
navigating backward, all entries ahead of the current position can be accessed
by navigating forward. The same page can occur multiple times in the list.
'''

import gobject
import logging

from zim.notebook import Path
from zim.config import json

MAX_HISTORY = 25


logger = logging.getLogger('zim.history')


class HistoryPath(Path):
	'''Path withsome additional info from the history.

	Adds attributes 'cursor', 'scroll', 'is_first' and 'is_last'.
	Both 'cursor' and 'scroll' give a position within the page and
	should be integer, or None when undefined.
	Both 'is_first' and 'is_last' are boolean and show whether this
	record is the first or last record in the history.
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
	# Wrapper for a list of HistoryPaths which takes care of (de-)serialization
	# when saving in the config

	def __init__(self, list):
		# Convert list from config to use Path objects
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
		data = [(path.name, path.cursor, path.scroll) for path in self]
		return json.dumps(data, separators=(',',':'))


class History(gobject.GObject):
	'''History class.

	Signals:
		* changed - emitted whenever something changes
	'''
	# TODO should inherit from the selection object ?

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_LAST, None, tuple())
	}

	def __init__(self, notebook, uistate=None):
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
		if self.history:
			return self.history[self.current]
		else:
			return None

	def set_current(self, path):
		assert isinstance(path, HistoryPath)
		self.current = self.history.index(path)
			# fails if path not in history

	def get_previous(self):
		if len(self.history) > 1 and self.current > 0:
			return self.history[self.current - 1]
		else:
			return None

	def get_next(self):
		if self.current < len(self.history) - 1:
			return self.history[self.current + 1]
		else:
			return None

	def get_child(self, path):
		'''Returns a path for a direct child of path or None'''
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i].ischild(path):
				relname = self.history[i].relname(path)
				basename = relname.split(':')[0]
				return path + basename
		else:
			return None

	def get_grandchild(self, path):
		'''Returns a path for the deepest child of path that could be found or None'''
		child = path
		for i in range(len(self.history)-1, -1, -1):
			if self.history[i].ischild(child):
				child = self.history[i]

		if child == path: return None
		else: return child

	def get_history(self):
		'''Generator function that yields history records, latest first'''
		for i in range(len(self.history)-1, -1, -1):
			yield self.history[i]

	def get_unique(self):
		'''Generator function that yields unique records'''
		seen = set()
		for i in range(len(self.history)-1, -1, -1):
			path = self.history[i]
			if not path in seen and not path.deleted:
				seen.add(path)
				yield path


gobject.type_register(History)
