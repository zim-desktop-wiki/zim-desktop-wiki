
# Copyright 2015-2016 Pavel_M <plprgt@gmail.com>,
# released under the GNU GPL version 3.

# This is the test for BookmarksBar plugin.
# BookmarksBar is the plugin for Zim program
# by Jaap Karssenberg <jaap.karssenberg@gmail.com>.


import tests
from gi.repository import Gtk

from zim.notebook import Path
from zim.plugins.bookmarksbar import *
from zim.config import ConfigDict
from zim.gui.clipboard import Clipboard

import logging
logger = logging.getLogger('zim.plugins.bookmarksbar')


class TestBookmarksBar(tests.TestCase):

	def setUp(self):
		self.PATHS = ('Parent:Daughter:Granddaughter', 'Test:tags', 'Test:foo', 'Books')
		self.LEN_PATHS = len(self.PATHS)
		self.PATHS_NAMES = {self.PATHS[0]: 'name 1', self.PATHS[1]: 'name 2', self.PATHS[2]: 'name 3'}

		self.notebook = self.setUpNotebook(content=self.PATHS)

		self.uistate = ConfigDict()
		self.uistate.setdefault('bookmarks', [])
		self.uistate.setdefault('bookmarks_names', {})
		self.uistate.setdefault('show_full_page_name', True)


	def testGeneral(self):
		'''Test general functions: add, delete bookmarks.'''
		navigation = tests.MockObject()
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		bar.max_bookmarks = 15 # set maximum number of bookmarks

		# Add paths to the beginning of the bar.
		for i, path in enumerate(self.PATHS):
			bar._add_new(path, add_bookmarks_to_beginning = True)
			self.assertEqual(len(bar.paths), i + 1)
		self.assertTrue(bar.paths == list(reversed(self.PATHS)))

		# Add paths to the end of the bar.
		bar.paths = []
		for i, path in enumerate(self.PATHS):
			bar._add_new(path, add_bookmarks_to_beginning = False)
			self.assertEqual(len(bar.paths), i + 1)
		self.assertEqual(bar.paths, list(self.PATHS))

		# Check that the same path can't be added to the bar.
		bar._add_new(self.PATHS[0])
		bar._add_new(self.PATHS[1])
		self.assertEqual(bar.paths, list(self.PATHS))

		# Delete paths from the bar.
		for i, button in enumerate(bar.scrolledbox.get_scrolled_children()):
			path = button.zim_path
			self.assertTrue(path in bar.paths)
			bar.delete(button.zim_path)
			self.assertEqual(len(bar.paths), self.LEN_PATHS - i - 1)
			self.assertTrue(path not in bar.paths)
		self.assertEqual(bar.paths, [])

		# Delete all bookmarks from the bar.
		bar.delete_all()
		self.assertEqual(bar.paths, [])


	def testDeletePages(self):
		'''Check deleting a bookmark after deleting a page in the notebook.'''
		self.uistate['bookmarks'] = list(self.PATHS)
		navigation = tests.MockObject()
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		for i, path in enumerate(self.PATHS):
			self.assertTrue(path in bar.paths)
			self.notebook.delete_page(Path(path))
			self.assertTrue(path not in bar.paths)
			self.assertEqual(len(bar.paths), self.LEN_PATHS - i - 1)
		self.assertEqual(bar.paths, [])


	def testFunctions(self):
		'''Test bookmark functions: changing, reordering, ranaming.'''
		navigation = tests.MockObject()
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		bar.max_bookmarks = 15 # set maximum number of bookmarks

		# Check changing a bookmark.
		for i, path in enumerate(self.PATHS):
			bar._add_new(path, add_bookmarks_to_beginning = False)

		self.assertTrue('Test' not in bar.paths)
		self.assertTrue('Books' in bar.paths)
		bar.change_bookmark('Books', 'Books')
		self.assertEqual(bar.paths, list(self.PATHS))
		bar.change_bookmark('Books', 'Test')
		self.assertTrue('Test' in bar.paths)
		self.assertTrue('Books' not in bar.paths)
		_result = [a if a != 'Books' else 'Test' for a in self.PATHS]
		self.assertEqual(bar.paths, _result)

		bar.change_bookmark('Test', 'Books')
		self.assertEqual(bar.paths, list(self.PATHS))

		# Check reordering bookmarks.
		new_paths = ('1', '2', '3', '4', '5')

		bar.paths = list(new_paths)
		bar.move_bookmark(new_paths[2], new_paths[2], 'left')
		self.assertEqual(bar.paths, list(new_paths))
		bar.move_bookmark(new_paths[3], new_paths[3], 'right')
		self.assertEqual(bar.paths, list(new_paths))
		bar.move_bookmark('3', '1', 'left')
		self.assertEqual(bar.paths, ['3', '1', '2', '4', '5'])
		bar.move_bookmark('5', '1', 'left')
		self.assertEqual(bar.paths, ['3', '5', '1', '2', '4'])
		bar.move_bookmark('5', '1', 'right')
		self.assertEqual(bar.paths, ['3', '1', '5', '2', '4'])
		bar.move_bookmark('3', '4', 'right')
		self.assertEqual(bar.paths, ['1', '5', '2', '4', '3'])
		bar.move_bookmark('5', '4', '-')
		self.assertEqual(bar.paths, ['1', '5', '2', '4', '3'])

		# Check rename_bookmark and save options.
		preferences_changed = lambda save: bar.on_preferences_changed({'save': save,
				'add_bookmarks_to_beginning': False,
				'max_bookmarks': 15})

		new_path_names = {new_paths[0]: '11', new_paths[1]: '22', new_paths[2]: '33'}
		bar.paths = list(new_paths)
		preferences_changed(True)
		bar._reload_bar()

		def rename_check(label, path, paths_names, path_names_uistate):
			self.assertEqual(button.get_label(), label)
			self.assertEqual(button.zim_path, path)
			self.assertEqual(bar.paths_names, paths_names)
			self.assertEqual(self.uistate['bookmarks_names'], path_names_uistate)

		button = Gtk.Button(label = new_paths[0], use_underline = False)
		button.zim_path = new_paths[0]
		rename_check(new_paths[0], new_paths[0], {}, {})

		Clipboard.set_text('new name')
		bar.rename_bookmark(button)
		rename_check('new name', new_paths[0], {new_paths[0]: 'new name'}, {new_paths[0]: 'new name'})
		preferences_changed(False)
		rename_check('new name', new_paths[0], {new_paths[0]: 'new name'}, {})
		preferences_changed(True)
		rename_check('new name', new_paths[0], {new_paths[0]: 'new name'}, {new_paths[0]: 'new name'})
		bar.rename_bookmark(button)
		rename_check(new_paths[0], new_paths[0], {}, {})

		# Check delete with renaming.
		preferences_changed(True)
		paths_names_copy = dict(new_path_names)
		bar.paths_names = dict(new_path_names)
		for key in new_path_names:
			bar.delete(key)
			del paths_names_copy[key]
			self.assertEqual(bar.paths_names, paths_names_copy)
			self.assertEqual(self.uistate['bookmarks_names'], bar.paths_names)

		# Check delete all with renaming.
		bar.paths_names = dict(new_path_names)
		bar.delete_all()
		self.assertEqual(bar.paths_names, {})
		self.assertEqual(self.uistate['bookmarks_names'], {})

		# Check change bookmark with renaming.
		new_path_names = {new_paths[0]: '11', new_paths[1]: '22', new_paths[2]: '33'}

		bar.paths = list(new_paths)
		bar.paths_names = dict(new_path_names)
		paths_names_copy = dict(new_path_names)
		_name = paths_names_copy.pop(new_paths[0])
		paths_names_copy['new path'] = _name
		bar.change_bookmark(new_paths[0], 'new path')
		self.assertEqual(bar.paths_names, paths_names_copy)
		self.assertEqual(bar.paths, ['new path'] + list(new_paths[1:]))


	def testPreferences(self):
		'''Check preferences: full/short page names, save option,
		max number of bookmarks.'''

		# Check short page names.
		navigation = tests.MockObject()
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		self.uistate['show_full_page_name'] = False
		for path in self.PATHS:
			bar._add_new(path)
		self.assertEqual(bar.paths, list(self.PATHS))
		for i, button in enumerate(bar.scrolledbox.get_scrolled_children()):
			self.assertEqual(self.PATHS[i], button.zim_path)
			self.assertEqual(Path(self.PATHS[i]).basename, button.get_label())

		# Show full page names.
		bar.toggle_show_full_page_name()
		self.assertEqual(bar.paths, list(self.PATHS))
		for i, button in enumerate(bar.scrolledbox.get_scrolled_children()):
			self.assertEqual(self.PATHS[i], button.zim_path)
			self.assertEqual(self.PATHS[i], button.get_label())

		# Check save option.
		self.uistate['bookmarks'] = list(self.PATHS)
		self.uistate['bookmarks_names'] = dict(self.PATHS_NAMES)
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		self.assertEqual(bar.paths, list(self.PATHS))
		self.assertEqual(bar.paths_names, self.PATHS_NAMES)

		self.uistate['bookmarks'] = []
		self.uistate['bookmarks_names'] = {}
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		self.assertEqual(bar.paths, [])
		self.assertEqual(bar.paths_names, {})

		# Get pages to check max number of bookmarks.
		pagelist = []
		for path in [Path('Page %i' % i) for i in range(25)]:
			page = self.notebook.get_page(path)
			page.parse('wiki', 'TEst 123')
			self.notebook.store_page(page)
			pagelist.append(path.name)
		self.assertTrue(len(pagelist) > 20)

		def preferences_changed(save, max_b):
			bar.on_preferences_changed({
				'save': save,
				'add_bookmarks_to_beginning': False,
				'max_bookmarks': max_b})

		# Check that more than max bookmarks can be loaded at start.
		self.uistate['bookmarks'] = pagelist
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		self.assertEqual(pagelist, bar.paths)
		preferences_changed(True, 5)
		self.assertEqual(pagelist, bar.paths)
		self.assertEqual(pagelist, self.uistate['bookmarks'])

		# Set maximum number of bookmarks.
		self.uistate['bookmarks'] = []
		bar = BookmarkBar(self.notebook, navigation, self.uistate, get_page_func = lambda: '')
		for max_bookmarks in (5, 10, 15, 20):
			preferences_changed(False, max_bookmarks)
			for page in pagelist:
				bar._add_new(page)
			self.assertEqual(len(bar.paths), max_bookmarks)
			self.assertEqual(bar.paths, pagelist[:max_bookmarks])
			bar.delete_all()

		# Check 'save' option in preferences.
		for i, path in enumerate(self.PATHS):
			preferences_changed(False, 15)
			bar._add_new(path)
			self.assertEqual(self.uistate['bookmarks'], [])
			preferences_changed(True, 15)
			self.assertEqual(self.uistate['bookmarks'], list(self.PATHS[:i + 1]))
		self.assertEqual(self.uistate['bookmarks'], list(self.PATHS))
