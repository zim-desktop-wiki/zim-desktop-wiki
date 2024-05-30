#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
#           2011-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# License:  same as zim (gpl)
#
#
# !! NOTE: when changing this plugin, do test performance on a folder with lots of photos!
#

import datetime
import os
import ntpath

from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import GdkPixbuf

import logging

logger = logging.getLogger('zim.plugins.attachmentbrowser')


from zim.newfs import localFileOrFolder, LocalFile, LocalFolder, FileNotFoundError
from zim.newfs.helpers import format_file_size, FSObjectMonitor, TrashHelper

from zim.gui.widgets import gtk_popup_at_pointer, QuestionDialog

from zim.gui.applications import get_mime_icon, get_mime_description, \
	OpenWithMenu, open_file

from zim.gui.clipboard import \
	URI_TARGETS, URI_TARGET_NAMES, \
	pack_urilist, unpack_urilist


from .thumbnailer import ThumbnailQueue, ThumbnailManager, \
	THUMB_SIZE_NORMAL, THUMB_SIZE_LARGE

from .filerenamedialog import FileRenameDialog

MIN_THUMB_SIZE = 64 # don't render thumbs when icon size is smaller than this
MAX_ICON_SIZE = 128 # never render icons larger than this - thumbs go up


def delete_file(widget, file):
	'''Delete a file

	@param widget: parent for new dialogs, C{Gtk.Widget} or C{None}
	@param file: a L{File} object

	@raises FileNotFoundError: if C{file} does not exist
	'''
	logger.debug('delete_file(%s)', file)
	file = localFileOrFolder(file)
	assert isinstance(file, LocalFile) and not isinstance(file, LocalFolder)

	if not file.exists():
		raise FileNotFoundError(file)

	dialog = QuestionDialog(widget, _('Are you sure you want to delete the file \'%s\'?') % file.basename)
		# T: text in confirmation dialog on deleting a file
	if dialog.run():
		TrashHelper().trash(file)


def rename_file(widget, file):
	'''Rename a file

	@param widget: parent for new dialogs, C{Gtk.Widget} or C{None}
	@param file: a L{File} object

	@raises FileNotFoundError: if C{file} does not exist
	'''
	logger.debug('rename_file(%s)', file)
	file = localFileOrFolder(file)
	assert isinstance(file, LocalFile) and not isinstance(file, LocalFolder)

	if not file.exists():
		raise FileNotFoundError(file)

	dialog = FileRenameDialog(widget, file)
	if dialog.run() == Gtk.ResponseType.OK:
		if file.path != dialog.new_file:
			file.moveto(dialog.new_file)


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
		'folder-changed': (GObject.SignalFlags.RUN_LAST, None, ()),
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
		self._parent_signal_id = None

		GObject.GObject.__init__(self)
		self.set_model(
			Gtk.ListStore(str, GdkPixbuf.Pixbuf, object) # BASENAME_COL, PIXBUF_COL, MTIME_COL
		)
		self.set_text_column(BASENAME_COL)
		self.set_pixbuf_column(PIXBUF_COL)
		self.set_icon_size(icon_size)
		self.set_row_spacing(0)
		self.set_column_spacing(0)

		self.enable_model_drag_source(
			Gdk.ModifierType.BUTTON1_MASK,
			[Gtk.TargetEntry.new(*t) for t in URI_TARGETS],
			Gdk.DragAction.LINK | Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
		self.enable_model_drag_dest(
			[Gtk.TargetEntry.new(*t) for t in URI_TARGETS],
			Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
		self.connect('drag-data-get', self.on_drag_data_get)
		self.connect('drag-data-received', self.on_drag_data_received)

		self.props.has_tooltip = True
		self.connect("query-tooltip", self._query_tooltip_cb)

		self.connect('button-press-event', self.on_button_press_event)
		self.connect('item-activated', self.on_item_activated)

		self.connect('parent-set', self.__class__.on_parent_set)

	def on_parent_set(self, old_parent):
		# Bootstrap hack
		if old_parent and self._parent_signal_id:
			old_window = old_parent.get_parent()
			if old_window:
				old_window.disconnect(self._parent_signal_id)
			self._parent_signal_id = None
		
		parent = self.get_parent()
		if parent:
			window = self.get_parent().get_parent()
			if window:
				self._parent_signal_id = window.connect('size-allocate', self._recalc_n_columns)

	def _recalc_n_columns(self, *a):
		# HACK: Force number of columns - automatic setting of "-1" fails to do the right thing :(
		# Use parent of parent - want size of ScrolledWindow, not ViewPort
		# FUTURE: We could be more flexible in actually adjusting widget width to fit exactly in the widget width
		parent = self.get_parent()
		if parent is None:
			return
		window = parent.get_parent()
		if window is None:
			return
		widget_width = window.get_allocated_width()
		col_width = self.get_item_width() + self.get_column_spacing() + 2 * self.get_item_padding()
		n_cols = max(1, int(0.75*widget_width/col_width)) # XXX 0.75 is arbitrary fudge factor because somehow iconview takes more space than it says !?
		self.set_columns(n_cols)

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
				return

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
		text_size = max_text_length * 11 # XXX assume 11x per char - make sure code below is robust if this is not correct
		icon_size = self.icon_size

		if icon_size < 64:
			# Text next to the icons
			if icon_size > 16 and max_text_length > 15:
				# Wrap text over 2 rows
				self.set_item_width(icon_size + int((text_size + 1) / 2))
			else:
				# Single row
				self.set_item_width(icon_size + text_size)

			self.set_item_orientation(Gtk.Orientation.HORIZONTAL)
		else:
			# Text below the icons
			self.set_item_width(icon_size + 12) # allow text slightly more width than image
			self.set_item_orientation(Gtk.Orientation.VERTICAL)

		self._recalc_n_columns()

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
				self.do_populate_popup(popup_menu, pathinfo)
					# FIXME should use a signal here
				gtk_popup_at_pointer(popup_menu, event)
				return True
		return False

	def do_populate_popup(self, menu, pathinfo):
		# print("do_populate_popup")
		store = self.get_model()
		iter = store.get_iter(pathinfo)
		file = self.folder.file(store[iter][BASENAME_COL])

		item = Gtk.MenuItem.new_with_mnemonic(_('_Delete...')) # T: menu item to delete file
		item.connect('activate', lambda o: delete_file(self, file))
		menu.prepend(item)

		item = Gtk.MenuItem.new_with_mnemonic(_('_Rename...')) # T: menu item to rename file
		item.connect('activate', lambda o: rename_file(self, file))
		menu.prepend(item)

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
		markup = "%s\n\n<b>%s:</b> %s\n<b>%s:</b> %s\n<b>%s:</b>\n%s" % (
			name,
			t_label, mtype_desc or mtype,
			s_label, size,
			m_label, mdate,
		)
		markup = markup.replace('&', '&amp;')
		tooltip.set_markup(markup)
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
