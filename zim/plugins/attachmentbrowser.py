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


# Thumbnail handling following freedesktop.org spec mostly
#
# Spec version May 2012 -- http://specifications.freedesktop.org/thumbnail-spec/thumbnail-spec-latest.html
# * storage
# 	* XDG_CACHE_HOME/thumbnails/normal <= 128 x 128
# 	* XDG_CACHE_HOME/thumbnails/large <= 256 x 256
# 	* XDG_CACHE_HOME/thumbnails/fail
# * thumbnail file creation
# 	* Name is md5 hex of full uri
# 	* Must have PNG attributes for mtime and uri (if mtime cannot be determined, do not create a thumbnail)
# 	* Must write as tmp file in same dir and then rename atomic
# 	* Permissions on files must be 0600 --> manager
# * lookup / recreate
# 	* Must equal orig mtime vs thumbnail mtime property (not thumbnail file mtime)
# 	* Only store failures for permanent failures, to prevent re-doing them
# 	* Failure is app specific, so subdir with app name and version
# 	* Failure record is just empty png
#	* Don't attempt creation when not readable (do not store failure)
#
# Uri according to RFC 2396
# * file/// for files on localhost
# * No clear consensus on encoding and white space - do most strict version
#
# The ThumbnailCreator should take case of the png attributes and
# the usage of tmp file + atomic rename (on unix)
# The ThumbnailManager implements the rest of the spec
#
# File.uri is already encoded, don't do anything else here



'''Zim plugin to display files in attachments folder.'''


import os
import re
import hashlib
import datetime
import logging
import threading
import Queue

import gobject
import gtk
import pango
try:
	import gio
except ImportError:
	gio = None


import zim
import zim.config # Asserts HOME is defined

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import toggle_action

from zim.fs import File, Dir, format_file_size
from zim.config import XDG_CACHE_HOME

from zim.gui.widgets import Button, BOTTOM_PANE, PANE_POSITIONS, \
	IconButton, ScrolledWindow, button_set_statusbar_style, \
	WindowSidePaneWidget, rotate_pixbuf
from zim.gui.applications import OpenWithMenu
from zim.gui.clipboard import \
	URI_TARGETS, URI_TARGET_NAMES, \
	pack_urilist, unpack_urilist


logger = logging.getLogger('zim.plugins.attachmentbrowser')


# freedesktop.org spec
LOCAL_THUMB_STORAGE_NORMAL = XDG_CACHE_HOME.subdir('thumbnails/normal')
LOCAL_THUMB_STORAGE_LARGE = XDG_CACHE_HOME.subdir('thumbnails/large')
LOCAL_THUMB_STORAGE_FAIL = XDG_CACHE_HOME.subdir('thumbnails/fail/zim-%s' % zim.__version__)

THUMB_SIZE_NORMAL = 128
THUMB_SIZE_LARGE = 256

# For plugin
MIN_THUMB_SIZE = 64 # don't render thumbs when icon size is smaller than this
MAX_ICON_SIZE = 128 # never render icons larger than this - thumbs go up

MIN_ICON_ZOOM = 16
DEFAULT_ICON_ZOOM = 64


_last_warning_missing_icon = None
	# used to surpress redundant logging



####### TODO add in utils ?
class uistate_property(object):

	# TODO add hook such that it will be initialized on init of owner obj

	def __init__(self, key, *default):
		self.key = key
		self.default = default
		self._initialized = False

	def __get__(self, obj, klass):
		if obj:
			if not self._initialized:
				obj.uistate.setdefault(self.key, *self.default)
				self._initialized = True
			return obj.uistate[self.key]

	def __set__(self, obj, value):
		obj.uistate[self.key] = value
#######

### TODO - put this in zim.fs
def get_mime_icon(file, size):
	if not gio:
		return None

	try:
		f = gio.File(uri=file.uri)
		info = f.query_info('standard::*')
		icon = info.get_icon()
	except:
		logger.exception('Failed to query info for file: %s', file)
		return None

	global _last_warning_missing_icon

	if isinstance(icon, gio.ThemedIcon):
		names = icon.get_names()
		icon_theme = gtk.icon_theme_get_default()
		try:
			icon_info = icon_theme.choose_icon(names, size, 0)
			if icon_info:
				return icon_info.load_icon()
			else:
				if _last_warning_missing_icon != names:
					logger.debug('Missing icons in icon theme: %s', names)
					_last_warning_missing_icon = names
				return None
		except gobject.GError:
			logger.exception('Could not load icon for file: %s', file)
			return None
	else:
		return None


