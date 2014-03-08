# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


import tests

import copy

import zim.history
from zim.history import History, HistoryPath, RecentPath
from zim.notebook import Path
from zim.config import INIConfigFile


class VirtualFile(object):
	### TODO - proper class for this in zim.fs
	###        unify with code in config manager

	def __init__(self, lines):
		self.lines = lines

	def readlines(self):
		return self.lines

	def connect(self, handler, *a):
		pass

	def disconnect(self, handler):
		pass


class TestHistory(tests.TestCase):

	def setUp(self):
		zim.history.MAX_HISTORY = 100
		self.notebook = tests.new_notebook()
		self.pages = [self.notebook.get_page(Path(name))
			for name in self.notebook.testdata_manifest]

	def assertCurrentEquals(self, history, path):
		current = history.get_current()
		self.assertTrue(isinstance(current, HistoryPath))
		self.assertEqual(current.name, path.name)

	def assertHistoryEquals(self, history, pages):
		self._checkPaths(history.get_history(), pages, HistoryPath)

	def assertRecentEquals(self, history, pages):
		self._checkPaths(history.get_recent(), pages, RecentPath)

	def _checkPaths(self, paths, wanted, klass):
		paths = list(paths)
		paths.reverse()

		self.assertTrue(any(isinstance(p, klass) for p in paths),  'All should have klass: %s' % klass)
		self.assertEqual([p.name for p in paths], [p.name for p in wanted])

	def testState(self):
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)
		self.assertHistoryEquals(history, self.pages)

		path = history.get_current()
		self.assertEqual(history.get_state(path), (None, None))
		path.cursor = 42
		self.assertEqual(history.get_state(path), (42, None))

	def testLinear(self):
		'''Walk back and forth through the history'''
		history = History(self.notebook)
		self.assertTrue(history.get_current() is None)
		for page in self.pages:
			history.append(page)
		self.assertHistoryEquals(history, self.pages)
		self.assertCurrentEquals(history, self.pages[-1])

		pages = list(history.get_history())
		self.assertEqual(pages[0], history.get_current())
		self.assertEqual(len(pages), len(self.pages))

		self.assertEqual(pages[0].cursor, None)
			# Newly appended pages should not have the cursor
			# set - pageview has logic to do the right thing when
			# no cursor is set. Setting default e.g. 0 will
			# overrule this logic.

		# walk backwards
		for i in range(2, len(self.pages)+1):
			prev = history.get_previous()
			self.assertFalse(prev is None)
			self.assertEqual(prev.name, self.pages[-i].name)
			self.assertFalse(prev.is_last)
			history.set_current(prev)

		self.assertCurrentEquals(history, self.pages[0])
		self.assertTrue(history.get_previous() is None)
		self.assertTrue(prev.is_first)
		self.assertHistoryEquals(history, self.pages)

		# walk forward
		for i in range(1, len(self.pages)):
			next = history.get_next()
			self.assertFalse(next is None)
			self.assertEqual(next.name, self.pages[i].name)
			self.assertFalse(next.is_first)
			history.set_current(next)

		self.assertCurrentEquals(history, self.pages[-1])
		self.assertTrue(history.get_next() is None)
		self.assertTrue(history.get_current().is_last)
		self.assertHistoryEquals(history, self.pages)

		# Add page multiple times
		current = history.get_current()
		path = Path(current.name)
		for j in range(5):
			history.append(path)
		self.assertHistoryEquals(history, self.pages) # history does not store duplicates
		self.assertEquals(history.get_current(), current)

		# Test dropping forward stack
		historylist = list(history.get_history())
		path1 = historylist[10]
		path2 = historylist[0]
		history.set_current(path1)
		self.assertEquals(history.get_current(), path1) # rewind
		self.assertHistoryEquals(history, self.pages) # no change

		history.append(path2) # new path - drop forward stack
		i = len(pages) - 10
		wanted = self.pages[:i] + [path2]
		self.assertHistoryEquals(history, wanted)

		# Test max entries
		default_max_history = zim.history.MAX_HISTORY
		zim.history.MAX_HISTORY = 3
		for page in self.pages:
			history.append(page)
		zim.history.MAX_HISTORY = default_max_history

		self.assertHistoryEquals(history, self.pages[-3:])

	def testUnique(self):
		'''Get recent pages from history'''
		default_max_recent = zim.history.MAX_RECENT

		zim.history.MAX_RECENT = len(self.pages) + 1
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)
		self.assertHistoryEquals(history, self.pages)

		unique = list(history.get_recent())
		self.assertEqual(unique[0], history.get_current())
		self.assertEqual(len(unique), len(self.pages))

		for page in self.pages:
			history.append(page)
		self.assertHistoryEquals(history, 2 * self.pages)

		unique = list(history.get_recent())
		self.assertEqual(unique[0], history.get_current())
		self.assertEqual(len(unique), len(self.pages))

		unique = set([page.name for page in unique]) # collapse doubles
		self.assertEqual(len(unique), len(self.pages))

		zim.history.MAX_RECENT = 3
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)
		zim.history.MAX_RECENT = default_max_recent

		self.assertHistoryEquals(history, self.pages)

		unique = list(history.get_recent())
		self.assertEqual(unique[0], history.get_current())
		self.assertEqual(len(unique), 3)


	def testChildren(self):
		'''Test getting namespace from history'''
		history = History(self.notebook)
		for name in ('Test:wiki', 'Test:foo:bar', 'Test:foo', 'TaskList:bar'):
			page = self.notebook.get_page(Path(name))
			history.append(page)

		self.assertEqual(history.get_child(Path('Test')), Path('Test:foo'))
		self.assertEqual(history.get_grandchild(Path('Test')), Path('Test:foo:bar'))
		self.assertEqual(history.get_child(Path('NonExistent')), None)
		self.assertEqual(history.get_grandchild(Path('NonExistent')), None)

		history.append(self.notebook.get_page(Path('Test:wiki')))
		self.assertEqual(history.get_child(Path('Test')), Path('Test:wiki'))
		self.assertEqual(history.get_grandchild(Path('Test')), Path('Test:wiki'))

		page = self.notebook.get_page(Path('Some:deep:nested:page'))
		history.append(page)
		self.assertEqual(history.get_child(Path('Some')), Path('Some:deep'))
		self.assertEqual(history.get_grandchild(Path('Some')), Path('Some:deep:nested:page'))


	def testMovePage(self):
		'''Test history is updated for moved pages'''
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)

		self.assertIn(Path('Test:wiki'), list(history.get_history()))

		history._on_page_moved(self.notebook, Path('Test'), Path('New'), False)
		self.assertNotIn(Path('Test:wiki'), list(history.get_history()))
		self.assertIn(Path('New:wiki'), list(history.get_history()))

		history._on_page_moved(self.notebook, Path('New'), Path('Test'), False)
		self.assertNotIn(Path('New:wiki'), list(history.get_history()))
		self.assertIn(Path('Test:wiki'), list(history.get_history()))

		self.assertHistoryEquals(history, self.pages)

	def testDeletedNotInUnique(self):
		'''Test if deleted pages and their children show up in unique history list'''
		zim.history.MAX_RECENT = len(self.pages) + 1
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)
		for page in self.pages:
			history.append(page)

		self.assertHistoryEquals(history, 2 * self.pages)

		uniques = list(history.get_recent())
		self.assertEqual(len(uniques), len(self.pages))

		page = history.get_current()
		history._on_page_deleted(self.notebook, page)
		uniques = list(history.get_recent())
		self.assertTrue(len(uniques) < len(self.pages))
		i = len(uniques)

		history.set_current(page)
		uniques = list(history.get_recent())
		self.assertEqual(len(uniques), i + 1)
			# Not same as len(self.pages) because of deleted children

		for page in self.pages:
			history._on_page_deleted(self.notebook, page)
		uniques = list(history.get_recent())
		self.assertEqual(len(uniques), 0)

		self.assertEqual(
			len(list(history.get_history())),
			2 * len(self.pages)  )

		for page in history.get_history():
			history.set_current(page)
		uniques = list(history.get_recent())
		self.assertEqual(len(uniques), len(self.pages))

	def testSerialize(self):
		'''Test parsing the history from the state file'''
		uistate = INIConfigFile(VirtualFile([]))
		history = History(self.notebook, uistate)

		for page in self.pages:
			history.append(page)
		self.assertHistoryEquals(history, self.pages)
		self.assertCurrentEquals(history, self.pages[-1])

		# rewind 2
		for i in range(2):
			prev = history.get_previous()
			history.set_current(prev)

		# check state
		#~ import pprint
		#~ pprint.pprint(uistate)
		self.assertHistoryEquals(history, uistate['History']['list'])
		self.assertRecentEquals(history, uistate['History']['recent'])
		self.assertEqual(uistate['History']['current'], len(self.pages) - 3)

		# clone uistate by text
		lines = uistate.dump()
		newuistate = INIConfigFile(VirtualFile(lines))
		newuistate['History'].setdefault('list', [])
		newuistate['History'].setdefault('recent', [])
		newuistate['History'].setdefault('current', 0)

		# check new state
		self.assertHistoryEquals(history, [Path(t[0]) for t in newuistate['History']['list']])
		self.assertRecentEquals(history, [Path(t[0]) for t in newuistate['History']['recent']])
		self.assertEqual(newuistate['History']['current'], len(self.pages) - 3)

		# and compare resulting history object
		newhistory = History(self.notebook, newuistate)
		self.assertEqual(list(newhistory.get_history()), list(history.get_history()))
		self.assertEqual(list(newhistory.get_recent()), list(history.get_recent()))
		self.assertEqual(newhistory.get_current(), history.get_current())

		# Check recent is initialized if needed
		newuistate = INIConfigFile(VirtualFile(lines))
		newuistate['History'].setdefault('recent', [])
		newuistate['History'].pop('recent')
		newhistory = History(self.notebook, newuistate)

		self.assertEqual(list(newhistory.get_history()), list(history.get_history()))
		self.assertEqual(list(newhistory.get_recent()), list(history.get_recent()))
		self.assertEqual(newhistory.get_current(), history.get_current())


	def testRobustness(self):
		'''Test history can deal with garbage data'''
		uistate = INIConfigFile(VirtualFile([]))
		uistate['History'].input({
			'list': 'FOOOO',
			'recent': [["BARRRR", 0]],
			'cursor': 'Not an integer',
		})

		with tests.LoggingFilter(
			logger='zim.config',
			message='Invalid config'
		):
			with tests.LoggingFilter(
				logger='zim.history',
				message='Could not parse'
			):
				history = History(self.notebook, uistate)
		self.assertEqual(list(history.get_history()), [])
		self.assertEqual(list(history.get_recent()), [])
		self.assertIsNone(history.get_current())
