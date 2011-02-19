# -*- coding: utf-8 -*-
#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
#           2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# License:  same as zim (gpl)
#
# ChangeLog
# 2011-01-25 Refactored widget and plugin code (Jaap)
#		tested on gtk < 2.12 (tooltip interface)
#		add pref for image magick (convert cmd exists on win32 but is not the same)
#		added buttons to side of widget
# 2011-01-02 Fixed use of uistate and updated for new framework to add to the mainwindow (Jaap)
# 2010-11-14 Fixed Bug 664551
# 2010-08-31 freedesktop.org thumnail spec mostly implemented
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
# [ ] use thumbnailes/settings from gnome or other DEs
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

import hashlib # for thumbfilenames
import tempfile
import os
import re
import logging

import gobject
import gtk
import pango


from zim.async import AsyncOperation, AsyncLock
from zim.plugins import PluginClass
from zim.gui.widgets import Button, BOTTOM_PANE, IconButton
from zim.notebook import Path
from zim.stores import encode_filename
from zim.fs import *
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

# freedesktop.org thumbnail storage
def get_home_dir():
	try:
		from win32com.shell import shellcon, shell
		homedir = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, 0, 0)
	except ImportError: # quick semi-nasty fallback for non-windows/win32com case
		homedir = os.path.expanduser("~")
	return homedir


