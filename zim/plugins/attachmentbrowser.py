# -*- coding: utf-8 -*-
#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
#           2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# License:  same as zim (gpl)
#
# ChangeLog
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
# Bugs:
# textrendering is slow
# problems with Umlaut in filenames
# TODO:
# * integer plugin_preferences do not to work as expected (zim bug?)
# [ ] draw frames around thumbnails (in the view)
# [*] where to store thumbnails?
#   freedesktop.org: ~/.thumbnails/  (gnome/nautilus)
#   http://jens.triq.net/thumbnail-spec/thumbsave.html
#    [ ] store fileinfo in thumbnails
#    [ ] dont thumb small images
#    [ ] thmubs for other formats: word,openoffice,...
#    [ ] textrendering: syntax-hl
# [ ] preview in textarea (see emacs+speedbar)
# [*] dont start all thumbnailing processes at a time, and make them nice 10
# [*] small and lager thumbs
# [ ] use mimetype and extension
# [*] rethumb broken (e.g. shutdown while thumbnailing)
# [ ] code cleanup
#    [*] clean up plugin class and widget
#    [ ] refactor thumbnailer
# [*] new gui concept for zim : sidepane r/l,bottom- and top pane both with tabs (see gedit)
# [ ] show file infos in tooltip (size, camera,... what else?)
# [*] update icon when thumbnail is ready
# [ ] mimetype specific icons
# [ ] evaluate imagemagick python libs
# [ ] thumbnailers as plugins
# [ ] libgsf thumbnailer
# [ ] use thumbnailers/settings from gnome or other DEs
# [ ] make a reference implementation for thumbnail spec
# [ ] rewrite thumbnail spec
# http://ubuntuforums.org/showthread.php?t=76566
#
# tooltip example
#  http://nullege.com/codes/show/src@pygtk-2.14.1@examples@pygtk-demo@demos@tooltip.py/160/gtk.gdk.Color
# file info example
#  http://ubuntuforums.org/showthread.php?t=880967
#

'''Zim plugin to display files in attachments folder.'''


import re
import hashlib # for thumbfilenames
import logging

import gobject
import gtk
import pango

import zim
import zim.config # Asserts HOME is defined
from zim.fs import File, Dir, TmpFile

from zim.async import AsyncOperation, AsyncLock
from zim.plugins import PluginClass
from zim.gui.widgets import Button, BOTTOM_PANE, IconButton
from zim.notebook import Path
from zim.stores import encode_filename
from zim.fs import File, Dir
from zim.errors import Error
from zim.applications import Application
from zim.gui.applications import OpenWithMenu


logger = logging.getLogger('zim.plugins.attachmentbrowser')


ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('toggle_fileview', gtk.STOCK_DIRECTORY, _('AttachmentBrowser'),  '', 'Show Attachment Folder',False, True), # T: menu item
)


#Menubar and toolbar
ui_xml = '''
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


# freedesktop.org spec
LOCAL_THUMB_STORAGE = Dir('~/.thumbnails')
LOCAL_THUMB_STORAGE_NORMAL = LOCAL_THUMB_STORAGE.subdir('normal')
LOCAL_THUMB_STORAGE_LARGE = LOCAL_THUMB_STORAGE.subdir('large')
LOCAL_THUMB_STORAGE_FAIL = LOCAL_THUMB_STORAGE.subdir('fail/zim-%s' % zim.__version__)

THUMB_SIZE_NORMAL = 128
THUMB_SIZE_LARGE = 256
# evil hack: ignore the specs and create larger thumbs
PREVIEW_SIZE = 396




# TODO: chaneg size
#pdftopng_cmd = ('convert','-size', '480x480', '-trim','+repage','-resize','480x480>','-quality','50')
#pdftopng_cmd = ('convert','-trim')
#txttopng_cmd = ('dvipng', '-q', '-bg', 'Transparent', '-T', 'tight', '-o')
#txttopng_cmd = ('convert', '-size', '480x480'  'caption:')
#pdftojpg_cmd = ('convert','-size', '480x480', '-trim','+repage','-resize','480x480>','-quality','50')


class AttachmentBrowserPlugin(PluginClass):

	plugin_info = {
		'name': _('Attachment Browser'), # T: plugin name
		'description': _('''\
This plugin shows the attachments folder of the current page as an
icon view at bottom pane.

