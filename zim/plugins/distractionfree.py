# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import logging

from zim.plugins import PluginClass

from zim.gui import PATHBAR_NONE, PATHBAR_RECENT


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
		('hide_pathbar', 'bool', _('Hide pathbar in fullscreen mode'), True), # T: plugin preference
		('hide_statusbar', 'bool', _('Hide statusbar in fullscreen mode'), True), # T: plugin preference
		('max_page_width', 'int', _('Maximum page width'), 850, (_minsize, 10000)), # T: plugin preference
		('vmargin', 'int', _('Vertical margin'), 50, (0, 10000)), # T: plugin preference
		('basecolor', 'color', _('Text background color'), '#babdb6'), # T: plugin preference
		('textcolor', 'color', _('Text foreground color'), '#2e3436'), # T: plugin preference
		('bgcolor', 'color', _('Screen background color'), '#2e3436'), # T: plugin preference
		#('fgcolor', 'color', _('Screen foreground color'), '#eeeeec'),
	)

	def __init__(self, *a):
		self._normal_colors = None
		self._show_panes = True
		PluginClass.__init__(self, *a)

	def finalize_ui(self, ui):
		self.connectto(self.ui.mainwindow.pageview.view, 'size-allocate')
		self.connectto(self.ui.mainwindow, 'fullscreen-changed')
		self.do_preferences_changed()

	def do_preferences_changed(self):
		# Set show menubar & Update margins
		show_menubar = not self.preferences['hide_menubar']
		show_toolbar = not self.preferences['hide_toolbar']
		show_pathbar = not self.preferences['hide_pathbar']
		show_statusbar = not self.preferences['hide_statusbar']
		if self.ui.mainwindow.isfullscreen:
			self.ui.mainwindow.toggle_menubar(show_menubar)
			self.ui.mainwindow.toggle_toolbar(show_toolbar)
			self.ui.mainwindow.toggle_statusbar(show_statusbar)

			if show_pathbar \
			and self.ui.uistate['MainWindow']['pathbar_type_fullscreen'] == PATHBAR_NONE:
				self.ui.mainwindow.set_pathbar(PATHBAR_RECENT)
			elif not show_pathbar:
				self.ui.mainwindow.set_pathbar(PATHBAR_NONE)

			textview = self.ui.mainwindow.pageview.view
			self.on_size_allocate(textview, textview.get_allocation())
		else:
			self.ui.uistate['MainWindow']['show_menubar_fullscreen'] = show_menubar
			self.ui.uistate['MainWindow']['show_toolbar_fullscreen'] = show_toolbar
			self.ui.uistate['MainWindow']['show_statusbar_fullscreen'] = show_statusbar

			if show_pathbar \
			and self.ui.uistate['MainWindow']['pathbar_type_fullscreen'] == PATHBAR_NONE:
				self.ui.uistate['MainWindow']['pathbar_type_fullscreen'] = PATHBAR_RECENT
			elif not show_pathbar:
				self.ui.uistate['MainWindow']['pathbar_type_fullscreen'] = PATHBAR_NONE

		# TODO - would be nice to be able to toggle hide/show for pathbar without need to set type
		#        allow hiding container or seperate widget from "model"

	def on_fullscreen_changed(self, window):
		if window.isfullscreen:
			self._show_panes = bool(window.get_visible_panes())
			self._save_colors()
			self._set_colors(self._custom_colors)
			window.toggle_panes(show=False)
		elif self._normal_colors:
			self._set_colors(self._normal_colors)
			window.toggle_panes(show=self._show_panes)
			window.pageview.grab_focus()
		else:
			pass

	# NOTE: would be nice to change color of _all_ widgets when switching
	#       to fullscreen, but this is practically not possible because
	#       we can not set just the few colors in RcStyle, would need to
	#       switch the whole theme

	def _save_colors(self):
		style = self.ui.mainwindow.pageview.view.rc_get_style()
		self._normal_colors = []
		for state in (
			gtk.STATE_NORMAL,
			#gtk.STATE_ACTIVE,
			#gtk.STATE_PRELIGHT,
			#gtk.STATE_SELECTED,
			#gtk.STATE_INSENSITIVE
		):
			self._normal_colors.append({
				'base': style.base[gtk.STATE_NORMAL],
				'text': style.text[gtk.STATE_NORMAL],
				'bg': style.bg[gtk.STATE_NORMAL],
				#'fg': style.fg[gtk.STATE_NORMAL],
			})

	@property
	def _custom_colors(self):
		# array of NORMAL, ACTIVE, PRELIGHT, SELECTED, INSENSITIVE
		normal = {
			'base': self.preferences['basecolor'],
			'text': self.preferences['textcolor'],
			'bg': self.preferences['bgcolor'],
			#'fg': self.preferences['fgcolor'],
		}
		#selected = { # like normal, but reverse text and base
		#	'base': self.preferences['textcolor'],
		#	'text': self.preferences['basecolor'],
		#	'bg': self.preferences['bgcolor'],
		#	'fg': self.preferences['fgcolor'],
		#}
		#return [normal, normal, normal, selected, normal]
		return (normal,)


	def _set_colors(self, colors):
		# See gtk.RcStyle docs for all values in RC file
		rc = 'style "zim-colors"\n{\n'
		for i, state in enumerate((
			'NORMAL',
			#'ACTIVE',
			#'PRELIGHT',
			#'SELECTED',
			#'INSENSITIVE',
		)):
			values = colors[i]
			values['state'] = state
			rc += 	'\tbase[%(state)s] = "%(base)s"\n' \
				'\ttext[%(state)s] = "%(text)s"\n' \
				'\tbg[%(state)s] = "%(bg)s"\n' % values
				#'\tfg[%(state)s] = "%(fg)s"\n' % values

		#rc += '}\nclass "GtkWidget" style "zim-colors"'
		rc += '}\nwidget "*.zim-pageview" style "zim-colors"\n'

		logger.debug('Parse RC: >>>\n%s<<<', rc)
		gtk.rc_parse_string(rc)
		gtk.rc_reset_styles(gtk.settings_get_default())

	def on_size_allocate(self, textview, allocation):
		# Here we play with textview margin windows to position text
		# in center of screen with a maximum size
		if not self.ui.mainwindow.isfullscreen:
			self._set_margins(0, 0, 0, 0)
			return

		# Screen geometry
		screen = gtk.gdk.screen_get_default()
		root_window = screen.get_root_window()
		mouse_x, mouse_y, mouse_mods = root_window.get_pointer()
		current_monitor_number = screen.get_monitor_at_point(mouse_x, mouse_y)
		monitor_geometry = screen.get_monitor_geometry(current_monitor_number)
		screen_width = monitor_geometry.width
		screen_height = monitor_geometry.height

		# X max width based on user preference
		max_x = self.preferences['max_page_width']
		xmargin = int((screen_width - max_x)/2)
		if allocation.width > max_x:
			if allocation.x > xmargin:
				# we are bumped to the right
				left = _minmargin
				right = allocation.width - max_x
			elif (allocation.x + allocation.width) < (screen_width - xmargin):
				# we are bumped to the left
				left = allocation.width - max_x
				right = _minmargin
			else:
				# room on both sides
				left = xmargin - allocation.x
				right = allocation.width - max_x - left
		else:
			left = _minmargin
			right = _minmargin

		# Y setting simply keeps a small margin
		vmargin = self.preferences['vmargin']
		if vmargin > ((screen_height - _minsize) / 2):
			vmargin = ((screen_height - _minsize) / 2)

		if allocation.y < vmargin:
			top = vmargin - allocation.y
		else:
			top = _minmargin

		if (allocation.y + allocation.height) > (screen_height - vmargin):
			bottom = (allocation.y + allocation.height) - (screen_height - vmargin)
		else:
			bottom = _minmargin

		self._set_margins(left, right, top, bottom)

	def _set_margins(self, left, right, top, bottom):
		self.ui.mainwindow.pageview.view.set_border_window_size(gtk.TEXT_WINDOW_LEFT, left)
		self.ui.mainwindow.pageview.view.set_border_window_size(gtk.TEXT_WINDOW_RIGHT, right)
		self.ui.mainwindow.pageview.view.set_border_window_size(gtk.TEXT_WINDOW_TOP, top)
		self.ui.mainwindow.pageview.view.set_border_window_size(gtk.TEXT_WINDOW_BOTTOM, bottom)

	def destroy(self):
		# show at least menubar again, set margins to zero & restore colors
		self.ui.uistate['MainWindow']['show_menubar_fullscreen'] = True
		self._set_margins(0, 0, 0, 0)
		if self._normal_colors:
			self._set_colors(self._normal_colors)
		PluginClass.destroy(self)

