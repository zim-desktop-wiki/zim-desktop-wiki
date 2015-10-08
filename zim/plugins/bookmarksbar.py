# -*- coding: utf-8 -*-

# Copyright 2015 Pavel_M <plprgt@gmail.com>.
# This plugin is for Zim program by Jaap Karssenberg <jaap.karssenberg@gmail.com>.
#
# This plugin uses an icon from Tango Desktop Project (http://tango.freedesktop.org/)
# (the Tango base icon theme is released to the Public Domain).

import gobject
import gtk
import pango

from zim.actions import toggle_action, action
from zim.plugins import PluginClass, extends, WindowExtension
from zim.notebook import Path
from zim.gui.widgets import TOP, TOP_PANE
from zim.signals import ConnectorMixin
from zim.gui.pathbar import ScrolledHBox
from zim.gui.clipboard import Clipboard

import logging
logger = logging.getLogger('zim.plugins.bookmarksbar')

# Constant for max number of bookmarks in the bar.
MAX_BOOKMARKS = 15

# Keyboard shortcut constants.
BM_TOGGLE_BAR_KEY ='F4'
BM_ADD_BOOKMARK_KEY ='<alt>1'

class BookmarksBarPlugin(PluginClass):

	plugin_info = {
	'name': _('BookmarksBar'), # T: plugin name
	'description': _('''\
		This plugin provides bar for bookmarks.
		'''), # T: plugin description
	'author': 'Pavel_M',
	'help': 'Plugins:BookmarksBar',}

	plugin_preferences = (
		# key, type, label, default
		('save', 'bool', _('Save bookmarks'), True), # T: preferences option
		('add_bookmarks_to_beginning', 'bool', _('Add new bookmarks to the beginning of the bar'), False), # T: preferences option
	)

