#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
#           2011-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# License:  same as zim (gpl)
#
#
# !! NOTE: when changing this plugin, do test performance on a folder with lots of photos!
#

import datetime

from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import GdkPixbuf

import logging

logger = logging.getLogger('zim.plugins.attachmentbrowser')


from zim.newfs import LocalFile, FileNotFoundError
from zim.newfs.helpers import format_file_size, FSObjectMonitor

from zim.gui.widgets import gtk_popup_at_pointer

from zim.gui.applications import get_mime_icon, get_mime_description, \
	OpenWithMenu, open_file

from zim.gui.clipboard import \
	URI_TARGETS, URI_TARGET_NAMES, \
	pack_urilist, unpack_urilist


from .thumbnailer import ThumbnailQueue, ThumbnailManager, \
	THUMB_SIZE_NORMAL, THUMB_SIZE_LARGE


MIN_THUMB_SIZE = 64 # don't render thumbs when icon size is smaller than this
MAX_ICON_SIZE = 128 # never render icons larger than this - thumbs go up


def render_file_icon(widget, size):
	# Sizes defined in gtk source,
	# gtkiconfactory.c for gtk+ 2.18.9
	#
	#	(Gtk.IconSize.MENU, 16),
	#	(Gtk.IconSize.BUTTON, 20),
	#	(Gtk.IconSize.SMALL_TOOLBAR, 18),
	#	(Gtk.IconSize.LARGE_TOOLBAR, 24),
	#	(Gtk.IconSize.DND, 32),
	#	(Gtk.IconSize.DIALOG, 48),
	#
	# We expect sizes in list: 16, 32, 64, 128
	# But only give back 16 or 32, bigger icons
	# do not look good
	assert size in (16, 32, 64, 128)
	if size == 16:
		pixbuf = widget.render_icon(Gtk.STOCK_FILE, Gtk.IconSize.MENU)
	else:
		pixbuf = widget.render_icon(Gtk.STOCK_FILE, Gtk.IconSize.DND)

	# Not sure how much sizes depend on theming,
	# so we scale down if needed, do not scale up
	if pixbuf.get_width() > size or pixbuf.get_height() > size:
		return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
	else:
		return pixbuf



BASENAME_COL = 0
PIXBUF_COL = 1
MTIME_COL = 2

