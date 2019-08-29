
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import os
import logging
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk

logger = logging.getLogger('zim.gui')


from zim.config import data_file, value_is_coord, ConfigDict, Boolean, ConfigManager
from zim.signals import DelayedCallback

from zim.notebook import Path, Page, LINK_DIR_BACKWARD
from zim.notebook.index import IndexNotFoundError
from zim.history import History, HistoryPath

from zim.actions import action, toggle_action, radio_action, radio_option, get_gtk_actiongroup, \
	PRIMARY_MODIFIER_STRING, PRIMARY_MODIFIER_MASK
from zim.gui.widgets import \
	MenuButton, \
	Window, Dialog, \
	ErrorDialog, FileDialog, ProgressDialog, MessageDialog, \
	ScrolledTextView, \
	gtk_popup_at_pointer

from zim.gui.navigation import NavigationModel
from zim.gui.uiactions import UIActions
from zim.gui.customtools import CustomToolManagerUI
from zim.gui.insertedobjects import InsertedObjectUI

from zim.gui.pageview import PageView

from zim.plugins import ExtensionBase, extendable
from zim.gui.actionextension import ActionExtensionBase


TOOLBAR_ICONS_AND_TEXT = 'icons_and_text'
TOOLBAR_ICONS_ONLY = 'icons_only'
TOOLBAR_TEXT_ONLY = 'text_only'

TOOLBAR_ICONS_LARGE = 'large'
TOOLBAR_ICONS_SMALL = 'small'
TOOLBAR_ICONS_TINY = 'tiny'

MENU_ACTIONS = (
	('file_menu', None, _('_File')), # T: Menu title
	('edit_menu', None, _('_Edit')), # T: Menu title
	('view_menu', None, _('_View')), # T: Menu title
	('insert_menu', None, _('_Insert')), # T: Menu title
	('search_menu', None, _('_Search')), # T: Menu title
	('format_menu', None, _('For_mat')), # T: Menu title
	('tools_menu', None, _('_Tools')), # T: Menu title
	('go_menu', None, _('_Go')), # T: Menu title
	('help_menu', None, _('_Help')), # T: Menu title
	('toolbar_menu', None, _('_Toolbar')), # T: Menu title
	('checkbox_menu', None, _('_Checkbox')), # T: Menu title
)

#: Preferences for the user interface
ui_preferences = (
	# key, type, category, label, default
	('toggle_on_ctrlspace', 'bool', 'Interface', _('Use %s to switch to the side pane') % (PRIMARY_MODIFIER_STRING + '<Space>'), False),
		# T: Option in the preferences dialog - %s will map to either <Control><Space> or <Command><Space> key binding
		# default value is False because this is mapped to switch between
		# char sets in certain international key mappings
	('remove_links_on_delete', 'bool', 'Interface', _('Remove links when deleting pages'), True),
		# T: Option in the preferences dialog
	('always_use_last_cursor_pos', 'bool', 'Interface', _('Always use last cursor position when opening a page'), True),
		# T: Option in the preferences dialog
)


def schedule_on_idle(function, args=()):
	'''Helper function to schedule stuff that can be done later, it will
	be triggered on the gtk "idle" signal.

	@param function: function to call
	@param args: positional arguments
	'''
	def callback():
		function(*args)
		return False # delete signal
	GObject.idle_add(callback)


class MainWindowExtension(ActionExtensionBase):
	'''Base class for extending the L{MainWindow}

	Menu and toolbar actions can be defined by defining an action method
	and specifying where in the menu this should be placed.

	An action method is any object method of the extension method that
	is decorated by the L{action()} or L{toggle_action()} decorators
	(see L{zim.actions}). Such a method is called when the user clicks
	to correcponding menu item or presses the corresponding key binding.
	The decorator is used to define the text to display in the menu
	and the key binding.

	@ivar window: the L{MainWindow}

	@ivar uistate: a L{ConfigDict} to store the extensions ui state or

	The "uistate" is the per notebook state of the interface, it is
	intended for stuff like the last folder opened by the user or the
	size of a dialog after resizing. It is stored in the X{state.conf}
	file in the notebook cache folder. It differs from the preferences,
	which are stored globally and dictate the behavior of the application.
	(To access the preference use C{plugin.preferences}.)
	'''

	def __init__(self, plugin, window):
		'''Constructor
		@param plugin: the plugin object to which this extension belongs
		@param window: the C{Gtk.Window} being extended
		'''
		ExtensionBase.__init__(self, plugin, window)
		self.window = window
		self.uistate = window.notebook.state[plugin.config_key]
		self._add_actions(window.uimanager)
		self.connectto(window, 'destroy')

	def on_destroy(self, window):
		self.destroy()


