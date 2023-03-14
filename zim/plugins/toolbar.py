
# Copyright 2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

logger = logging.getLogger('zim.plugins.toolbar')

from gi.repository import Gtk

from zim.plugins import PluginClass
from zim.signals import SignalHandler
from zim.gui.pageview import PageViewExtension
from zim.plugins.tasklist.gui import TaskListWindowExtension
from zim.gui.widgets import TOP, POSITIONS


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
This plugin allows to customize the toolbar in the main window.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:ToolBar',
	}

	plugin_preferences = (
		# key, type, label, default
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


class ToolBarMainWindowExtension(PageViewExtension):

	def __init__(self, plugin, view):
		PageViewExtension.__init__(self, plugin, view)
		self.connectto(self.plugin.preferences, 'changed', self.on_preferences_changed)
		self.on_preferences_changed(self.plugin.preferences)
		self.connectto(self.obj.preferences, 'changed', self.on_pageview_preferences_changed)

	def on_preferences_changed(self, preferences):
		window = self.pageview.get_toplevel()
		with self.on_pageview_preferences_changed.blocked():
			self.obj.preferences['show_edit_bar'] = \
				not preferences['include_formatting'] # Force these prefs to always be in sync
		toolbar = window.setup_toolbar(
			show=preferences['show_toolbar'],
			position=preferences['position'],
		)
		toolbar.set_style(_get_style(self.plugin.preferences['style']))
		toolbar.set_icon_size(_get_size(self.plugin.preferences['size']))

	@SignalHandler
	def on_pageview_preferences_changed(self, preferences):
		# Force these prefs to always be in sync
		if self.plugin.preferences['include_formatting'] == preferences['show_edit_bar']:
			self.plugin.preferences['include_formatting'] = not preferences['show_edit_bar']

	def teardown(self):
		window = self.pageview.get_toplevel()
		window.setup_toolbar() # Restore default


class ToolbarTaskListWindowExtension(TaskListWindowExtension):
	# FIXME - should be extension of generic Window base class

	def __init__(self, plugin, window):
		TaskListWindowExtension.__init__(self, plugin, window)
		self.connectto(self.plugin.preferences, 'changed', self.on_preferences_changed)
		self.on_preferences_changed(self.plugin.preferences)

	def on_preferences_changed(self, preferences):
		if self.window._toolbar:
			self.window._toolbar.set_style(_get_style(self.plugin.preferences['style']))
			self.window._toolbar.set_icon_size(_get_size(self.plugin.preferences['size']))
