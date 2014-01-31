# -*- coding: utf-8 -*-
#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
#           2011-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# License:  same as zim (gpl)
#
# ChangeLog
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
# [ ] Better management of queue - how to avoid flooding it ?
# [ ] Action for deleting files in context menu
# [ ] Copy / cut files in context menu
# [ ] Button to clean up the folder - only show when the folder is empty
# [x] GIO watcher to detect folder update - add API to zim.fs for watcher ?
# [ ] Allow more than 1 thread for thumbnailing ?
# [ ] Can we cache image to thumb mapping (or image MD5) to spead up ?
# [ ] Dont thumb small images
# [x] Mimetype specific icons
# [ ] Restore ImageMagick thumbnailer
# [ ] Use thumbnailers/settings from gnome or other DEs ?

'''Zim plugin to display files in attachments folder.'''


import os
import re
import hashlib # for thumbfilenames
import datetime
import logging
import Queue
import threading

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
from zim.errors import Error
from zim.applications import Application
from zim.parsing import url_encode, URL_ENCODE_READABLE

from zim.gui.widgets import Button, BOTTOM_PANE, PANE_POSITIONS, \
	IconButton, ScrolledWindow, button_set_statusbar_style, \
	WindowSidePaneWidget
from zim.gui.applications import OpenWithMenu
from zim.gui.clipboard import \
	URI_TARGETS, URI_TARGET_NAMES, \
	pack_urilist, unpack_urilist


logger = logging.getLogger('zim.plugins.attachmentbrowser')


# freedesktop.org spec
LOCAL_THUMB_STORAGE = Dir('~/.thumbnails')
LOCAL_THUMB_STORAGE_NORMAL = LOCAL_THUMB_STORAGE.subdir('normal')
LOCAL_THUMB_STORAGE_LARGE = LOCAL_THUMB_STORAGE.subdir('large')
LOCAL_THUMB_STORAGE_FAIL = LOCAL_THUMB_STORAGE.subdir('fail/zim-%s' % zim.__version__)

THUMB_SIZE_NORMAL = 128
THUMB_SIZE_LARGE = 256

# For plugin
MIN_ICON_SIZE = 16
DEFAULT_ICON_SIZE = 64


_last_warning_missing_icon = None
	# used to surpress redundant logging


def get_mime_icon(file, size):
	# FIXME put this in some library ?
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
	# TODO move this to zim.fs or something
	#
	# Check XML file /usr/share/mime/MEDIA/SUBTYPE.xml
	# Find element "comment" with "xml:lang" attribute for the locale
	# Etree fills in the namespaces which obfuscates the names
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


def is_hidden_file(file):
	# FIXME put this in zim.fs
	if not os.name == 'nt':
		return False

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


