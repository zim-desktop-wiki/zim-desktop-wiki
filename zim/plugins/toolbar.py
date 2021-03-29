
# Copyright 2021 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# Plugin to add a toolbar to the window, replaces the "classic" toolbar that
# has been removed in favor of the editbar in the pageview and window titlebar
#
# Layout: [editing | default tools, plugins | custom tools]
# - optionally duplicate editbar contents
# - do not duplicate actions available in the titlebar
#
# Options:
# - "classic toolbar" - hide EditBar & show edting part of toolbar
# - position: top, bottom, left, right - default "right", set "top" for classic
# - style: icons / labels / both
# - size: small / large
#
# Implementation:
# - Use PageView extension to extend both MainWindow and PageWindow
# - Option in pageview class to hide default editbar
# - Use CustomToolManager to monitor custom tools
# - Watch for changes in actions of window & pageview & extensions
# - Check menuhints for action ('tool' + hasicon and not 'headerbar' or explicit 'toolbar')


from gi.repository import Gtk

from zim.plugins import PluginClass, list_actions, PluginManager
from zim.gui.pageview import PageViewExtension
from zim.gui.pageview.editbar import EditActionMixin
from zim.gui.widgets import TOP, BOTTOM, RIGHT, POSITIONS
from zim.gui.customtools import CustomToolManager


STYLES = (
	('ICONS', _('Icons')), # T: toolbar style
	('TEXT', _('Text')), # T: toolbar style
	('BOTH', _('Icons & Text')), # T: toolbar style
	('BOTH_HORIZ', _('Icons & Text horizontal')), # T: toolbar style
)

def _get_style(key):
	return getattr(Gtk.ToolbarStyle, key)


SIZES = (
	('SMALL_TOOLBAR', _('Small')), # T: Toolbar size small
	('LARGE_TOOLBAR', _('Large')), # T: Toolbar size large
)

def _get_size(key):
	return getattr(Gtk.IconSize, key)


class ToolBarPlugin(PluginClass):

	plugin_info = {
		'name': _('Tool Bar'), # T: plugin name
		'description': _('''\
This plugin adds a "tool bar" to the main window.
It can be a "classic" toolbar at the top of the window
or running along the side of the window.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:ToolBar',
	}

	plugin_preferences = (
		# key, type, label, default
		('classic', 'bool', _('Include editing tools (classic toolbar)'), False),
			# T: option for plugin preferences
		('position', 'choice', _('Position in the window'), RIGHT, POSITIONS),
			# T: option for plugin preferences
		('style', 'choice', _('Toolbar style'), 'ICONS', STYLES),
			# T: option for plugin preferences
		('size', 'choice', _('Toolbar size'), 'SMALL_TOOLBAR', SIZES),
			# T: option for plugin preferences
	)


class ToolBarMainWindowExtension(EditActionMixin, PageViewExtension):

	def __init__(self, plugin, view):
		PageViewExtension.__init__(self, plugin, view)
		EditActionMixin.__init__(self, view)
		self.toolbar = None
		self._customtoolmanager = CustomToolManager()
		self.refresh_toolbar()

		def on_change(o, *a):
			self.refresh_toolbar()

		self.connectto(plugin.preferences, 'changed', on_change)
		self.connectto(self._customtoolmanager, 'changed', on_change)

		def on_extensions_changed(o, obj):
			if obj in (view, view.get_toplevel()):
				self.refresh_toolbar()

		self.connectto(PluginManager, 'extensions-changed', on_extensions_changed)

	def refresh_toolbar(self):
		if self.toolbar is not None:
			self.pageview.get_toplevel().remove(self.toolbar)

		self.toolbar = Gtk.Toolbar()

		if self.plugin.preferences['classic']:
			self.pageview.set_edit_bar_visible(False)

			self.toolbar.insert_action_group('pageview', self.obj.get_action_group('pageview'))
			for action in self.edit_format_actions:
				item = action.create_tool_button(connect_button=False)
				item.set_action_name('pageview.' + action.name)
				self.toolbar.insert(item, -1)

			for label, icon_name, menu in self.edit_menus:
				button = self._create_menu_button(label, icon_name, menu)
				button.set_is_important(True)
				self.toolbar.insert(button, -1)

			self.toolbar.insert(Gtk.SeparatorToolItem(), -1)
		else:
			self.pageview.set_edit_bar_visible(True)

		content = (
			self._get_tools_actions(),
			self._get_custom_tools(),
		)
		content = [group for group in content if group]
		for group in content:
			for item in group:
				self.toolbar.insert(item, -1)
			if group != content[-1]:
				self.toolbar.insert(Gtk.SeparatorToolItem(), -1)

		position = self.plugin.preferences['position']
		if position in (TOP, BOTTOM):
			self.toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
		else: # LEFT, RIGHT
			self.toolbar.set_orientation(Gtk.Orientation.VERTICAL)

		self.toolbar.set_style(_get_style(self.plugin.preferences['style']))
		self.toolbar.set_icon_size(_get_size(self.plugin.preferences['size']))
		self.toolbar.show_all()

		window = self.pageview.get_toplevel()
		window.add_bar(self.toolbar, position)

	def _create_menu_button(self, label, icon_name, menu):
		button = Gtk.ToggleToolButton()
		button.set_label(label+'...')
		button.set_use_underline(True)
		button.set_tooltip_text(label.replace('_', '')+'...') # icon button should always have tooltip
		button.set_icon_name(icon_name)

		popover = Gtk.Popover()
		popover.bind_model(menu)
		popover.set_relative_to(button)
		def toggle_popover(button):
			if button.get_active():
				popover.popup()
			else:
				popover.popdown()
		button.connect('toggled', toggle_popover)
		popover.connect('closed', lambda o: button.set_active(False))
		popover.connect('closed', lambda o: self.pageview.grab_focus())

		return button

	def _get_tools_actions(self):
		items = []
		pageview, window = self.pageview, self.pageview.get_toplevel()
		for o in (window, pageview):
			if o is not None:
				for name, action in list_actions(o):
					if 'tools' in action.menuhints and action.hasicon and not 'headerbar' in action.menuhints:
						items.append(action.create_tool_button())
					elif 'toolbar' in action.menuhints:
						items.append(action.create_tool_button(fallback_icon='system-run'))

		return items

	def _get_custom_tools(self):
		items = []
		size = _get_size(self.plugin.preferences['size'])
		for tool in self._customtoolmanager:
			if tool.showintoolbar:
				button = Gtk.ToolButton()
				button.set_label(tool.name)
				button.set_icon_widget(Gtk.Image.new_from_pixbuf(tool.get_pixbuf(size)))
				button.set_tooltip_text(tool.comment) # icon button should always have tooltip
				items.append(button)

		return items

	def teardown(self):
		self.pageview.set_edit_bar_visible(True)
		if self.toolbar is not None:
			self.pageview.get_toplevel().remove(self.toolbar)
			self.toolbar = None
