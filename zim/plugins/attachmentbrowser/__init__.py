# -*- coding: utf-8 -*-
#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
#           2011-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# License:  same as zim (gpl)
#
#
# !! NOTE: when changing this plugin, do test performance on a folder with lots of photos!
#
# ChangeLog
# 2015-10-04 Reworked threads to better avoid blocking user interface (Jaap)
# 2013-03-03 Change to new plugin extension structure (Jaap)
# 2013-02-25 Added zooming icon size, made icon rendering more robust (Jaap)
# 2012-08-17 Added mimetype icons, statusbar toggle button, and gio monitor support (Jaap)
# 2012-07-20 Updated code for pane uistate (Jaap)
# 2012-04-17 Allow drag&drop when folder does not exist yet + fix drag&drop on windows (Jaap)
# 2012-02-29 Further work on making iconview look nice and support drag&drop (Jaap)
# 2012-02-27 Complete refactoring of thumbnail manager + test case (Jaap)
# 2012-02-26 Rewrote direct filessystem calls in order to support non-utf8 file systems (Jaap)
# 2011-01-25 Refactored widget and plugin code (Jaap)
#		tested on gtk < 2.12 (tooltip interface)
#		add pref for image magick (convert cmd exists on win32 but is not the same)
#		added buttons to side of widget
# 2011-01-02 Fixed use of uistate and updated for new framework to add to the mainwindow (Jaap)
# 2010-11-14 Fixed Bug 664551
# 2010-08-31 freedesktop.org thumbnail spec mostly implemented
# 2010-06-29 1st working version
#
# TODO:
# [ ] Action for deleting files in context menu
# [ ] Copy / cut files in context menu
# [ ] Button to clean up the folder - only show when the folder is empty
# [ ] Avoid scaling up small images when thumbnailing (check spec on this)
# [ ] Store failures as well


'''Zim plugin to display files in attachments folder.'''

import logging

import gtk


from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import toggle_action

from zim.gui.applications import open_folder_prompt_create

from zim.gui.widgets import Button, BOTTOM_PANE, PANE_POSITIONS, \
	IconButton, ScrolledWindow, \
	WindowSidePaneWidget, uistate_property


from .filebrowser import FileBrowserIconView, THUMB_SIZE_LARGE


logger = logging.getLogger('zim.plugins.attachmentbrowser')


MIN_ICON_ZOOM = 16
DEFAULT_ICON_ZOOM = 64



class AttachmentBrowserPlugin(PluginClass):

	plugin_info = {
		'name': _('Attachment Browser'), # T: plugin name
		'description': _('''\
This plugin shows the attachments folder of the current page as an
icon view at bottom pane.
'''), # T: plugin description
		'author': 'Thorsten Hackbarth <thorsten.hackbarth@gmx.de>\nJaap Karssenberg <jaap.karssenberg@gmail.com>',
		'help': 'Plugins:Attachment Browser',
	}

	plugin_preferences = (
		# key, type, label, default
		('pane', 'choice', _('Position in the window'), BOTTOM_PANE, PANE_POSITIONS),
			# T: option for plugin preferences

	#	('preview_size', 'int', _('Tooltip preview size [px]'), (THUMB_SIZE_MIN,480,THUMB_SIZE_MAX)), # T: input label
	#	('thumb_quality', 'int', _('Preview jpeg Quality [0..100]'), (0,50,100)), # T: input label
	#~	('use_imagemagick', 'bool', _('Use ImageMagick for thumbnailing'), False), # T: input label
	)

	#~ @classmethod
	#~ def check_dependencies(klass):
		#~ return [("ImageMagick",Application(('convert',None)).tryexec())]


@extends('MainWindow')
class AttachmentBrowserWindowExtension(WindowExtension):

	TAB_KEY = 'attachmentbrowser'

	uimanager_xml = '''
	<ui>
		<menubar name='menubar'>
			<menu action='view_menu'>
				<placeholder name="plugin_items">
					<menuitem action="toggle_attachmentbrowser" />
				</placeholder>
			</menu>
		</menubar>
		<toolbar name='toolbar'>
			<placeholder name='tools'>
				<toolitem action='toggle_attachmentbrowser'/>
			</placeholder>
		</toolbar>
	</ui>
	'''

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.preferences = plugin.preferences
		self._monitor = None

		# Init browser widget
		opener = self.window.navigation
		self.widget = AttachmentBrowserPluginWidget(self, opener, self.preferences)
			# FIXME FIXME FIXME - get rid of ui object here

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

		if self.window.page:
			self.on_page_changed(self.window, self.window.page)
		self.connectto(self.window, 'page-changed')

		self.connectto(self.window, 'pane-state-changed')

	def on_preferences_changed(self, preferences):
		if self.widget is None:
			return

		try:
			self.window.remove(self.widget)
		except ValueError:
			pass
		self.window.add_tab(self.TAB_KEY, self.widget, preferences['pane'])
		self.widget.show_all()

	@toggle_action(
		_('Attachment Browser'), # T: Menu item
		gtk.STOCK_DIRECTORY,
		tooltip=_('Show Attachment Browser') # T: Toolbar item tooltip
	)
	def toggle_attachmentbrowser(self, active):
		# This toggle is called to focus on our widget
		# but also after the fact when we detect focus changed
		# so check state explicitly and don't do more than needed
		visible, size, tab = self.window.get_pane_state(self.preferences['pane'])

		if active:
			if not (visible and tab == self.TAB_KEY):
				self.window.set_pane_state(
					self.preferences['pane'], True,
					activetab=self.TAB_KEY,
					grab_focus=True)
			# else pass
		else:
			if visible and tab == self.TAB_KEY:
				self.window.set_pane_state(
					self.preferences['pane'], False)
			# else pass

	def on_pane_state_changed(self, window, pane, visible, active):
		if pane != self.preferences['pane']:
			return

		if visible and active == self.TAB_KEY:
			self.toggle_attachmentbrowser(True)
		else:
			self.toggle_attachmentbrowser(False)

	def on_page_changed(self, window, page):
		self.widget.set_folder(
			window.notebook.get_attachments_dir(page)
		)

	def teardown(self):
		self.widget.iconview.teardown_folder()
		self.toggle_attachmentbrowser(False)
		self.window.remove(self.widget)
		if self.statusbar_frame:
			self.window.statusbar.remove(self.statusbar_frame)
		self.widget = None

	def destroy(self):
		self.widget.iconview.teardown_folder()


