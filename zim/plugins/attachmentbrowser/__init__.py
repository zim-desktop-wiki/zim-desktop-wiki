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

from gi.repository import Gtk
from gi.repository import GObject


from zim.plugins import PluginClass
from zim.actions import toggle_action

from zim.gui.pageview import PageViewExtension
from zim.gui.applications import open_folder_prompt_create

from zim.gui.widgets import BOTTOM_PANE, PANE_POSITIONS, \
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
		('use_thumbnails', 'bool', _('Use thumbnails'), True),
			# T: option for plugin preferences
		('thumbnail_svg', 'bool', _('Support thumbnails for SVG'), False),
			# T: option for plugin preferences
			# NOTE: svg cases crashes on some systems, so needs to be off by default

	#	('preview_size', 'int', _('Tooltip preview size [px]'), (THUMB_SIZE_MIN,480,THUMB_SIZE_MAX)), # T: input label
	#	('thumb_quality', 'int', _('Preview jpeg Quality [0..100]'), (0,50,100)), # T: input label
	#~	('use_imagemagick', 'bool', _('Use ImageMagick for thumbnailing'), False), # T: input label
	)

	#~ @classmethod
	#~ def check_dependencies(klass):
		#~ return [("ImageMagick",Application(('convert',None)).tryexec())]


class AttachmentBrowserWindowExtension(PageViewExtension):

	def __init__(self, plugin, window):
		PageViewExtension.__init__(self, plugin, window)
		self.preferences = plugin.preferences
		self._monitor = None

		# Init browser widget
		self.widget = AttachmentBrowserPluginWidget(self, self.navigation, self.preferences)

		if self.pageview.page is not None:
			self.on_page_changed(self.pageview, self.pageview.page)
		self.connectto(self.pageview, 'page-changed')

		self.add_sidepane_widget(self.widget, 'pane')

	def on_page_changed(self, pageview, page):
		self.widget.set_folder(
			pageview.notebook.get_attachments_dir(page)
		)

	def teardown(self):
		self.widget.iconview.teardown_folder()


class AttachmentBrowserPluginWidget(Gtk.HBox, WindowSidePaneWidget):
	'''Wrapper aroung the L{FileBrowserIconView} that adds the buttons
	for zoom / open folder / etc. ...
	'''

	title = _('Attachments') # T: label for attachment browser pane

	icon_size = uistate_property('icon_size', DEFAULT_ICON_ZOOM)

	def __init__(self, extension, opener, preferences):
		GObject.GObject.__init__(self)
		self.extension = extension # XXX
		self.opener = opener
		self.uistate = extension.uistate
		self.preferences = preferences
		self._close_button = None

		self.iconview = FileBrowserIconView(opener, self.icon_size)
		self.add(ScrolledWindow(self.iconview, shadow=Gtk.ShadowType.NONE))

		self.on_preferences_changed()
		self.preferences.connect('changed', self.on_preferences_changed)

		self.buttonbox = Gtk.VBox()
		self.pack_end(self.buttonbox, False, True, 0)

		open_folder_button = IconButton(Gtk.STOCK_OPEN, relief=False)
		open_folder_button.connect('clicked', self.on_open_folder)
		self.buttonbox.pack_start(open_folder_button, False, True, 0)

		refresh_button = IconButton(Gtk.STOCK_REFRESH, relief=False)
		refresh_button.connect('clicked', lambda o: self.on_refresh_button())
		self.buttonbox.pack_start(refresh_button, False, True, 0)

		zoomin = IconButton(Gtk.STOCK_ZOOM_IN, relief=False)
		zoomout = IconButton(Gtk.STOCK_ZOOM_OUT, relief=False)
		zoomin.connect('clicked', lambda o: self.on_zoom_in())
		zoomout.connect('clicked', lambda o: self.on_zoom_out())
		self.buttonbox.pack_end(zoomout, False, True, 0)
		self.buttonbox.pack_end(zoomin, False, True, 0)
		self.zoomin_button = zoomin
		self.zoomout_button = zoomout

		self.set_icon_size(self.icon_size)

		self.iconview.connect('folder-changed', lambda o: self.update_title())

	def on_preferences_changed(self, *a):
		self.iconview.set_use_thumbnails(self.preferences['use_thumbnails'])
		self.iconview.set_thumbnail_svg(self.preferences['thumbnail_svg'])

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
			self.buttonbox.pack_start(button, False, True, 0)
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
