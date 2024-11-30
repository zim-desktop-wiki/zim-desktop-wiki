
# Copyright 2008-2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import os
import sys
import logging
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Gdk

logger = logging.getLogger('zim.gui')


from zim.config import data_file, value_is_coord, ConfigDict, Boolean, ConfigManager
from zim.signals import DelayedCallback, ConnectorMixin

from zim.notebook import Path, Page, LINK_DIR_BACKWARD, PageNotAvailableError
from zim.notebook.index import IndexNotFoundError
from zim.notebook.operations import ongoing_operation
from zim.history import History, HistoryPath

from zim.actions import action, toggle_action, radio_action, radio_option, \
	get_gtk_actiongroup, initialize_actiongroup, \
	PRIMARY_MODIFIER_STRING, PRIMARY_MODIFIER_MASK
from zim.gui.widgets import \
	MenuButton, \
	Window, Dialog, \
	ErrorDialog, FileDialog, ProgressDialog, MessageDialog, QuestionDialog, \
	ScrolledTextView, \
	gtk_popup_at_pointer, \
	TOP, BOTTOM

from zim.gui.navigation import NavigationModel
from zim.gui.uiactions import UIActions
from zim.gui.customtools import CustomToolManager, CustomToolManagerUI
from zim.gui.insertedobjects import InsertedObjectUI

from zim.gui.pageview import PageView
from zim.gui.pageview.editbar import ToolBarEditBarManager
from zim.gui.notebookview import NotebookView

from zim.plugins import ExtensionBase, extendable, PluginManager
from zim.gui.actionextension import ActionExtensionBase, \
	populate_toolbar_with_actions, os_default_headerbar


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
	('checkbox_menu', None, _('_Checkbox')), # T: Menu title
)
if sys.platform == "darwin":
	# don't use mnemonics on macOS to allow alt-<letter> shortcuts
	MENU_ACTIONS = tuple((t[0], t[1], t[2].replace('_', '')) for t in MENU_ACTIONS)


