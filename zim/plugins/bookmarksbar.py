
# Copyright 2015-2016 Pavel_M <plprgt@gmail.com>,
# released under the GNU GPL version 3.
# This plugin is for Zim program by Jaap Karssenberg <jaap.karssenberg@gmail.com>.
#
# This plugin uses an icon from Tango Desktop Project (http://tango.freedesktop.org/)
# (the Tango base icon theme is released to the Public Domain).



from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from zim.actions import toggle_action, action
from zim.plugins import PluginClass
from zim.notebook import Path
from zim.signals import ConnectorMixin, SignalHandler

from zim.gui.mainwindow import MainWindowExtension
from zim.gui.clipboard import Clipboard
from zim.gui.widgets import gtk_popup_at_pointer

from zim.plugins.pathbar import ScrolledHBox

import logging
logger = logging.getLogger('zim.plugins.bookmarksbar')

# Keyboard shortcut constants.
BM_TOGGLE_BAR_KEY = 'F4'
BM_ADD_BOOKMARK_KEY = '<alt>0'

class BookmarksBarPlugin(PluginClass):

	plugin_info = {
	'name': _('BookmarksBar'), # T: plugin name
	'description': _('''\
		This plugin provides bar for bookmarks.
		'''), # T: plugin description
	'author': 'Pavel_M',
	'help': 'Plugins:BookmarksBar', }

	plugin_preferences = (
		# key, type, label, default
		('max_bookmarks', 'int', _('Maximum number of bookmarks'), 15, (5, 20)), # T: plugin preference
		('save', 'bool', _('Save bookmarks'), True), # T: preferences option
		('add_bookmarks_to_beginning', 'bool', _('Add new bookmarks to the beginning of the bar'), False), # T: preferences option
	)

class BookmarksBarMainWindowExtension(MainWindowExtension):

	def __init__(self, plugin, window):
		MainWindowExtension.__init__(self, plugin, window)
		self.widget = BookmarkBar(window.notebook, window.navigation, self.uistate,
					  self.window.pageview.get_page)
		self.widget.connectto(window, 'page-changed', lambda o, p: self.widget.set_page(p))

		self.widget.show_all()

		# Add a new option to the Index popup menu.
		#try:
		#	self.widget.connectto(self.window.pageindex.treeview,
		#						  'populate-popup', self.on_populate_popup)
		#except AttributeError:
		#	logger.error('BookmarksBar: popup menu not initialized.')

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
		self.window.add_center_bar(self.widget)

	def on_populate_popup(self, treeview, menu):
		'''Add 'Add Bookmark' option to the Index popup menu.'''
		path = treeview.get_selected_path()
		if path:
			item = Gtk.SeparatorMenuItem()
			menu.prepend(item)
			item = Gtk.MenuItem.new_with_mnemonic(_('Add Bookmark')) # T: menu item bookmark plugin
			page = self.window.notebook.get_page(path)
			item.connect('activate', lambda o: self.widget.add_new_page(page))
			menu.prepend(item)
			menu.show_all()


	@action('', accelerator='<alt>1', menuhints='accelonly')
	def bookmark_1(self):
		self._open_bookmark(1)

	@action('', accelerator='<alt>2', menuhints='accelonly')
	def bookmark_2(self):
		self._open_bookmark(2)

	@action('', accelerator='<alt>3', menuhints='accelonly')
	def bookmark_3(self):
		self._open_bookmark(3)

	@action('', accelerator='<alt>4', menuhints='accelonly')
	def bookmark_4(self):
		self._open_bookmark(4)

	@action('', accelerator='<alt>5', menuhints='accelonly')
	def bookmark_5(self):
		self._open_bookmark(5)

	@action('', accelerator='<alt>6', menuhints='accelonly')
	def bookmark_6(self):
		self._open_bookmark(6)

	@action('', accelerator='<alt>7', menuhints='accelonly')
	def bookmark_7(self):
		self._open_bookmark(7)

	@action('', accelerator='<alt>8', menuhints='accelonly')
	def bookmark_8(self):
		self._open_bookmark(8)

	@action('', accelerator='<alt>9', menuhints='accelonly')
	def bookmark_9(self):
		self._open_bookmark(9)

	def _open_bookmark(self, number):
		number -= 1
		try:
			self.window.open_page(Path(self.widget.paths[number]))
		except IndexError:
			pass

	@toggle_action(_('Bookmarks'), accelerator=BM_TOGGLE_BAR_KEY, menuhints='view') # T: menu item bookmark plugin
	def toggle_show_bookmarks(self, active):
		'''
		Show/hide the bar with bookmarks.
		'''
		if active:
			self.show_widget()
		else:
			self.hide_widget()
		self.uistate['show_bar'] = active

	@action(_('Add Bookmark'), accelerator=BM_ADD_BOOKMARK_KEY, menuhints='page') # T: menu item bookmark plugin
	def add_bookmark(self):
		'''
		Function to add new bookmarks to the bar.
		Introduced to be used via keyboard shortcut.
		'''
		self.widget.add_new_page()


