# -*- coding: utf-8 -*-
#
# Copyright 2010 Thorsten Hackbarth <thorsten.hackbarth@gmx.de>
#           2011-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# License:  same as zim (gpl)
#
#
# !! NOTE: when changing this plugin, do test performance on a folder with lots of photos!
#


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

from __future__ import with_statement


import os
import hashlib
import time
import threading
import Queue

import gtk

import logging

logger = logging.getLogger('zim.plugins.attachmentbrowser')


import zim

from zim.config import XDG_CACHE_HOME
from zim.gui.widgets import rotate_pixbuf


LOCAL_THUMB_STORAGE_NORMAL = XDG_CACHE_HOME.subdir('thumbnails/normal')
LOCAL_THUMB_STORAGE_LARGE = XDG_CACHE_HOME.subdir('thumbnails/large')
LOCAL_THUMB_STORAGE_FAIL = XDG_CACHE_HOME.subdir('thumbnails/fail/zim-%s' % zim.__version__)

THUMB_SIZE_NORMAL = 128
THUMB_SIZE_LARGE = 256


class ThumbnailCreatorFailure(ValueError):
	pass


from zim.fs import _replace_file as _atomic_rename

def pixbufThumbnailCreator(file, thumbfile, thumbsize):
	'''Thumbnailer implementation that uses the C{gtk.gdk.Pixbuf}
	functions to create the thumbnail.
	'''
	tmpfile = thumbfile.dir.file('zim-thumb.new~')
	options = { # no unicode allowed in options!
		'tEXt::Thumb::URI': str( file.uri ),
		'tEXt::Thumb::MTime': str( int( file.mtime() ) ),
	}
	try:
		pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.encodedpath, thumbsize, thumbsize)
		pixbuf = rotate_pixbuf(pixbuf)
		pixbuf.save(tmpfile.encodedpath, 'png', options)
		_atomic_rename(tmpfile.encodedpath, thumbfile.encodedpath)
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
