# -*- coding: utf-8 -*-
#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
# License:  same as zim (gpl)
#
# ChangeLog
# 2010-08-31 freedesktop.org thumnail spec mostly implemented
# 2010-06-29 1st working version
#
# Bugs:
# textrendering is slow
# problems with Umlaut in filenames
# TODO:
# * integer plugin_preferences do not to work as expected (zim bug?)
# * toggle: inital toolbar button state wrong
# * toggle-btn icon
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
# [ ] use mimtype and extension
# [*] rethumb broken (e.g. shutdown while thumbnailing)
# [ ] code cleanup
# [ ] new gui concept for zim : sidepane r/l,bottom- and top pane both with tabs (see gedit)
# [ ] show file infos in tooltip (size, camera,... what else?)
# [*] update icon when thumbnail is ready
# [ ] mimi-type specific icons
# [ ] evaluate imagemagick python libs
# [ ] thumbnailers as plugins
# [ ] libgsf thumbnailer
# [ ] use thumbnailes/settings from gnome or other DEs
# [ ] make a reference implementation for thumbnail spec
# [ ] rewrite thumbnail spec
# http://ubuntuforums.org/showthread.php?t=76566
#
#
# tooltip example
#  http://nullege.com/codes/show/src@pygtk-2.14.1@examples@pygtk-demo@demos@tooltip.py/160/gtk.gdk.Color
# file info example
#  http://ubuntuforums.org/showthread.php?t=880967
#

'''Zim plugin to display files in attachments folder.'''

import hashlib # for thumbfilenames
import shutil
import tempfile


import gobject
import gtk

import pango

import os
import stat
import time

import re
import logging
from datetime import date as dateclass

from zim.async import AsyncOperation, AsyncLock


from zim.plugins import PluginClass
from zim.gui import Dialog
from zim.gui.widgets import Button
from zim.notebook import Path
from zim.stores import encode_filename
from zim.fs import *
from zim.errors import Error
logger = logging.getLogger('zim.plugins.attachmentbrowser')
from zim.applications import Application
from zim.gui.applications import OpenWithMenu


ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('toggle_fileview', gtk.STOCK_MISSING_IMAGE, _('AttachmentBrowser'),  '', 'Show Attachment Folder',False, True), # T: menu item
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
		'name': _('Atachment Browser'), # T: plugin name
		'description': _('''\
This plugin shows the attachments folder of the current page as an
icon view at bottom pane.

This plugin is still under development.
'''), # T: plugin description
		'author': 'Thorsten Hackbarth <thorsten.hackbarth@gmx.de>',
		#~ 'help': 'Plugins:AttachmentBrowser',
	}

	#plugin_preferences = (
	#	# key, type, label, default
	#	('icon_size', 'int', _('Icon size [px]'), [ICON_SIZE_MIN,128,ICON_SIZE_MAX]), # T: preferences option
	#	('preview_size', 'int', _('Tooltip preview size [px]'), (THUMB_SIZE_MIN,480,THUMB_SIZE_MAX)), # T: input label
	#	('thumb_quality', 'int', _('Preview jpeg Quality [0..100]'), (0,50,100)), # T: input label
	#)

	@classmethod
	def check_dependencies(klass):
		return [("ImageMagick",Application(('convert',None)).tryexec())]


	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.bottompane_widget = None
		self.scrollpane = None
		if self.ui.ui_type == 'gtk':
			self.ui.add_toggle_actions(ui_toggle_actions, self)
			#self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
		self.ui.connect_after('open-notebook', self.do_open_notebook)


	def do_open_notebook(self, ui, notebook):
		self.do_preferences_changed()
		#notebook.register_hook('suggest_link', self.suggest_link)


	def disconnect(self):
		PluginClass.disconnect(self)


	def add_to_mainwindow(self):
		bottompane = self.ui.mainwindow.pageview.get_parent()
		if self.bottompane_widget is None:
			self.bottompane_widget = AttachmentBrowserPluginWidget(self)
			self.scrollpane=gtk.ScrolledWindow()
			self.scrollpane.set_size_request(-1,THUMB_SIZE_NORMAL+32)
			self.scrollpane.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
			self.scrollpane.add_with_viewport(self.bottompane_widget)
			bottompane.pack_end(self.scrollpane, False)
		#bottompane.pack_end(self.bottompane_widget, False)

		#bottompane.reorder_child(self.bottompane_widget, 0)
		self.handlerID_do_open_notebook=self.ui.connect_after('open-notebook', self.do_open_notebook)
		#self.bottompane_widget.show_all()
		self.scrollpane.show_all()


	def remove_from_mainwindow(self):
		if self.bottompane_widget is not None:
			#doesnt work:? self.ui.disconnect(self.handlerID_do_open_notebook)
			self.scrollpane.hide_all()


	def do_preferences_changed(self):
		#print self.preferences['icon_size']

		# bug?
		#
		# self.preferences['icon_size'] is integer after  changeing it
		# but must be (min,val,max) for the dialog, which is strange

		self.add_to_mainwindow()


	def toggle_fileview(self, enable=None):
		action = self.actiongroup.get_action('toggle_fileview')
		if enable is None or enable != action.get_active():
			action.activate()
		else:
			self.do_toggle_fileview(enable=enable)


	def do_toggle_fileview(self, enable=None):
		#~ print 'do_toggle_fileview', enable
		if enable is None:
			action = self.actiongroup.get_action('toggle_fileview')
			enable = action.get_active()
		if enable:
			# print "enabled"
			self.add_to_mainwindow()
		else:
			# print "disabled"
			self.remove_from_mainwindow()
		self.uistate['active'] = enable
		return False # we can be called from idle event