@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
	<ui>
	<menubar name='menubar'>
	<menu action='view_menu'>
			<placeholder name='plugin_items'>
		<menuitem action='toggle_show_bookmarks'/>
		</placeholder>
	</menu>
		<menu action='tools_menu'>
		<placeholder name='plugin_items'>
			<menuitem action='add_bookmark'/>
			</placeholder>
	</menu>
	</menubar>
	<toolbar name='toolbar'>
		<placeholder name='tools'>
			<toolitem action='toggle_show_bookmarks'/>
		</placeholder>
	</toolbar>
	</ui>'''
	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.widget = BookmarkBar(self.window.ui, self.uistate,
								  self.window.pageview.get_page)
		self.widget.show_all()

		# Add a new option to the Index popup menu.
		try:
			self.widget.connectto(self.window.pageindex.treeview,
								  'populate-popup', self.on_populate_popup)
		except AttributeError:
			logger.error('BookmarksBar: popup menu not initialized.')

		# Show/hide bookmarks.
		self.uistate.setdefault('show_bar', True)
		self.toggle_show_bookmarks(self.uistate['show_bar'])

		# Init preferences in self.widget.
		self.widget.on_preferences_changed(plugin.preferences)
		self.widget.connectto(plugin.preferences, 'changed',
							  lambda o: self.widget.on_preferences_changed(plugin.preferences))

	def teardown(self):
		if self.widget:
			try:
				self.window.remove(self.widget)
			except ValueError:
				pass
			self.widget.disconnect_all()
			self.widget = None

	def hide_widget(self):
		'''Hide Bar.'''
		self.window.remove(self.widget)

	def show_widget(self):
		'''Show Bar.'''
		self.window.add_widget(self.widget, (TOP_PANE, TOP))

	def on_populate_popup(self, treeview, menu):
		'''Add 'Add Bookmark' option to the Index popup menu.'''
		path = treeview.get_selected_path()
		if path:
			item = gtk.SeparatorMenuItem()
			menu.prepend(item)
			item = gtk.MenuItem(_('Add Bookmark')) # T: menu item bookmark plugin
			page = self.window.ui.notebook.get_page(path)
			item.connect('activate', lambda o: self.widget.add_new_page(page))
			menu.prepend(item)
			menu.show_all()


	@toggle_action(_('Bookmarks'), stock='zim-add-bookmark',
				   tooltip = 'Show/Hide Bookmarks', accelerator = BM_TOGGLE_BAR_KEY) # T: menu item bookmark plugin
	def toggle_show_bookmarks(self, active):
		'''
		Show/hide the bar with bookmarks.
		'''
		if active:
			self.show_widget()
		else:
			self.hide_widget()
		self.uistate['show_bar'] = active

	@action(_('Add Bookmark'), accelerator = BM_ADD_BOOKMARK_KEY) # T: menu item bookmark plugin
	def add_bookmark(self):
		'''
		Function to add new bookmarks to the bar.
		Introduced to be used via keyboard shortcut.
		'''
		self.widget.add_new_page()


class BookmarkBar(gtk.HBox, ConnectorMixin):

	def __init__(self, ui, uistate, get_page_func):
		gtk.HBox.__init__(self)

		self.ui = ui
		self.uistate = uistate
		self.save_flag = False # if True save bookmarks in config
		self.add_bookmarks_to_beginning = False # add new bookmarks to the end of the bar
		self._get_page = get_page_func # function to get current page

		# Create button to add new bookmarks.
		self.plus_button = IconsButton(gtk.STOCK_ADD, gtk.STOCK_REMOVE, relief = False)
		self.plus_button.connect('clicked', lambda o: self.add_new_page())
		self.plus_button.connect('button-release-event', self.do_plus_button_popup_menu)
		self.pack_start(self.plus_button, expand = False)

		# Create widget for bookmarks.
		self.container = ScrolledHBox()
		self.pack_start(self.container, expand = True)

		# Toggle between full/short page names.
		self.uistate.setdefault('show_full_page_name', False)

		# Save path to use later in Cut/Paste menu.
		self._saved_bookmark = None

		self.paths = [] # list of bookmarks as string objects
		self.uistate.setdefault('bookmarks', [])

		# Add pages from config to the bar.
		for path in self.uistate['bookmarks']:
			page = self.ui.notebook.get_page(Path(path))
			self.add_new_page(page, reload_bar = False)

		self.paths_names = {} # dict of changed names of bookmarks
		self.uistate.setdefault('bookmarks_names', {})
		# Function to transform random string to paths_names format.
		self._convert_path_name = lambda a: ' '.join(a[:25].split())

		# Add alternative bookmark names from config.
		for path, name in self.uistate['bookmarks_names'].iteritems():
			if path in self.paths:
				try:
					name = self._convert_path_name(name)
					self.paths_names[path] = name
				except:
					logger.error('BookmarksBar: Error while loading path_names.')

		self._reload_bar()

		# Delete a bookmark if a page is deleted.
		self.connectto(self.ui.notebook.index, 'page-deleted',
					   lambda obj, path: self.delete(path.name))

	def add_new_page(self, page = None, reload_bar = True):
		'''
		Add new page as bookmark to the bar.
		:param page: L{Page}, if None takes currently opened page,
		:reload_bar: if True reload the bar.
		'''
		if not page:
			page = self._get_page()

		if page.exists():
			return self._add_new(page.name, self.add_bookmarks_to_beginning, reload_bar)

	def _add_new(self, path, add_bookmarks_to_beginning = False, reload_bar = True):
		'''Add bookmark to the bar.
		:param path: path as a string object
		:param add_bookmarks_to_beginning: bool,
		add new bookmarks to the beginning of the bar,
		:reload_bar: if True reload the bar.
		'''
		if path in self.paths:
			logger.debug('BookmarksBar: path is already in the bar.')

			# Temporary change icon for plus_button to show
			# that bookmark is already in the bar.
			def _change_icon():
				'''Function to be called only once.'''
				self.plus_button.change_state()
				return False
			self.plus_button.change_state()
			gobject.timeout_add(300, _change_icon)
			return False

		# Limit max number of bookmarks.
		if len(self.paths) >= MAX_BOOKMARKS:
			logger.debug('BookmarksBar: max number of bookmarks is achieved.')
			return False

		# Add a new bookmark to the end or to the beginning.
		if add_bookmarks_to_beginning:
			self.paths.insert(0, path)
		else:
			self.paths.append(path)

		if reload_bar: self._reload_bar()

	def delete(self, path):
		'''
		Remove one button from the bar.
		:param path: string corresponding to Path.name.
		'''
		if path in self.paths:
			self.paths.remove(path)
			self.paths_names.pop(path, None)
		        self._reload_bar()

	def delete_all(self, ask_confirmation = False):
		'''
		Remove all bookmarks.
		:param ask_confirmation: to confirm deleting.
		'''
		def _delete_all():
			self.paths = []
			self.paths_names = {}
			self._reload_bar()

		if ask_confirmation:
			# Prevent accidental deleting of all bookmarks.
			menu = gtk.Menu()
			item = gtk.MenuItem(_('Do you want to delete all bookmarks?')) # T: message for bookmark plugin
			item.connect('activate', lambda o: _delete_all())
			menu.append(item)
			menu.show_all()
			menu.popup(None, None, None, 3, 0)
		else:
			_delete_all()

	def change_bookmark(self, old_path, new_path = None):
		'''
		Change path in bookmark from 'old_path' to 'new_path'.
		:param new_path, old_path: strings corresponding to Path.name.
		If 'new_path' == None takes currently opened page.
		'''
		if not new_path:
			page = self._get_page()
			if page.exists():
				new_path = page.name

		if new_path and (new_path not in self.paths) and (new_path != old_path):
			self.paths[self.paths.index(old_path)] = new_path
			self.paths_names.pop(old_path, None)
			self._reload_bar()

	def move_bookmark(self, first, second, direction):
		'''
		Move bookmark 'first' to the place near the bookmark 'second'.
		:param first, second: strings corresponding to Path.name.
		:param direction: move 'first' bookmark to the 'left' or 'right' of the 'second'.
		'''
		if (first == second) or (direction not in ('left','right')):
			return False

		if (first in self.paths) and (second in self.paths):
			self.paths.remove(first)
			ind = self.paths.index(second)

			if direction == 'left':
				self.paths.insert(ind, first)
			else: # direction == 'right'
				self.paths.insert(ind + 1, first)
			self._reload_bar()

	def rename_bookmark(self, button):
		'''
		Change label of the button.
		New name is taken from the clipboard.
		If button's name has been changed before,
		change it back to its initial state.
		'''
		_full, _short = button.zim_path, self._get_short_page_name(button.zim_path)

		if button.get_label() in (_short, _full):
			# Change the button to new name.
			new_name = None
			try:
				# Take from clipboard.
				new_name = self._convert_path_name(Clipboard.get_text())
			except:
				logger.error('BookmarksBar: Error while converting from buffer.')
			if new_name:
				self.paths_names[_full] = new_name
				button.set_label(new_name)
		else:
			# Change the button back to its initial state.
			new_name = _full if self.uistate['show_full_page_name'] else _short
			button.set_label(new_name)
			self.paths_names.pop(_full, None)

		if self.save_flag:
			self.uistate['bookmarks_names'] = self.paths_names

	def do_plus_button_popup_menu(self, button, event):
		'''Handler for button-release-event, triggers popup menu for plus button.'''
		if event.button == 3:
			menu = gtk.Menu()
			item = gtk.CheckMenuItem(_('Show full Page Name')) # T: menu item for context menu
			item.set_active(self.uistate['show_full_page_name'])
			item.connect('activate', lambda o: self.toggle_show_full_page_name())
			menu.append(item)
			menu.show_all()
			menu.popup(None, None, None, 3, 0)
			return True

	def do_bookmarks_popup_menu(self, button, event):
		'''Handler for button-release-event, triggers popup menu for bookmarks.'''
		if event.button != 3:
                        return False

		path = button.zim_path

		_button_width = button.size_request()[0]
		direction = 'left' if (int(event.x) <= _button_width/2) else 'right'

		def set_save_bookmark(path):
			self._saved_bookmark = path

		if button.get_label() in (path, self._get_short_page_name(path)):
			rename_button_text = _('Set New Name') # T: button label
		else:
			rename_button_text = _('Back to Original Name') # T: button label

		# main popup menu
		main_menu = gtk.Menu()
		main_menu_items = (
					(_('Remove'), lambda o: self.delete(path)),			# T: menu item
				    (_('Remove All'), lambda o: self.delete_all(True)),	# T: menu item
				    ('separator', ''),
				    (_('Open in New Window'), lambda o: self.ui.open_new_window(Path(path))), # T: menu item
				    ('separator', ''),
				    ('gtk-copy', lambda o: set_save_bookmark(path)),
				    ('gtk-paste', lambda o: self.move_bookmark(self._saved_bookmark, path, direction)),
				    ('separator', ''),
				    (rename_button_text, lambda o: self.rename_bookmark(button)),
				    ('separator', ''),
				    (_('Set to Current Page'), lambda o: self.change_bookmark(path)) ) # T: menu item

		for name, func in main_menu_items:
			if name == 'separator':
				item = gtk.SeparatorMenuItem()
			else:
				if 'gtk-' in name:
					item = gtk.ImageMenuItem(name)
				else:
					item = gtk.MenuItem(name)
			        item.connect('activate', func)
			main_menu.append(item)

		main_menu.show_all()
		main_menu.popup(None, None, None, 3, 0)
		return True

	def on_bookmark_clicked(self, button):
		'''Open page if a bookmark is clicked.'''
		self.ui.open_page(Path(button.zim_path))

	def on_preferences_changed(self, preferences):
		'''Plugin preferences were changed.'''

		self.save_flag = preferences['save']
		self.add_bookmarks_to_beginning = preferences['add_bookmarks_to_beginning']

		if self.save_flag:
			self.uistate['bookmarks'] = self.paths
			self.uistate['bookmarks_names'] = self.paths_names
		else:
			self.uistate['bookmarks'] = []
			self.uistate['bookmarks_names'] = {}

	def _get_short_page_name(self, name):
		'''
		Function to return short name for the page.
		Is used to set short names to bookmarks.
		'''
		path = Path(name)
		return path.basename

	def toggle_show_full_page_name(self):
		'''Change page name from short to full and vice versa.'''
		self.uistate['show_full_page_name'] = not self.uistate['show_full_page_name']
		self._reload_bar()

	def _reload_bar(self):
		'''Reload bar with bookmarks.'''
		for button in self.container.get_children()[2:]:
			self.container.remove(button)

		for path in self.paths:
			if path in self.paths_names:
				name = self.paths_names[path]
			elif not self.uistate['show_full_page_name']:
				name = self._get_short_page_name(path)
			else:
				name = path
			button = gtk.Button(label = name, use_underline = False)
			button.set_tooltip_text(path)
			button.zim_path = path
			button.connect('clicked', self.on_bookmark_clicked)
			button.connect('button-release-event', self.do_bookmarks_popup_menu)
			button.show()
			self.container.add(button)

		# 'Disable' plus_button if max bookmarks is reached.
		if len(self.paths) >= MAX_BOOKMARKS:
			self.plus_button.change_state(False)
		else:
			self.plus_button.change_state(True)

		# Update config files.
		if self.save_flag:
			self.uistate['bookmarks'] = self.paths
			self.uistate['bookmarks_names'] = self.paths_names


class IconsButton(gtk.Button):
	'''
	Need a button which can change icons.
	Use this instead of set_sensitive to show 'disabled'/'enabled' state
	because of the need to get signal for popup menu.
	For using only with one icon look for the standard IconButton from widgets.py.
	'''

	def __init__(self, stock_enabled, stock_disabled, relief=True, size=gtk.ICON_SIZE_BUTTON):
		'''
		:param stock_enabled: the stock item for enabled state,
		:param stock_disabled: the stock item for disabled state,
		:param relief: when C{False} the button has no visible raised,
		edge and will be flat against the background,
		:param size: the icons size
		'''
		gtk.Button.__init__(self)
		self.stock_enabled = gtk.image_new_from_stock(stock_enabled, size)
		self.stock_disabled = gtk.image_new_from_stock(stock_disabled, size)
		self.add(self.stock_enabled)
		self._enabled_state = True

		self.set_alignment(0.5, 0.5)
		if not relief:
			self.set_relief(gtk.RELIEF_NONE)

	def change_state(self, active = 'default'):
		'''
		Change icon in the button.
		:param active: if True - 'enabled', False - 'disabled',
		if 'default' change state to another.
		'''
		if active == 'default':
			active = not self._enabled_state

		if active != self._enabled_state:
			self.remove(self.get_child())
			if active:
				self.add(self.stock_enabled)
			else:
				self.add(self.stock_disabled)
			self._enabled_state = not self._enabled_state
			self.show_all()

