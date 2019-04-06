
# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.fs module.'''


import tests

import os
import time

import zim.fs
from zim.fs import *
from zim.fs import SEP
from zim.errors import Error


def modify_file_mtime(path, func):
	'''Helper function to modify a file in such a way that mtime
	changed.
	'''
	mtime = os.stat(path).st_mtime
	m = mtime
	i = 0
	while m == mtime:
		time.sleep(1)
		func(path)
		m = os.stat(path).st_mtime
		i += 1
		assert i < 5
	#~ print('>>>', m, mtime)


class FilterOverWriteWarning(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self, 'zim.fs', 'mtime check failed')


class FilterFileMissingWarning(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self, 'zim.fs', 'File missing:')


class TestFS(tests.TestCase):

	def testFunctions(self):
		smb_urls = (
			('smb://MyHost.local/share/My%20Documents', r'\\MyHost.local\share\My Documents'),
		)
		for url, share in smb_urls:
			if os.name == 'nt':
				self.assertEqual(normalize_win32_share(share), share)
				self.assertEqual(normalize_win32_share(url), share)
			else:
				self.assertEqual(normalize_win32_share(share), url)
				self.assertEqual(normalize_win32_share(url), url)

		self.assertTrue(isabs('/foo/bar'))
		self.assertTrue(isabs('~/foo/bar'))
		self.assertFalse(isabs('./bar'))

		self.assertEqual(cleanup_filename('foo&bar:dus\\foo.txt'), 'foo&bardusfoo.txt')

	def testFilePath(self):
		'''Test Path object'''
		path = FilePath(['foo', 'bar'])
		test = os.path.abspath(os.path.join('foo', 'bar')).replace(os.path.sep, SEP)
		self.assertEqual(path.path, test)

		path = FilePath('/foo/bar')
		uri = 'file:///' + os.path.abspath('/foo/bar').replace('\\', '/').strip('/')
		self.assertEqual(path.uri, uri)

		self.assertEqual(FilePath('file:///foo/bar'), FilePath('/foo/bar'))
		self.assertEqual(FilePath('file:/foo/bar'), FilePath('/foo/bar'))
		self.assertEqual(FilePath('file://localhost/foo/bar'), FilePath('/foo/bar'))
		self.assertEqual(FilePath('file:///C:/foo/bar'), FilePath('/C:/foo/bar'))
		if os.name == 'nt':
			self.assertEqual(FilePath('file:///C:/foo/bar'), FilePath(r'C:\foo\bar'))

		path = FilePath('/foo//bar/baz/')
		drive, p = os.path.splitdrive(path.path)
		self.assertEqual(path.split(), [drive + SEP + 'foo', 'bar', 'baz'])
		dirs = []
		for d in path:
			dirs.append(d)
		wanted = [Dir(os.path.abspath(drive + p)) for p in ['/foo', '/foo/bar', '/foo/bar/baz']]
		self.assertEqual(dirs, wanted)

		for path1, path2, common in (
			('/foo/bar/baz/', '/foo/dus', '/foo'),
			('/foo/bar', '/dus/ja', '/'),
		):
			self.assertEqual(FilePath(path1).commonparent(FilePath(path2)), Dir(common))

		if os.name == 'nt':
			path1 = 'C:\\foo\\bar'
			path2 = 'D:\\foo\\bar\\baz'
			self.assertEqual(FilePath(path1).commonparent(FilePath(path2)), None)

		for path1, path2, relpath in (
			('/foo/bar/baz', '/foo', 'bar/baz'),
		):
			self.assertEqual(FilePath(path1).relpath(FilePath(path2)), relpath)

		self.assertRaises(AssertionError, FilePath('/foo/bar').relpath, FilePath('/dus/ja'))

		for path1, path2, relpath in (
			('/foo/bar', '/dus/ja/', '../../foo/bar'),
			('/source/dir/foo/bar/dus.pdf', '/source/dir/foo', 'bar/dus.pdf'),
			('/source/dir/foo/dus.pdf', '/source/dir/foo', 'dus.pdf'),
			('/source/dir/dus.pdf', '/source/dir/foo', '../dus.pdf'),
		):
			self.assertEqual(FilePath(path1).relpath(FilePath(path2), allowupward=True), relpath)

		if os.name == 'nt':
			path1 = 'C:\foo\bar'
			path2 = 'D:\foo\bar\baz'
			self.assertEqual(FilePath(path1).relpath(FilePath(path2), allowupward=True), None)

		self.assertEqual(FilePath('/foo') + 'bar', FilePath('/foo/bar'))

		path = FilePath('~/foo')
		self.assertNotEqual(path.path, '~/foo')
		self.assertEqual(path.user_path, '~/foo')
		self.assertEqual(path.serialize_zim_config(), '~/foo')

		path = FilePath('/foo')
		self.assertIsNotNone(path.path)
		self.assertIsNone(path.user_path)
		self.assertIsNotNone(path.serialize_zim_config())

		# Test unicode compat
		string = '\u0421\u0430\u0439\u0442\u043e\u0432\u044b\u0439'
		path = FilePath(string)
		self.assertTrue(path.path.endswith(string))
		path = FilePath((string, 'foo'))
		self.assertTrue(path.path.endswith(SEP.join((string, 'foo'))))

	def testFile(self):
		'''Test File object'''
		tmpdir = self.create_tmp_dir('testFile')
		file = File(tmpdir + '/foo/bar/baz.txt')
		assert not file.exists()
		file.touch()
		self.assertTrue(os.path.isfile(tmpdir + '/foo/bar/baz.txt'))
		File(tmpdir + '/anotherfile.txt').touch()
		file.cleanup()
		self.assertTrue(os.path.isfile(tmpdir + '/anotherfile.txt'))
		self.assertTrue(os.path.isdir(tmpdir))
		self.assertFalse(os.path.isfile(tmpdir + '/foo/bar/baz.txt'))
		self.assertFalse(os.path.isdir(tmpdir + '/foo'))

		file = File(tmpdir + '/bar.txt')
		file.writelines(['c\n', 'd\n'])
		self.assertEqual(file.readlines(), ['c\n', 'd\n'])

		# test read-only
		path = tmpdir + '/read-only-file.txt'
		open(path, 'w').write('test 123')
		os.chmod(path, 0o444)
		file = File(path)
		self.assertRaises(FileWriteError, file.write, 'Overwritten!')
		os.chmod(path, 0o644) # make it removable again

		# with windows line-ends
		file = open(tmpdir + '/newlines.txt', 'w', newline='')
		file.write('Some lines\r\nWith win32 newlines\r\n')
		file = File(tmpdir + '/newlines.txt')
		self.assertEqual(file.read(), 'Some lines\nWith win32 newlines\n')

		# test encoding error
		non_utf8_file = File('tests/data/non-utf8.txt')
		self.assertRaises(FileUnicodeError, non_utf8_file.read)

		# test byte order mark
		file = File('tests/data/byteordermark.txt')
		self.assertEqual(file.raw(), b'\xef\xbb\xbffoobar\n')
		self.assertEqual(file.read(), 'foobar\n')
		self.assertEqual(file.readlines(), ['foobar\n'])

		# test compare & copyto
		file1 = File(tmpdir + '/foo.txt')
		file2 = File(tmpdir + '/bar.txt')
		file1.write('foo\nbar\n')
		file2.write('foo\nbar\n')
		self.assertTrue(file1.compare(file2))
		file2.write('foo\nbar\nbaz\n')
		self.assertFalse(file1.compare(file2))
		file2.copyto(file1)
		self.assertTrue(file1.compare(file2))

		# rename is being used when testing Dir

		# test mimetype
		file = File('test.txt')
		self.assertFalse(file.isimage())
		file = File('test.jpg')
		self.assertTrue(file.isimage())

		file = File(tmpdir + '/foo/')
		self.assertFalse(file.isdir())

		dir = Dir(tmpdir + '/foo/')
		dir.touch()
		self.assertTrue(file.isdir())

	def testTmpFile(self):
		'''Test TmpFile object'''
		dir = get_tmpdir()
		file = TmpFile('foo.txt')
		self.assertTrue(file.ischild(dir))
		# What else to test here ?

	def testDir(self):
		'''Test Dir object'''
		tmpdir = self.create_tmp_dir('testDir')
		dir = Dir(tmpdir + '/foo/bar')
		assert not dir.exists()

		file1 = dir.file('unique.txt')
		file1.touch()
		file2 = dir.new_file('unique.txt')
		file2.touch()
		file3 = dir.new_file('unique.txt')
		self.assertEqual(file1.basename, 'unique.txt')
		self.assertEqual(file2.basename, 'unique001.txt')
		self.assertEqual(file3.basename, 'unique002.txt')

		self.assertEqual(dir.list(), ['unique.txt', 'unique001.txt'])
			# we did not touch unique002.txt, so don't want to see it show up here

		file1.rename(dir.file('foo.txt'))
		self.assertEqual(file1.basename, 'unique.txt') # don't update the object !
		self.assertEqual(dir.list(), ['foo.txt', 'unique001.txt'])

		file1 = dir.file('foo.txt')
		file1.rename(dir.subdir('foo').file('bar.txt'))
		self.assertEqual(dir.list(), ['foo', 'unique001.txt'])
		self.assertEqual(dir.subdir('foo').list(), ['bar.txt'])

		fdir = FilteredDir(dir)
		fdir.ignore('*.txt')
		self.assertEqual(fdir.list(), ['foo'])

		self.assertEqual(File((dir, 'foo.txt')), dir.file('foo.txt'))
		self.assertEqual(dir.file(File((dir, 'foo.txt'))), dir.file('foo.txt'))
		self.assertEqual(dir.file(FilePath((dir, 'foo.txt'))), dir.file('foo.txt'))
		self.assertEqual(dir.file(('foo.txt',)), dir.file('foo.txt'))
		self.assertRaises(PathLookupError, dir.file, File('/foo/bar.txt')) # not below dir

		self.assertEqual(dir.resolve_file('../foo.txt'), dir.dir.file('foo.txt'))
		self.assertEqual(dir.resolve_file(File('/foo/bar.txt')), File('/foo/bar.txt'))

		self.assertEqual(Dir((dir, 'bar')), dir.subdir('bar'))
		self.assertEqual(dir.subdir(Dir((dir, 'bar'))), dir.subdir('bar'))
		self.assertEqual(dir.subdir(FilePath((dir, 'bar'))), dir.subdir('bar'))
		self.assertEqual(dir.subdir(('bar',)), dir.subdir('bar'))
		self.assertRaises(PathLookupError, dir.subdir, Dir('/foo/bar')) # not below dir

		self.assertEqual(dir.resolve_dir('../bar'), dir.dir.subdir('bar'))
		self.assertEqual(dir.resolve_dir(Dir('/foo/bar')), Dir('/foo/bar'))

		self.assertRaises(OSError, dir.remove) # dir not empty
		self.assertTrue(dir.exists())
		dir.cleanup()
		self.assertTrue(dir.exists())
		dir.remove_children()
		self.assertEqual(dir.list(), [])
		self.assertTrue(dir.exists())
		dir.remove()
		self.assertFalse(dir.exists())
		self.assertEqual(dir.list(), []) # list non-existing dir

	# TODO skip if no gio available
	# TODO slow test
	#~ def testMonitor(self):
		#~ tmpdir = Dir(self.create_tmp_dir('testMonitor'))

		#~ # Monitor file
		#~ events = []
		#~ def monitor(*args):
			#~ events.append(args)

		#~ file = tmpdir.file('foo')
		#~ file.connect('changed', monitor)
		#~ file.touch()
		#~ file.write('Foo')
		#~ # timeout ?
		#~ print('>>', events)

		#~ # Monitor dir
		#~ tmpdir.connect('changed', monitor)
		#~ tmpdir.file('bar').touch()
		#~ # timeout ?
		#~ print('>>', events)