class BookmarkBar(Gtk.HBox, ConnectorMixin):

	def __init__(self, notebook, navigation, uistate, get_page_func):
		GObject.GObject.__init__(self)

		self.notebook = notebook
		self.navigation = navigation
		self.uistate = uistate
		self.save_flag = False # if True save bookmarks in config
		self.add_bookmarks_to_beginning = False # add new bookmarks to the end of the bar
		self.max_bookmarks = False # maximum number of bookmarks
		self._get_page = get_page_func # function to get current page

		# Create button to add new bookmarks.
		self.plus_button = IconsButton(Gtk.STOCK_ADD, Gtk.STOCK_REMOVE, relief = False)
		self.plus_button.set_tooltip_text(_('Add bookmark/Show settings')) # T: button label
		self.plus_button.connect('clicked', lambda o: self.add_new_page())
		self.plus_button.connect('button-release-event', self.do_plus_button_popup_menu)
		self.pack_start(self.plus_button, False, False, 0)

		# Create widget for bookmarks.
		self.scrolledbox = ScrolledHBox()
		self.pack_start(self.scrolledbox, True, True, 0)

		# Toggle between full/short page names.
		self.uistate.setdefault('show_full_page_name', False)

		# Save path to use later in Copy/Paste menu.
		self._saved_bookmark = None

		self.paths = [] # list of bookmarks as string objects
		self.uistate.setdefault('bookmarks', [])

		# Add pages from config to the bar.
		for path in self.uistate['bookmarks']:
			page = self.notebook.get_page(Path(path))
			if page.exists() and (page.name not in self.paths):
				self.paths.append(page.name)

		self.paths_names = {} # dict of changed names of bookmarks
		self.uistate.setdefault('bookmarks_names', {})
		# Function to transform random string to paths_names format.
		self._convert_path_name = lambda a: ' '.join(a[:25].split())

		# Add alternative bookmark names from config.
		for path, name in self.uistate['bookmarks_names'].items():
			if path in self.paths:
				try:
					name = self._convert_path_name(name)
					self.paths_names[path] = name
				except:
					logger.error('BookmarksBar: Error while loading path_names.')

		# Delete a bookmark if a page is deleted.
		self.connectto(self.notebook, 'deleted-page',
					   lambda obj, path: self.delete(path.name))

	def set_page(self, page):
		'''If a page is present as a bookmark than select it.'''
		pagename = page.name
		with self.on_bookmark_clicked.blocked():
			for button in self.scrolledbox.get_scrolled_children():
				if button.zim_path == pagename:
					button.set_active(True)
				else:
					button.set_active(False)

	def add_new_page(self, page = None):
		'''
		Add new page as bookmark to the bar.
		:param page: L{Page}, if None takes currently opened page,
		'''
		if not page:
			page = self._get_page()

		if page.exists():
			return self._add_new(page.name, self.add_bookmarks_to_beginning)

	def _add_new(self, path, add_bookmarks_to_beginning = False):
		'''Add bookmark to the bar.
		:param path: path as a string object
		:param add_bookmarks_to_beginning: bool,
		add new bookmarks to the beginning of the bar,
		'''
		if path in self.paths:
			logger.debug('BookmarksBar: path is already in the bar.')
			self.plus_button.blink()
			return False

		# Limit max number of bookmarks.
		if self.max_bookmarks and (len(self.paths) >= self.max_bookmarks):
			logger.debug('BookmarksBar: max number of bookmarks is achieved.')
			return False

		# Add a new bookmark to the end or to the beginning.
		if add_bookmarks_to_beginning:
			self.paths.insert(0, path)
		else:
			self.paths.append(path)

		self._reload_bar()

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
			menu = Gtk.Menu()
			item = Gtk.MenuItem.new_with_mnemonic(_('Do you want to delete all bookmarks?')) # T: message for bookmark plugin
			item.connect('activate', lambda o: _delete_all())
			menu.append(item)
			menu.show_all()
			gtk_popup_at_pointer(menu)
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
			name = self.paths_names.pop(old_path, None)
			if name:
				self.paths_names[new_path] = name

			self._reload_bar()
		else:
			self.plus_button.blink()

	def move_bookmark(self, first, second, direction):
		'''
		Move bookmark 'first' to the place near the bookmark 'second'.
		:param first, second: strings corresponding to Path.name.
		:param direction: move 'first' bookmark to the 'left' or 'right' of the 'second'.
		'''
		if (first == second) or (direction not in ('left', 'right')):
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
			menu = Gtk.Menu()
			item = Gtk.CheckMenuItem(_('Show full Page Name')) # T: menu item for context menu
			item.set_active(self.uistate['show_full_page_name'])
			item.connect('activate', lambda o: self.toggle_show_full_page_name())
			menu.append(item)
			menu.show_all()
			gtk_popup_at_pointer(menu)
			return True

	def do_bookmarks_popup_menu(self, button, event):
		'''Handler for button-release-event, triggers popup menu for bookmarks.'''
		if event.button != 3:
			return False

		path = button.zim_path

		_button_width = button.size_request().width
		direction = 'left' if (int(event.x) <= _button_width / 2) else 'right'

		def set_save_bookmark(path):
			self._saved_bookmark = path

		if button.get_label() in (path, self._get_short_page_name(path)):
			rename_button_text = _('Set New Name') # T: button label
		else:
			rename_button_text = _('Back to Original Name') # T: button label

		# main popup menu
		main_menu = Gtk.Menu()
		main_menu_items = (
					(_('Remove'), lambda o: self.delete(path)),			# T: menu item
				    (_('Remove All'), lambda o: self.delete_all(True)),	# T: menu item
				    ('separator', ''),
				    (_('Copy'), lambda o: set_save_bookmark(path)), # T: menu item
				    (_('Paste'), lambda o: self.move_bookmark(self._saved_bookmark, path, direction)), # T: menu item
				    ('separator', ''),
				    (_('Open in New Window'), lambda o: self.navigation.open_page(Path(path), new_window=True)), # T: menu item
				    ('separator', ''),
				    (rename_button_text, lambda o: self.rename_bookmark(button)),
				    (_('Set to Current Page'), lambda o: self.change_bookmark(path))) # T: menu item

		for name, func in main_menu_items:
			if name == 'separator':
				item = Gtk.SeparatorMenuItem()
			else:
				item = Gtk.MenuItem.new_with_mnemonic(name)
				item.connect('activate', func)
			main_menu.append(item)

		main_menu.show_all()
		gtk_popup_at_pointer(main_menu)
		return True

	@SignalHandler
	def on_bookmark_clicked(self, button):
		'''Open page if a bookmark is clicked.'''
		self.navigation.open_page(Path(button.zim_path))

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

		if self.max_bookmarks != preferences['max_bookmarks']:
			self.max_bookmarks = preferences['max_bookmarks']
			self._reload_bar() # to update plus_button

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
		for button in self.scrolledbox.get_scrolled_children():
			self.scrolledbox.remove(button)

		page = self._get_page()
		if page:
			pagename = page.name
		else:
			pagename = None

		for path in self.paths:
			if path in self.paths_names:
				name = self.paths_names[path]
			elif not self.uistate['show_full_page_name']:
				name = self._get_short_page_name(path)
			else:
				name = path
			button = Gtk.ToggleButton(label=name, use_underline=False)
			button.set_tooltip_text(path)
			button.get_child().set_ellipsize(Pango.EllipsizeMode.MIDDLE)
			button.zim_path = path
			if path == pagename:
				button.set_active(True)

			button.connect('clicked', self.on_bookmark_clicked)
			button.connect('button-release-event', self.do_bookmarks_popup_menu)
			button.show()
			self.scrolledbox.add(button)

		# 'Disable' plus_button if max bookmarks is reached.
		if self.max_bookmarks and (len(self.paths) >= self.max_bookmarks):
			self.plus_button.change_state(False)
		else:
			self.plus_button.change_state(True)

		# Update config files.
		if self.save_flag:
			self.uistate['bookmarks'] = self.paths
			self.uistate['bookmarks_names'] = self.paths_names


