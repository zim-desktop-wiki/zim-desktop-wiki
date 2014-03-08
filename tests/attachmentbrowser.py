# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.parsing import url_encode, URL_ENCODE_READABLE
from zim.plugins.attachmentbrowser import *

class TestMimeData(tests.TestCase):

	def runTest(self):
		dir = Dir('./data/pixmaps')
		for filename in dir.list():
			file = dir.file(filename)
			icon = get_mime_icon(file, THUMB_SIZE_NORMAL)
			desc = get_mime_description(file.get_mimetype())
			# TODO assert something on icon and text ?


class ThumbnailManagerTest(tests.TestCase):

	def testCreateThumbnail(self):
		manager = ThumbnailManager(preferences={})
		dir = Dir('./data/pixmaps')

		# Test API and functions
		#~ for file in dir.list_objects(): # TODO
		for filename in dir.list():
			file = dir.file(filename)

			# Remove and assert thumbnail does not exist
			manager.remove_thumbnails(file)
			for size in (THUMB_SIZE_NORMAL, THUMB_SIZE_LARGE):
				thumbfile = manager.get_thumbnail_file(file, size)
				self.assertFalse(thumbfile.exists(), msg="File exists: %s" % thumbfile)

			# Get thumbnails - twice, first they don't exist, than they do
			for (size, pixels) in (
				(THUMB_SIZE_NORMAL, 128),
				(THUMB_SIZE_LARGE, 256),
				(THUMB_SIZE_NORMAL, 128),
				(THUMB_SIZE_LARGE, 256),
			):
				thumb = manager.get_thumbnail(file, size)
				self.assertIsInstance(thumb, gtk.gdk.Pixbuf)
				self.assertEqual(thumb.get_width(), pixels)
				self.assertEqual(thumb.get_height(), pixels)
				self.assertTrue(thumb.get_option('tEXt::Thumb::URI').startswith('file:///'))
					# Specific requirement of spec to use file:/// and not file://localhost/
				self.assertEqual(thumb.get_option('tEXt::Thumb::URI'), url_encode(file.uri, URL_ENCODE_READABLE))
				self.assertEqual(thumb.get_option('tEXt::Thumb::MTime'), str( int( file.mtime() ) ))

				thumbfile = manager.get_thumbnail_file(file, size)
				self.assertTrue(thumbfile.exists(), msg="Missing file: %s" % thumbfile)
				basename = hashlib.md5(file.uri).hexdigest() + '.png'
				self.assertEqual(thumbfile.basename, basename)
				# TODO assert permission on file is 0600 -- stat ?

			# TODO test detection of invalid thumbs
			# TODO test with utf-8 char in image name


	def testAsyncCreateThumbnail(self):
		manager = ThumbnailManager(preferences={})
		dir = Dir('./data/pixmaps')

		seen = set()
		def on_thumbnail_ready(o, file, size, pixbuf):
			seen.add(file)
		manager.connect('thumbnail-ready', on_thumbnail_ready)

		# Test API and functions
		#~ for file in dir.list_objects(): # TODO
		for filename in dir.list():
			file = dir.file(filename)

			# Remove and assert thumbnail does not exist
			manager.remove_thumbnails(file)
			for size in (THUMB_SIZE_NORMAL, THUMB_SIZE_LARGE):
				manager.get_thumbnail_async(file, size)

		manager.async_queue.join()
		self.assertTrue(len(seen) > 3)