#: Preferences for the user interface
ui_preferences = (
	# key, type, category, label, default
	('prefer-dark-theme', 'bool', 'Interface', _('Prefer dark theme')
		+ '\n' + _('This option requires a Gtk theme supporting a dark variant')
		+ '\n' + _('This option requires restart of the application'), False),
		# T: option for preferences dialog
	('show_headerbar', 'bool', 'Interface', _('Show controls in the window decoration') + '\n' + _('This option requires restart of the application'), os_default_headerbar),
		# T: option for preferences dialog
	('toggle_on_ctrlspace', 'bool', 'Interface', _('Use %s to switch to the side pane') % (PRIMARY_MODIFIER_STRING + '<Space>'), False),
		# T: Option in the preferences dialog - %s will map to either <Control><Space> or <Command><Space> key binding
		# default value is False because this is mapped to switch between
		# char sets in certain international key mappings
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

	Menu actions can be defined by defining an action method
	and specifying where in the menu this should be placed.

	An action method is any object method of the extension method that
	is decorated by the L{action()} or L{toggle_action()} decorators
	(see L{zim.actions}). Such a method is called when the user clicks
	a corresponding menu item or presses the corresponding key binding.
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


class WindowBaseMixin(ConnectorMixin, object):
	'''Common logic between MainWindow and PageWindow'''

	def _init_fullscreen_headerbar(self):
		# Create eventbox for headerbar
		self._in_fullscreen_eventbox = False
		self._fullscreen_eventbox = Gtk.EventBox()
		self._fullscreen_eventbox.set_valign(Gtk.Align.START)
		self._fullscreen_eventbox.set_size_request(1, -1) # 1 pixel sensitive area on top of the screen
		self._zim_window_overlay.add_overlay(self._fullscreen_eventbox)
		self._fullscreen_revealer = Gtk.Revealer()
		self._fullscreen_eventbox.add(self._fullscreen_revealer)
		self._fullscreen_headerbar = Gtk.HeaderBar()
		self._fullscreen_revealer.add(self._fullscreen_headerbar)

		close_button = Gtk.Button()
		close_button.set_image(Gtk.Image.new_from_icon_name('view-restore-symbolic',  Gtk.IconSize.BUTTON))
		close_button.set_tooltip_text(_('Leave Fullscreen')) # T: button label for fullscreen window header
		close_button.connect('clicked', lambda o: self.toggle_fullscreen(False))
		self._fullscreen_headerbar.pack_end(close_button)

		self._fullscreen_eventbox.show_all()
		self._fullscreen_eventbox.set_no_show_all(True)
		self._fullscreen_eventbox.hide()
		self._fullscreen_eventbox.connect('enter-notify-event', self._on_fullscreen_eventbox_enter)
		self._fullscreen_eventbox.connect('leave-notify-event', self._on_fullscreen_eventbox_leave)

		# Generic state for fullscreen
		self.maximized = False
		self.isfullscreen = False
		self.connect_after('window-state-event', self.__class__.on_window_state_event)

	def on_window_state_event(self, event):
		if bool(event.changed_mask & Gdk.WindowState.MAXIMIZED):
			self.maximized = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
			schedule_on_idle(lambda: self.pageview.scroll_cursor_on_screen())

		if bool(event.changed_mask & Gdk.WindowState.FULLSCREEN):
			self.isfullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
			self.toggle_fullscreen.set_active(self.isfullscreen)
			schedule_on_idle(lambda: self.pageview.scroll_cursor_on_screen())

			if self.isfullscreen:
				self._fullscreen_eventbox.show()
			else:
				self._fullscreen_eventbox.hide()

			self.update_toolbar()

	def _on_fullscreen_eventbox_enter(self, *a):
		if self._headerbar is None and self._toolbar and self._toolbar.get_visible():
			# Do not show fullscreen headerbar if headerbar controls are in toolbar *and* visible
			# because headerbar will be redundant. If toolbar is not visible, we need at least "exit fullscreen"
			return

		self._in_fullscreen_eventbox = True
		self._update_fullscreen_revealer()

	def _on_fullscreen_eventbox_leave(self, *a):
		self._in_fullscreen_eventbox = False
		self._update_fullscreen_revealer()

	def _update_fullscreen_revealer(self, *a):
		# keep showing headerbar as long as any popup menu is open
		show = self._in_fullscreen_eventbox or any(
			c.get_active() for c in self._fullscreen_headerbar.get_children() if isinstance(c, Gtk.MenuButton)
		)
		self._fullscreen_revealer.set_reveal_child(show)

	def _populate_headerbars(self):
		for headerbar in (self._headerbar, self._fullscreen_headerbar):
			if headerbar is not None:
				self._populate_headerbar(headerbar)
				headerbar.show_all()

		for c in self._fullscreen_headerbar.get_children():
			if isinstance(c, Gtk.MenuButton):
				c.connect('toggled', self._update_fullscreen_revealer)

	def _init_toolbar(self):
		# One time setup of the toolbar widget
		assert self.pageview, 'Ensure pageview is initalized to let preferences be loaded'

		self._toolbar = Gtk.Toolbar()
		self._toolbar_editbar_manager = ToolBarEditBarManager(self.pageview, self._toolbar)

		self.setup_toolbar()

		def on_extensions_changed(o, obj):
			if obj in (self, self.pageview):
				self.update_toolbar()

		self.connectto(PluginManager, 'extensions-changed', on_extensions_changed)

		def on_changed_update(o, *a):
			self.update_toolbar()

		self.connectto(CustomToolManager(), 'changed', on_changed_update)
		self.connectto(self.pageview.preferences, 'changed', on_changed_update)

	def setup_toolbar(self, show=None, position=None):
		# Default setup for toolbar - can be called multiple times - also used by "toolbar" plugin
		try:
			self.remove(self._toolbar)
		except ValueError:
			pass

		# Defaults
		if show is None:
			show = not self.preferences['show_headerbar']

		position = TOP if position is None else position

		# Set toolbar in window
		if show:
			self.add_bar(self._toolbar, position=position)
			if position in (TOP, BOTTOM):
				self._toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
			else: # LEFT, RIGHT
				self._toolbar.set_orientation(Gtk.Orientation.VERTICAL)
			self._toolbar.show()
			self.update_toolbar()
		else:
			self._toolbar.hide()

		return self._toolbar

	def update_toolbar(self):
		# This method updates the toolbar content. See setup_toolbar() to
		# control placement and visibility.
		if self._toolbar.get_visible():
			for item in self._toolbar.get_children():
				self._toolbar.remove(item)
			self._populate_toolbar(self._toolbar)

			if self.isfullscreen and not self.preferences['show_headerbar']:
				close_button = Gtk.ToolButton()
				close_button.set_icon_name('view-restore-symbolic')
				close_button.set_tooltip_text(_('Leave Fullscreen')) # T: button label for fullscreen window header
				close_button.connect('clicked', lambda o: self.toggle_fullscreen(False))
				self._toolbar.insert(close_button, -1)

			self._toolbar.show_all()

	def _populate_toolbar_inner(self, toolbar):
		if not self.pageview.preferences['show_edit_bar']:
			self._toolbar_editbar_manager.populate_toolbar(toolbar)

		populate_toolbar_with_actions(
			self._toolbar, self, self.pageview,
			include_headercontrols=(not self.preferences['show_headerbar']),
			include_customtools=True
		)

	def set_title(self, text):
		Gtk.Window.set_title(self, text)
		if self._headerbar is not None:
			self._headerbar.set_title(text)
		self._fullscreen_headerbar.set_title(text)

	@toggle_action(_('_Fullscreen'), 'F11', icon='view-fullscreen-symbolic', init=False) # T: Menu item
	def toggle_fullscreen(self, show):
		'''Menu action to toggle the fullscreen state of the window'''
		if show:
			self.fullscreen()
		else:
			self.unfullscreen()

	@toggle_action(_('Toggle _Editable'), icon='document-edit-symbolic', init=True, tooltip=_('Toggle editable')) # T: menu item
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

		try:
			self.uistate['readonly'] = readonly
		except KeyError:
			pass
		self.emit('readonly-changed', readonly)

	def set_toggle_editable_state(self, editable_uistate):
		'''Set sensitivity of the "toggle_editable" action
		@param editable_uistate: default state if control is sensitive
		'''
		if self.notebook.readonly or self.page.readonly:
			if self.toggle_editable.get_sensitive():
				self.toggle_editable.set_sensitive(False)
				self._set_tooltip_hack(_('Page is read-only and cannot be edited')) # T: message in toggle editable tooltip

		else:
			if not self.toggle_editable.get_sensitive():
				self.toggle_editable.set_sensitive(True)
				self._set_tooltip_hack(self.toggle_editable.tooltip) # reset to default

			self.toggle_editable(editable_uistate)

	def _set_tooltip_hack(self, text):
		for proxy in self.toggle_editable._proxies: # XXX
			if hasattr(proxy, 'set_tooltip_text'):
				proxy.set_tooltip_text(text)

	def _style_toggle_editable_button(self, button):
		def _change_style_on_toggle(button):
			context = button.get_style_context()
			if button.get_active():
				context.remove_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
			else:
				context.add_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
		_change_style_on_toggle(button)
		button.connect('toggled', _change_style_on_toggle)

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

	@action(_('Focus Sidepane')) # T: menu item
	def focus_sidepane_key_toggle(self):
		self.do_focus_sidepane_key_toggle()

	def do_focus_sidepane_key_toggle(self, *a):
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


@extendable(MainWindowExtension)
class MainWindow(WindowBaseMixin, Window):

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
		self.preferences.define({p[0]: Boolean(p[-1]) for p in ui_preferences})
		self.preferences.connect('changed', self.do_preferences_changed)

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
		self.uistate.setdefault('readonly', False)

		self.history = History(notebook, notebook.state)

		# init uimanager
		self.uimanager = Gtk.UIManager()
		self.uimanager.add_ui_from_string('''
		<ui>
			<menubar name="menubar">
			</menubar>
		</ui>
		''')

		# setup menubar
		self.add_accel_group(self.uimanager.get_accel_group())
		self.menubar = self.uimanager.get_widget('/menubar')
		self.add_bar(self.menubar, position=TOP)

		self.pageview = NotebookView(self.notebook, self.navigation)
		self.connect_object('readonly-changed', NotebookView.set_readonly, self.pageview)

		self.add(self.pageview)

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
		self.__zim_extension_objects__.append(self._uiactions) # HACK to make actions discoverable
		group = get_gtk_actiongroup(self._uiactions)
		self.uimanager.insert_action_group(group, 0)

		group = get_gtk_actiongroup(self.pageview)
		self.uimanager.insert_action_group(group, 0)

		group = get_gtk_actiongroup(self)
		group.add_actions(MENU_ACTIONS)
		self.uimanager.insert_action_group(group, 0)

		self.open_page_back.set_sensitive(False)
		self.open_page_forward.set_sensitive(False)

		fname = 'menubar.xml'
		self.uimanager.add_ui_from_string(data_file(fname).read())

		# header & tool bars
		if self.preferences['show_headerbar']:
			self._headerbar = Gtk.HeaderBar()
			self._headerbar.set_show_close_button(True)
			self.set_titlebar(self._headerbar)
		else:
			self._headerbar = None

		self._init_fullscreen_headerbar()
		self._populate_headerbars()
		self._init_toolbar()

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

		PluginManager.register_new_extendable(self.pageview)
		initialize_actiongroup(self, 'win')

		self.pageview.grab_focus()

	def _populate_headerbar(self, headerbar):
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		for action in (
			self.open_page_back,
			self.open_page_home,
			self.open_page_forward,
		):
			hbox.add(action.create_icon_button())
		context = hbox.get_style_context()
		context.add_class("linked")
		headerbar.pack_start(hbox)

		headerbar.pack_end(self._uiactions.show_search.create_icon_button())

		button = self.toggle_editable.create_icon_button()
		self._style_toggle_editable_button(button)
		headerbar.pack_end(button)

	def _populate_toolbar(self, toolbar):
		# Add default controls
		if not self.preferences['show_headerbar']:
			for action in (
				self.open_page_back,
				self.open_page_home,
				self.open_page_forward,
			):
				toolbar.insert(action.create_tool_button(), -1)
			toolbar.insert(Gtk.SeparatorToolItem(), -1)

			item = self.toggle_editable.create_tool_button(connect_button=False)
			item.set_action_name('win.toggle_editable')
			self._style_toggle_editable_button(item)
			toolbar.insert(item, -1)
			toolbar.insert(Gtk.SeparatorToolItem(), -1)

			self._populate_toolbar_inner(toolbar)

			space = Gtk.SeparatorToolItem()
			space.set_draw(False)
			space.set_expand(True)
			toolbar.insert(space, -1)

			toolbar.insert(self._uiactions.show_search.create_tool_button(), -1)
		else:
			self._populate_toolbar_inner(toolbar)

	@action(_('_Close'), '<Primary>W') # T: Menu item
	def close(self):
		'''Menu action for close. Will hide when L{hideonclose} is set,
		otherwise destroys window, which could result in the application
		closing if there are no other toplevel windows.
		'''
		if self.hideonclose: # XXX
			self._do_close()
		else:
			self.destroy()

	def _do_close(self):
		self.save_uistate()
		self.hide()
		self.emit('close')

	def destroy(self):
		self.pageview.save_changes()
		if self.page.modified:
			return # Do not quit if page not saved

		self._do_close()

		while Gtk.events_pending():
			Gtk.main_iteration_do(False)

		self.notebook.index.stop_background_check()
		op = ongoing_operation(self.notebook)
		if op:
			op.wait()

		Window.destroy(self) # gtk destroy & will also emit destroy signal

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
			group.connect( # <Alt><Space>
				space, Gdk.ModifierType.MOD1_MASK, Gtk.AccelFlags.VISIBLE,
				self.do_focus_sidepane_key_toggle)

		# Toggled by preference menu, also causes issues with international
		# layouts - esp. when switching input method on Meta-Space
		if self.preferences['toggle_on_ctrlspace']:
			group.connect( # <Primary><Space>
				space, PRIMARY_MODIFIER_MASK, Gtk.AccelFlags.VISIBLE,
				self.do_focus_sidepane_key_toggle)

		self.add_accel_group(group)
		self._switch_focus_accelgroup = group

		# Toggle dark theme
		gtk_settings = Gtk.Settings.get_default()
		text_style = ConfigManager.get_config_dict('style.conf')
		if self.preferences['prefer-dark-theme']:
			gtk_settings.set_property('gtk-application-prefer-dark-theme', True)
			text_style.set_selectors(('darktheme',))
		else:
			gtk_settings.set_property('gtk-application-prefer-dark-theme', False)
			text_style.set_selectors(None)

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

		Window.init_uistate(self) # takes care of sidepane positions etc

		self.toggle_fullscreen(self._set_fullscreen)

		# And hook to notebook properties
		self.on_notebook_properties_changed(self.notebook.properties)
		self.notebook.properties.connect('changed', self.on_notebook_properties_changed)

		# Notify plugins
		self.emit('init-uistate')

		# Update menus etc.
		self.uimanager.ensure_update()
			# Prevent flashing when the toolbar is loaded after showing the window
			# and do this before connecting signal below for accelmap.

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

	def save_uistate(self):
		if not self.pageview._zim_extendable_registered:
			return
			# Not allowed to save before plugins are loaded, could overwrite
			# pane state based on empty panes

		cursor = self.pageview.get_cursor_pos()
		scroll = self.pageview.get_scroll_pos()
		self.history.set_state(self.page, cursor, scroll)

		if self.is_visible() and not self.isfullscreen:
			self.uistate['windowpos'] = tuple(self.get_position())
			self.uistate['windowsize'] = tuple(self.get_size())
			self.uistate['windowmaximized'] = self.maximized

		Window.save_uistate(self) # takes care of sidepane positions etc.

		if self.notebook.state.modified:
			self.notebook.state.write()

	def on_notebook_properties_changed(self, properties):
		self._update_window_title()
		if self.notebook.icon:
			try:
				self.set_icon_from_file(self.notebook.icon)
			except (GObject.GError, GLib.Error):
				logger.exception('Could not load icon %s', self.notebook.icon)

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

	def open_page(self, path, anchor=None, anchor_fail_silent=False):
		'''Method to open a page in the mainwindow, and menu action for
		the "jump to" menu item.

		Fails silently when saving current page failed (which is usually the
		result of pressing "cancel" in the error dialog shown when saving
		fails). Check return value for success if you want to be sure.

		@param path: a L{path} for the page to open.
		@param anchor: name of an anchor (optional)
		@raises PageNotFound: if C{path} can not be opened
		@emits: page-changed
		@returns: C{True} for success
		'''
		assert isinstance(path, Path)
		try:
			page = self.notebook.get_page(path) # can raise
		except PageNotAvailableError as error:
			# Same code in NewPageDialog
			if QuestionDialog(self, (
				_('File exists, do you want to import?'), # T: short question on open-page if file exists
				_('The file "%s" exists but is not a wiki page.\nDo you want to import it?') % error.file.basename # T: longer question on open-page if file exists
			)).run():
				from zim.import_files import import_file
				page = import_file(error.file, self.notebook, path)
			else:
				return # user cancelled

		if self.page and id(self.page) == id(page):
			if anchor:
				self.pageview.navigate_to_anchor(anchor, fail_silent=anchor_fail_silent)
			return
		elif self.page:
			self.pageview.save_changes() # XXX - should connect to signal instead of call here
			self.notebook.wait_for_store_page_async() # XXX - should not be needed - hide in notebook/page class - how?
			if self.page.modified:
				return False # Assume SavePageErrorDialog was shown and cancelled

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
			cursor, x = self.history.get_state(page)

		self.pageview.set_page(page, cursor)

		if anchor:
			self.pageview.navigate_to_anchor(anchor, fail_silent=anchor_fail_silent)

		self.emit('page-changed', page)

		self.pageview.grab_focus()

	def do_page_changed(self, page):
		self.update_buttons_history()
		self.update_buttons_hierarchy()
		self._update_window_title()
		self.set_toggle_editable_state(not self.uistate['readonly'])

	def _update_window_title(self):
		if self.notebook.readonly or (self.page and self.page.readonly):
			readonly = ' [' + _('readonly') + ']' # T: page status for title bar
		else:
			readonly = ''

		if self.page:
			title = self.page.name + ' - ' + self.notebook.name + readonly
		else:
			title = self.notebook.name + readonly

		self.set_title(title)

	def do_page_info_changed(self, notebook, page):
		if page == self.page:
			self.update_buttons_hierarchy()

	def update_buttons_history(self):
		historyrecord = self.history.get_current()
		self.open_page_back.set_sensitive(not historyrecord.is_first)
		self.open_page_forward.set_sensitive(not historyrecord.is_last)

	def update_buttons_hierarchy(self):
		self.open_page_parent.set_sensitive(len(self.page.namespace) > 0)
		self.open_page_child.set_sensitive(self.page.haschildren)

		has_prev, has_next = self.notebook.pages.get_has_previous_has_next(self.page)
		self.open_page_previous.set_sensitive(has_prev)
		self.open_page_next.set_sensitive(has_next)

	@action(_('_Jump To...'), '<Primary>J') # T: Menu item
	def show_jump_to(self):
		return OpenPageDialog(self, self.page, self.open_page).run()

	@action(
		_('_Back'), verb_icon='go-previous-symbolic', # T: Menu item
		accelerator='<alt>Left', alt_accelerator='XF86Back',
		tooltip=_('Go back') # T: tooltip for navigation button
	)
	def open_page_back(self):
		'''Menu action to open the previous page from the history
		@returns: C{True} if successfull
		'''
		record = self.history.get_previous()
		if not record is None:
			self.open_page(record)

	@action(
		_('_Forward'), verb_icon='go-next-symbolic', # T: Menu item
		accelerator='<alt>Right', alt_accelerator='XF86Forward',
		tooltip=_('Go forward') # T: tooltip for navigation button
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

	@action(_('_Previous in Index'), accelerator='<alt>Page_Up') # T: Menu item
	def open_page_previous(self):
		'''Menu action to open the previous page from the index
		@returns: C{True} if successfull
		'''
		path = self.notebook.pages.get_previous(self.page)
		if not path is None:
			self.open_page(path)

	@action(_('_Next in Index'), accelerator='<alt>Page_Down') # T: Menu item
	def open_page_next(self):
		'''Menu action to open the next page from the index
		@returns: C{True} if successfull
		'''
		path = self.notebook.pages.get_next(self.page)
		if not path is None:
			self.open_page(path)

	@action(_('_Home'), '<alt>Home', verb_icon='go-home-symbolic', tooltip=_('Go to home page')) # T: Menu item
	def open_page_home(self):
		'''Menu action to open the home page'''
		self.open_page(self.notebook.get_home_page())


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


class PageWindow(WindowBaseMixin, Window):
	'''Window to show a single page'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'readonly-changed': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
	}

	def __init__(self, notebook, page, navigation, editable=True):
		Window.__init__(self)
		self._block_toggle_panes = False
		self._sidepane_autoclose = False
		self.navigation = navigation
		self.notebook = notebook
		self.page = notebook.get_page(page)

		self.preferences = ConfigManager.preferences['GtkInterface']
		self.preferences.define({p[0]: Boolean(p[-1]) for p in ui_preferences})
		#self.preferences.connect('changed', self.do_preferences_changed)

		if self.preferences['show_headerbar']:
			self._headerbar = Gtk.HeaderBar()
			self._headerbar.set_show_close_button(True)
			self.set_titlebar(self._headerbar)
		else:
			self._headerbar = None

		self._init_fullscreen_headerbar()
		self._populate_headerbars()

		if self.notebook.readonly or self.page.readonly:
			title = page.name + ' [' + _('readonly') + ']' # T: page status for title bar
		else:
			title = page.name
		self.set_title(title)
		#if ui.notebook.icon:
		#	try:
		#		self.set_icon_from_file(ui.notebook.icon)
		#	except (GObject.GError, GLib.Error):
		#		logger.exception('Could not load icon %s', ui.notebook.icon)


		self.uistate = notebook.state['PageWindow']
		self.uistate.setdefault('windowsize', (500, 400), check=value_is_coord)
		w, h = self.uistate['windowsize']
		self.set_default_size(w, h)

		self.pageview = PageView(notebook, navigation)
		self.connect_object('readonly-changed', PageView.set_readonly, self.pageview)
		self.pageview.set_page(self.page)
		self.add(self.pageview)

		# Need UIManager & menubar to make accelerators and plugin actions work
		self.uimanager = Gtk.UIManager()
		self.add_accel_group(self.uimanager.get_accel_group())

		group = get_gtk_actiongroup(self)
		group.add_actions(MENU_ACTIONS)
		self.uimanager.insert_action_group(group, 0)

		group = get_gtk_actiongroup(self.pageview)
		self.uimanager.insert_action_group(group, 0)

		self._uiactions = UIActions(self, self.notebook, self.page, self.navigation)
		group = get_gtk_actiongroup(self._uiactions)
		self.uimanager.insert_action_group(group, 0)

		fname = 'pagewindow_ui.xml'
		self.uimanager.add_ui_from_string(data_file(fname).read())

		self.menubar = self.uimanager.get_widget('/menubar')
		self.add_bar(self.menubar, position=TOP)

		self._init_toolbar()

		# Close window when page is moved or deleted
		def on_notebook_change(o, path, *a):
			if path == self.page or self.page.ischild(path):
				logger.debug('Close PageWindow for %s (page is gone)', self.page)
				self.save_uistate()
				self.destroy()

		notebook.connect('deleted-page', on_notebook_change)
		notebook.connect('moved-page', on_notebook_change)

		# setup state
		self.set_toggle_editable_state(editable)

		# on close window
		def do_delete_event(*a):
			logger.debug('Close PageWindow for %s', self.page)
			self.save_uistate()

		self.connect('delete-event', do_delete_event)

		PluginManager.register_new_extendable(self.pageview)
		initialize_actiongroup(self, 'win')

		self.pageview.grab_focus()

	def _populate_headerbar(self, headerbar):
		#if headerbar is self._headerbar:
		#	headerbar.pack_end(self.toggle_fullscreen.create_icon_button()) # FIXME: should go in menu popover

		button = self.toggle_editable.create_icon_button()
		self._style_toggle_editable_button(button)
		headerbar.pack_end(button)

	def _populate_toolbar(self, toolbar):
		# Add default controls
		if not self.preferences['show_headerbar']:
			item = self.toggle_editable.create_tool_button(connect_button=False)
			item.set_action_name('win.toggle_editable')
			self._style_toggle_editable_button(item)
			toolbar.insert(item, -1)
			toolbar.insert(Gtk.SeparatorToolItem(), -1)

			self._populate_toolbar_inner(toolbar)

			space = Gtk.SeparatorToolItem()
			space.set_draw(False)
			space.set_expand(True)
			toolbar.insert(space, -1)

			# FIXME: should go in menu popover
			#item = self.toggle_fullscreen.create_tool_button(connect_button=False)
			#item.set_action_name('win.toggle_fullscreen')
			#toolbar.insert(item, -1)
		else:
			self._populate_toolbar_inner(toolbar)

	def save_uistate(self):
		if not self.pageview._zim_extendable_registered:
			return
			# Not allowed to save before plugins are loaded, could overwrite
			# pane state based on empty panes
		self.uistate['windowsize'] = tuple(self.get_size())
		Window.save_uistate(self) # takes care of sidepane positions etc.


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