def get_mime_description(mimetype):
	# Check XML file /usr/share/mime/MEDIA/SUBTYPE.xml
	# Find element "comment" with "xml:lang" attribute for the locale
	from zim.config import XDG_DATA_DIRS

	media, subtype = mimetype.split('/', 1)
	for dir in XDG_DATA_DIRS:
		file = dir.file(('mime', media, subtype + '.xml'))
		if file.exists():
			return _read_comment_from(file)
	else:
		return None


def _read_comment_from(file):
	import locale
	from zim.formats import ElementTreeModule as et
	# Etree fills in the namespaces which obfuscates the names

	mylang, enc = locale.getdefaultlocale()
	xmlns = "{http://www.w3.org/XML/1998/namespace}"
	xml = et.parse(file.path)
	fallback = []
	#~ print "FIND COMMENT", file, mylang
	for elt in xml.getroot():
		if elt.tag.endswith('comment'):
			lang = elt.attrib.get(xmlns+'lang', '')
			if lang == mylang:
				return elt.text
			elif not lang or mylang.startswith(lang+'_'):
				fallback.append((lang, elt.text))
			else:
				pass
	else:
		#~ print "FALLBACK", fallback
		if fallback:
			fallback.sort()
			return fallback[-1][1] # longest match
		else:
			return None


#### TODO put in zim.fs, remove in dir iter by default
def is_hidden_file(file):
	# FIXME put this in zim.fs
	if os.name != 'nt':
		return file.basename.startswith('.')

	import ctypes
	INVALID_FILE_ATTRIBUTES = -1
	FILE_ATTRIBUTE_HIDDEN = 2

	try:
		attrs = ctypes.windll.kernel32.GetFileAttributesW(file.path)
			# note: GetFileAttributesW is unicode version of GetFileAttributes
	except AttributeError:
		return False
	else:
		if attrs == INVALID_FILE_ATTRIBUTES:
			return False
		else:
			return bool(attrs & FILE_ATTRIBUTE_HIDDEN)
###


def render_file_icon(widget, size):
	# Sizes defined in gtk source,
	# gtkiconfactory.c for gtk+ 2.18.9
	#
	#	(gtk.ICON_SIZE_MENU, 16),
	#	(gtk.ICON_SIZE_BUTTON, 20),
	#	(gtk.ICON_SIZE_SMALL_TOOLBAR, 18),
	#	(gtk.ICON_SIZE_LARGE_TOOLBAR, 24),
	#	(gtk.ICON_SIZE_DND, 32),
	#	(gtk.ICON_SIZE_DIALOG, 48),
	#
	# We expect sizes in list: 16, 32, 64, 128
	# But only give back 16 or 32, bigger icons
	# do not look good
	assert size in (16, 32, 64, 128)
	if size == 16:
		pixbuf = widget.render_icon(gtk.STOCK_FILE, gtk.ICON_SIZE_MENU)
	else:
		pixbuf = widget.render_icon(gtk.STOCK_FILE, gtk.ICON_SIZE_DND)

	# Not sure how much sizes depend on theming,
	# so we scale down if needed, do not scale up
	if pixbuf.get_width() > size or pixbuf.get_height() > size:
		return pixbuf.scale_simple(size, size, gtk.gdk.INTERP_BILINEAR)
	else:
		return pixbuf