This plugin is still under development.
'''), # T: plugin description
		'author': 'Thorsten Hackbarth <thorsten.hackbarth@gmx.de>',
		#~ 'help': 'Plugins:Attachment Browser',
	}

	plugin_preferences = (
	#	# key, type, label, default
	#	('icon_size', 'int', _('Icon size [px]'), [ICON_SIZE_MIN,128,ICON_SIZE_MAX]), # T: preferences option
	#	('preview_size', 'int', _('Tooltip preview size [px]'), (THUMB_SIZE_MIN,480,THUMB_SIZE_MAX)), # T: input label
	#	('thumb_quality', 'int', _('Preview jpeg Quality [0..100]'), (0,50,100)), # T: input label
		('use_imagemagick', 'bool', _('Use ImageMagick for thumbnailing'), False), # T: input label
	)

	#~ @classmethod
	#~ def check_dependencies(klass):
		#~ return [("ImageMagick",Application(('convert',None)).tryexec())]

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.ui.add_toggle_actions(ui_toggle_actions, self)
			#self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)

	def finalize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.widget = AttachmentBrowserPluginWidget(self.ui, self.preferences)
			self.widget.on_open_page(self.ui, self.ui.page, self.ui.page)
			self.uistate.setdefault('active', True)
			self.toggle_fileview(enable=self.uistate['active'])
			self.ui.connect('close-page', self.on_close_page)

	def toggle_fileview(self, enable=None):
		self.toggle_action('toggle_fileview', active=enable)

	def do_toggle_fileview(self, enable=None):
		#~ print 'do_toggle_fileview', enable
		if enable is None:
			action = self.actiongroup.get_action('toggle_fileview')
			enable = action.get_active()

		if enable:
			self.uistate.setdefault('bottompane_pos', int(450 - 1.5*THUMB_SIZE_NORMAL))
				# HACK, using default window size here
			if not self.widget.get_property('visible'):
				self.ui.mainwindow.add_tab(_('Attachments'), self.widget, BOTTOM_PANE)
					# T: label for attachment browser pane
				self.widget.show_all()
				self.widget.refresh()
				self.ui.mainwindow._zim_window_bottom_pane.set_position(
					self.uistate['bottompane_pos'])
					# FIXME - method for this in Window class
			self.uistate['active'] = True
		else:
			if self.widget.get_property('visible'):
				self.uistate['bottompane_pos'] = \
					self.ui.mainwindow._zim_window_bottom_pane.get_position()
					# FIXME - method for this in Window class
				self.widget.hide_all()
				self.ui.mainwindow.remove(self.widget)
			self.uistate['active'] = False

	def on_close_page(self, *a):
		if self.widget.get_property('visible'):
			self.uistate['bottompane_pos'] = \
				self.ui.mainwindow._zim_window_bottom_pane.get_position()
				# FIXME - method for this in Window class

	def disconnect(self):
		self.do_toggle_fileview(enable=False)

		PluginClass.disconnect(self)

	def do_preferences_changed(self):
		if self.widget.get_property('visible'):
			self.widget.refresh() # re-start thumbnailing with other settings


BASENAME_COL = 0
PIXBUF_COL = 1


class AttachmentBrowserPluginWidget(gtk.HBox):

	def __init__(self, ui, preferences):
		gtk.HBox.__init__(self)
		self.ui = ui
		self.preferences = preferences
		self.dir = None

		self.thumbman = ThumbnailManager(preferences)

		self.fileview = gtk.IconView()

		self.store = gtk.ListStore(str, gtk.gdk.Pixbuf) # BASENAME_COL, PIXBUF_COL

		self.fileview = gtk.IconView(self.store)
		self.fileview.set_text_column(BASENAME_COL)
		self.fileview.set_pixbuf_column(PIXBUF_COL)

		window = gtk.ScrolledWindow()
		window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		window.set_shadow_type(gtk.SHADOW_IN)
		window.add(self.fileview)
		self.add(window)

		self.buttonbox = gtk.VBox()
		self.pack_end(self.buttonbox, False)

		open_folder_button = IconButton(gtk.STOCK_OPEN, relief=False)
		open_folder_button.connect('clicked', lambda o: self.ui.open_attachments_folder())
		self.buttonbox.pack_start(open_folder_button, False)

		refresh_button = IconButton(gtk.STOCK_REFRESH, relief=False)
		refresh_button.connect('clicked', lambda o: self.refresh())
		self.buttonbox.pack_start(refresh_button, False)

		self.ui.connect('open-page', self.on_open_page)

		self.fileview.connect('button-press-event', self.on_button_press_event)
		self.fileview.connect('item-activated', self.on_item_activated)

		if gtk.gtk_version >= (2, 12):
			# custom tooltip
			self.fileview.props.has_tooltip = True
			self.fileview.connect("query-tooltip", self.query_tooltip_icon_view_cb)

	def on_open_page(self, ui, page, path):
		self.set_folder(ui.notebook.get_attachments_dir(page))

	def set_folder(self, dir):
		#~ print "set_folder", dir
		if dir != self.dir:
			self.dir = dir
			if self.get_property('visible'):
				self.refresh()

	def refresh(self):
		self.store.clear()
		self.thumbman.clear()

		if self.dir is None or not self.dir.exists():
			self.fileview.set_sensitive(False)
			return # Show empty view
		else:
			self.fileview.set_sensitive(True)

		for name in self.dir.list():
			# If dir is an attachment folder, sub-pages maybe filtered out already
			file = self.dir.file(name)
			if file.isdir():
				continue # Ignore subfolders -- FIXME ?

			pixbuf = self.thumbman.get_thumbnail(file, THUMB_SIZE_NORMAL, self.set_thumb, file)
			if not pixbuf:
				# TODO: icon by mime-type
				pixbuf = self.render_icon(gtk.STOCK_FILE, gtk.ICON_SIZE_BUTTON)

			self.store.append((name, pixbuf)) # BASENAME_COL, PIXBUF_COL

	def set_thumb(self, file, pixbuf):
		'''callback to replace the placeholder icon by a background generated thumbnail'''
		if not file.dir == self.dir:
			return

		name = file.basename
		def update(model, path, iter):
			if model[iter][BASENAME_COL] == name:
				model[iter][PIXBUF_COL] = pixbuf

		self.store.foreach(update)

	def on_item_activated(self, iconview, path):
		iter = self.store.get_iter(path)
		file = self.dir.file(self.store[iter][BASENAME_COL])
		self.ui.open_file(file)

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

		submenu = OpenWithMenu(file)
		item.set_submenu(submenu)

		item = gtk.MenuItem(_('_Open')) # T: menu item to open file or folder
		item.connect('activate', lambda o: self.ui.open_file(file))
		menu.prepend(item)

		menu.show_all()

	def query_tooltip_icon_view_cb(self, widget, x, y, keyboard_tip, tooltip):
		context = widget.get_tooltip_context(x, y, keyboard_tip)
		if not context:
			return False

		model, path, iter = context
		name = model[iter][BASENAME_COL]
		file = self.dir.file(name)
		pixbuf = self.thumbman.get_thumbnail(file, PREVIEW_SIZE)
		if not pixbuf:
			pixbuf = model[iter][PIXBUF_COL]

		# TODO stat file for size and m_time

		f_label = _('Name') # T: label for file name
		s_label = _('Size') # T: label for file size
		m_label = _('Modified') # T: label for file modification date
		tooltip.set_markup(
			"<b>%s:</b> %s\n <b>%s:</b> %s\n<b>%s:</b> %s" % (
				f_label, name,
				s_label, 'TODO',
				m_label, 'TODO',
			))
		tooltip.set_icon(pixbuf)
		widget.set_tooltip_item(tooltip, path)

		return True



class ThumbnailManager():
	''' Thumbnail handling following freedesktop.org spec mostly'''

	def __init__(self, preferences):
		self.preferences = preferences
		self.queue=[]
		self.worker_is_active=False
		self.lock = AsyncLock()

		for dir in (
			LOCAL_THUMB_STORAGE_NORMAL,
			LOCAL_THUMB_STORAGE_LARGE,
			LOCAL_THUMB_STORAGE_FAIL
		):
			try:
				dir.touch(mode=0700)
			except OSError:
				pass


	def get_thumbnailfile(self, file, size):
		'''generates md5 hash and appends it to local thumb storage
		@param file: a L{File} object for the original file
		@paran size: size in pixels for the requested thumbnail
		@returns: a L{File} object for the thumbnail (may not yet exist)
		'''
		assert isinstance(file, File)
		name = hashlib.md5(file.uri).hexdigest() + '.png'
		#  ~/.thumbnails/normal
		# it is a png file and name is the md5 hash calculated earlier
		if (size<=THUMB_SIZE_NORMAL):
			return LOCAL_THUMB_STORAGE_NORMAL.file(name)
		else:
			return LOCAL_THUMB_STORAGE_LARGE.file(name)

	def get_tmp_thumbnailfile(self, file, size):
		name = hashlib.md5(file.uri).hexdigest() + '.png'
		return TmpFile('thumbnails/%s/%s' % (str(size), name), unique=False, persistent=True)

	def get_fail_thumbnailfile(self, file):
		name = hashlib.md5(file.uri).hexdigest() + '.png'
		return LOCAL_THUMB_STORAGE_FAIL.file(name)

	def _file_to_image_pixbbuf(self,infile,outfile,w,h,fileinfo=None):
		#logger.debug('file_to_image('+ filenameabs +','+','+thumbfilenameabs +','+','+ size +')'
		size=str(w)+'x'+str(h)
		try:
			logger.debug('Trying PixBuffer')
			pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(infile.path,w,h)
			# TODO: set image info
			#pixbuf_file = gtk.gdk.pixbuf_new_from_file(infile)
			#pixbuf=pixbuf_file.scale_simple(w, h)
			# TODO: save to tmp and ten move
			pixbuf.save(outfile.path,'png')
			return pixbuf
		except:
			logger.debug('  Error converting Image')

	def _file_to_image_magick(self,infile,outfile,w,h,fileinfo=None):
		''' pdf to thumbnail '''
		try:
			logger.debug('  trying Imagemagick')
			infile_p1=infile.path +'[0]' # !????
			#print infile_p1
			size=str(w)+'x'+str(h)
			cmd = ('convert','-size', size, '-trim','+repage','-resize',size+'>')
			Application(cmd).run((infile_p1, outfile.path))
			return True
		except:
			logger.exception('Error running %s', cmd)
		return False

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


	def _file_to_image_txt(self,infile,outfile,w,h,fileinfo=None):
		try:
			textcont='caption:'
			size=str(h/4*3)+'x'+str(h)
			linecount=0;
			# lines: 18 at 128px
			# linewidth 35 at 128px
			while linecount<(h/32+10):
				line = file.readline()
				if not line:
					break
				linecount+=1
				textcont+=line[0:w/24+12]
				if (len(line)>(w/24+12) ):
					textcont+='\n'
			logger.debug('Trying TXT')

			cmd = ('convert','-font','Courier','-size', size)# '-frame', '1' )
			Application(cmd).run((textcont,outfile.path))
			return True
		except:
			logger.debug('  Error converting TXT')
		return False

	def file_to_image(self,infile,outfile,tmpfile,w,h):
		logger.debug('file_to_image(%s, %s, %s)', infile, outfile, tmpfile)
		# try build in formats
		pixbuf=self._file_to_image_pixbbuf(infile,outfile,w,h,None)
		if pixbuf:
			return pixbuf
		elif not self.preferences['use_imagemagick']:
			return


		magickextensions=('SVG','PDF','PS','EPS','DVI','DJVU','RAW','DOT','HTML','HTM','TTF','XCF')
		textextensions=('SH','BAT','TXT','C','C++','CPP','H','H++','HPP','PY','PL') #'AVI','MPG','M2V','M4V','MPEG'
		# TODO use mimetypes here ?? "image/" and "text/" -- or isimage() and istext()

		tmpfile.touch()
		pixbuf = None
		extension=infile.path.split(".")[-1].upper()
		if extension in magickextensions:
			fileinfo=self._file_to_image_magick(infile,tmpfile,w,h,None)
			if (fileinfo):
				pixbuf = self._file_to_image_pixbbuf(tmpfile,outfile,w,h,fileinfo)
		elif extension in textextensions:
			#convert -size 400x  caption:@-  caption_manual.gif
			fileinfo=self._file_to_image_txt(infile,tmpfile,w,h,None)
			if (fileinfo):
				pixbuf=self._file_to_image_pixbbuf(tmpfile,outfile,w,h,fileinfo)
		else:
			logger.debug('Can\'t convert: %s', infile)

		try:
			tmpfile.remove()
		except OSError:
			logger.exception('Could not delete tmp file: %s', tmpfile)
		return pixbuf

	def queue_worker(self):
		#~ print 'i am the worker'
		while (len(self.queue)>0) :
			item = self.queue.pop() #work on the youngest item first
			file = item[0]
			size = item[1]
			if (size<=THUMB_SIZE_NORMAL):
				w=THUMB_SIZE_NORMAL
				h=THUMB_SIZE_NORMAL
			else:
				w=PREVIEW_SIZE
				h=PREVIEW_SIZE

			thumbfile = self.get_thumbnailfile(file, size)
			tmpfile = self.get_tmp_thumbnailfile(file, size)

			if not (tmpfile.exists() or thumbfile.exists()):
				pixbuf=self.file_to_image(file, thumbfile, tmpfile, w, h)

			if pixbuf:
				if (item[2]):
					#print 'job done try callback'
					fkt=item[2]
					parm=item[3]
					fkt(parm,pixbuf)
			else:
				#print 'thumb create failed'
				self.get_fail_thumbnailfile(file).touch()

			# FIXME FIXME - shouldn't we call the callback here !???

		self.worker_is_active=False
		#print 'queue worker: job done'


	def start_queue_worker(self):
		#print 'start_queue_worker'
		#print '  remaining jobs:' + str(len(self.queue))
		#print '  current job: '+ self.queue[-1][0]
		if not self.worker_is_active:
			self.worker_is_active=True
			try:
				#print 'worker started'
				AsyncOperation(self.queue_worker,lock=self.lock).start()
			except:
				self.worker_is_active=False
				#print 'worker died'


	def enqueue(self, file, size, set_pixbuf_callback, callbackparm):
		#logger.debug ("Thumbnail enqueued:" +filenameabs+","+str(size)+","+str(pixbuf))
		# start thumb generator in bg, if not already

		# dont enqueue twice
		found=False
		for e in self.queue:
			if e[0]==file:
				logger.debug("Already in the queue: %s", file)
				break
		else: # no break
			self.queue.append((file, size, set_pixbuf_callback, callbackparm))
			logger.debug ("Thumbnail enqueued: %s @ %s", file, size)

		self.start_queue_worker()


	def clear(self):
		''' clears the queue'''
		self.queue=[]


	def get_thumbnail(self, file, size, set_pixbuf_callback=None, parm=None):
		''' create a pixbuffer

		load the thumb if available
		else load smaller thumbnail
		and generate thumb async
		'''
		thumbfile=self.get_thumbnailfile(file, size)
		#print thumbfile

		if thumbfile.exists():
			if thumbfile.mtime() < file.mtime():
				# Existing thumbnail is outdated
				try:
					thumbfile.remove()
				except OSError:
					logger.debug('Can\'t delete outdated thumbnail: %s', thumbfile)
					# TODO mark as failed
					return None
			else:
				# Load existing thumbnail
				logger.debug('Load existing thumbnail: %s', thumbfile)
				try:
					pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(thumbfile.path, size, size)
					return pixbuf
				except:
					logger.debug('Error loading thumbnail')
					# TODO mark as failed
					return None

		# Enqueue for background creation
		self.enqueue(file, size, set_pixbuf_callback, parm)

		# try to load the other size temporarily
		#~ if (size<=THUMB_SIZE_NORMAL):
			#~ size_alt=THUMB_SIZE_LARGE
		#~ else:
			#~ size_alt=THUMB_SIZE_NORMAL

		#~ logger.debug('  load alternative size')
		#~ thumbfile=self.get_thumbnailfilename(filenameabs,size_alt)
		#~ if (os.path.isfile(thumbfile)) and (os.stat(thumbfile).st_mtime > os.stat(filenameabs).st_mtime):
				#~ try:
					#~ logger.debug('  load alt thumbnail')
					#~ pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(thumbfile,size,size)
					#~ return pixbuf
				#~ except:
					#~ logger.debug('  Error loading alt. thumbnail')
		#~ else:
			#~ logger.debug('  alt thumbnail not valid')
		# enqueue for background creation



		# race condition: if the tb generator finishes first
		# the caller must take care for the icon
		#logger.debug('  Fallback: stock icon')
		#widget = gtk.HBox() # Need *some* widget here...
		# TODO: icon by mime-type
		#pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE,gtk.ICON_SIZE_DIALOG)
		#return pixbuf
		return None