class Fileview(gtk.IconView):
	'''Custom fileview widget class. Adds an 'activate' signal for what i dont know yet'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'activate': (gobject.SIGNAL_RUN_LAST, None, ()),
	}


class ThumbnailManager():
	''' Thumbnail handling following freedesktop.org spec mostly'''
	def __init__(self):
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


	def get_thumbnail(self,filenameabs,size,set_pixbuf_callback=None,parm=None):
		''' create a pixbuffer
			load the thumb if available
			else load smaller thumbnail
			  and genertate thumb asyncr'''
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



# Need to register classes defining gobject signals
gobject.type_register(Fileview)


class AttachmentBrowserPluginWidget(gtk.HBox):
	__gsignals__ = {
		'modified-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}
	def __init__(self, plugin):
		gtk.HBox.__init__(self)
		self.plugin = plugin
		self.thumbman = ThumbnailManager()
		self.fileview = Fileview()
		self.store = None
		self.store=gtk.ListStore(str, gtk.gdk.Pixbuf,str) #gtk.TextBuffer()
		#self.fileview.set_buffer(self.textbuffer)
		self.fileview.set_model(self.store)
		self.fileview.set_text_column(0)
		self.fileview.set_pixbuf_column(1)

		self.pack_start(self.fileview, True)

		self.plugin.ui.connect('open-page', self.on_open_page)

		self.fileview.connect_object('button-press-event',AttachmentBrowserPluginWidget.on_button_press_event, self)
		#self.fileview.set_tooltip_column(2) # filename as tooltip
		self.fileview.props.has_tooltip = True
		# custom tooltip
		self.fileview.connect("query-tooltip", self.query_tooltip_icon_view_cb)


	def on_button_press_event(self,event):
		# print 'on_button_press_event'
		if event.button == 3:
			popup_menu=gtk.Menu()
			x = int(event.x)
			y = int(event.y)
			time = event.time
			#iteminfo = self.fileview.get_item_at_pos(x, y)
			pathinfo = self.fileview.get_path_at_pos(x, y)
			if pathinfo is not None:
				self.fileview.grab_focus()
				#print self.store.get_value(self.store.get_iter(pathinfo),2)
				popup_menu.popup(None, None, None, event.button, time)
				self.do_populate_popup(popup_menu,pathinfo)
				return True
		return False


	def set_current_folder(self,path):
		self.store.clear()
		self.thumbman.clear()
		if not os.path.isdir(path):
			# TODO maybe hide myself
			# FIXME: ugly hack
			if (self.plugin.uistate['active']):
				self.plugin.remove_from_mainwindow()
			return
		if (self.plugin.uistate['active'] ):
			self.plugin.add_to_mainwindow()

		filelist = os.listdir(path)
		for filename in filelist:
			#	self.textbuffer.insert_at_cursor(filename+'\n')
			filenameabs=path+os.sep+filename
			# only for existing files
			# and not for blocked
			if os.path.isfile(filenameabs) and filename[0]!='.': #.encode('utf-8')):
				widget = gtk.HBox() # Need *some* widget here...
				# TODO: icon by mime-type
				pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE,gtk.ICON_SIZE_DIALOG)
				# TODO: thumbman with callback
				listelement=self.store.append( [filename,pixbuf,path] )
				pixbuf=self.thumbman.get_thumbnail(filenameabs,THUMB_SIZE_NORMAL,self.set_thumb,listelement)
				if pixbuf is not None:
					self.set_thumb(listelement,pixbuf)


	def set_thumb(self,listelement,pixbuf):
		'''callback to replace the placeholder icon by a background generated thumbnail'''
		self.store.set(listelement,1,pixbuf)


	def do_populate_popup(self, menu,pathinfo):
		# print "do_populate_popup"
		file= File(self.store.get_value(self.store.get_iter(pathinfo),2)+os.sep+self.store.get_value(self.store.get_iter(pathinfo),0))

		# open with & open folder
		item = gtk.MenuItem(_('Open Folder'))
			# T: menu item to open containing folder of files
		menu.prepend(item)

		dir = file.dir
		if dir.exists():
			item.connect('activate', lambda o: self.plugin.ui.open_file(dir))
		else:
			item.set_sensitive(False)

		item = gtk.MenuItem(_('Open With...'))
		menu.prepend(item)

		submenu = OpenWithMenu(file)
		item.set_submenu(submenu)

		menu.show_all()


	def query_tooltip_icon_view_cb(self, widget, x, y, keyboard_tip, tooltip):
		if not widget.get_tooltip_context(x, y, keyboard_tip):
			return False
		else:
			model, path, iter = widget.get_tooltip_context(x, y, keyboard_tip)
			value = model.get(iter, 0)
			tooltip.set_markup("<b>Filename: </b> %s \n <b>Size: </b> %s \n <b>Date: </b> %s" %(value[0],'(UNKNOWN)','(UNKNOWN)'))
			filename=model.get(iter, 0)[0]
			filepath=model.get(iter, 2)[0]
			filenameabs=filepath+os.sep+filename

			tooltip.set_icon(self.thumbman.get_thumbnail(filenameabs,PREVIEW_SIZE))

			widget.set_tooltip_item(tooltip, path)
			return True


	def on_open_page(self, ui, page, path):
		try:
			#print path
			#print encode_filename(page.name)
			self.set_current_folder(str(self.plugin.ui.notebook.get_attachments_dir(page)+os.sep))
		except AssertionError:
			pass