@tests.slowTest
class TestFileOverwrite(tests.TestCase):

	def setUp(self):
		self.path = self.create_tmp_dir() + '/file.txt'

	def modify(self, func):
		modify_file_mtime(self.path, func)

	def runTest(self):
		'''Test file overwrite check'''
		# Check we can write without reading
		file = File(self.path, checkoverwrite=True)
		file.write('bar')
		self.assertEqual(file.read(), 'bar')

		# Check edge case where file goes missing after read or write
		os.remove(file.path)
		self.assertFalse(file.exists())
		self.assertTrue(file.check_has_changed_on_disk())
		with FilterFileMissingWarning():
			file.write('bar')
		self.assertEqual(file.read(), 'bar')
		self.assertFalse(file.check_has_changed_on_disk())

		# Check overwrite error when content changed
		self.modify(lambda p: open(p, 'w').write('XXX'))
			# modify mtime and content
		with FilterOverWriteWarning():
			self.assertRaises(FileWriteError, file.write, 'foo')
			self.assertTrue(file.check_has_changed_on_disk())
		self.assertEqual(file.read(), 'XXX')

		# Check md5 check passes
		file = File(self.path, checkoverwrite=True)
		file.write('bar')
		self.modify(lambda p: open(p, 'w').write('bar'))
			# modify mtime but keep content the same
		with FilterOverWriteWarning():
			file.write('foo')
		self.assertEqual(file.read(), 'foo')


