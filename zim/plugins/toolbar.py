
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

import logging

logger = logging.getLogger('zim.plugins.toolbar')

from gi.repository import Gtk

from zim.plugins import PluginClass, list_actions, PluginManager
from zim.gui.pageview import PageViewExtension
from zim.gui.notebookview import NotebookView
from zim.gui.pageview.editbar import EditActionMixin
from zim.gui.widgets import TOP, BOTTOM, RIGHT, POSITIONS
from zim.gui.customtools import CustomToolManager

import zim.errors

import os  # see issue #2007 - Gtk bug on Windows and macOS
DEFAULT_DECOR = not (os.name == 'nt' or \
	(hasattr(os, 'uname') and os.uname().sysname == 'Darwin')
)

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
		'description': _(f'''\
This plugin adds a "tool bar" to the main window.
It can be a "classic" toolbar at the top of the window
or running along the side of the window.

It also allows configuring the window decoration,
thought changing the defaults can have unintended
consequences on Windows and macOS; please consult
the manual before disabling the plugin or modifying
the window decoration related settings.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:ToolBar',
	}

	plugin_preferences = (
		# key, type, label, default
		('show_headerbar', 'bool', _('Show controls in the window decoration') + '\n' + _('This option requires restart of the application'), DEFAULT_DECOR),  # OS spesific
			# T: option for plugin preferences
		('show_toolbar', 'bool', _('Show toolbar'), True),
			# T: option for plugin preferences
		('include_formatting', 'bool', _('Include formatting tools in toolbar'), True),
			# T: option for plugin preferences
		('position', 'choice', _('Position in the window'), TOP, POSITIONS),
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
		self.setup()
		self.update()

		def on_change(o, *a):
			self.update()

		self.connectto(plugin.preferences, 'changed', on_change)
		self.connectto(self._customtoolmanager, 'changed', on_change)

		def on_extensions_changed(o, obj):
			if obj in (view, view.get_toplevel()):
				self.update()

		self.connectto(PluginManager, 'extensions-changed', on_extensions_changed)

		self.on_readonly_changed(self.pageview, self.pageview.readonly)
		self.connectto(self.pageview, 'readonly-changed')

	def on_readonly_changed(self, pageview, readonly):
		for item in self._formatting_items:
			item.set_sensitive(not readonly)

		if self._toggle_editable_item:
			self._toggle_editable_item.set_sensitive(not self.pageview.page.readonly)

	def setup(self):
		if self.plugin.preferences['show_headerbar']:
			pass
		else:
			window = self.pageview.get_toplevel()
			if not window.get_property('visible'):
				# only do this when window not yet realized
				window.set_titlebar(None)

	def update(self):
		window = self.pageview.get_toplevel()

		if self.toolbar is not None:
			try:
				window.remove(self.toolbar)
			except ValueError:
				pass
			finally:
				self.toolbar = None

		if self.plugin.preferences['show_toolbar']:
			self.toolbar = Gtk.Toolbar()
			include_headercontrols = not self.plugin.preferences['show_headerbar']
			self._populate_toolbar(window, self.toolbar, include_headercontrols)
			window.add_bar(self.toolbar, self.plugin.preferences['position'])

	def _populate_toolbar(self, window, toolbar, include_headercontrols):
		if include_headercontrols:
			if isinstance(self.pageview, NotebookView):
				for action in (
					window.open_page_back,
					window.open_page_home,
					window.open_page_forward,
				):
					toolbar.insert(action.create_tool_button(), -1)
				toolbar.insert(Gtk.SeparatorToolItem(), -1)

			item = window.toggle_editable.create_tool_button(connect_button=False)
			item.set_action_name('win.toggle_editable')
			window._style_toggle_editable_button(item)
			toolbar.insert(item, -1)
			self._toggle_editable_item = item
			toolbar.insert(Gtk.SeparatorToolItem(), -1)
		else:
			self._toggle_editable_item = None

		self._formatting_items = []
		if self.plugin.preferences['include_formatting']:
			self.pageview.set_edit_bar_visible(False)

			toolbar.insert_action_group('pageview', self.obj.get_action_group('pageview'))
			for action in self.edit_format_actions:
				item = action.create_tool_button(connect_button=False)
				item.set_action_name('pageview.' + action.name)
				toolbar.insert(item, -1)
				self._formatting_items.append(item)

			for label, icon_name, menu in self.edit_menus:
				button = self._create_menu_button(label, icon_name, menu)
				button.set_is_important(True)
				toolbar.insert(button, -1)
				self._formatting_items.append(button)

			toolbar.insert(Gtk.SeparatorToolItem(), -1)
		else:
			self.pageview.set_edit_bar_visible(True)

		content = list(self._get_plugin_actions(include_headercontrols))
		content.append(self._get_custom_tools())
		content = [group for group in content if group]
		for group in content:
			for item in group:
				toolbar.insert(item, -1)
			if group != content[-1]:
				toolbar.insert(Gtk.SeparatorToolItem(), -1)

		if include_headercontrols and isinstance(self.pageview, NotebookView):
			space = Gtk.SeparatorToolItem()
			space.set_draw(False)
			space.set_expand(True)
			self.toolbar.insert(space, -1)
			toolbar.insert(window._uiactions.show_search.create_tool_button(), -1)

		position = self.plugin.preferences['position']
		if position in (TOP, BOTTOM):
			toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
		else: # LEFT, RIGHT
			toolbar.set_orientation(Gtk.Orientation.VERTICAL)

		toolbar.set_style(_get_style(self.plugin.preferences['style']))
		toolbar.set_icon_size(_get_size(self.plugin.preferences['size']))
		toolbar.show_all()

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

	def _get_plugin_actions(self, include_headercontrols):
		viewitems, toolitems = [], []
		pageview, window = self.pageview, self.pageview.get_toplevel()
		for o in (window, pageview):
			if o is not None:
				for name, action in list_actions(o):
					if 'tools' in action.menuhints and action.hasicon \
						and (include_headercontrols or not 'headerbar' in action.menuhints):
							toolitems.append(action.create_tool_button())
					if 'view' in action.menuhints and action.hasicon \
						and (include_headercontrols or not 'headerbar' in action.menuhints):
							viewitems.append(action.create_tool_button())
					elif 'toolbar' in action.menuhints:
						toolitems.append(action.create_tool_button(fallback_icon='system-run'))

		return viewitems, toolitems

	def _get_custom_tools(self):
		items = []
		size = _get_size(self.plugin.preferences['size'])
		for tool in self._customtoolmanager:
			if tool.showintoolbar:
				button = Gtk.ToolButton()
				button.set_label(tool.name)
				button.set_icon_widget(Gtk.Image.new_from_pixbuf(tool.get_pixbuf(size)))
				button.set_tooltip_text(tool.comment) # icon button should always have tooltip
				button.connect('clicked', self._run_custom_tool, tool)
				items.append(button)

		return items

	def _run_custom_tool(self, button, tool):
		logger.info('Execute custom tool %s', tool.name)
		pageview = self.pageview
		notebook, page = pageview.notebook, pageview.page
		try:
			tool.run(notebook, page, pageview)
		except:
			zim.errors.exception_handler(
				'Exception during action: %s' % tool.name)

	def teardown(self):
		self.pageview.set_edit_bar_visible(True)
		if self.toolbar is not None:
			self.pageview.get_toplevel().remove(self.toolbar)
			self.toolbar = None
