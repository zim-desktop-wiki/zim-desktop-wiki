
# Copyright 2012,2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>





import tests

import time

from zim.newfs import LocalFile, LocalFolder

from zim.plugins.attachmentbrowser.thumbnailer import *
from zim.plugins.attachmentbrowser.filebrowser import FileBrowserIconView


@tests.slowTest
class TestThumbnailCreators(tests.TestCase):

	creators = [pixbufThumbnailCreator]

	def runTest(self):
		for creator in self.creators:
			thumbdir = LocalFolder(self.create_tmp_dir(creator.__name__))

			dir = LocalFolder(tests.ZIM_DATADIR).folder('pixmaps')
			for i, basename in enumerate(dir.list_names()):
				if basename.endswith('.svg'):
					continue # fails on windows in some cases
				file = dir.file(basename)
				thumbfile = thumbdir.file('thumb--' + basename)

				self.assertFalse(thumbfile.exists())
				pixbuf = creator(file, thumbfile, THUMB_SIZE_NORMAL)
				self.assertIsInstance(pixbuf, GdkPixbuf.Pixbuf)
				self.assertTrue(thumbfile.exists())

				pixbuf = GdkPixbuf.Pixbuf.new_from_file(thumbfile.path)
				self.assertEqual(pixbuf.get_option('tEXt::Thumb::URI'), file.uri)
				self.assertTrue(pixbuf.get_option('tEXt::Thumb::URI').startswith('file:///'))
					# Specific requirement of spec to use file:/// and not file://localhost/
				self.assertEqual(int(pixbuf.get_option('tEXt::Thumb::MTime')), int(file.mtime()))

			self.assertTrue(i > 3)

			src_file = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL).file('test.txt')
			src_file.write('Test 123\n')
			thumbfile = thumbdir.file('thumb-test.txt')
			self.assertRaises(
				ThumbnailCreatorFailure,
				creator, src_file, thumbfile, THUMB_SIZE_NORMAL
			)

@tests.slowTest
class TestThumbnailManager(tests.TestCase):

	def testThumbnailFile(self):
		manager = ThumbnailManager()

		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('./foo-\u00e8\u00e1\u00f1.png') # non-existing path with unicode name
		self.assertTrue('%C3%A8%C3%A1%C3%B1' in file.uri) # utf encoded!
		basename = hashlib.md5(file.uri.encode('ascii')).hexdigest() + '.png'

		for file, size, wanted in (
			(file, 28, LOCAL_THUMB_STORAGE_NORMAL.file(basename)),
			(file, 64, LOCAL_THUMB_STORAGE_NORMAL.file(basename)),
			(file, 128, LOCAL_THUMB_STORAGE_NORMAL.file(basename)),
			(file, 200, LOCAL_THUMB_STORAGE_LARGE.file(basename)),
			(file, 500, LOCAL_THUMB_STORAGE_LARGE.file(basename)),
		):
			thumbfile = manager.get_thumbnail_file(file, size)
			self.assertEqual(thumbfile, wanted)
			self.assertTrue(len(thumbfile.basename) == 32 + 4) # lenght hexdigest according to spec + ".png"

	def removeThumbnail(self, manager, file):
		# Remove and assert thumbnail does not exist
		manager.remove_thumbnails(file)
		for size in (THUMB_SIZE_NORMAL, THUMB_SIZE_LARGE):
			thumbfile = manager.get_thumbnail_file(file, size)
			self.assertFalse(thumbfile.exists(), msg="File exists: %s" % thumbfile)

	def testCreateThumbnail(self):
		manager = ThumbnailManager()

		dir = LocalFolder(self.create_tmp_dir())
		file = dir.file('zim.png')
		LocalFolder(tests.ZIM_DATADIR).file('zim.png').copyto(file)
		self.assertTrue(file.exists())
		self.assertTrue(file.isimage())
		self.removeThumbnail(manager, file)

		# Thumbfile does not exist
		thumbfile, pixbuf = manager.get_thumbnail(file, 64, create=False)
		self.assertEqual((thumbfile, pixbuf), (None, None))

		thumbfile, pixbuf = manager.get_thumbnail(file, 64)
		self.assertTrue(thumbfile.exists())
		self.assertIsInstance(pixbuf, GdkPixbuf.Pixbuf)

		thumbfile, pixbuf = manager.get_thumbnail(file, 64)
		self.assertTrue(thumbfile.exists())
		self.assertIsInstance(pixbuf, GdkPixbuf.Pixbuf)

		if os.name != 'nt': # Windows support chmod() is limitted
			import stat
			mode = os.stat(thumbfile.path).st_mode
			self.assertEqual(stat.S_IMODE(mode), 0o600)
			mode = os.stat(thumbfile.parent().parent().path).st_mode # thumnails dir
			self.assertEqual(stat.S_IMODE(mode), 0o700)

		# Change mtime to make thumbfile invalid
		oldmtime = file.mtime()
		os.utime(file.path, None)
		self.assertNotEqual(file.mtime(), oldmtime)

		thumbfile, pixbuf = manager.get_thumbnail(file, 64, create=False)
		self.assertEqual((thumbfile, pixbuf), (None, None))

		thumbfile, pixbuf = manager.get_thumbnail(file, 64)
		self.assertTrue(thumbfile.exists())
		self.assertIsInstance(pixbuf, GdkPixbuf.Pixbuf)

		# ensure next call to get_thumbnail cannot call create_thumbnail
		manager.create_thumbnail = None

		thumbfile, pixbuf = manager.get_thumbnail(file, 64)
		self.assertTrue(thumbfile.exists())
		self.assertIsInstance(pixbuf, GdkPixbuf.Pixbuf)

		# Test remove
		self.removeThumbnail(manager, file)