@tests.slowTest
@tests.skipUnless(hasattr(os, 'symlink') and os.name != 'nt', 'OS does not support symlinks')
class TestSymlinks(tests.TestCase):

	def runTest(self):
		'''Test file operations are safe for symlinks'''

		# Set up a file structue with a symlink
		tmpdir = self.create_tmp_dir()
		targetdir = Dir(tmpdir + '/target')
		targetdir.file('foo.txt').touch()
		targetfile = File(tmpdir + '/target.txt')
		targetfile.write('foo\n')

		dir = Dir(tmpdir + '/data')
		file = dir.file('bar.txt')
		file.touch()
		os.symlink(targetdir.path, dir.path + '/link')
		os.symlink(targetfile.path, dir.path + '/link.txt')

		# Test transparent access to the linked data
		linkedfile = dir.file('link.txt')
		self.assertTrue(linkedfile.read(), 'foo\n')
		self.assertEqual(dir.list(), ['bar.txt', 'link', 'link.txt'])
		linkeddir = dir.subdir('link')
		self.assertEqual(linkeddir.list(), ['foo.txt'])

		# Test modifying a linked file
		linkedfile.write('bar\n')
		self.assertTrue(linkedfile.read(), 'bar\n')
		self.assertTrue(targetfile.read(), 'bar\n')
		linkedfile.rename(dir.file('renamed_link.txt'))
		self.assertEqual(dir.list(), ['bar.txt', 'link', 'renamed_link.txt'])
		linkedfile = dir.file('renamed_link.txt')
		linkedfile.write('foobar\n')
		self.assertTrue(linkedfile.read(), 'foobar\n')
		self.assertTrue(targetfile.read(), 'foobar\n')

		# Test removing the links (but not the data)
		linkedfile.remove()
		self.assertFalse(linkedfile.exists())
		self.assertTrue(targetfile.exists())
		self.assertTrue(targetfile.read(), 'foobar\n')
		dir.remove_children()
		self.assertEqual(dir.list(), [])
		self.assertTrue(targetdir.exists())
		self.assertEqual(targetdir.list(), ['foo.txt'])