class AttachmentBrowserPluginWidget(gtk.HBox, WindowSidePaneWidget):
	'''Wrapper aroung the L{FileBrowserIconView} that adds the buttons
	for zoom / open folder / etc. ...
	'''

	title = _('Attachments') # T: label for attachment browser pane

	icon_size = uistate_property('icon_size', DEFAULT_ICON_ZOOM)

	def __init__(self, extension, opener, preferences):
		gtk.HBox.__init__(self)
		self.extension = extension # XXX
		self.opener = opener
		self.uistate = extension.uistate
		self.preferences = preferences
		self._close_button = None

		use_thumbs = self.preferences.setdefault('use_thumbnails', True) # Hidden setting
		self.iconview = FileBrowserIconView(opener, self.icon_size, use_thumbs)
		self.add(ScrolledWindow(self.iconview, shadow=gtk.SHADOW_NONE))

		self.buttonbox = gtk.VBox()
		self.pack_end(self.buttonbox, False)

		open_folder_button = IconButton(gtk.STOCK_OPEN, relief=False)
		open_folder_button.connect('clicked', self.on_open_folder)
		self.buttonbox.pack_start(open_folder_button, False)

		refresh_button = IconButton(gtk.STOCK_REFRESH, relief=False)
		refresh_button.connect('clicked', lambda o: self.on_refresh_button())
		self.buttonbox.pack_start(refresh_button, False)

		zoomin = IconButton(gtk.STOCK_ZOOM_IN, relief=False)
		zoomout = IconButton(gtk.STOCK_ZOOM_OUT, relief=False)
		zoomin.connect('clicked', lambda o: self.on_zoom_in())
		zoomout.connect('clicked', lambda o: self.on_zoom_out())
		self.buttonbox.pack_end(zoomout, False)
		self.buttonbox.pack_end(zoomin, False)
		self.zoomin_button = zoomin
		self.zoomout_button = zoomout

		self.set_icon_size(self.icon_size)

		self.iconview.connect('folder-changed', lambda o: self.update_title())

	def set_folder(self, folder):
		self.iconview.set_folder(folder)
		self.update_title()

	def update_title(self):
		n = len(self.iconview.get_model())
		self.set_title(ngettext('%i Attachment', '%i Attachments', n) % n)
		# T: Label for the statusbar, %i is the number of attachments for the current page

	def set_embeded_closebutton(self, button):
		if self._close_button:
			self.buttonbox.remove(self._close_button)

		if button is not None:
			self.buttonbox.pack_start(button, False)
			self.buttonbox.reorder_child(button, 0)

		self._close_button = button
		return True

	def on_open_folder(self, o):
		# Callback for the "open folder" button
		open_folder_prompt_create(self, self.iconview.folder)
		self.iconview.refresh()

	def on_refresh_button(self):
		self.iconview.refresh()
		self.update_title()

	def on_zoom_in(self):
		self.set_icon_size(
			min((self.icon_size * 2, THUMB_SIZE_LARGE))) # 16 > 32 > 64 > 128 > 256

	def on_zoom_out(self):
		self.set_icon_size(
			max((self.icon_size / 2, MIN_ICON_ZOOM))) # 16 < 32 < 64 < 128 < 256

	def set_icon_size(self, icon_size):
		self.iconview.set_icon_size(icon_size)
		self.zoomin_button.set_sensitive(False)
		self.zoomout_button.set_sensitive(False)
		self.zoomin_button.set_sensitive(icon_size < THUMB_SIZE_LARGE)
		self.zoomout_button.set_sensitive(icon_size > MIN_ICON_ZOOM)
		self.icon_size = icon_size # Do this last - avoid store state after fail