@tests.slowTest
class TestThumbnailQueue(tests.TestCase):

	def testQueue(self):
		queue = ThumbnailQueue()
		self.assertTrue(queue.queue_empty())

		# Test input / output
		src_file = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL).file('test.txt')
		src_file.write('Test 123\n')
		queue.queue_thumbnail_request(src_file, 64)
			# put an error in the queue

		dir = LocalFolder(tests.ZIM_DATADIR).folder('pixmaps')
		pixmaps = set()
		for basename in dir.list_names():
			if not basename.endswith('.svg'):
				file = dir.file(basename)
				pixmaps.add(file.path)
				queue.queue_thumbnail_request(file, 64)

		self.assertFalse(queue.queue_empty())

		with tests.LoggingFilter('zim.plugins.attachmentbrowser', 'Exception'):
			queue.start()

			seen = set()
			i = len(pixmaps)
			while i > 0:
				i -= 1
				file, size, thumbfile, pixbuf, mtime = queue.get_ready_thumbnail(block=True)
				seen.add(file.path)
				self.assertEqual(size, 64)
				self.assertTrue(thumbfile.exists())
				self.assertIsInstance(pixbuf, GdkPixbuf.Pixbuf)
				self.assertEqual(mtime, file.mtime())

		self.assertEqual(seen, pixmaps)

		# Test clear
		self.assertTrue(queue.queue_empty())
		for path in pixmaps:
			file = LocalFile(path)
			queue.queue_thumbnail_request(file, 64)
		self.assertFalse(queue.queue_empty())
		queue.start()
		time.sleep(0.1)
		queue.clear_queue()
		self.assertTrue(queue.queue_empty())

	def testError(self):

		def creator_with_failure(*a):
			raise ThumbnailCreatorFailure

		def creator_with_error(*a):
			raise ValueError

		file = LocalFolder(tests.ZIM_DATADIR).file('zim.png')
		self.assertTrue(file.exists())
		self.assertTrue(file.isimage())

		for creator in creator_with_failure, creator_with_error:
			#~ print(">>", creator.__name__)
			queue = ThumbnailQueue(creator)
			queue.queue_thumbnail_request(file, 64)

			with tests.LoggingFilter('zim.plugins.attachmentbrowser', 'Exception'):
				queue.start()
				while not queue.queue_empty():
					r = queue.get_ready_thumbnail()
					self.assertIsNone(r[0], None)


@tests.slowTest
class TestFileBrowserIconView(tests.TestCase):

	def runTest(self):
		opener = tests.MockObject()
		iconview = FileBrowserIconView(opener)

		dir = LocalFolder(tests.ZIM_DATADIR).folder('pixmaps')
		iconview.set_folder(dir)

		# simulate idle events
		while not iconview._thumbnailer.queue_empty():
			iconview._on_check_thumbnail_queue()

		# refresh while nothing changed
		iconview.refresh()
		while not iconview._thumbnailer.queue_empty():
			iconview._on_check_thumbnail_queue()

		iconview.teardown_folder()


## Plugin & extention objects are loaded in generic "plugins" test ##