class AttachmentBrowserPlugin(PluginClass):

	plugin_info = {
		'name': _('Attachment Browser ALT'), # T: plugin name
		'description': _('''\
This plugin shows the attachments folder of the current page as an
icon view at bottom pane.

This plugin is still under development.
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

	TAB_NAME = _('Attachments') # T: label for attachment browser pane

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

		# Init statusbar button
		self.statusbar_frame = gtk.Frame()
		self.statusbar_frame.set_shadow_type(gtk.SHADOW_IN)
		self.window.statusbar.pack_end(self.statusbar_frame, False)

		self.statusbar_button = gtk.ToggleButton('<attachments>') # translated below
		button_set_statusbar_style(self.statusbar_button)

		self.statusbar_button.set_use_underline(True)
		self.__class__.toggle_attachmentbrowser.connect_actionable(
			self, self.statusbar_button)

		self.statusbar_frame.add(self.statusbar_button)
		self.statusbar_frame.show_all()

		# Init browser widget
		opener = self.window.get_resource_opener()
		self.widget = AttachmentBrowserPluginWidget(self, opener, self.preferences)
			# FIXME FIXME FIXME - get rid of ui object here

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

		# XXX
		if self.window.ui.page:
			self.on_open_page(self.window.ui, self.window.ui.page, self.window.ui.page)
		self.connectto(self.window.ui, 'open-page')
		self.connectto(self.window.ui, 'close-page')

		self.connectto(self.window, 'pane-state-changed')

	def on_preferences_changed(self, preferences):
		if self.widget is None:
			return

		try:
			self.window.remove(self.widget)
		except ValueError:
			pass
		self.window.add_tab(self.TAB_NAME, self.widget, preferences['pane'])
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
			if not (visible and tab == self.TAB_NAME):
				self.window.set_pane_state(
					self.preferences['pane'], True,
					activetab=self.TAB_NAME,
					grab_focus=True)
			# else pass
		else:
			if visible and tab == self.TAB_NAME:
				self.window.set_pane_state(
					self.preferences['pane'], False)
			# else pass

	def on_pane_state_changed(self, window, pane, visible, active):
		if pane != self.preferences['pane']:
			return

		if visible and active == self.TAB_NAME:
			self.toggle_attachmentbrowser(True)
		else:
			self.toggle_attachmentbrowser(False)

	def on_open_page(self, ui, page, path):
		dir = self.window.ui.notebook.get_attachments_dir(page) # XXX -> page.get_attachemnts_dir()
		self.widget.iconview.set_folder(dir)
		self._refresh_statusbar()

	def on_close_page(self, ui, page, final):
		self.widget.iconview.teardown_folder()

	def _refresh_statusbar(self):
		model = self.widget.iconview.get_model() # XXX
		n = len(model)
		self.statusbar_button.set_label(
			ngettext('%i _Attachment', '%i _Attachments', n) % n)
			# T: Label for the statusbar, %i is the number of attachments for the current page

	def teardown(self):
		self.widget.iconview.teardown_folder()
		self.toggle_attachmentbrowser(False)
		self.window.remove(self.widget)
		if self.statusbar_frame:
			self.window.statusbar.remove(self.statusbar_frame)
		self.widget = None



class AttachmentBrowserPluginWidget(gtk.HBox, WindowSidePaneWidget):

	'''Wrapper aroung the L{FileBrowserIconView} that adds the buttons
	for zoom / open folder / etc. ...
	'''

	icon_size = uistate_property('icon_size', DEFAULT_ICON_ZOOM)

	def __init__(self, extension, opener, preferences):
		gtk.HBox.__init__(self)
		self.extension = extension # XXX
		self.opener = opener
		self.uistate = extension.uistate
		self.preferences = preferences

		use_thumbs = self.preferences.setdefault('use_thumbnails', True) # Hidden setting
		self.iconview = FileBrowserIconView(opener, self.icon_size, use_thumbs)
		self.add(ScrolledWindow(self.iconview))

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

		self.iconview.connect('folder-changed', lambda o: self.extension._refresh_statusbar())

	def embed_closebutton(self, button):
		if button:
			self.buttonbox.pack_start(button, False)
			self.buttonbox.reorder_child(button, 0)
		else:
			for widget in self.buttonbox.get_children():
				if hasattr(widget, 'window_close_button'):
					self.buttonbox.remove(widget)
		return True

	def on_open_folder(self, o):
		# Callback for the "open folder" button
		self.opener.open_dir(self.iconview.folder)
		self.iconview.refresh()

	def on_refresh_button(self):
		self.iconview.refresh()
		self.extension._refresh_statusbar() # XXX

	def on_zoom_in(self):
		self.set_icon_size(
			min((self.icon_size * 2, THUMB_SIZE_LARGE))) # 16 > 32 > 64 > 128 > 256

	def on_zoom_out(self):
		self.set_icon_size(
			max((self.icon_size/2, MIN_ICON_ZOOM))) # 16 < 32 < 64 < 128 < 256

	def set_icon_size(self, icon_size):
		self.iconview.set_icon_size(icon_size)
		self.zoomin_button.set_sensitive(False)
		self.zoomout_button.set_sensitive(False)
		self.zoomin_button.set_sensitive(icon_size < THUMB_SIZE_LARGE)
		self.zoomout_button.set_sensitive(icon_size > MIN_ICON_ZOOM)
		self.icon_size = icon_size # Do this last - avoid store state after fail


BASENAME_COL = 0
PIXBUF_COL = 1
MTIME_COL = 2

class FileBrowserIconView(gtk.IconView):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'folder_changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, opener, icon_size=THUMB_SIZE_NORMAL, use_thumbnails=True):
		self.opener = opener
		self.use_thumbnails = use_thumbnails
		self.icon_size = None
		self.folder = None
		self._thumbnailer = ThumbnailQueue()
		self._idle_event_id = None
		self._monitor = None
		self._mtime = None

		gtk.IconView.__init__(self,
			gtk.ListStore(str, gtk.gdk.Pixbuf, object) ) # BASENAME_COL, PIXBUF_COL, MTIME_COL
		self.set_text_column(BASENAME_COL)
		self.set_pixbuf_column(PIXBUF_COL)
		self.set_icon_size(icon_size)

		self.enable_model_drag_source(
			gtk.gdk.BUTTON1_MASK,
			URI_TARGETS,
			gtk.gdk.ACTION_LINK | gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE )
		self.enable_model_drag_dest(
			URI_TARGETS,
			gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE )
		self.connect('drag-data-get', self.on_drag_data_get)
		self.connect('drag-data-received', self.on_drag_data_received)

		if gtk.gtk_version >= (2, 12) \
		and gtk.pygtk_version >= (2, 12):
			# custom tooltip
			self.props.has_tooltip = True
			self.connect("query-tooltip", self._query_tooltip_cb)

		# Store colors
		self._sensitive_color = None
		self._insensitive_color = None

		def _init_base_color(*a):
			# This is handled on expose event, because style does not
			# yet reflect theming on construction
			self._sensitive_color = self.style.base[gtk.STATE_NORMAL]
			self._insensitive_color = self.style.base[gtk.STATE_INSENSITIVE]
			self._update_state()
			self.disconnect(self._expose_event_id) # only need this once

		self._expose_event_id = self.connect('expose-event', _init_base_color)
		self.connect('button-press-event', self.on_button_press_event)
		self.connect('item-activated', self.on_item_activated)


	def set_icon_size(self, icon_size):
		self.icon_size = icon_size
		self.refresh(icon_size_changed=True)

	def set_folder(self, folder):
		self.teardown_folder() # clears _thumbnailer and _monitor
		self.folder = folder

		self.refresh()

		id = self.folder.connect('changed', self._on_folder_changed)
		self._monitor = (self.folder, id)

	def refresh(self, icon_size_changed=False):
		if self.folder is None:
			return # Not yet initialized
		else:
			try:
				self._mtime = self.folder.mtime()
			except OSError: # folder went missing?
				self.teardown_folder()
				self._update_state()
				return
			else:
				self._update_state()

		#~ import time
		#~ print "start", time.time()

		self._thumbnailer.clear_queue()
		if self._idle_event_id:
			gobject.source_remove(self._idle_event_id)
			self._idle_event_id = None

		# Get cache, clear model
		cache = {}
		model = self.get_model()
		for str, pixbuf, mtime in model:
			cache[str] = (pixbuf, mtime)
		model.clear()

		# Cache for mime icons - speed up lookup
		min_icon_size = min((self.icon_size, MAX_ICON_SIZE)) # Avoid huge icons
		file_icon = render_file_icon(self, min_icon_size)
		mime_cache = {}
		def my_get_mime_icon(file):
			mt = file.get_mimetype()
			if not mt in mime_cache:
				mime_cache[mt] = get_mime_icon(file, min_icon_size) or file_icon
			return mime_cache[mt]

		# Add (new) files & queue thumbnails
		max_text = 1
		show_thumbs = self.use_thumbnails and self.icon_size >= MIN_THUMB_SIZE
		for basename in self.folder.list():
			file = self.folder.file(basename)
			if file.isdir() or is_hidden_file(file):
				continue

			max_text = max(max_text, len(basename))

			pixbuf, mtime = cache.pop(basename, (None, None))
			if show_thumbs and file.isimage():
				if not pixbuf:
					pixbuf = my_get_mime_icon(file) # temporary icon
					mtime = None

				if icon_size_changed:
					self._thumbnailer.queue_thumbnail_request(file, self.icon_size)
				else:
					self._thumbnailer.queue_thumbnail_request(file, self.icon_size, mtime)
			elif pixbuf is None or icon_size_changed:
				pixbuf = my_get_mime_icon(file)
				mtime  = None
			else:
				pass # re-use from cache

			model.append((basename, pixbuf, mtime))

		self._set_orientation_and_size(max_text)

		if not self._thumbnailer.queue_empty():
			self._thumbnailer.start() # delay till here - else reduces our speed on loading
			self._idle_event_id = \
				gobject.idle_add(self._on_check_thumbnail_queue)

		#~ print "stop ", time.time()

	def _on_check_thumbnail_queue(self):
		file, size, thumbfile, pixbuf, mtime = \
			self._thumbnailer.get_ready_thumbnail()
		if file is not None:
			basename = file.basename
			model = self.get_model()
			def update(model, path, iter):
				if model[iter][BASENAME_COL] == basename:
					model[iter][PIXBUF_COL] = pixbuf
					model[iter][MTIME_COL] = mtime
			model.foreach(update)

		cont = not self._thumbnailer.queue_empty()
		if not cont:
			self._idle_event_id = None
		return cont # if False event is stopped

	def _set_orientation_and_size(self, max_text_length):
		# Set item width to force wrapping text for long items
		# Set to icon size + some space for padding etc.
		# And set orientation etc.
		text_size = max_text_length * 13 # XXX assume 13x per char
		icon_size = self.icon_size

		if icon_size < 64:
			# Text next to the icons
			if icon_size > 16 and max_text_length > 15:
				# Wrap text over 2 rows
				self.set_item_width(
					icon_size + int((text_size+1) / 2) )
			else:
				# Single row
				self.set_item_width(icon_size + text_size)

			self.set_orientation(gtk.ORIENTATION_HORIZONTAL)
			self.set_row_spacing(0)
			self.set_column_spacing(0)
		else:
			# Text below the icons
			self.set_item_width(max((icon_size + 12, 96)))
			self.set_orientation(gtk.ORIENTATION_VERTICAL)
			self.set_row_spacing(3)
			self.set_column_spacing(3)

	def _update_state(self):
		# Here we set color like sensitive or insensitive widget without
		# really making the widget insensitive - reason is to allow
		# drag & drop for a non-existing folder; making the widget
		# insensitive also blocks drag & drop.
		if self.folder is None or not self.folder.exists():
			self.modify_base(
				gtk.STATE_NORMAL, self._insensitive_color)
		else:
			self.modify_base(
				gtk.STATE_NORMAL, self._sensitive_color)

	def teardown_folder(self):
		try:
			if self._monitor:
				dir, id = self._monitor
				dir.disconnect(id)
		except:
			logger.exception('Could not cancel file monitor')
		finally:
			self._monitor = None

		if self._idle_event_id:
			gobject.source_remove(self._idle_event_id)
			self._idle_event_id = None

		try:
			self._thumbnailer.clear_queue()
		except:
			logger.exception('Could not stop thumbnailer')

		self.get_model().clear()

	def _on_folder_changed(self, *a):
		if self.folder and self.folder.mtime() != self._mtime:
			logger.debug('Folder change detected: %s', self.folder)
			self.refresh()
			self.emit('folder-changed')

	def on_item_activated(self, iconview, path):
		store = iconview.get_model()
		iter = store.get_iter(path)
		file = self.folder.file(store[iter][BASENAME_COL])
		self.opener.open_file(file)

	def on_button_press_event(self, iconview, event):
		# print 'on_button_press_event'
		if event.button == 3:
			popup_menu=gtk.Menu()
			x = int(event.x)
			y = int(event.y)
			time = event.time
			pathinfo = iconview.get_path_at_pos(x, y)
			if pathinfo is not None:
				iconview.grab_focus()
				popup_menu.popup(None, None, None, event.button, time)
				self.do_populate_popup(popup_menu, pathinfo)
					# FIXME should use a signal here
				return True
		return False

	def do_populate_popup(self, menu, pathinfo):
		# print "do_populate_popup"
		store = self.get_model()
		iter = store.get_iter(pathinfo)
		file = self.folder.file(store[iter][BASENAME_COL])

		item = gtk.MenuItem(_('Open With...')) # T: menu item
		menu.prepend(item)

		window = self.get_toplevel()
		submenu = OpenWithMenu(window, file) # XXX any widget should do to find window
		item.set_submenu(submenu)

		item = gtk.MenuItem(_('_Open')) # T: menu item to open file or folder
		item.connect('activate', lambda o: self.opener.open_file(file))
		menu.prepend(item)

		menu.show_all()

	def _query_tooltip_cb(self, widget, x, y, keyboard_tip, tooltip):
		context = widget.get_tooltip_context(x, y, keyboard_tip)
		if not context:
			return False

		thumbman = ThumbnailManager()
		model, path, iter = context
		name = model[iter][BASENAME_COL]
		file = self.folder.file(name)
		mtime = file.mtime()
		if mtime:
			mdate = datetime.datetime.fromtimestamp(file.mtime()).strftime('%c')
			# TODO: fix datetime format
		else:
			mdate = _('Unknown') # T: unspecified value for file modification time
		size = format_file_size(file.size())

		thumbfile, pixbuf = thumbman.get_thumbnail(file, THUMB_SIZE_LARGE)
		if not pixbuf:
			pixbuf = get_mime_icon(file, 64) or render_file_icon(self, 64)

		mtype = file.get_mimetype()
		mtype_desc = get_mime_description(mtype)
		if mtype_desc:
			mtype_desc = mtype_desc + " (%s)" % mtype # E.g. "PDF document (application/pdf)"

		f_label = _('Name') # T: label for file name
		t_label = _('Type') # T: label for file type
		s_label = _('Size') # T: label for file size
		m_label = _('Modified') # T: label for file modification date
		tooltip.set_markup(
			"%s\n\n<b>%s:</b> %s\n<b>%s:</b> %s\n<b>%s:</b>\n%s" % (
				name,
				t_label, mtype_desc or mtype,
				s_label, size,
				m_label, mdate,
			))
		tooltip.set_icon(pixbuf)
		widget.set_tooltip_item(tooltip, path)

		return True

	# TODO - test drag and drop
	def on_drag_data_get(self, iconview, dragcontext, selectiondata, info, time):
		assert selectiondata.target in URI_TARGET_NAMES
		paths = self.iconview.get_selected_items()
		if paths:
			model = self.iconview.get_model()
			path_to_uri = lambda p: self.folder.file(model[p][BASENAME_COL]).uri
			uris = map(path_to_uri, paths)
			data = pack_urilist(uris)
			selectiondata.set(URI_TARGET_NAMES[0], 8, data)

	def on_drag_data_received(self, iconview, dragcontext, x, y, selectiondata, info, time):
		assert selectiondata.target in URI_TARGET_NAMES
		names = unpack_urilist(selectiondata.data)
		files = [File(uri) for uri in names if uri.startswith('file://')]
		action = dragcontext.action
		logger.debug('Drag received %s, %s', action, files)

		if action == gtk.gdk.ACTION_MOVE:
			self._move_files(files)
		elif action == gtk.gdk.ACTION_ASK:
			menu = gtk.Menu()

			item = gtk.MenuItem(_('_Move Here')) # T: popup menu action on drag-drop of a file
			item.connect('activate', lambda o: self._move_files(files))
			menu.append(item)

			item = gtk.MenuItem(_('_Copy Here')) # T: popup menu action on drag-drop of a file
			item.connect('activate', lambda o: self._copy_files(files))
			menu.append(item)

			menu.append(gtk.SeparatorMenuItem())
			item = gtk.MenuItem(_('Cancel')) # T: popup menu action on drag-drop of a file
			# cancel action needs no action
			menu.append(item)

			menu.show_all()
			menu.popup(None, None, None, 1, time)
		else:
			# Assume gtk.gdk.ACTION_COPY or gtk.gdk.ACTION_DEFAULT
			# on windows we get "0" which is not mapped to any action
			self._copy_files(files)

	def _move_files(self, files):
		for file in files:
			newfile = self.folder.new_file(file.basename)
			file.rename(newfile)

		self.refresh()

	def _copy_files(self, files):
		for file in files:
			newfile = self.folder.new_file(file.basename)
			file.copyto(newfile)

		self.refresh()


class ThumbnailCreatorFailure(ValueError):
	pass


if os.name == 'nt':
	assert False, "Put code for atomic rename here"
else:
	atomic_rename = os.rename


def pixbufThumbnailCreator(file, thumbfile, thumbsize):
	'''Thumbnailer implementation that uses the C{gtk.gdk.Pixbuf}
	functions to create the thumbnail.
	'''
	tmpfile = thumbfile.dir.file('zim-thumb.new~')
	options = {
		'tEXt::Thumb::URI': file.uri,
		'tEXt::Thumb::MTime': str( int( file.mtime() ) ),
	}
	try:
		pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.encodedpath, thumbsize, thumbsize)
		pixbuf = rotate_pixbuf(pixbuf)
		pixbuf.save(tmpfile.encodedpath, 'png', options)
		atomic_rename(tmpfile.encodedpath, thumbfile.encodedpath)
	except:
		raise ThumbnailCreatorFailure
	else:
		return pixbuf


class ThumbnailQueue(object):

	'''Wrapper for L{ThumbnailManager} that does that actual thumbnailing
	in a separate thread and manages the requests and the results with
	queues.
	'''

	def __init__(self, thumbnailcreator=pixbufThumbnailCreator):
		self._thread = None
		self._in_queue = Queue.Queue()
		self._out_queue = Queue.Queue()
		self._thumbmanager = ThumbnailManager(thumbnailcreator)
		self._count = 0
		self._count_lock = threading.Lock()
		self._running = threading.Event()

	def queue_empty(self):
		'''Returns C{True} when both input and output queue are empty'''
		# Guard total count of items in process
		# input + output + in between in main function
		# use lock to protect queue
		return self._count == 0

	def queue_thumbnail_request(self, file, size, mtime=None):
		'''Add a new request to the queue
		@param file: a L{File} object
		@param size: the size of the thumbnail in pixels
		@param mtime: the mtime of a previous loaded thumbnail, if this
		matches the current file, the request will be dropped
		'''
		with self._count_lock:
			self._count += 1
			self._in_queue.put_nowait((file, size, mtime))

	def start(self):
		if not (self._thread and self._thread.is_alive()):
			self._running.set()
			self._thread = threading.Thread(
				name=self.__class__.__name__,
				target=self._thread_main,
			)
			self._thread.setDaemon(True)
			self._thread.start()

	def _thread_main(self):
		# Loop executed in the thread
		import time
		try:
			while self._running.is_set():
				time.sleep(0.1) # give other threads a change as well
				file, size, mtime = self._in_queue.get_nowait()
				self._in_queue.task_done()

				try:
					if mtime and file.mtime() == mtime:
						self._count -= 1 # skip
					else:
						mtime = file.mtime()
						thumbfile, pixbuf = self._thumbmanager.get_thumbnail(file, size)
						if thumbfile and pixbuf:
							self._out_queue.put_nowait((file, size, thumbfile, pixbuf, mtime))
						else:
							self._count -= 1 # skip
				except:
					logger.exception('Exception in thumbnail queue')
					self._count -= 1 # drop
		except Queue.Empty:
			pass
		finally:
			self._running.clear()

	def get_ready_thumbnail(self, block=False):
		'''Check output queue for a thumbnail that is ready
		@returns: a 5-tuple C{(file, size, thumbfile, pixbuf, mtime)} or 5 times
		C{None} when nothing is ready and C{block} is C{False}.
		'''
		with self._count_lock:
			try:
				file, size, thumbfile, pixbuf, mtime = self._out_queue.get(block=block)
				self._out_queue.task_done()
				assert self._count > 0
				self._count -= 1
				return file, size, thumbfile, pixbuf, mtime
			except Queue.Empty:
				return (None, None, None, None, None)

	def clear_queue(self):
		def _clear_queue(queue):
				try:
					while True:
						queue.get_nowait()
						queue.task_done()
				except Queue.Empty:
					pass

		with self._count_lock: # nothing in or out while locked!
			self._running.clear() # stop thread from competing with us
			_clear_queue(self._in_queue)

			if self._thread and self._thread.is_alive():
				self._thread.join()
				self._thread = None

			_clear_queue(self._out_queue)

			self._count = 0


class ThumbnailManager(object):
	'''This class implements thumbnails management (mostly) following
	the C{freedesktop.org} spec.
	'''

	def __init__(self, thumbnailcreator=pixbufThumbnailCreator):
		self._thumbnailcreator = thumbnailcreator

	def get_thumbnail_file(self, file, size):
		'''Get L{File} object for thumbnail
		Does not guarantee that the thumbnail actually exists.
		Do not use this method to lookup the thumbnail, use L{get_thumbnail()}
		instead.
		@param file: the original file to be thumbnailed
		@param size: thumbnail size in pixels (C{THUMB_SIZE_NORMAL}, C{THUMB_SIZE_LARGE}, or integer)
		@returns: a L{File} object
		'''
		basename = hashlib.md5(file.uri).hexdigest() + '.png'
		if size <= THUMB_SIZE_NORMAL:
			return LOCAL_THUMB_STORAGE_NORMAL.file(basename)
		else:
			return LOCAL_THUMB_STORAGE_LARGE.file(basename)

	def get_thumbnail(self, file, size, create=True):
		'''Looksup thumbnail and return it if a valid thumbnail is
		availabel.
		@param file: the file to be thumbnailed as L{File} object
		@param size: pixel size for thumbnail image as integer
		@param create: if C{True} we try to create the thumbnail if
		it doesn't exist
		@returns: a 2-tuple of the thumbnail file and a pixbuf object
		or 2 times C{None}
		'''
		thumbfile = self.get_thumbnail_file(file, size)
		if thumbfile.exists():
			# Check the thumbnail is valid
			pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(thumbfile.encodedpath, size, size)
			mtime = pixbuf.get_option('tEXt::Thumb::MTime')
			if mtime and int(mtime) == int(file.mtime()):
				return thumbfile, pixbuf
			else:
				pass # according to spec recreate when option is missing

		if create:
			try:
				return self.create_thumbnail(file, size)
			except ThumbnailCreatorFailure:
				return None, None
		else:
			return None, None

	def create_thumbnail(self, file, size):
		'''(Re-)create a thumbnail without any checking whether the
		old one is still valid.
		@param file: the file to be thumbnailed as L{File} object
		@param size: pixel size for thumbnail file as integer
		@returns: a 2-tuple of the thumbnail file and a pixbuf object
		@raises ThumbnailCreatorFailure: if creation fails unexpectedly
		'''
		thumbfile = self.get_thumbnail_file(file, size)
		thumbsize = THUMB_SIZE_NORMAL if size <= THUMB_SIZE_NORMAL else THUMB_SIZE_LARGE

		thumbfile.dir.touch(mode=0700)
		pixbuf = self._thumbnailcreator(file, thumbfile, thumbsize)
		os.chmod(thumbfile.encodedpath, 0600)

		if not pixbuf:
			pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(thumbfile.encodedpath, size, size)
		elif thumbsize != size:
			w, h = pixbuf.get_width(), pixbuf.get_height()
			sw, sh = (size, int(size*float(h)/w)) if (w > h) else (int(size*float(w)/h), size)
			pixbuf = pixbuf.scale_simple(sw, sh, gtk.gdk.INTERP_NEAREST)

		return thumbfile, pixbuf

	def remove_thumbnails(self, file):
		'''Remove thumbnails for at all sizes
		To be used when thumbnails are outdated, e.g. when the original
		file is removed or updated.
		@param file: the original file
		'''
		for size in (THUMB_SIZE_NORMAL, THUMB_SIZE_LARGE):
			thumbfile = self.get_thumbnail_file(file, size)
			try:
				thumbfile.remove()
			except OSError:
				pass



#~ class ImageMagickThumbnailer(Thumbnailer):

	#~ def create_thumbnail(self, file, thumbfile, size):

		#~ magickextensions=('SVG','PDF','PS','EPS','DVI','DJVU','RAW','DOT','HTML','HTM','TTF','XCF')
		#~ textextensions=('SH','BAT','TXT','C','C++','CPP','H','H++','HPP','PY','PL') #'AVI','MPG','M2V','M4V','MPEG'
		#~ # TODO use mimetypes here ?? "image/" and "text/" -- or isimage() and istext()

		#~ tmpfile.touch()
		#~ pixbuf = None
		#~ extension=infile.path.split(".")[-1].upper()
		#~ if extension in magickextensions:
			#~ fileinfo=self._file_to_image_magick(infile,tmpfile,w,h,None)
			#~ if (fileinfo):
				#~ pixbuf = self._file_to_image_pixbbuf(tmpfile,outfile,w,h,fileinfo)
		#~ elif extension in textextensions:
			#~ #convert -size 400x  caption:@-  caption_manual.gif
			#~ fileinfo=self._file_to_image_txt(infile,tmpfile,w,h,None)
			#~ if (fileinfo):
				#~ pixbuf=self._file_to_image_pixbbuf(tmpfile,outfile,w,h,fileinfo)
		#~ else:
			#~ logger.debug('Can\'t convert: %s', infile)

		#~ try:
			#~ tmpfile.remove()
		#~ except OSError:
			#~ logger.exception('Could not delete tmp file: %s', tmpfile)
		#~ return pixbuf


	#~ def _file_to_image_magick(self,infile,outfile,w,h,fileinfo=None):
		#~ ''' pdf to thumbnail '''
		#~ try:
			#~ logger.debug('  trying Imagemagick')
			#~ infile_p1=infile.path +'[0]' # !????
			#~ #print infile_p1
			#~ size=str(w)+'x'+str(h)
			#~ cmd = ('convert','-size', size, '-trim','+repage','-resize',size+'>')
			#~ Application(cmd).run((infile_p1, outfile.path))
			#~ return True
		#~ except:
			#~ logger.exception('Error running %s', cmd)
		#~ return False

	#~ def _file_to_image_txt(self,infile,outfile,w,h,fileinfo=None):
		#~ try:
			#~ textcont='caption:'
			#~ size=str(h/4*3)+'x'+str(h)
			#~ linecount=0;
			#~ # lines: 18 at 128px
			#~ # linewidth 35 at 128px
			#~ while linecount<(h/32+10):
				#~ line = file.readline()
				#~ if not line:
					#~ break
				#~ linecount+=1
				#~ textcont+=line[0:w/24+12]
				#~ if (len(line)>(w/24+12) ):
					#~ textcont+='\n'
			#~ logger.debug('Trying TXT')

			#~ cmd = ('convert','-font','Courier','-size', size)# '-frame', '1' )
			#~ Application(cmd).run((textcont,outfile.path))
			#~ return True
		#~ except:
			#~ logger.debug('  Error converting TXT')
		#~ return False


# class GnomeThumbnailer(Thumbnailer):

#	def _file_to_image_gnome(self,infile,outfile,w,h,fileinfo=None):
#		''' gnome thumbnailer '''
#		global gnome_thumbnailer
#		if (not gnome_thumbnailer)
#			return False
#		try:
#			logger.debug('  trying Gnome-Thumbnailer')
#			#print infile_p1
#			size=str(w)+'x'+str(h)
#			cmd = ('/usr/bin/gnome-video-thumbnailer, size, '-trim','+repage','-resize',size+'>')
#			#print cmd
#			pdftopng = Application(cmd)
#			pdftopng.run((infile, outfile))
#			return True
#		except:
#			logger.debug('  Error converting PDF')
