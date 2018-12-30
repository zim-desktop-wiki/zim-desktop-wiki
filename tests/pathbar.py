
# Copyright 2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.plugins import find_extension, PluginManager
from zim.plugins.pathbar import *

from zim.history import History
from zim.notebook import Path

from tests.mainwindow import setUpMainWindow


class TestPluginExtendsMainWindow(tests.TestCase):

	def runTest(self):
		plugin = PluginManager.load_plugin('pathbar')
		window = setUpMainWindow(self.setUpNotebook())
		extension = find_extension(window, PathBarMainWindowExtension)

		for ptype in PATHBAR_TYPES:
			extension.set_pathbar(ptype)
			pathbar = window._zim_window_central_vbox.get_children()[0]
			if ptype == PATHBAR_NONE:
				self.assertNotIsInstance(pathbar, PathBar)
			else:
				self.assertIsInstance(pathbar, extension._klasses[ptype])


class TestPathBar(tests.TestCase):

	@tests.expectedFailure
	def testActivatePage(self):
		raise NotImplementedError

	@tests.expectedFailure
	def testActivateContextMenu(self):
		raise NotImplementedError

	@tests.expectedFailure
	def testDragAndDropFromPathBar(self):
		raise NotImplementedError

	# TODO:
	# Scroll left / right
	# Allocate space
	# ...


class TestHistoryPathBar(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content=('A', 'B', 'C', 'D'))
		history = History(notebook)
		pathbar = HistoryPathBar(history, notebook, None)
		for name in ('A', 'A', 'B', 'A', 'D', 'D'):
			history.append(Path(name))
			pathbar.set_page(Path(name))
		self.assertEqual(
			[button.zim_path
				for button in pathbar.get_children()
					if not isinstance(button, ScrollButton)
			],
			list(reversed(list(history.get_history())))
		)


class TestRecentPathBar(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content=('A', 'B', 'C', 'D'))
		history = History(notebook)
		pathbar = RecentPathBar(history, notebook, None)
		for name in ('A', 'A', 'B', 'A', 'D', 'D'):
			history.append(Path(name))
			pathbar.set_page(Path(name))
		self.assertEqual(
			[button.zim_path
				for button in pathbar.get_children()
					if not isinstance(button, ScrollButton)
			],
			list(reversed(list(history.get_recent())))
		)


import time

class TestRecentChangesPathBar(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook()
		history = History(notebook)
		pathbar = RecentChangesPathBar(history, notebook, None)
		for name in ('A', 'A', 'B', 'A', 'D', 'D'):
			p = notebook.get_page(Path(name))
			text = p.dump('wiki') # prevent etag fail
			p.parse('wiki', 'test 123')
			time.sleep(0.01) # ensure timestamp order ...
			notebook.store_page(p)
			pathbar.set_page(Path(name))
		self.assertEqual(
			[button.zim_path
				for button in pathbar.get_children()
					if not isinstance(button, ScrollButton)
			],
			[Path(n) for n in ('B', 'A', 'D')]
		)

class TestNamespacePathBar(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content=('A', 'B', 'C', 'D'))
		history = History(notebook)
		pathbar = NamespacePathBar(history, notebook, None)
		for name in ('A:A1:AA1', 'B', 'C:C1', 'D'):
			history.append(Path(name))
			pathbar.set_page(Path(name))
			self.assertEqual(
				[button.zim_path
					for button in pathbar.get_children()
						if not isinstance(button, ScrollButton)
				],
				[p for p in reversed(list(Path(name).parents())) if not p.isroot] + [Path(name)]
			)