# freedesktop.org spec
LOCAL_THUMB_STORAGE=get_home_dir()+os.sep+'.thumbnails'
LOCAL_THUMB_STORAGE_NORMAL = LOCAL_THUMB_STORAGE+os.sep+'normal'
LOCAL_THUMB_STORAGE_LARGE = LOCAL_THUMB_STORAGE+os.sep+'large'
# TODO: import zim version
LOCAL_THUMB_STORAGE_FAIL = LOCAL_THUMB_STORAGE+os.sep+'fail'+os.sep+'zim-0.48'
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
		#~ 'help': 'Plugins:AttachmentBrowser',
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
		try:
			os.mkdir(LOCAL_THUMB_STORAGE_NORMAL,0700)
		except:
			pass
		try:
			os.mkdir(LOCAL_THUMB_STORAGE_LARGE,0700)
		except:
			pass
		try:
			os.mkdir(LOCAL_THUMB_STORAGE_FAIL,0700)
		except:
			pass


	def get_thumbnailfilename(self,filename,size):
		'''generates md5 hash and appedns ist to local thums storage '''
		file_hash = hashlib.md5('file://'+filename).hexdigest()
		#  ~/.thumbnails/normal
		# it is a png file and name is the md5 hash calculated earlier
		if (size<=THUMB_SIZE_NORMAL):
			fn = os.path.join(LOCAL_THUMB_STORAGE_NORMAL,file_hash) + '.png'
		else:
			fn = os.path.join(LOCAL_THUMB_STORAGE_LARGE,file_hash) + '.png'
		return fn

	def get_tmp_thumbnailfilename(self,filename,size):
		file_hash = hashlib.md5('file://'+filename).hexdigest()
		return os.path.join(tempfile.gettempdir(),file_hash+str(os.getpid())+'-'+str(size)+'.png')

	def get_fail_thumbnailfilename(self,filename):
		file_hash = hashlib.md5('file://'+filename).hexdigest()
		return os.path.join(LOCAL_THUMB_STORAGE_FAIL,file_hash) + '.png'


	def _file_to_image_pixbbuf(self,infile,outfile,w,h,fileinfo=None):
		#logger.debug('file_to_image('+ filenameabs +','+','+thumbfilenameabs +','+','+ size +')'
		size=str(w)+'x'+str(h)
		try:
			logger.debug('  trying PixBuffer')
			pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(infile,w,h)
			# TODO: set image info
			#pixbuf_file = gtk.gdk.pixbuf_new_from_file(infile)
			#pixbuf=pixbuf_file.scale_simple(w, h)
			# TODO: save to tmp and ten move
			pixbuf.save(outfile,'png')
			return pixbuf
		except:
			logger.debug('  Error converting Image')

	def _file_to_image_magick(self,infile,outfile,w,h,fileinfo=None):
		''' pdf to thumbnail '''
		try:
			logger.debug('  trying Imagemagick')
			infile_p1=infile +'[0]'
			#print infile_p1
			size=str(w)+'x'+str(h)
			pdftopng_cmd = ('convert','-size', size, '-trim','+repage','-resize',size+'>')
			#print pdftopng_cmd
			pdftopng = Application(pdftopng_cmd)
			pdftopng.run((infile_p1, outfile))
			return True
		except:
			logger.debug('  Error converting PDF')
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
			file = open(infile)
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
			logger.debug('  trying TXT')

			txttopng_cmd = ('convert','-font','Courier','-size', size)# '-frame', '1' )
			txttopng = Application(txttopng_cmd)
			txttopng.run((textcont,outfile))
			return True
		except:
			logger.debug('  Error converting TXT')
		return False

	def file_to_image(self,infile,outfile,tmpfile,w,h):
		logger.debug('file_to_image('+ infile +','+ outfile +','+ tmpfile +')')
		# try build in formats
		pixbuf=self._file_to_image_pixbbuf(infile,outfile,w,h,None)
		if pixbuf:
			return pixbuf
		elif not self.preferences['use_imagemagick']:
			return

		extension=infile.split(".")[-1].upper()
		#print extension
		#touch the tmpfile first
		open(tmpfile, "a")

		magickextensions=('SVG','PDF','PS','EPS','DVI','DJVU','RAW','DOT','HTML','HTM','TTF','XCF')
		textextensions=('SH','BAT','TXT','C','C++','CPP','H','H++','HPP','PY','PL') #'AVI','MPG','M2V','M4V','MPEG'


		if extension in magickextensions:
			fileinfo=self._file_to_image_magick(infile,tmpfile,w,h,None)
			if (fileinfo):
				pixbuf=self._file_to_image_pixbbuf(tmpfile,outfile,w,h,fileinfo)
				try:
					os.remove(tmpfile)
				except:
					pass #print "cant del tmpfile"
				return pixbuf
		elif extension in textextensions:
			#convert -size 400x  caption:@-  caption_manual.gif
			fileinfo=self._file_to_image_txt(infile,tmpfile,w,h,None)
			if (fileinfo):
				pixbuf=self._file_to_image_pixbbuf(tmpfile,outfile,w,h,fileinfo)
				try:
					os.remove(tmpfile)
				except:
					pass  #print "cant del tmpfile"
				return pixbuf


	def queue_worker(self):
		print 'i am the worker'
		while (len(self.queue)>0) :
			item=self.queue.pop() #work on the youngest item first
			filenameabs=item[0]
			size=item[1]
			if (size<=THUMB_SIZE_NORMAL):
				w=THUMB_SIZE_NORMAL
				h=THUMB_SIZE_NORMAL
			else:
				w=PREVIEW_SIZE
				h=PREVIEW_SIZE
			thumbfile=self.get_thumbnailfilename(filenameabs,size)
			tmpfile=self.get_tmp_thumbnailfilename(filenameabs,size)
			if (not os.path.isfile(tmpfile)) and (not os.path.isfile(thumbfile)):
				pixbuf=self.file_to_image(filenameabs,thumbfile,tmpfile,w,h)

			if pixbuf:
				if (item[2]):
					#print 'job done try callback'
					fkt=item[2]
					parm=item[3]
					fkt(parm,pixbuf)
			else:
				#print 'thumb crate failed'
				open (self.get_fail_thumbnailfilename(filenameabs) ,"a")
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


	def enqueue(self,filenameabs,size,set_pixbuf_callback,callbackparm):
		#logger.debug ("Thumbnail enqueued:" +filenameabs+","+str(size)+","+str(pixbuf))
		# start thumb generator in bg, if not allready

		# dont enqueue twice
		found=False
		for e in self.queue:
			if e[0]==filenameabs:
				found=True
				break
		if not found:
			self.queue.append((filenameabs,size,set_pixbuf_callback,callbackparm))
			logger.debug ("thumbnail enqueued:" +filenameabs+","+str(size))
			#print self.queue
		else:
			logger.debug ("  already in the queue:" +filenameabs+","+str(size))
		self.start_queue_worker()


	def clear(self):
		''' clears the queue'''
		self.queue=[]


	def get_thumbnail(self, file, size, set_pixbuf_callback=None, parm=None):
		''' create a pixbuffer
			load the thumb if available
			else load smaller thumbnail
			  and genertate thumb asyncr'''
		filenameabs = file.path
		#print 'get_thumbnail(' , filenameabs ,size

		# FIXME size handling
		if (size<=THUMB_SIZE_NORMAL):
			size_alt=THUMB_SIZE_LARGE
		else:
			size_alt=THUMB_SIZE_NORMAL
		thumbfile=self.get_thumbnailfilename(filenameabs,size)
		#print thumbfile

		# delete outdated thumbnail
		try:
			if (os.path.isfile(thumbfile)):
				if (os.stat(thumbfile).st_mtime < os.stat(filenameabs).st_mtime):
					logger.debug('  delete outdated thumbnail ')
					os.remove(thumbfile)
		except:
			logger.debug('  can''t delete outdated thumbnail ')

		if (os.path.isfile(thumbfile)):
			try: # load existing thumbnail
				logger.debug('  load existing thumbnail')
				pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(thumbfile,size,size)
				return pixbuf
			except:
				logger.debug('  Error loading thumbnail')
		else:
				logger.debug('  thumbnail not valid')
				# dont try again
				# TODO check_failed
				if  (os.path.isfile ( self.get_fail_thumbnailfilename(filenameabs) ) ):
					if ( os.stat( self.get_fail_thumbnailfilename(filenameabs)).st_mtime > os.stat(filenameabs).st_mtime):
						#print "marked as fail"
						return None
					#else:
					#print "  ignore old marked as fail"

					#else: remove fail-mark

				# enque for background creation
				self.enqueue(filenameabs,size,set_pixbuf_callback,parm)

				# try to load the other size temporarly
				logger.debug('  load alternavie size')
				thumbfile=self.get_thumbnailfilename(filenameabs,size_alt)
				if (os.path.isfile(thumbfile)) and (os.stat(thumbfile).st_mtime > os.stat(filenameabs).st_mtime):
						try:
							logger.debug('  load alt thumbnail')
							pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(thumbfile,size,size)
							return pixbuf
						except:
							logger.debug('  Error loading alt. thumbnail')
				else:
					logger.debug('  alt thumbnail not valid')
				# enque for background creation



		# race codidion: if the tb generator finisches first
		# the caller must take care for the icon
		#logger.debug('  Fallback: stock icon')
		#widget = gtk.HBox() # Need *some* widget here...
		# TODO: icon by mime-type
		#pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE,gtk.ICON_SIZE_DIALOG)
		#return pixbuf
		return None