class AttachmentBrowserPlugin(PluginClass):

	plugin_info = {
		'name': _('Attachment Browser'), # T: plugin name
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
class MainWindowExtension(WindowExtension):

	TAB_NAME = _('Attachments') # T: label for attachment browser pane

	uimanager_xml = '''
	<ui>
		<menubar name='menubar'>
			<menu action='view_menu'>
				<placeholder name="plugin_items">
					<menuitem action="toggle_fileview" />
				</placeholder>
			</menu>
		</menubar>
		<toolbar name='toolbar'>
			<placeholder name='tools'>
				<toolitem action='toggle_fileview'/>
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
		self.__class__.toggle_fileview.connect_actionable(
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
	def toggle_fileview(self, active):
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
			self.toggle_fileview(True)
			if not self.widget.get_active():
				self.widget.set_active(True) # implies refresh
		else:
			self.toggle_fileview(False)
			self.widget.set_active(False)

	def on_open_page(self, ui, page, path):
		self._disconnect_monitor()

		self.widget.set_page(ui.notebook, page) # XXX
		self._refresh_statusbar(page)

		dir = self.window.ui.notebook.get_attachments_dir(page) # XXX -> page.get_attachemnts_dir()
		id = dir.connect('changed', self.on_dir_changed)
		self._monitor = (dir, id)

	def _disconnect_monitor(self):
		if self._monitor:
			dir, id = self._monitor
			dir.disconnect(id)
			self._monitor = None

	def on_dir_changed(self, *a):
		logger.debug('Dir change detected: %s', a)
		self._refresh_statusbar(self.window.ui.page) # XXX
		self.widget.refresh()

	def _refresh_statusbar(self, page):
		n = self.get_n_attachments(page)
		self.statusbar_button.set_label(
			ngettext('%i _Attachment', '%i _Attachments', n) % n)
			# T: Label for the statusbar, %i is the number of attachments for the current page

	def get_n_attachments(self, page):
		# Calculate independent from the widget
		# (e.g. widget is not refreshed when hidden)
		n = 0
		dir = self.window.ui.notebook.get_attachments_dir(page) # XXX -> page.get_
		from zim.fs import isdir
		for name in dir.list():
			# If dir is an attachment folder, sub-pages maybe filtered out already
			# TODO need method in zim.fs to do this count efficiently
			# TODO ignore hidden files here as well
			if not isdir(dir.path + '/' + name):
				# Ignore subfolders -- FIXME ?
				n += 1
		return n

	def teardown(self):
		self._disconnect_monitor()
		self.toggle_fileview(False)
		self.window.remove(self.widget)
		if self.statusbar_frame:
			self.window.statusbar.remove(self.statusbar_frame)
		self.widget = None


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


BASENAME_COL = 0
PIXBUF_COL = 1

class AttachmentBrowserPluginWidget(gtk.HBox, WindowSidePaneWidget):

	icon_size = uistate_property('icon_size', DEFAULT_ICON_SIZE)

	def __init__(self, extension, opener, preferences):
		gtk.HBox.__init__(self)
		self.page = None # XXX
		self.extension = extension # XXX
		self.opener = opener
		self.uistate = extension.uistate
		self.preferences = preferences
		self.dir = None
		self._active = True

		self.thumbman = ThumbnailManager(preferences)
		self.thumbman.connect('thumbnail-ready', self.on_thumbnail_ready)

		self.fileview = gtk.IconView()

		self.store = gtk.ListStore(str, gtk.gdk.Pixbuf) # BASENAME_COL, PIXBUF_COL

		self.fileview = gtk.IconView(self.store)
		self.fileview.set_text_column(BASENAME_COL)
		self.fileview.set_pixbuf_column(PIXBUF_COL)

		self.fileview.enable_model_drag_source(
			gtk.gdk.BUTTON1_MASK,
			URI_TARGETS,
			gtk.gdk.ACTION_LINK | gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE )
		self.fileview.enable_model_drag_dest(
			URI_TARGETS,
			gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE )
		self.fileview.connect('drag-data-get', self.on_drag_data_get)
		self.fileview.connect('drag-data-received', self.on_drag_data_received)

		self.add(ScrolledWindow(self.fileview))

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
		zoomin.connect('clicked', lambda o: self.zoom_in())
		zoomout.connect('clicked', lambda o: self.zoom_out())
		self.buttonbox.pack_end(zoomout, False)
		self.buttonbox.pack_end(zoomin, False)
		self.fileview.connect('button-press-event', self.on_button_press_event)
		self.fileview.connect('item-activated', self.on_item_activated)
		self.zoomin_button = zoomin
		self.zoomout_button = zoomout

		if gtk.gtk_version >= (2, 12):
			# custom tooltip
			self.fileview.props.has_tooltip = True
			self.fileview.connect("query-tooltip", self.query_tooltip_icon_view_cb)

		# Store colors
		self._senstive_color = None
		self._insenstive_color = None

		def _init_base_color(*a):
			# This is handled on expose event, because style does not
			# yet reflect theming on construction
			if self._senstive_color is None:
				self._senstive_color = self.fileview.style.base[gtk.STATE_NORMAL]
				self._insenstive_color = self.fileview.style.base[gtk.STATE_INSENSITIVE]

			self._update_state()

		self.connect('expose-event', _init_base_color)

	def embed_closebutton(self, button):
		if button:
			self.buttonbox.pack_start(button, False)
			self.buttonbox.reorder_child(button, 0)
		else:
			for widget in self.buttonbox.get_children():
				if hasattr(widget, 'window_close_button'):
					self.buttonbox.remove(widget)
		return True

	def set_page(self, notebook, page):
		self.page = page # XXX
		dir = notebook.get_attachments_dir(page) # XXX page.get_attachments_dir
		self.set_folder(dir)

	def set_folder(self, dir):
		#~ print "set_folder", dir
		if dir != self.dir:
			self.dir = dir
			self.refresh()

	def get_active(self):
		return self._active

	def set_active(self, active):
		self._active = active
		self.refresh()

	def on_open_folder(self, o):
		# Callback for the "open folder" button
		self.opener.open_dir(self.dir)
		self._update_state()

	def on_refresh_button(self):
		self.refresh()
		self.extension._refresh_statusbar(self.page)
			# XXX FIXME communicate to extension by signal

	def zoom_in(self):
		self.icon_size = min((self.icon_size * 2, THUMB_SIZE_LARGE)) # 16 > 32 > 64 > 128 > 256
		self.refresh()

	def zoom_out(self):
		self.icon_size = max((self.icon_size/2, MIN_ICON_SIZE)) # 16 < 32 < 64 < 128 < 256
		self.refresh()

	def refresh(self):
		if not self._active:
			return # avoid unnecessary work

		# Clear data
		self.store.clear()
		self.thumbman.clear_async_queue()
		self._update_state()

		# Update once, re-use below
		self._file_icon = render_file_icon(self, min((self.icon_size, THUMB_SIZE_NORMAL)))
		self._file_icon_tooltip = render_file_icon(self, THUMB_SIZE_NORMAL)

		# Add files
		for name in self.dir.list():
			# If dir is an attachment folder, sub-pages maybe filtered out already
			file = self.dir.file(name)
			if file.isdir() or is_hidden_file(file):
				continue # Ignore subfolders -- FIXME ?
			else:
				self._add_file(file)

		# Update column size etc.
		if self.icon_size < 64:
			# Would like to switch to by-column layout here, but looks
			# like gtk.IconView does not support that
			self.fileview.set_orientation(gtk.ORIENTATION_HORIZONTAL)
			size = self._get_max_width()
			if size > 0:
				if self.icon_size > 16:
					size = int((size+1) / 2) # Wrap over 2 rows
				# Else no wrap
				size += self.icon_size
				self.fileview.set_item_width(size)
			self.fileview.set_row_spacing(0)
			self.fileview.set_column_spacing(0)
		else:
			self.fileview.set_orientation(gtk.ORIENTATION_VERTICAL)
			size = max((self.icon_size + 12, 96))
			self.fileview.set_item_width(size)
				# Set item width to force wrapping text for long items
				# Set to icon size + some space for padding etc.
			self.fileview.set_row_spacing(3)
			self.fileview.set_column_spacing(3)

	def _get_max_width(self):
		import pango
		layout = self.fileview.create_pango_layout('')
		model = self.fileview.get_model()
		l = 0
		for r in model:
			l = max((l, len(r[BASENAME_COL])))
			#layout.set_text(r[BASENAME_COL])
			#l = max((l, layout.get_pixel_size()[0]))
		return l * 10 # XXX Rough estimate with 10px per char...


	def _update_state(self):
		# Here we set color like senstive or insensitive widget without
		# really making the widget insensitive - reason is to allow
		# drag & drop for a non-existing folder; making the widget
		# insensitive also blocks drag & drop.
		if self.dir is None or not self.dir.exists():
			self.fileview.modify_base(
				gtk.STATE_NORMAL, self._insenstive_color)

			self.zoomin_button.set_sensitive(False)
			self.zoomout_button.set_sensitive(False)
		else:
			self.fileview.modify_base(
				gtk.STATE_NORMAL, self._senstive_color)

			self.zoomin_button.set_sensitive(self.icon_size < THUMB_SIZE_LARGE)
			self.zoomout_button.set_sensitive(self.icon_size > MIN_ICON_SIZE)


	def _add_file(self, file):
		if self.icon_size >= DEFAULT_ICON_SIZE:
			# Only use thumbnails if icons sufficiently large to show them
			pixbuf = self.thumbman.get_thumbnail_async(file, self.icon_size)
		else:
			pixbuf = None

		if pixbuf is None:
			# Set generic icon first - maybe thumbnail follows later, maybe not
			# Icon size for mime icons is limitted, avoid huge icons
			pixbuf = get_mime_icon(file, min((self.icon_size, THUMB_SIZE_NORMAL))) \
				or self._file_icon

		self.store.append((file.basename, pixbuf)) # BASENAME_COL, PIXBUF_COL

	def on_thumbnail_ready(self, o, file, size, pixbuf):
		#~ print "GOT THUMB:", file, size, pixbuf
		if size != self.icon_size or file.dir != self.dir:
			return

		basename = file.basename
		def update(model, path, iter):
			if model[iter][BASENAME_COL] == basename:
				model[iter][PIXBUF_COL] = pixbuf

		self.store.foreach(update)

	def on_item_activated(self, iconview, path):
		iter = self.store.get_iter(path)
		file = self.dir.file(self.store[iter][BASENAME_COL])
		self.opener.open_file(file)

	def on_button_press_event(self, iconview, event):
		# print 'on_button_press_event'
		if event.button == 3:
			popup_menu=gtk.Menu()
			x = int(event.x)
			y = int(event.y)
			time = event.time
			pathinfo = self.fileview.get_path_at_pos(x, y)
			if pathinfo is not None:
				self.fileview.grab_focus()
				popup_menu.popup(None, None, None, event.button, time)
				self.do_populate_popup(popup_menu, pathinfo)
					# FIXME should use a signal here
				return True
		return False

	def do_populate_popup(self, menu, pathinfo):
		# print "do_populate_popup"
		iter = self.store.get_iter(pathinfo)
		file = self.dir.file(self.store[iter][BASENAME_COL])

		item = gtk.MenuItem(_('Open With...')) # T: menu item
		menu.prepend(item)

		submenu = OpenWithMenu(self.extension.window, file) # XXX any widget should do to find window
		item.set_submenu(submenu)

		item = gtk.MenuItem(_('_Open')) # T: menu item to open file or folder
		item.connect('activate', lambda o: self.opener.open_file(file))
		menu.prepend(item)

		menu.show_all()

	def query_tooltip_icon_view_cb(self, widget, x, y, keyboard_tip, tooltip):
		context = widget.get_tooltip_context(x, y, keyboard_tip)
		if not context:
			return False

		model, path, iter = context
		name = model[iter][BASENAME_COL]
		file = self.dir.file(name)
		mtime = file.mtime()
		if mtime:
			mdate = datetime.datetime.fromtimestamp(file.mtime()).strftime('%c')
			# TODO: fix datetime format
		else:
			mdate = _('Unknown') # T: unspecified value for file modification time
		size = format_file_size(file.size())

		pixbuf = self.thumbman.get_thumbnail(file, THUMB_SIZE_LARGE)
		if not pixbuf:
			# No thumbnail, use icon, but use it at normal size
			pixbuf = get_mime_icon(file, THUMB_SIZE_NORMAL) \
				or self._file_icon_tooltip

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

	def on_drag_data_get(self, iconview, dragcontext, selectiondata, info, time):
		assert selectiondata.target in URI_TARGET_NAMES
		paths = self.fileview.get_selected_items()
		if paths:
			model = self.fileview.get_model()
			path_to_uri = lambda p: self.dir.file(model[p][BASENAME_COL]).uri
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
			newfile = self.dir.new_file(file.basename)
			file.rename(newfile)
			self._add_file(newfile)
			# TODO sort

		self._update_state()

	def _copy_files(self, files):
		for file in files:
			newfile = self.dir.new_file(file.basename)
			file.copyto(newfile)
			self._add_file(newfile)
			# TODO sort


class ThumbnailManager(gobject.GObject):
	''' Thumbnail handling following freedesktop.org spec mostly

	@signal: C{thumbnail-ready (file, size, pixbuf)}: thumbnail ready
	'''
	# TODO more doc here to explain what the function of the manager is

	# Spec retrieved 2012-02-26 from http://people.freedesktop.org/~vuntz/thumbnail-spec-cache/
	# Notes on spec:
	# * storage
	# 	* ~/.thumbnails/normal <= 128 x 128
	# 	* ~/.thumbnails/large <= 256 x 256
	# 	* ~/.thumbnails/fail
	# * thumbnail file
	# 	* Name is md5 hex of full uri (where uri must be "file:///" NOT "file://localhost/")
	# 	* Must have PNG attributes for mtime and uri
	# 		* If mtime orig can not be determined, do not create a thumbnail
	# 	* Must write as tmp file in same dir and then rename atomic
	# 	* Permissions on files must be 0600
	# * lookup / recreate
	# 	* Must equal orig mtime vs thumbnail mtime property (not thumbnail file mtime)
	# 	* Only store failures for permanent failures, to prevent re-doing them
	# 	* Failure is app specific, so subdir with app name and version
	# 	* Failure record is just empty png

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'thumbnail-ready': (gobject.SIGNAL_RUN_LAST, None, (object, int, gtk.gdk.Pixbuf)),
	}

	def __init__(self, preferences):
		gobject.GObject.__init__(self)

		self.preferences = preferences
		self.async_thread = None
		self.async_queue = Queue.Queue()

		for dir in (
			LOCAL_THUMB_STORAGE_NORMAL,
			LOCAL_THUMB_STORAGE_LARGE,
			LOCAL_THUMB_STORAGE_FAIL
		):
			try:
				dir.touch(mode=0700)
			except OSError:
				pass

	def clear_async_queue(self):
		if self.async_thread:
			self.async_thread.stop()

		self.async_thread = None
		self.async_queue = Queue.Queue()

	def get_thumbnail(self, file, size):
		'''Get a C{Pixbuf} with the thumbnail for a given file
		@param file: the original file to be thumbnailed
		@param size: thumbnail size in pixels
		(C{THUMB_SIZE_NORMAL}, C{THUMB_SIZE_LARGE}, or integer)
		@returns: a C{gtk.gdk.Pixbuf} object
		'''
		thumbfile = self.get_thumbnail_file(file, size)
		pixbuf = self._existing_thumbnail(file, thumbfile, size)
		if pixbuf:
			return pixbuf
		else:
			return self._create_thumbnail(file, thumbfile, size)

	def _existing_thumbnail(self, file, thumbfile, size):
		if thumbfile.exists():
			# Check the thumbnail is valid
			pixbuf = self._pixbuf(thumbfile, size)
			mtime = self._mtime_from_pixbuf(pixbuf)
			if mtime is not None:
				# Check mtime from PNG attribute
				if mtime == int(file.mtime()):
					return pixbuf
				else:
					return None
			else:
				# Fallback for thumbnails without proper attributes
				if thumbfile.mtime() > file.mtime():
					return pixbuf
				else:
					return None

	def _pixbuf(self, file, size):
		# Read file at size and return pixbuf
		pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.path, size, size)
		return pixbuf

	def _mtime_from_pixbuf(self, pixbuf):
		# Get mtime and return as int, if any
		mtime = pixbuf.get_option('tEXt::Thumb::MTime')
		if mtime is not None:
			return int(mtime)
		else:
			return None

	def _create_thumbnail(self, file, thumbfile, size):
		assert file.exists()
		normsize = self._norm_size(size)
		thumbnailer = PixbufThumbnailer()
		try:
			thumbnailer.create_thumbnail(file, thumbfile, normsize)
				# TODO enforce tmp file, 0600 permissions, as specced
			pixbuf = self._pixbuf(thumbfile, size)
			self.emit('thumbnail-ready', file, size, pixbuf)
			return pixbuf
		except:
			# TODO Error class, logging, create failure file ?
			#~ logger.info('Failed to generate thumbnail for: %s', file)
			return None

		#~ if self.preferences['use_imagemagick']:
			#~ TODO TODO

	def get_thumbnail_async(self, file, size):
		'''Get a C{Pixbuf} with the thumbnail for a given file
		Like L{get_thumbnail()} but if thumbnail needs to be generated
		first it will be done asynchronously. When the thumbnail is
		ready the C{thumbnail-ready} signal will be emitted.
		@param file: the original file to be thumbnailed
		@param size: thumbnail size in pixels
		(C{THUMB_SIZE_NORMAL}, C{THUMB_SIZE_LARGE}, or integer)
		@returns: C{gtk.gdk.Pixbuf} is thumbnail exists already,
		C{None} otherwise
		'''
		thumbfile = self.get_thumbnail_file(file, size)
		pixbuf = self._existing_thumbnail(file, thumbfile, size)
		if pixbuf:
			return pixbuf
		else:
			self.async_queue.put( (file, thumbfile, size) )

			if not self.async_thread \
			or not self.async_thread.is_alive():
				self.async_thread = WorkerThread(self.async_queue, self._create_thumbnail_async)
				self.async_thread.start()

	def _create_thumbnail_async(self, file, thumbfile, size):
		try:
			self._create_thumbnail(file, thumbfile, size)
		except:
			logger.exception('Error while creating thumbnail')

	def get_thumbnail_file(self, file, size):
		'''Get L{File} object for thumbnail
		Does not gurarntee that the thumbnail actually exists.
		Do not use this method to lookup the thumbnail, use L{get_thumbnail()}
		instead.
		@param file: the original file to be thumbnailed
		@param size: thumbnail size in pixels (C{THUMB_SIZE_NORMAL}, C{THUMB_SIZE_LARGE}, or integer)
		@returns: a L{File} object
		'''
		basename = hashlib.md5(file.uri).hexdigest() + '.png'
		size = self._norm_size(size)
		if (size == THUMB_SIZE_NORMAL):
			return LOCAL_THUMB_STORAGE_NORMAL.file(basename)
		else:
			return LOCAL_THUMB_STORAGE_LARGE.file(basename)

	def _norm_size(self, size):
		# Convert custom size to normalized size for storage
		if size <= THUMB_SIZE_NORMAL:
			return THUMB_SIZE_NORMAL
		else:
			return THUMB_SIZE_LARGE

	def remove_thumbnails(self, file):
		'''Remove thumbnails for at all sizes
		To be used when thumbnails are outdated, e.g. when the original
		file is removed or updated.
		@param file: the original file
		'''
		for size in (THUMB_SIZE_NORMAL, THUMB_SIZE_LARGE):
			thumbfile = self.get_thumbnail_file(file, size)
			if thumbfile.exists():
				thumbfile.remove()

# Need to register classes defining gobject signals
gobject.type_register(ThumbnailManager)


class WorkerThread(threading.Thread):

	daemon = True

	def __init__(self, queue, func):
		threading.Thread.__init__(self)
		self.queue = queue
		self.func = func
		self._stop = False

	def stop(self):
		self._stop = True

	def run(self):
		while not self._stop:
			args = self.queue.get()
			self.func(*args)
			self.queue.task_done()


class Thumbnailer(object):

	def create_thumbnail(self, file, thumbfile, size):
		'''Create a thumbnail
		@param file: the file to be thumbnailed as L{File} object
		@param thumbfile: to be created thumbnail file as L{File} object
		@param size: pixel size for thumbnail as integer
		@implementation: must be implemented in subclasses
		'''
		raise NotImplementedError


class PixbufThumbnailer(Thumbnailer):

	def create_thumbnail(self, file, thumbfile, size):
		options = {
			'tEXt::Thumb::URI': url_encode(file.uri, mode=URL_ENCODE_READABLE), # No UTF-8 here
			'tEXt::Thumb::MTime': str( int( file.mtime() ) ),
		}
		pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.path, size, size)
		pixbuf.save(thumbfile.path, 'png', options)


class ImageMagickThumbnailer(Thumbnailer):

	def create_thumbnail(self, file, thumbfile, size):
		pass

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
