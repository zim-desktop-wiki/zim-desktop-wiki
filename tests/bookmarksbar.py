# -*- coding: utf-8 -*-

# Copyright 2015 Pavel_M <plprgt@gmail.com>.
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

	def setUp(self):
		self.notebook = tests.new_notebook()
		self.index = self.notebook.index

	def runTest(self):
		'''There is one long test.'''

		ui = MockUI()
		ui.notebook = self.notebook
		ui.page = Path('Test:foo')
		uistate = ConfigDict()
		self.assertTrue(self.notebook.get_page(ui.page).exists())

		PATHS = ('Parent:Daughter:Granddaughter',
				 'Test:tags', 'Test:foo', 'Books')
		LEN_PATHS = len(PATHS)
		PATHS_NAMES = {PATHS[0]:'name 1', PATHS[1]:'name 2', PATHS[2]:'name 3'}

		# Check correctness of reading uistate.
		uistate.setdefault('bookmarks', [])
		uistate.setdefault('bookmarks_names', {})

		uistate['bookmarks'] = list(PATHS)
		uistate['bookmarks_names'] = dict(PATHS_NAMES)
		Bar = BookmarkBar(ui, uistate, get_page_func = lambda: '')
		self.assertTrue(Bar.paths == list(PATHS))
		self.assertTrue(Bar.paths_names == PATHS_NAMES)

		uistate['bookmarks'] = []
		uistate['bookmarks_names'] = {}
		Bar = BookmarkBar(ui, uistate, get_page_func = lambda: '')
		self.assertTrue(Bar.paths == [])
		self.assertTrue(Bar.paths_names == {})

		# Add paths to the beginning of the bar.
		for i, path in enumerate(PATHS):
			Bar._add_new(path, add_bookmarks_to_beginning = True)
			self.assertTrue(len(Bar.paths) == i + 1)
		self.assertTrue(Bar.paths == list(reversed(PATHS)))

		# Add paths to the end of the bar.
		Bar.paths = []
		for i, path in enumerate(PATHS):
			Bar._add_new(path, add_bookmarks_to_beginning = False)
			self.assertTrue(len(Bar.paths) == i + 1)
		self.assertTrue(Bar.paths == list(PATHS))

		# Check that the same path can't be added to the bar.
		Bar._add_new(PATHS[0])
		Bar._add_new(PATHS[1])
		self.assertTrue(Bar.paths == list(PATHS))

		# Delete paths from the bar.
		for i, button in enumerate(Bar.container.get_children()[2:]):
			path = button.zim_path
			self.assertTrue(path in Bar.paths)
			Bar.delete(button.zim_path)
			self.assertTrue(len(Bar.paths) == LEN_PATHS - i - 1)
			self.assertTrue(path not in Bar.paths)
		self.assertTrue(Bar.paths == [])

		# Check short page names.
		uistate['show_full_page_name'] = False
		for path in PATHS:
			Bar._add_new(path)
		self.assertTrue(Bar.paths == list(PATHS))
		for i, button in enumerate(Bar.container.get_children()[2:]):
			self.assertTrue(PATHS[i] == button.zim_path)
			self.assertTrue(Path(PATHS[i]).basename == button.get_label())
		uistate['show_full_page_name'] = True

		# Delete all bookmarks from the bar.
		Bar.delete_all()
		self.assertTrue(Bar.paths == [])

		# Check restriction of max bookmarks in the bar.
		pagelist = set(self.index.list_pages(None))
		_enhanced_pagelist = set()
		for page in pagelist:
			_enhanced_pagelist.update( set(self.index.list_pages(page)) )
			if len(_enhanced_pagelist) > MAX_BOOKMARKS:
				break
		pagelist.update(_enhanced_pagelist)
		self.assertTrue(len(pagelist) > MAX_BOOKMARKS)
		pagelist = list(pagelist)
		for page in pagelist:
			Bar._add_new(page.name)
		self.assertTrue(len(Bar.paths) == MAX_BOOKMARKS)
		self.assertTrue(Bar.paths == [a.name for a in pagelist[:MAX_BOOKMARKS]])
		Bar.delete_all()

		# Check 'save' option in preferences.
		for i, path in enumerate(PATHS):
			Bar.on_preferences_changed({'save':False, 'add_bookmarks_to_beginning':False})
			Bar._add_new(path)
			self.assertTrue(uistate['bookmarks'] == [])
			Bar.on_preferences_changed({'save':True, 'add_bookmarks_to_beginning':False})
			self.assertTrue(uistate['bookmarks'] == list(PATHS[:i+1]))
		self.assertTrue(uistate['bookmarks'] == list(PATHS))

		# Check changing a bookmark.
		self.assertTrue('Test' not in Bar.paths)
		self.assertTrue('Books' in Bar.paths)
		Bar.change_bookmark('Books', 'Books')
		self.assertTrue(Bar.paths == list(PATHS))
		_b_paths = [a for a in Bar.paths if a != 'Books']
		Bar.change_bookmark('Books', 'Test')
		self.assertTrue('Test' in Bar.paths)
		self.assertTrue('Books' not in Bar.paths)
		_e_paths = [a for a in Bar.paths if a != 'Test']
		self.assertTrue(_b_paths == _e_paths)

		Bar.change_bookmark('Test', 'Books')
		self.assertTrue(Bar.paths == list(PATHS))

		# Check deleting a bookmark after deleting a page in the notebook.
		self.assertTrue(len(Bar.paths) == LEN_PATHS)
		for i, path in enumerate(PATHS):
			self.assertTrue(path in Bar.paths)
			self.notebook.delete_page(Path(path))
			self.assertTrue(path not in Bar.paths)
			self.assertTrue(len(Bar.paths) == LEN_PATHS - i - 1)
		self.assertTrue(Bar.paths == [])

		# Check reordering bookmarks.
		PATHS_2 = ('1','2','3','4','5')
		PATHS_NAMES_2 = {PATHS_2[0]:'11', PATHS_2[1]:'22', PATHS_2[2]:'33'}

		Bar.paths = list(PATHS_2)
		Bar.move_bookmark(PATHS_2[2], PATHS_2[2], 'left')
		self.assertTrue(Bar.paths == list(PATHS_2))
		Bar.move_bookmark(PATHS_2[3], PATHS_2[3], 'right')
		self.assertTrue(Bar.paths == list(PATHS_2))
		Bar.move_bookmark('3', '1', 'left')
		self.assertTrue(Bar.paths == ['3','1','2','4','5'])
		Bar.move_bookmark('5', '1', 'left')
		self.assertTrue(Bar.paths == ['3','5','1','2','4'])
		Bar.move_bookmark('5', '1', 'right')
		self.assertTrue(Bar.paths == ['3','1','5','2','4'])
		Bar.move_bookmark('3', '4', 'right')
		self.assertTrue(Bar.paths == ['1','5','2','4','3'])
		Bar.move_bookmark('5', '4', '-')
		self.assertTrue(Bar.paths == ['1','5','2','4','3'])

		# CHECK RENAMING
		# Check rename_bookmark and save options.
		Bar.paths = list(PATHS_2)
		button = gtk.Button(label = PATHS_2[0], use_underline = False)
		button.zim_path = PATHS_2[0]
		Bar.on_preferences_changed({'save':True, 'add_bookmarks_to_beginning':False})
		Bar._reload_bar()

		def rename_check(label, path, paths_names, path_names_uistate):
			self.assertTrue(button.get_label() == label)
			self.assertTrue(button.zim_path == path)
			self.assertTrue(Bar.paths_names == paths_names)
			self.assertTrue(uistate['bookmarks_names'] == path_names_uistate)

		rename_check(PATHS_2[0], PATHS_2[0], {}, {})
		Clipboard.set_text('new name')
		Bar.rename_bookmark(button)
		rename_check('new name', PATHS_2[0], {PATHS_2[0]:'new name'}, {PATHS_2[0]:'new name'})
		Bar.on_preferences_changed({'save':False, 'add_bookmarks_to_beginning':False})
		rename_check('new name', PATHS_2[0], {PATHS_2[0]:'new name'}, {})
		Bar.on_preferences_changed({'save':True, 'add_bookmarks_to_beginning':False})
		rename_check('new name', PATHS_2[0], {PATHS_2[0]:'new name'}, {PATHS_2[0]:'new name'})
		Bar.rename_bookmark(button)
		rename_check(PATHS_2[0], PATHS_2[0], {}, {})

		# Check delete with renaming.
		Bar.on_preferences_changed({'save':True, 'add_bookmarks_to_beginning':False})
		paths_names_copy = dict(PATHS_NAMES_2)
		Bar.paths_names = dict(PATHS_NAMES_2)
		for key in PATHS_NAMES_2:
			Bar.delete(key)
			del paths_names_copy[key]
			self.assertTrue(Bar.paths_names == paths_names_copy)
			self.assertTrue(uistate['bookmarks_names'] == Bar.paths_names)

		# Check delete all with renaming.
		Bar.paths_names = dict(PATHS_NAMES_2)
		Bar.delete_all()
		self.assertTrue(Bar.paths_names == {})
		self.assertTrue(uistate['bookmarks_names'] == {})

		# Check change bookmark with renaming.
		Bar.paths = list(PATHS_2)
		Bar.paths_names = dict(PATHS_NAMES_2)
		paths_names_copy = dict(PATHS_NAMES_2)
		paths_names_copy.pop(PATHS_2[0], None)
		Bar.change_bookmark(PATHS_2[0], 'new path')
		self.assertTrue(Bar.paths_names == paths_names_copy)
		self.assertTrue(Bar.paths == ['new path'] + list(PATHS_2[1:]))

		# Check that paths and paths_names didn't change in the process.
		self.assertTrue(PATHS_2 == ('1','2','3','4','5'))
		self.assertTrue(PATHS_NAMES_2 == {PATHS_2[0]:'11', PATHS_2[1]:'22', PATHS_2[2]:'33'})


class MockUI(tests.MockObject):
	page = None
	notebook = None