@extendable(MainWindowExtension)
class MainWindow(Window):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'init-uistate': (GObject.SignalFlags.RUN_LAST, None, ()),
		'page-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'readonly-changed': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
		'close': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	def __init__(self, notebook, page=None, fullscreen=False, geometry=None):
		'''Constructor
		@param notebook: the L{Notebook} to show in this window
		@param page: a C{Path} object to open
		@param fullscreen: if C{True} the window is shown fullscreen,
		if C{None} the previous state is restored
		@param geometry: the window geometry as string in format
		"C{WxH+X+Y}", if C{None} the previous state is restored
		'''
		Window.__init__(self)
		self.notebook = notebook
		self.page = None # will be set later by open_page
		self.navigation = NavigationModel(self)
		self.hideonclose = False

		self.preferences = ConfigManager.preferences['GtkInterface']
		self.preferences.define(
			toggle_on_ctrlspace=Boolean(False),
			remove_links_on_delete=Boolean(True),
			always_use_last_cursor_pos=Boolean(True),
		)
		self.preferences.connect('changed', self.do_preferences_changed)

		self.maximized = False
		self.isfullscreen = False
		self.connect_after('window-state-event', self.__class__.on_window_state_event)

		# Hidden setting to force the gtk bell off. Otherwise it
		# can bell every time you reach the begin or end of the text
		# buffer. Especially specific gtk version on windows.
		# See bug lp:546920
		self.preferences.setdefault('gtk_bell', False)
		if not self.preferences['gtk_bell']:
			Gtk.rc_parse_string('gtk-error-bell = 0')

		self._block_toggle_panes = False
		self._sidepane_autoclose = False
		self._switch_focus_accelgroup = None

		# Catching this signal prevents the window to actually be destroyed
		# when the user tries to close it. The action for close should either
		# hide or destroy the window.
		def do_delete_event(*a):
			logger.debug('Action: close (delete-event)')
			self.close()
			return True # Do not destroy - let close() handle it
		self.connect('delete-event', do_delete_event)

		# setup uistate
		self.uistate = notebook.state['MainWindow']
		self.uistate.setdefault('windowpos', None, check=value_is_coord)
		self.uistate.setdefault('windowsize', (600, 450), check=value_is_coord)
		self.uistate.setdefault('windowmaximized', False)
		self.uistate.setdefault('active_tabs', None, tuple)
		self.uistate.setdefault('show_toolbar', True)
		self.uistate.setdefault('show_statusbar', True)
		self.uistate.setdefault('readonly', False)

		self.history = History(notebook, notebook.state)

		# init uimanager
		self.uimanager = Gtk.UIManager()
		self.uimanager.add_ui_from_string('''
		<ui>
			<menubar name="menubar">
			</menubar>
			<toolbar name="toolbar">
			</toolbar>
		</ui>
		''')

		# setup menubar and toolbar
		self.add_accel_group(self.uimanager.get_accel_group())
		self.menubar = self.uimanager.get_widget('/menubar')
		self.toolbar = self.uimanager.get_widget('/toolbar')
		self.toolbar.connect('popup-context-menu', self.do_toolbar_popup)
		self.add_bar(self.menubar)
		self.add_bar(self.toolbar)

		self.pageview = PageView(self.notebook, self.navigation)
		self.connect_object('readonly-changed', PageView.set_readonly, self.pageview)
		self.pageview.connect_after(
			'textstyle-changed', self.on_textview_textstyle_changed)
		self.pageview.textview.connect_after(
			'toggle-overwrite', self.on_textview_toggle_overwrite)
		self.pageview.textview.connect('link-enter', self.on_link_enter)
		self.pageview.textview.connect('link-leave', self.on_link_leave)

		self.add(self.pageview)

		# create statusbar
		self.statusbar = Gtk.Statusbar()
		self.statusbar.push(0, '<page>')
		self.add_bar(self.statusbar, start=False)
		self.statusbar.set_property('margin', 0)
		self.statusbar.set_property('spacing', 0)

		def statusbar_element(string, size):
			frame = Gtk.Frame()
			frame.set_shadow_type(Gtk.ShadowType.NONE)
			self.statusbar.pack_end(frame, False, True, 0)
			label = Gtk.Label(label=string)
			label.set_size_request(size, 10)
			label.set_alignment(0.1, 0.5)
			frame.add(label)
			return label

		# specify statusbar elements right-to-left
		self.statusbar_insert_label = statusbar_element('INS', 60)
		self.statusbar_style_label = statusbar_element('<style>', 100)

		# and build the widget for backlinks
		self.statusbar_backlinks_button = \
			BackLinksMenuButton(self.notebook, self.open_page, status_bar_style=True)
		frame = Gtk.Frame()
		frame.set_shadow_type(Gtk.ShadowType.NONE)
		self.statusbar.pack_end(Gtk.Separator(), False, True, 0)
		self.statusbar.pack_end(frame, False, True, 0)
		self.statusbar.pack_end(Gtk.Separator(), False, True, 0)
		frame.add(self.statusbar_backlinks_button)

		self.move_bottom_minimized_tabs_to_statusbar(self.statusbar)

		self.do_preferences_changed()

		self._geometry_set = False
		self._set_fullscreen = False
		if geometry:
			try:
				self.parse_geometry(geometry)
				self._geometry_set = True
			except:
				logger.exception('Parsing geometry string failed:')
		elif fullscreen:
			self._set_fullscreen = True

		# Init mouse settings
		self.preferences.setdefault('mouse_nav_button_back', 8)
		self.preferences.setdefault('mouse_nav_button_forw', 9)

		# Finish uimanager
		self._uiactions = UIActions(self, self.notebook, self.page, self.navigation)
		group = get_gtk_actiongroup(self._uiactions)
		self.uimanager.insert_action_group(group, 0)

		group = get_gtk_actiongroup(self.pageview)
		self.uimanager.insert_action_group(group, 0)

		group = get_gtk_actiongroup(self)
		group.add_actions(MENU_ACTIONS)
		self.uimanager.insert_action_group(group, 0)

		group.get_action('open_page_back').set_sensitive(False)
		group.get_action('open_page_forward').set_sensitive(False)

		fname = 'menubar.xml'
		self.uimanager.add_ui_from_string(data_file(fname).read())
		self.pageview.emit('ui-init') # Needs to trigger after default menus are build

		# Do this last, else menu items show up in wrong place
		self._customtools = CustomToolManagerUI(self.uimanager, self.pageview)
		self._insertedobjects = InsertedObjectUI(self.uimanager, self.pageview)
			# XXX: would like to do this in PageView itself, but need access to uimanager

		# Setup notebook signals
		notebook.connect('page-info-changed', self.do_page_info_changed)

		def move_away(o, path):
			# Try several options to get awaay
			actions = [self.open_page_back, self.open_page_parent, self.open_page_home]
			while (path == self.page or self.page.ischild(path)) and actions:
				action = actions.pop(0)
				action()

		notebook.connect('deleted-page', move_away) # after action

		def follow(o, path, newpath):
			if path == self.page:
				self.open_page(newpath)
			elif self.page.ischild(path):
				newpath = newpath + self.page.relname(path)
				self.open_page(newpath)
			else:
				pass

		notebook.connect('moved-page', follow) # after action

		# init page
		page = page or self.history.get_current()
		if page:
			page = notebook.get_page(page)
			self.open_page(page)
		else:
			self.open_page_home()

		self.pageview.grab_focus()

	@action(_('_Close'), '<Primary>W') # T: Menu item
	def close(self):
		'''Menu action for close. Will hide when L{hideonclose} is set,
		otherwise destroys window, which could result in the application
		closing if there are no other toplevel windows.
		'''
		if self.hideonclose: # XXX
			self.save_uistate()
			self.hide()
			self.emit('close')
		else:
			self.destroy()

	def destroy(self):
		self.pageview.save_changes()
		if self.page.modified:
			return # Do not quit if page not saved
		self.pageview.page.set_ui_object(None) # XXX

		self.save_uistate()

		self.hide() # look more responsive
		self.notebook.index.stop_background_check()
		while Gtk.events_pending():
			Gtk.main_iteration_do(False)

		Window.destroy(self) # gtk destroy & will also emit destroy signal

	def do_update_statusbar(self, *a):
		page = self.pageview.get_page()
		if not page:
			return
		label = page.name
		if page.modified:
			label += '*'
		if self.notebook.readonly or page.readonly:
			label += ' [' + _('readonly') + ']' # T: page status in statusbar
		self.statusbar.pop(0)
		self.statusbar.push(0, label)

	def on_window_state_event(self, event):
		if bool(event.changed_mask & Gdk.WindowState.MAXIMIZED):
			self.maximized = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)

		if bool(event.changed_mask & Gdk.WindowState.FULLSCREEN):
			self.isfullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
			self.__class__.toggle_fullscreen.set_toggleaction_state(self, self.isfullscreen)

		if bool(event.changed_mask & Gdk.WindowState.MAXIMIZED) \
			or bool(event.changed_mask & Gdk.WindowState.FULLSCREEN):
				schedule_on_idle(lambda: self.pageview.scroll_cursor_on_screen())

	def do_preferences_changed(self, *a):
		if self._switch_focus_accelgroup:
			self.remove_accel_group(self._switch_focus_accelgroup)

		space = Gdk.unicode_to_keyval(ord(' '))
		group = Gtk.AccelGroup()

		self.preferences.setdefault('toggle_on_altspace', False)
		if self.preferences['toggle_on_altspace']:
			# Hidden param, disabled because it causes problems with
			# several international layouts (space mistaken for alt-space,
			# see bug lp:620315)
			group.connect_group( # <Alt><Space>
				space, Gdk.ModifierType.MOD1_MASK, Gtk.AccelFlags.VISIBLE,
				self.toggle_sidepane_focus)

		# Toggled by preference menu, also causes issues with international
		# layouts - esp. when switching input method on Meta-Space
		if self.preferences['toggle_on_ctrlspace']:
			group.connect( # <Primary><Space>
				space, PRIMARY_MODIFIER_MASK, Gtk.AccelFlags.VISIBLE,
				self.toggle_sidepane_focus)

		self.add_accel_group(group)
		self._switch_focus_accelgroup = group

	@toggle_action(_('Menubar'), init=True) # T: label for View->Menubar menu item
	def toggle_menubar(self, show):
		'''Menu action to toggle the visibility of the menu bar
		@param show: when C{True} or C{False} force the visibility,
		when C{None} toggle based on current state
		'''
		if show:
			self.menubar.set_no_show_all(False)
			self.menubar.show()
		else:
			self.menubar.hide()
			self.menubar.set_no_show_all(True)

	@toggle_action(_('_Toolbar'), init=True) # T: Menu item
	def toggle_toolbar(self, show):
		'''Menu action to toggle the visibility of the tool bar'''
		if show:
			self.toolbar.set_no_show_all(False)
			self.toolbar.show()
		else:
			self.toolbar.hide()
			self.toolbar.set_no_show_all(True)

		self.uistate['show_toolbar'] = show

	def do_toolbar_popup(self, toolbar, x, y, button):
		'''Show the context menu for the toolbar'''
		menu = self.uimanager.get_widget('/toolbar_popup')
		gtk_popup_at_pointer(menu)

	@toggle_action(_('_Statusbar'), init=True) # T: Menu item
	def toggle_statusbar(self, show):
		'''Menu action to toggle the visibility of the status bar'''
		if show:
			self.statusbar.set_no_show_all(False)
			self.statusbar.show()
		else:
			self.statusbar.hide()
			self.statusbar.set_no_show_all(True)

		self.uistate['show_statusbar'] = show

	@toggle_action(_('_Fullscreen'), 'F11', icon='gtk-fullscreen', init=False) # T: Menu item
	def toggle_fullscreen(self, show):
		'''Menu action to toggle the fullscreen state of the window'''
		if show:
			self.fullscreen()
		else:
			self.unfullscreen()

	def do_pane_state_changed(self, pane, *a):
		if not hasattr(self, 'actiongroup') \
		or self._block_toggle_panes:
			return

		action = self.actiongroup.get_action('toggle_panes')
		visible = bool(self.get_visible_panes())
		if visible != action.get_active():
			action.set_active(visible)

	@toggle_action(_('_Side Panes'), 'F9', icon='gtk-index', init=True) # T: Menu item
	def toggle_panes(self, show):
		'''Menu action to toggle the visibility of the all panes
		@param show: when C{True} or C{False} force the visibility,
		when C{None} toggle based on current state
		'''
		self._block_toggle_panes = True
		Window.toggle_panes(self, show)
		self._block_toggle_panes = False

		if show:
			self.focus_sidepane()
		else:
			self.pageview.grab_focus()

		self._sidepane_autoclose = False
		self.save_uistate()

	def do_set_focus(self, widget):
		Window.do_set_focus(self, widget)
		if widget == self.pageview.textview \
		and self._sidepane_autoclose:
			# Sidepane open and should close automatically
			self.toggle_panes(False)

	def toggle_sidepane_focus(self, *a):
		'''Switch focus between the textview and the page index.
		Automatically opens the sidepane if it is closed
		(but sets a property to automatically close it again).
		This method is used for the (optional) <Primary><Space> keybinding.
		'''
		action = self.actiongroup.get_action('toggle_panes')
		if action.get_active():
			# side pane open
			if self.pageview.textview.is_focus():
				self.focus_sidepane()
			else:
				if self._sidepane_autoclose:
					self.toggle_panes(False)
				else:
					self.pageview.grab_focus()
		else:
			# open the pane
			self.toggle_panes(True)
			self._sidepane_autoclose = True

		return True # stop

	@radio_action(
		None,
		radio_option(TOOLBAR_ICONS_AND_TEXT, _('Icons _And Text')), # T: Menu item
		radio_option(TOOLBAR_ICONS_ONLY, _('_Icons Only')), # T: Menu item
		radio_option(TOOLBAR_TEXT_ONLY, _('_Text Only')), # T: Menu item
	)
	def set_toolbar_style(self, style):
		'''Set the toolbar style
		@param style: can be either:
			- C{TOOLBAR_ICONS_AND_TEXT}
			- C{TOOLBAR_ICONS_ONLY}
			- C{TOOLBAR_TEXT_ONLY}
		'''
		if style == TOOLBAR_ICONS_AND_TEXT:
			self.toolbar.set_style(Gtk.ToolbarStyle.BOTH)
		elif style == TOOLBAR_ICONS_ONLY:
			self.toolbar.set_style(Gtk.ToolbarStyle.ICONS)
		elif style == TOOLBAR_TEXT_ONLY:
			self.toolbar.set_style(Gtk.ToolbarStyle.TEXT)
		else:
			assert False, 'BUG: Unkown toolbar style: %s' % style

		self.preferences['toolbar_style'] = style

	@radio_action(
		None,
		radio_option(TOOLBAR_ICONS_LARGE, _('_Large Icons')), # T: Menu item
		radio_option(TOOLBAR_ICONS_SMALL, _('_Small Icons')), # T: Menu item
		radio_option(TOOLBAR_ICONS_TINY, _('_Tiny Icons')), # T: Menu item
	)
	def set_toolbar_icon_size(self, size):
		'''Set the toolbar style
		@param size: can be either:
			- C{TOOLBAR_ICONS_LARGE}
			- C{TOOLBAR_ICONS_SMALL}
			- C{TOOLBAR_ICONS_TINY}
		'''
		if size == TOOLBAR_ICONS_LARGE:
			self.toolbar.set_icon_size(Gtk.IconSize.LARGE_TOOLBAR)
		elif size == TOOLBAR_ICONS_SMALL:
			self.toolbar.set_icon_size(Gtk.IconSize.SMALL_TOOLBAR)
		elif size == TOOLBAR_ICONS_TINY:
			self.toolbar.set_icon_size(Gtk.IconSize.MENU)
		else:
			assert False, 'BUG: Unkown toolbar size: %s' % size

		self.preferences['toolbar_size'] = size

	@toggle_action(_('Notebook _Editable'), icon='gtk-edit', init=True) # T: menu item
	def toggle_editable(self, editable):
		'''Menu action to toggle the read-only state of the application
		@emits: readonly-changed
		'''
		readonly = not editable
		if readonly and self.page and self.page.modified:
			# Save any modification now - will not be allowed after switch
			self.pageview.save_changes()

		for group in self.uimanager.get_action_groups():
			for action in group.list_actions():
				if hasattr(action, 'zim_readonly') \
				and not action.zim_readonly:
					action.set_sensitive(not readonly)

		self.uistate['readonly'] = readonly
		self.emit('readonly-changed', readonly)

	def init_uistate(self):
		# Initialize all the uistate parameters
		# delayed till show or show_all because all this needs real
		# uistate to be in place and plugins to be loaded
		# Run between loading plugins and actually presenting the window to the user

		if not self._geometry_set:
			# Ignore this if an explicit geometry was specified to the constructor
			if self.uistate['windowpos'] is not None:
				x, y = self.uistate['windowpos']
				self.move(x, y)

			w, h = self.uistate['windowsize']
			self.set_default_size(w, h)

			if self.uistate['windowmaximized']:
				self.maximize()

		# For these two "None" means system default, but we don't know what that default is :(
		self.preferences.setdefault('toolbar_style', None,
			(TOOLBAR_ICONS_ONLY, TOOLBAR_ICONS_AND_TEXT, TOOLBAR_TEXT_ONLY))
		self.preferences.setdefault('toolbar_size', None,
			(TOOLBAR_ICONS_TINY, TOOLBAR_ICONS_SMALL, TOOLBAR_ICONS_LARGE))

		self.toggle_toolbar(self.uistate['show_toolbar'])
		self.toggle_statusbar(self.uistate['show_statusbar'])

		Window.init_uistate(self) # takes care of sidepane positions etc

		if self.preferences['toolbar_style'] is not None:
			self.set_toolbar_style(self.preferences['toolbar_style'])

		if self.preferences['toolbar_size'] is not None:
			self.set_toolbar_icon_size(self.preferences['toolbar_size'])

		self.toggle_fullscreen(self._set_fullscreen)

		if self.notebook.readonly:
			self.toggle_editable(False)
			action = self.actiongroup.get_action('toggle_editable')
			action.set_sensitive(False)
		else:
			self.toggle_editable(not self.uistate['readonly'])

		# And hook to notebook properties
		self.on_notebook_properties_changed(self.notebook.properties)
		self.notebook.properties.connect('changed', self.on_notebook_properties_changed)

		# Hook up the statusbar
		self.connect('page-changed', self.do_update_statusbar)
		self.connect('readonly-changed', self.do_update_statusbar)
		self.pageview.connect('modified-changed', self.do_update_statusbar)
		self.notebook.connect_after('stored-page', self.do_update_statusbar)

		# Notify plugins
		self.emit('init-uistate')

		# Update menus etc.
		self.uimanager.ensure_update()
			# Prevent flashing when the toolbar is loaded after showing the window
			# and do this before connecting signal below for accelmap.

		# Add search bar onec toolbar is loaded
		space = Gtk.SeparatorToolItem()
		space.set_draw(False)
		space.set_expand(True)
		self.toolbar.insert(space, -1)

		from zim.gui.widgets import InputEntry
		entry = InputEntry(placeholder_text=_('Search'))
		entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
		entry.set_icon_activatable(Gtk.EntryIconPosition.SECONDARY, True)
		entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Search Pages...'))
			# T: label in search entry
		inline_search = lambda e, *a: self._uiactions.show_search(query=e.get_text() or None)
		entry.connect('activate', inline_search)
		entry.connect('icon-release', inline_search)
		entry.show()
		item = Gtk.ToolItem()
		item.add(entry)
		self.toolbar.insert(item, -1)

		# Load accelmap config and setup saving it
		# TODO - this probably belongs in the application class, not here
		accelmap = ConfigManager.get_config_file('accelmap').file
		logger.debug('Accelmap: %s', accelmap.path)
		if accelmap.exists():
			Gtk.AccelMap.load(accelmap.path)

		def on_accel_map_changed(o, path, key, mod):
			logger.info('Accelerator changed for %s', path)
			Gtk.AccelMap.save(accelmap.path)

		Gtk.AccelMap.get().connect('changed', on_accel_map_changed)

		self.do_update_statusbar()

	def save_uistate(self):
		if self.is_visible() and not self.isfullscreen:
			self.uistate['windowpos'] = tuple(self.get_position())
			self.uistate['windowsize'] = tuple(self.get_size())
			self.uistate['windowmaximized'] = self.maximized

		Window.save_uistate(self) # takes care of sidepane positions etc.

		if self.notebook.state.modified:
			self.notebook.state.write()

	def on_notebook_properties_changed(self, properties):
		self.set_title(self.notebook.name + ' - Zim')
		if self.notebook.icon:
			try:
				self.set_icon_from_file(self.notebook.icon)
			except GObject.GError:
				logger.exception('Could not load icon %s', self.notebook.icon)

	def on_textview_toggle_overwrite(self, view):
		state = view.get_overwrite()
		if state:
			text = 'OVR'
		else:
			text = 'INS'
		self.statusbar_insert_label.set_text(text)

	def on_textview_textstyle_changed(self, view, style):
		label = style.title() if style else 'None'
		self.statusbar_style_label.set_text(label)

	def on_link_enter(self, view, link):
		self.statusbar.push(1, 'Go to "%s"' % link['href'])

	def on_link_leave(self, view, link):
		self.statusbar.pop(1)

	def do_button_press_event(self, event):
		## Try to capture buttons for navigation
		if event.button > 3:
			if event.button == self.preferences['mouse_nav_button_back']:
				self.open_page_back()
			elif event.button == self.preferences['mouse_nav_button_forw']:
				self.open_page_forward()
			else:
				logger.debug("Unused mouse button %i", event.button)
		#~ return Window.do_button_press_event(self, event)

	def open_page(self, path):
		'''Method to open a page in the mainwindow, and menu action for
		the "jump to" menu item.

		Fails silently when saving current page failed (which is usually the
		result of pressing "cancel" in the error dialog shown when saving
		fails). Check return value for success if you want to be sure.

		@param path: a L{path} for the page to open.
		@raises PageNotFound: if C{path} can not be opened
		@emits: page-changed
		@returns: C{True} for success
		'''
		assert isinstance(path, Path)
		if isinstance(path, Page) and path.valid:
			page = path
		else:
			page = self.notebook.get_page(path) # can raise

		if self.page and id(self.page) == id(page):
			# XXX: Check ID to enable reload_page but catch all other
			# redundant calls.
			return
		elif self.page:
			self.pageview.save_changes() # XXX - should connect to signal instead of call here
			self.notebook.wait_for_store_page_async() # XXX - should not be needed - hide in notebook/page class - how?
			if self.page.modified:
				return False # Assume SavePageErrorDialog was shown and cancelled

			old_cursor = self.pageview.get_cursor_pos()
			old_scroll = self.pageview.get_scroll_pos()
			self.history.set_state(self.page, old_cursor, old_scroll)

			self.save_uistate()

		logger.info('Open page: %s (%s)', page, path)
		self.page = page
		self._uiactions.page = page

		self.notebook.index.touch_current_page_placeholder(path)

		paths = [page] + list(page.parents())
		self.notebook.index.check_async(self.notebook, paths, recursive=False)

		if isinstance(path, HistoryPath):
			self.history.set_current(path)
			cursor = path.cursor # can still be None
		else:
			self.history.append(page)
			cursor = None

		if cursor is None and self.preferences['always_use_last_cursor_pos']:
			cursor, _ = self.history.get_state(page)

		self.pageview.set_page(page, cursor)

		self.emit('page-changed', page)

		self.pageview.grab_focus()

	def do_page_changed(self, page):
		#TODO: set toggle_editable() insensitive when page is readonly
		self.update_buttons_history()
		self.update_buttons_hierarchy()
		self.statusbar_backlinks_button.set_page(self.page)

	def do_page_info_changed(self, notebook, page):
		if page == self.page:
			self.update_buttons_hierarchy()

	def update_buttons_history(self):
		historyrecord = self.history.get_current()

		back = self.actiongroup.get_action('open_page_back')
		back.set_sensitive(not historyrecord.is_first)

		forward = self.actiongroup.get_action('open_page_forward')
		forward.set_sensitive(not historyrecord.is_last)

	def update_buttons_hierarchy(self):
		parent = self.actiongroup.get_action('open_page_parent')
		child = self.actiongroup.get_action('open_page_child')
		parent.set_sensitive(len(self.page.namespace) > 0)
		child.set_sensitive(self.page.haschildren)

		previous = self.actiongroup.get_action('open_page_previous')
		next = self.actiongroup.get_action('open_page_next')
		has_prev, has_next = self.notebook.pages.get_has_previous_has_next(self.page)
		previous.set_sensitive(has_prev)
		next.set_sensitive(has_next)

	@action(_('_Jump To...'), '<Primary>J') # T: Menu item
	def show_jump_to(self):
		return OpenPageDialog(self, self.page, self.open_page).run()

	@action(
		_('_Back'), verb_icon='gtk-go-back', # T: Menu item
		accelerator='<alt>Left', alt_accelerator='XF86Back'
	)
	def open_page_back(self):
		'''Menu action to open the previous page from the history
		@returns: C{True} if successfull
		'''
		record = self.history.get_previous()
		if not record is None:
			self.open_page(record)

	@action(
		_('_Forward'), verb_icon='gtk-go-forward', # T: Menu item
		accelerator='<alt>Right', alt_accelerator='XF86Forward'
	)
	def open_page_forward(self):
		'''Menu action to open the next page from the history
		@returns: C{True} if successfull
		'''
		record = self.history.get_next()
		if not record is None:
			self.open_page(record)

	@action(_('_Parent'), '<alt>Up') # T: Menu item
	def open_page_parent(self):
		'''Menu action to open the parent page
		@returns: C{True} if successful
		'''
		namespace = self.page.namespace
		if namespace:
			self.open_page(Path(namespace))

	@action(_('_Child'), '<alt>Down') # T: Menu item
	def open_page_child(self):
		'''Menu action to open a child page. Either takes the last child
		from the history, or the first child.
		@returns: C{True} if successfull
		'''
		path = self.notebook.pages.lookup_by_pagename(self.page)
			# Force refresh "haschildren" ...
		if path.haschildren:
			record = self.history.get_child(path)
			if not record is None:
				self.open_page(record)
			else:
				child = self.notebook.pages.get_next(path)
				self.open_page(child)

	@action(_('_Previous in index'), accelerator='<alt>Page_Up') # T: Menu item
	def open_page_previous(self):
		'''Menu action to open the previous page from the index
		@returns: C{True} if successfull
		'''
		path = self.notebook.pages.get_previous(self.page)
		if not path is None:
			self.open_page(path)

	@action(_('_Next in index'), accelerator='<alt>Page_Down') # T: Menu item
	def open_page_next(self):
		'''Menu action to open the next page from the index
		@returns: C{True} if successfull
		'''
		path = self.notebook.pages.get_next(self.page)
		if not path is None:
			self.open_page(path)

	@action(_('_Home'), '<alt>Home', icon='gtk-home') # T: Menu item
	def open_page_home(self):
		'''Menu action to open the home page'''
		self.open_page(self.notebook.get_home_page())

	@action(_('_Reload'), '<Primary>R') # T: Menu item
	def reload_page(self):
		'''Menu action to reload the current page. Will first try
		to save any unsaved changes, then reload the page from disk.
		'''
		# TODO: this is depending on behavior of open_page(), should be more robust
		pos = self.pageview.get_cursor_pos()
		self.pageview.save_changes() # XXX
		self.notebook.flush_page_cache(self.page)
		if self.open_page(self.notebook.get_page(self.page)):
			self.pageview.set_cursor_pos(pos)


