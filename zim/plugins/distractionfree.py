
# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
import logging

from zim.plugins import PluginClass
from zim.gui.mainwindow import MainWindowExtension

from zim.signals import SIGNAL_AFTER
from zim.gui.widgets import widget_set_css

logger = logging.getLogger('zim.plugins.distractionfree')


_minsize = 300 # prevent pageview from disappearing altogether
_minmargin = 5 # minimum margin to keep from other widgets


class DistractionFreePlugin(PluginClass):

	plugin_info = {
		'name': _('Distraction Free Editing'), # T: plugin name
		'description': _(
			'This plugin adds settings that help using zim\n'
			'as a distraction free editor.\n'
		), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Distraction Free Editing',
	}

	plugin_preferences = (
		# key, type, label, default
		('hide_menubar', 'bool', _('Hide menubar in fullscreen mode'), True), # T: plugin preference
		('hide_toolbar', 'bool', _('Hide toolbar in fullscreen mode'), True), # T: plugin preference
		('hide_statusbar', 'bool', _('Hide statusbar in fullscreen mode'), True), # T: plugin preference
		('max_page_width', 'int', _('Maximum page width'), 850, (_minsize, 10000)), # T: plugin preference
		('vmargin', 'int', _('Border width'), 50, (0, 10000)), # T: plugin preference
		('basecolor', 'color', _('Text background color'), '#babdb6'), # T: plugin preference
		('textcolor', 'color', _('Text foreground color'), '#2e3436'), # T: plugin preference
		#('bgcolor', 'color', _('Screen background color'), '#2e3436'), # T: plugin preference
		#('fgcolor', 'color', _('Screen foreground color'), '#eeeeec'),
	)


class DistractionFreeMainWindowExtension(MainWindowExtension):

	def __init__(self, plugin, window):
		MainWindowExtension.__init__(self, plugin, window)
		self.preferences = plugin.preferences
		self._show_panes = True
		self._bar_state = None
		self._maxwidth = None
		self._css_provider = None

		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)
		self.connectto(window, 'window-state-event', order=SIGNAL_AFTER)

		if window.isfullscreen:
			self.on_fullscreen_changed(window)

	def _new_css_provider(self):
		css = '''
		#zim-pageview text {
			color: %s;
			background-color: %s;
		}
		''' % (self.preferences['textcolor'], self.preferences['basecolor'])
		provider = Gtk.CssProvider()
		provider.load_from_data(css.encode('UTF-8'))
		return provider

	def on_preferences_changed(self, preferences):
		if self.window.isfullscreen:
			self.window.toggle_menubar(not preferences['hide_menubar'])
			self.window.toggle_toolbar(not preferences['hide_toolbar'])
			self.window.toggle_statusbar(not preferences['hide_statusbar'])

	def on_window_state_event(self, window, event):
		if bool(event.changed_mask & Gdk.WindowState.FULLSCREEN):
			self.on_fullscreen_changed(window)

	def on_fullscreen_changed(self, window):
		self.window.toggle_menubar(True) # always do this first to allow recovery

		screen = Gdk.Screen.get_default()
		if window.isfullscreen:
			self._show_panes = bool(window.get_visible_panes())
			window.toggle_panes(False)
			self.save_bar_state()
			self.set_bar_state_fullscreen()
			self.insert_maxwidth()
			for widget in self._pathbar_widgets():
				widget.hide()
			self._css_provider = self._new_css_provider()
			Gtk.StyleContext.add_provider_for_screen(screen, self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
		else:
			Gtk.StyleContext.remove_provider_for_screen(screen, self._css_provider)
			self.remove_maxwidth()
			window.toggle_panes(self._show_panes)
			self.restore_bar_state()
			for widget in self._pathbar_widgets():
				widget.show()
			window.pageview.grab_focus()

	def save_bar_state(self):
		self._bar_state = (
			self.window.uistate['show_toolbar'],
			self.window.uistate['show_statusbar'],
		)

	def restore_bar_state(self):
		if self._bar_state is None:
			return
		show_toolbar, show_statusbar = self._bar_state
		self.window.toggle_toolbar(show_toolbar)
		self.window.toggle_statusbar(show_statusbar)

	def set_bar_state_fullscreen(self):
		self.window.toggle_menubar(not self.preferences['hide_menubar'])
		self.window.toggle_toolbar(not self.preferences['hide_toolbar'])
		self.window.toggle_statusbar(not self.preferences['hide_statusbar'])

	def insert_maxwidth(self):
		self._maxwidth = MaxWidth(self.preferences['max_page_width'])
		self.window.pageview.reparent(self._maxwidth)
		self.window.add(self._maxwidth)
		#widget_set_css(self._maxwidth, 'zim-distractionfree-bin',
		#	'border-top: %ipx solid; border-bottom: %ipx solid'
		#		% (self.preferences['vmargin'], self.preferences['vmargin'])
		#)
		self._maxwidth.set_border_width(self.preferences['vmargin'])
		self._maxwidth.show_all()

	def remove_maxwidth(self):
		self._maxwidth.remove(self.window.pageview)
		self.window.remove(self._maxwidth)
		self._maxwidth.destroy()
		self._maxwidth = None
		self.window.add(self.window.pageview)
		self.window.pageview.show_all()

	def _pathbar_widgets(self):
		# HACK - to much internals here ...
		for widget in self.window._zim_window_central_vbox.get_children():
			if widget == self.window._zim_window_top_minimized:
				break
			yield widget

	def teardown(self):
		self.restore_bar_state()


class MaxWidth(Gtk.Bin):

	def __init__(self, maxwidth):
		GObject.GObject.__init__(self)
		self.set_has_window(False)
		self.maxwidth = maxwidth

	def do_get_request_mode(self):
		'''Return what Gtk::SizeRequestMode is preferred by the container.'''
		child = self.get_child()
		return child.get_request_mode()

	def _adjust_preferred_width(self, minimum, natural):
		if minimum > self.maxwidth:
			return minimum, minimum
		elif natural > self.maxwidth:
			return minimum, self.maxwidth
		else:
			return minimum, natural

	def do_get_preferred_width(self):
		'''Calculate the minimum and natural width of the container.'''
		child = self.get_child()
		minimum, natural = child.get_preferred_width()
		return self._adjust_preferred_width(minimum, natural)

	def do_get_preferred_height(self):
		'''Calculate the minimum and natural height of the container.'''
		child = self.get_child()
		return child.get_preferred_height()

	def do_get_preferred_width_for_height(self, height):
		'''Calculate the minimum and natural width of the container, if it would be given the specified height.'''
		child = self.get_child()
		minimum, natural = child.get_preferred_width_for_height(height)
		return self._adjust_preferred_width(minimum, natural)

	def do_get_preferred_height_for_width(self, width):
		'''Calculate the minimum and natural height of the container, if it would be given the specified width.'''
		child = self.get_child()
		return child.get_preferred_height_for_width(width)

	def do_size_allocate(self, allocation):
		'''Position the child widgets, given the height and width that the container has actually been given.'''
		if allocation.width > self.maxwidth:
			child = self.get_child()
			minimum, natural = child.get_preferred_width_for_height(allocation.height)
			if minimum < self.maxwidth:
				allocation.x += int((allocation.width - self.maxwidth) / 2)
				allocation.width = self.maxwidth
		child = self.get_child()
		Gtk.Bin.do_size_allocate(self, allocation)