class FileBrowserIconView(Gtk.IconView):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'folder_changed': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	def __init__(self, opener, icon_size=THUMB_SIZE_NORMAL, use_thumbnails=True, thumbnail_svg=False):
		self.opener = opener
		self.use_thumbnails = use_thumbnails
		self.thumbnail_svg = thumbnail_svg
		self.icon_size = None
		self.folder = None
		self._thumbnailer = ThumbnailQueue()
		self._idle_event_id = None
		self._monitor = None
		self._mtime = None

		GObject.GObject.__init__(self)
		self.set_model(
			Gtk.ListStore(str, GdkPixbuf.Pixbuf, object) # BASENAME_COL, PIXBUF_COL, MTIME_COL
		)
		self.set_text_column(BASENAME_COL)
		self.set_pixbuf_column(PIXBUF_COL)
		self.set_icon_size(icon_size)

		self.enable_model_drag_source(
			Gdk.ModifierType.BUTTON1_MASK,
			[Gtk.TargetEntry.new(*t) for t in URI_TARGETS],
			Gdk.DragAction.LINK | Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
		self.enable_model_drag_dest(
			[Gtk.TargetEntry.new(*t) for t in URI_TARGETS],
			Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
		self.connect('drag-data-get', self.on_drag_data_get)
		self.connect('drag-data-received', self.on_drag_data_received)

		# custom tooltip
		self.props.has_tooltip = True
		self.connect("query-tooltip", self._query_tooltip_cb)

		# Store colors
		self._sensitive_color = None
		self._insensitive_color = None

		def _init_base_color(*a):
			# This is handled on expose event, because style does not
			# yet reflect theming on construction
			self._sensitive_color = self.style.base[Gtk.StateType.NORMAL]
			self._insensitive_color = self.style.base[Gtk.StateType.INSENSITIVE]
			self._update_state()
			self.disconnect(self._expose_event_id) # only need this once

		#self._expose_event_id = self.connect('expose-event', _init_base_color)
			# NOTE: when re-enabling the above, also enable occurences of _update_state
		self.connect('button-press-event', self.on_button_press_event)
		self.connect('item-activated', self.on_item_activated)

	def set_use_thumbnails(self, use_thumbnails):
		self.use_thumbnails = use_thumbnails
		self.refresh(settings_changed=True)

	def set_thumbnail_svg(self, thumbnail_svg):
		self.thumbnail_svg = thumbnail_svg
		self.refresh(settings_changed=True)

	def set_icon_size(self, icon_size):
		self.icon_size = icon_size
		self.refresh(settings_changed=True)

	def set_folder(self, folder):
		self.teardown_folder() # clears _thumbnailer and _monitor
		self.folder = folder

		self.refresh()

		monitor = FSObjectMonitor(self.folder)
		id = monitor.connect('changed', self._on_folder_changed)
		self._monitor = (monitor, id)

	def refresh(self, settings_changed=False):
		if self.folder is None:
			return # Not yet initialized
		else:
			try:
				self._mtime = self.folder.mtime()
			except FileNotFoundError: # folder went missing?
				self.teardown_folder()
				#self._update_state()
				return
			else:
				pass
				#self._update_state()

		#~ import time
		#~ print("start", time.time())

		self._thumbnailer.clear_queue()
		if self._idle_event_id:
			GObject.source_remove(self._idle_event_id)
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
			mt = file.mimetype()
			if not mt in mime_cache:
				mime_cache[mt] = get_mime_icon(file, min_icon_size) or file_icon
			return mime_cache[mt]

		# Add (new) files & queue thumbnails
		max_text = 1
		show_thumbs = self.use_thumbnails and self.icon_size >= MIN_THUMB_SIZE
		for file in self.folder.list_files():

			max_text = max(max_text, len(file.basename))

			pixbuf, mtime = cache.pop(file.basename, (None, None))
			if file.basename.endswith('.svg') and not self.thumbnail_svg:
				pixbuf = my_get_mime_icon(file)
				mtime = None
			elif show_thumbs and file.isimage():
				if not pixbuf:
					pixbuf = my_get_mime_icon(file) # temporary icon
					mtime = None

				if settings_changed:
					self._thumbnailer.queue_thumbnail_request(file, self.icon_size)
				else:
					self._thumbnailer.queue_thumbnail_request(file, self.icon_size, mtime)
			elif pixbuf is None or settings_changed:
				pixbuf = my_get_mime_icon(file)
				mtime = None
			else:
				pass # re-use from cache

			model.append((file.basename, pixbuf, mtime))

		self._set_orientation_and_size(max_text)

		if not self._thumbnailer.queue_empty():
			self._thumbnailer.start() # delay till here - else reduces our speed on loading
			self._idle_event_id = \
				GObject.idle_add(self._on_check_thumbnail_queue)

		#~ print("stop ", time.time())

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
					icon_size + int((text_size + 1) / 2))
			else:
				# Single row
				self.set_item_width(icon_size + text_size)

			self.set_item_orientation(Gtk.Orientation.HORIZONTAL)
			self.set_row_spacing(0)
			self.set_column_spacing(0)
		else:
			# Text below the icons
			self.set_item_width(max((icon_size + 12, 96)))
			self.set_item_orientation(Gtk.Orientation.VERTICAL)
			self.set_row_spacing(3)
			self.set_column_spacing(3)

	def _update_state(self):
		# Here we set color like sensitive or insensitive widget without
		# really making the widget insensitive - reason is to allow
		# drag & drop for a non-existing folder; making the widget
		# insensitive also blocks drag & drop.
		if self.folder is None or not self.folder.exists():
			self.modify_base(
				Gtk.StateType.NORMAL, self._insensitive_color)
		else:
			self.modify_base(
				Gtk.StateType.NORMAL, self._sensitive_color)

	def teardown_folder(self):
		try:
			if self._monitor:
				monitor, id = self._monitor
				monitor.disconnect(id)
		except:
			logger.exception('Could not cancel file monitor')
		finally:
			self._monitor = None

		if self._idle_event_id:
			GObject.source_remove(self._idle_event_id)
			self._idle_event_id = None

		try:
			self._thumbnailer.clear_queue()
		except:
			logger.exception('Could not stop thumbnailer')

		self.get_model().clear()

	def _on_folder_changed(self, *a):
		try:
			changed = self.folder and self.folder.exists() and self.folder.mtime() != self._mtime
		except OSError: # folder went missing?
			changed = True

		if changed:
			logger.debug('Folder change detected: %s', self.folder)
			self.refresh()
			self.emit('folder-changed')

	def on_item_activated(self, iconview, path):
		store = iconview.get_model()
		iter = store.get_iter(path)
		filename = self.folder.file(store[iter][BASENAME_COL])
		open_file(self, filename)

	def on_button_press_event(self, iconview, event):
		# print('on_button_press_event')
		if event.button == 3:
			popup_menu = Gtk.Menu()
			x = int(event.x)
			y = int(event.y)
			time = event.time
			pathinfo = iconview.get_path_at_pos(x, y)
			if pathinfo is not None:
				iconview.grab_focus()
				gtk_popup_at_pointer(popup_menu, event)
				self.do_populate_popup(popup_menu, pathinfo)
					# FIXME should use a signal here
				return True
		return False

	def do_populate_popup(self, menu, pathinfo):
		# print("do_populate_popup")
		store = self.get_model()
		iter = store.get_iter(pathinfo)
		file = self.folder.file(store[iter][BASENAME_COL])

		item = Gtk.MenuItem.new_with_mnemonic(_('Open With...')) # T: menu item
		menu.prepend(item)

		window = self.get_toplevel()
		submenu = OpenWithMenu(window, file) # XXX any widget should do to find window
		item.set_submenu(submenu)

		item = Gtk.MenuItem.new_with_mnemonic(_('_Open')) # T: menu item to open file or folder
		item.connect('activate', lambda o: open_file(self, file))
		menu.prepend(item)

		menu.show_all()

	def _query_tooltip_cb(self, widget, x, y, keyboard_tip, tooltip):
		context = widget.get_tooltip_context(x, y, keyboard_tip)
		if not context:
			return False

		thumbman = ThumbnailManager()
		model, path, iter = context.model, context.path, context.iter
		if not (model and iter):
			return
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

		mtype = file.mimetype()
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
		assert selectiondata.get_target().name() in URI_TARGET_NAMES
		paths = self.get_selected_items()
		if paths:
			model = self.get_model()
			path_to_uri = lambda p: self.folder.file(model[p][BASENAME_COL]).uri
			uris = list(map(path_to_uri, paths))
			data = pack_urilist(uris)
			selectiondata.set(selectiondata.get_target(), 8, data)

	def on_drag_data_received(self, iconview, dragcontext, x, y, selectiondata, info, time):
		assert selectiondata.get_target().name() in URI_TARGET_NAMES
		names = unpack_urilist(selectiondata.get_data())
		files = [LocalFile(uri) for uri in names if uri.startswith('file://')]
		action = dragcontext.get_selected_action()
		logger.debug('Drag received %s, %s', action, files)

		if action == Gdk.DragAction.MOVE:
			self._move_files(files)
		elif action == Gdk.DragAction.ASK:
			menu = Gtk.Menu()

			item = Gtk.MenuItem.new_with_mnemonic(_('_Move Here')) # T: popup menu action on drag-drop of a file
			item.connect('activate', lambda o: self._move_files(files))
			menu.append(item)

			item = Gtk.MenuItem.new_with_mnemonic(_('_Copy Here')) # T: popup menu action on drag-drop of a file
			item.connect('activate', lambda o: self._copy_files(files))
			menu.append(item)

			menu.append(Gtk.SeparatorMenuItem())
			item = Gtk.MenuItem.new_with_mnemonic(_('Cancel')) # T: popup menu action on drag-drop of a file
			# cancel action needs no action
			menu.append(item)

			menu.show_all()
			gtk_popup_at_pointer(menu)
		else:
			# Assume Gdk.DragAction.COPY or Gdk.DragAction.DEFAULT
			# on windows we get "0" which is not mapped to any action
			self._copy_files(files)

	def _move_files(self, files):
		for file in files:
			newfile = self.folder.new_file(file.basename)
			file.moveto(newfile)

		self.refresh()

	def _copy_files(self, files):
		for file in files:
			newfile = self.folder.new_file(file.basename)
			file.copyto(newfile)

		self.refresh()