class BackLinksMenuButton(MenuButton):

	def __init__(self, notebook, open_page, status_bar_style=False):
		MenuButton.__init__(self, '-backlinks-', Gtk.Menu(), status_bar_style)
		self.notebook = notebook
		self.open_page = open_page
		self.set_sensitive(False)

	def set_page(self, page):
		self.page = page
		try:
			n = self.notebook.links.n_list_links(self.page, LINK_DIR_BACKWARD)
		except IndexNotFoundError:
			n = 0

		self.label.set_text_with_mnemonic(
			ngettext('%i _Backlink', '%i _Backlinks', n) % n)
			# T: Label for button with backlinks in statusbar
		self.set_sensitive(n > 0)

	def popup_menu(self, event=None):
		# Create menu on the fly
		self.menu = Gtk.Menu()
		notebook = self.notebook
		links = list(notebook.links.list_links(self.page, LINK_DIR_BACKWARD))
		if not links:
			return

		links.sort(key=lambda a: a.source.name)
		for link in links:
			item = Gtk.MenuItem.new_with_mnemonic(link.source.name)
			item.connect_object('activate', self.open_page, link.source)
			self.menu.add(item)

		MenuButton.popup_menu(self, event)


class PageWindow(Window):
	'''Secondary window, showing a single page'''

	def __init__(self, notebook, page, navigation):
		Window.__init__(self)
		self.navigation = navigation
		self.notebook = notebook

		self.set_title(page.name + ' - Zim')
		#if ui.notebook.icon:
		#	try:
		#		self.set_icon_from_file(ui.notebook.icon)
		#	except GObject.GError:
		#		logger.exception('Could not load icon %s', ui.notebook.icon)

		page = notebook.get_page(page)

		self.uistate = notebook.state['PageWindow']
		self.uistate.setdefault('windowsize', (500, 400), check=value_is_coord)
		w, h = self.uistate['windowsize']
		self.set_default_size(w, h)

		self.pageview = PageView(notebook, navigation, secondary=True)
		self.pageview.set_page(page)
		self.add(self.pageview)


		def do_delete_event(*a):
			logger.debug('Close PageWindow for %s', page)
			self.uistate['windowsize'] = tuple(self.get_size())

		self.connect('delete-event', do_delete_event)

class OpenPageDialog(Dialog):
	'''Dialog to go to a specific page. Also known as the "Jump to" dialog.
	Prompts for a page name and navigate to that page on 'Ok'.
	'''

	def __init__(self, parent, page, callback):
		Dialog.__init__(self, parent, _('Jump to'), # T: Dialog title
			button=_('_Jump'), # T: Button label
		)
		self.callback = callback

		self.add_form(
			[('page', 'page', _('Jump to Page'), page)], # T: Label for page input
			notebook=parent.notebook
		)

	def do_response_ok(self):
		path = self.form['page']
		if not path:
			return False
		self.callback(path)
		return True
