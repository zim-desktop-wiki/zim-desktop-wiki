# -*- coding: utf-8 -*-

# Copyright 2015-2016 Pavel_M <plprgt@gmail.com>,
# released under the GNU GPL version 3.

# This is the test for BookmarksBar plugin.
# BookmarksBar is the plugin for Zim program
# by Jaap Karssenberg <jaap.karssenberg@gmail.com>.


import tests
import gtk

from zim.notebook import Path
from zim.plugins.bookmarksbar import *
from zim.config import ConfigDict
from zim.gui.clipboard import Clipboard

import logging
logger = logging.getLogger('zim.plugins.bookmarksbar')


class TestBookmarksBar(tests.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.notebook = tests.new_notebook()
		cls.index = cls.notebook.index
		cls.ui = MockUI()
		cls.ui.notebook = cls.notebook
		cls.ui.page = Path('Test:foo')


	def setUp(self):
		self.PATHS = ('Parent:Daughter:Granddaughter',
				 'Test:tags', 'Test:foo', 'Books')
		self.LEN_PATHS = len(self.PATHS)
		self.PATHS_NAMES = {self.PATHS[0]:'name 1', self.PATHS[1]:'name 2', self.PATHS[2]:'name 3'}

		self.uistate = ConfigDict()
		self.uistate.setdefault('bookmarks', [])
		self.uistate.setdefault('bookmarks_names', {})
		self.uistate.setdefault('show_full_page_name', True)


	def testGeneral(self):
		'''Test general functions: add, delete bookmarks.'''

		self.assertTrue(self.notebook.get_page(self.ui.page).exists())

		Bar = BookmarkBar(self.ui, self.uistate, get_page_func = lambda: '')
		Bar.max_bookmarks = 15 # set maximum number of bookmarks

		# Add paths to the beginning of the bar.
		for i, path in enumerate(self.PATHS):
			Bar._add_new(path, add_bookmarks_to_beginning = True)
			self.assertEqual(len(Bar.paths), i + 1)
		self.assertTrue(Bar.paths == list(reversed(self.PATHS)))

		# Add paths to the end of the bar.
		Bar.paths = []
		for i, path in enumerate(self.PATHS):
			Bar._add_new(path, add_bookmarks_to_beginning = False)
			self.assertEqual(len(Bar.paths), i + 1)
		self.assertEqual(Bar.paths, list(self.PATHS))

		# Check that the same path can't be added to the bar.
		Bar._add_new(self.PATHS[0])
		Bar._add_new(self.PATHS[1])
		self.assertEqual(Bar.paths, list(self.PATHS))

		# Delete paths from the bar.
		for i, button in enumerate(Bar.container.get_children()[2:]):
			path = button.zim_path
			self.assertTrue(path in Bar.paths)
			Bar.delete(button.zim_path)
			self.assertEqual(len(Bar.paths), self.LEN_PATHS - i - 1)
			self.assertTrue(path not in Bar.paths)
		self.assertEqual(Bar.paths, [])

		# Delete all bookmarks from the bar.
		Bar.delete_all()
		self.assertEqual(Bar.paths, [])


	def testDeletePages(self):
		'''Check deleting a bookmark after deleting a page in the notebook.'''

		notebook = tests.new_notebook()
		ui = MockUI()
		ui.notebook = notebook
		self.uistate['bookmarks'] = list(self.PATHS)

		Bar = BookmarkBar(ui, self.uistate, get_page_func = lambda: '')
		for i, path in enumerate(self.PATHS):
			self.assertTrue(path in Bar.paths)
			notebook.delete_page(Path(path))
			self.assertTrue(path not in Bar.paths)
			self.assertEqual(len(Bar.paths), self.LEN_PATHS - i - 1)
		self.assertEqual(Bar.paths, [])


	def testFunctions(self):
		'''Test bookmark functions: changing, reordering, ranaming.'''

		Bar = BookmarkBar(self.ui, self.uistate, get_page_func = lambda: '')
		Bar.max_bookmarks = 15 # set maximum number of bookmarks

		# Check changing a bookmark.
		for i, path in enumerate(self.PATHS):
			Bar._add_new(path, add_bookmarks_to_beginning = False)

		self.assertTrue('Test' not in Bar.paths)
		self.assertTrue('Books' in Bar.paths)
		Bar.change_bookmark('Books', 'Books')
		self.assertEqual(Bar.paths, list(self.PATHS))
		Bar.change_bookmark('Books', 'Test')
		self.assertTrue('Test' in Bar.paths)
		self.assertTrue('Books' not in Bar.paths)
		_result = [a if a != 'Books' else 'Test' for a in self.PATHS]
		self.assertEqual(Bar.paths, _result)

		Bar.change_bookmark('Test', 'Books')
		self.assertEqual(Bar.paths, list(self.PATHS))

		# Check reordering bookmarks.
		new_paths = ('1','2','3','4','5')

		Bar.paths = list(new_paths)
		Bar.move_bookmark(new_paths[2], new_paths[2], 'left')
		self.assertEqual(Bar.paths, list(new_paths))
		Bar.move_bookmark(new_paths[3], new_paths[3], 'right')
		self.assertEqual(Bar.paths, list(new_paths))
		Bar.move_bookmark('3', '1', 'left')
		self.assertEqual(Bar.paths, ['3','1','2','4','5'])
		Bar.move_bookmark('5', '1', 'left')
		self.assertEqual(Bar.paths, ['3','5','1','2','4'])
		Bar.move_bookmark('5', '1', 'right')
		self.assertEqual(Bar.paths, ['3','1','5','2','4'])
		Bar.move_bookmark('3', '4', 'right')
		self.assertEqual(Bar.paths, ['1','5','2','4','3'])
		Bar.move_bookmark('5', '4', '-')
		self.assertEqual(Bar.paths, ['1','5','2','4','3'])

		# Check rename_bookmark and save options.
		preferences_changed = lambda save: Bar.on_preferences_changed({'save': save,
				'add_bookmarks_to_beginning': False,
				'max_bookmarks': 15})

		new_path_names = {new_paths[0]:'11', new_paths[1]:'22', new_paths[2]:'33'}
		Bar.paths = list(new_paths)
		preferences_changed(True)
		Bar._reload_bar()

		def rename_check(label, path, paths_names, path_names_uistate):
			self.assertEqual(button.get_label(), label)
			self.assertEqual(button.zim_path, path)
			self.assertEqual(Bar.paths_names, paths_names)
			self.assertEqual(self.uistate['bookmarks_names'], path_names_uistate)

		button = gtk.Button(label = new_paths[0], use_underline = False)
		button.zim_path = new_paths[0]
		rename_check(new_paths[0], new_paths[0], {}, {})

		Clipboard.set_text('new name')
		Bar.rename_bookmark(button)
		rename_check('new name', new_paths[0], {new_paths[0]:'new name'}, {new_paths[0]:'new name'})
		preferences_changed(False)
		rename_check('new name', new_paths[0], {new_paths[0]:'new name'}, {})
		preferences_changed(True)
		rename_check('new name', new_paths[0], {new_paths[0]:'new name'}, {new_paths[0]:'new name'})
		Bar.rename_bookmark(button)
		rename_check(new_paths[0], new_paths[0], {}, {})

		# Check delete with renaming.
		preferences_changed(True)
		paths_names_copy = dict(new_path_names)
		Bar.paths_names = dict(new_path_names)
		for key in new_path_names:
			Bar.delete(key)
			del paths_names_copy[key]
			self.assertEqual(Bar.paths_names, paths_names_copy)
			self.assertEqual(self.uistate['bookmarks_names'], Bar.paths_names)

		# Check delete all with renaming.
		Bar.paths_names = dict(new_path_names)
		Bar.delete_all()
		self.assertEqual(Bar.paths_names, {})
		self.assertEqual(self.uistate['bookmarks_names'], {})

		# Check change bookmark with renaming.
		new_path_names = {new_paths[0]:'11', new_paths[1]:'22', new_paths[2]:'33'}

		Bar.paths = list(new_paths)
		Bar.paths_names = dict(new_path_names)
		paths_names_copy = dict(new_path_names)
		_name = paths_names_copy.pop(new_paths[0])
		paths_names_copy['new path'] = _name
		Bar.change_bookmark(new_paths[0], 'new path')
		self.assertEqual(Bar.paths_names, paths_names_copy)
		self.assertEqual(Bar.paths, ['new path'] + list(new_paths[1:]))


	def testPreferences(self):
		'''Check preferences: full/short page names, save option, 
		max number of bookmarks.'''

		# Check short page names.
		Bar = BookmarkBar(self.ui, self.uistate, get_page_func = lambda: '')
		self.uistate['show_full_page_name'] = False
		for path in self.PATHS:
			Bar._add_new(path)
		self.assertEqual(Bar.paths, list(self.PATHS))
		for i, button in enumerate(Bar.container.get_children()[2:]):
			self.assertEqual(self.PATHS[i], button.zim_path)
			self.assertEqual(Path(self.PATHS[i]).basename, button.get_label())

		# Show full page names.
		Bar.toggle_show_full_page_name()
		self.assertEqual(Bar.paths, list(self.PATHS))
		for i, button in enumerate(Bar.container.get_children()[2:]):
			self.assertEqual(self.PATHS[i], button.zim_path)
			self.assertEqual(self.PATHS[i], button.get_label())

		# Check save option.
		self.uistate['bookmarks'] = list(self.PATHS)
		self.uistate['bookmarks_names'] = dict(self.PATHS_NAMES)
		Bar = BookmarkBar(self.ui, self.uistate, get_page_func = lambda: '')
		self.assertEqual(Bar.paths, list(self.PATHS))
		self.assertEqual(Bar.paths_names, self.PATHS_NAMES)

		self.uistate['bookmarks'] = []
		self.uistate['bookmarks_names'] = {}
		Bar = BookmarkBar(self.ui, self.uistate, get_page_func = lambda: '')
		self.assertEqual(Bar.paths, [])
		self.assertEqual(Bar.paths_names, {})

		# Get pages to check max number of bookmarks.
		pagelist = set(self.index.list_pages(None))
		_enhanced_pagelist = set()
		for page in pagelist:
			_enhanced_pagelist.update( set(self.index.list_pages(page)) )
			if len(_enhanced_pagelist) > 20:
				break
		pagelist.update(_enhanced_pagelist)
		pagelist = [a.name for a in pagelist if a.exists()]
		self.assertTrue(len(pagelist) > 20)

		def preferences_changed(save, max_b):
			Bar.on_preferences_changed({
				'save': save,
				'add_bookmarks_to_beginning': False,
				'max_bookmarks': max_b})

		# Check that more than max bookmarks can be loaded at start.
		self.uistate['bookmarks'] = pagelist
		Bar = BookmarkBar(self.ui, self.uistate, get_page_func = lambda: '')
		self.assertEqual(pagelist, Bar.paths)
		preferences_changed(True, 5)
		self.assertEqual(pagelist, Bar.paths)
		self.assertEqual(pagelist, self.uistate['bookmarks'])

		# Set maximum number of bookmarks.
		self.uistate['bookmarks'] = []
		Bar = BookmarkBar(self.ui, self.uistate, get_page_func = lambda: '')
		for max_bookmarks in (5, 10, 15, 20):
			preferences_changed(False, max_bookmarks)
			for page in pagelist:
				Bar._add_new(page)
			self.assertEqual(len(Bar.paths), max_bookmarks)
			self.assertEqual(Bar.paths, pagelist[:max_bookmarks])
			Bar.delete_all()

		# Check 'save' option in preferences.
		for i, path in enumerate(self.PATHS):
			preferences_changed(False, 15)
			Bar._add_new(path)
			self.assertEqual(self.uistate['bookmarks'], [])
			preferences_changed(True, 15)
			self.assertEqual(self.uistate['bookmarks'], list(self.PATHS[:i+1]))
		self.assertEqual(self.uistate['bookmarks'], list(self.PATHS))


class MockUI(tests.MockObject):
	page = None
	notebook = None