class IconsButton(Gtk.Button):
	'''
	Need a button which can change icons.
	Use this instead of set_sensitive to show 'disabled'/'enabled' state
	because of the need to get signal for popup menu.
	For using only with one icon look for the standard IconButton from widgets.py.
	'''

	def __init__(self, stock_enabled, stock_disabled, relief=True, size=Gtk.IconSize.BUTTON):
		'''
		:param stock_enabled: the stock item for enabled state,
		:param stock_disabled: the stock item for disabled state,
		:param relief: when C{False} the button has no visible raised,
		edge and will be flat against the background,
		:param size: the icons size
		'''
		GObject.GObject.__init__(self)
		self.stock_enabled = Gtk.Image.new_from_stock(stock_enabled, size)
		self.stock_disabled = Gtk.Image.new_from_stock(stock_disabled, size)
		self.add(self.stock_enabled)
		self._enabled_state = True

		self.set_alignment(0.5, 0.5)
		if not relief:
			self.set_relief(Gtk.ReliefStyle.NONE)

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

	def blink(self):
		'''Quickly change an icon to show
		that bookmark can't be added/changed.'''

		def change_icon():
			'''Function to be called only once.'''
			self.change_state()
			return False
		self.change_state()
		GObject.timeout_add(300, change_icon)
