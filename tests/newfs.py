
# Copyright 2008-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim filesystem module.'''




import tests

from zim.newfs import *
from zim.newfs import _HOME as HOME

from zim.newfs.mock import *


import os
import time



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


#~ class FilterOverWriteWarning(tests.LoggingFilter):

	#~ logger = 'zim.fs'
	#~ message = 'mtime check failed'


#~ class FilterFileMissingWarning(tests.LoggingFilter):

	#~ logger = 'zim.fs'
	#~ message = 'File missing:'



def P(path):
	# Returns a windows path on windows, to make test cases platform
	# independent and keep them readable
	if os.name == 'nt':
		if path.startswith('/'):
			path = 'C:' + path
		return path.replace('/', '\\')
	else:
		return path


class TestFilePath(tests.TestCase):
	# Test pathname manipulation, it should support all variants,
	# platform independent

	def testFilePath(self):
		# all variants should give equal result in constructor
		testpath = P('/foo/bar')
		testpathnames = ('/foo', 'bar') if os.name != 'nt' else ('C:', 'foo', 'bar')
		testuri = 'file:///foo/bar' if os.name != 'nt' else 'file:///C:/foo/bar'
		for p in (
			testpath, testpathnames, testuri,
			testpath + '///', P('/foo/./bar/../bar'),
			'file:/' + testuri[8:], 'file://localhost/' + testuri[8:],
		):
			mypath = FilePath(p)
			self.assertTrue(mypath.islocal)
			self.assertEqual(mypath.path, testpath)
			self.assertEqual(mypath.pathnames, testpathnames)
			self.assertEqual(mypath.uri, testuri)

		# check basename and dirname, including unicode
		mypath = FilePath(testpath)
		self.assertEqual(mypath.basename, 'bar')
		self.assertEqual(mypath.dirname, P('/foo'))

		mypath = FilePath(P('/foo/\u0421\u0430\u0439\u0442\u043e\u0432\u044b\u0439'))
		self.assertEqual(mypath.basename, '\u0421\u0430\u0439\u0442\u043e\u0432\u044b\u0439')
		self.assertIsInstance(mypath.basename, str)

		path = FilePath(P('/foo'))
		self.assertIsNotNone(path.path)

		# Test relative paths are not accepted in constructor
		for p in (P('../foo'), P('/foo/bar/../../..')):
			self.assertRaises(ValueError, FilePath, p)

		if os.name == 'nt':
			# Absolute paths either have a drive letter, or a host name
			self.assertRaises(ValueError, FilePath, 'foo/bar')
			self.assertRaises(ValueError, FilePath, '/foo/bar') # no drive letter
			self.assertRaises(ValueError, FilePath, 'file:/host/share/foo',)
			self.assertRaises(ValueError, FilePath, 'file:///host/share/foo',)

		# Test home folder fallback
		f = FilePath('~non-existing-user/foo')
		self.assertEqual(f.path, P('/'.join((HOME.dirname, 'non-existing-user', 'foo'))))


	def testShareDrivePath(self):
		# Test pathnames for windows share drive
		for p in (
			r'\\host\share\foo',
			'file://host/share/foo',
			'smb:/host/share/foo',
			'smb://host/share/foo',
		):
			mypath = FilePath(p)
			self.assertFalse(mypath.islocal)
			self.assertEqual(mypath.path, r'\\host\share\foo')
			self.assertEqual(mypath.pathnames, (r'\\host', 'share', 'foo'))

	def testRelativePath(self):
		r = FilePath(P('/foo/bar/baz')).relpath(FilePath(P('/foo')))
		self.assertEqual(r, P('bar/baz'))

		for r in ('bar/baz', ('bar', 'baz'), 'bar/./foo/../baz'):
			p = FilePath(P('/foo')).get_childpath(r)
			self.assertEqual(p.path, P('/foo/bar/baz'))

		self.assertRaises(ValueError, FilePath(P('/foo')).get_childpath, '../bar')

		p = FilePath(P('/foo/bar/baz/')).commonparent(FilePath(P('/foo/dus')))
		self.assertEqual(p.path, P('/foo'))

		p = FilePath(P('/foo/bar/')).commonparent(FilePath(P('/foo/bar/baz')))
		self.assertEqual(p.path, P('/foo/bar'))

		p = FilePath(P('/foo/bar/baz')).commonparent(FilePath(P('/foo/bar')))
		self.assertEqual(p.path, P('/foo/bar'))


		if os.name == 'nt':
			p = FilePath(r'C:\foo\bar').commonparent(FilePath(r'D:\foo\bar\baz'))
			self.assertIsNone(p)

		self.assertRaises(ValueError, FilePath(P('/foo/bar')).relpath, FilePath(P('/dus/ja')))

		for path1, path2, relpath in (
			('/root/foo/bar', '/root/dus/ja/', '../../foo/bar'),
			('/source/dir/foo/bar/dus.pdf', '/source/dir/foo', 'bar/dus.pdf'),
			('/source/dir/foo/dus.pdf', '/source/dir/foo', 'dus.pdf'),
			('/source/dir/dus.pdf', '/source/dir/foo', '../dus.pdf'),
		):
			self.assertEqual(
				P(FilePath(P(path1)).relpath(FilePath(P(path2)), allowupward=True)),
				P(relpath)
			)

		if os.name == 'nt':
			path1 = r'C:\foo\bar'
			path2 = r'D:\foo\bar\baz'
			self.assertRaises(ValueError,
				FilePath(path1).relpath,
				FilePath(path2),
				allowupward=True
			)

	def testAbsPath(self):
		f = FilePath(P('/foo/bar/baz'))
		for p, want in (
			(P('/test'), P('/test')),
			('test', P('/foo/bar/baz/test')),
			('./test', P('/foo/bar/baz/test')),
			('../test', P('/foo/bar/test')),
			(FilePath(P('/test')).uri, P('/test')),
			('\\\\host\\share', '\\\\host\\share'),
		):
			self.assertEqual(f.get_abspath(p).path, want)

	def testUserpath(self):
		self.assertTrue(len(HOME.pathnames) >= 2)

		f = FilePath('~/foo')
		self.assertEqual(f.path, HOME.get_childpath('foo').path)
		self.assertEqual(f.userpath, P('~/foo'))

		f = FilePath(P('/foo'))
		self.assertEqual(f.userpath, P('/foo'))

	def testSerialize(self):
		f = FilePath(P('/foo'))
		self.assertEqual(f.serialize_zim_config(), P('/foo'))

		f = FilePath('~/foo')
		self.assertEqual(f.serialize_zim_config(), P('~/foo'))

		f = FilePath.new_from_zim_config('~/foo')
		self.assertEqual(f.path, FilePath(P('~/foo')).path)

	def testRootPath(self):
		# Test for corner case in parsing paths
		f = FilePath(P('/'))
		self.assertTrue(len(f.path) > 0)


class TestFS(object):

	def testClasses(self):
		root = self.get_root_folder('testClasses')
		self.assertIsInstance(root, Folder)

		folder = root.folder('foo')
		self.assertIsInstance(folder, Folder)
		self.assertNotIsInstance(folder, File)

		file = root.file('foo.txt')
		self.assertIsInstance(file, File)
		self.assertNotIsInstance(file, Folder)

		# Make sure both mock and real classes have exact same interface
		# in specific nothing added in subclass and used with
		# an "if hasattr" ...
		for child, base in (
			(file, File),
			(folder, Folder),
		):
			attrib = set(a for a in dir(child.__class__) if not a.startswith('_'))
			wanted = set(a for a in dir(base) if not a.startswith('_'))
			self.assertEqual(attrib, wanted)

			parent = child.parent()
			self.assertIsInstance(parent, Folder)
			self.assertEqual(parent.path, child.dirname)

	def testFileInfo(self):
		# Test retrieving file & folder attributes
		# ctime, mtime, size, iswritable, mimetype, isimage
		root = self.get_root_folder('testFileInfo')
		folder = root.folder('foo')
		file = root.file('foo.txt')

		for f in (file, folder):
			self.assertFalse(f.exists())
			self.assertRaises(FileNotFoundError, f.ctime)
			self.assertRaises(FileNotFoundError, f.mtime)
			self.assertTrue(f.iswritable())

		folder.touch()
		file.touch()

		for f in (file, folder):
			self.assertTrue(f.exists())
			self.assertIsInstance(f.ctime(), (int, float, int))
			self.assertIsInstance(f.mtime(), (int, float, int))
			self.assertGreaterEqual(f.mtime(), f.ctime())

		file.write('test123\n')
		self.assertIsInstance(file.size(), (int, float, int))
		self.assertTrue(file.size() > 0)

		self.assertEqual(file.mimetype(), 'text/plain')
		self.assertEqual(file.mimetype(), 'text/plain') # check caching
		self.assertFalse(file.isimage())

		file = root.file('image.png')
		self.assertTrue(file.isimage())

		# Test fallback
		import zim.newfs.base
		import mimetypes
		xdgmime = zim.newfs.base.xdgmime
		zim.newfs.base.xdgmime = None
		zim.newfs.base.mimetypes = mimetypes
		self.addCleanup(lambda: setattr(zim.newfs.base, 'xdgmime', xdgmime))

		for name, mtype in (
			('foo.txt', 'text/plain'),
			#('foo.png', 'image/png'), # image/x-png on windows
			('foo', 'application/octet-stream'),
			('foo.bz2', 'application/x-bzip2'),
			('foo.gz', 'application/x-gzip'),
			('foo.Z', 'application/x-compress'),
		):
			file = root.file(name)
			self.assertEqual(file.mimetype(), mtype)

	def testFileAccess(self):
		# File access: read, write, touch, remove -- including unicode in path
		file = self.get_root_folder('testFileAccess').file('test-αβγ.txt')
		self.assertFalse(file.exists())
		self.assertRaises(FileNotFoundError, file.read)

		file.touch()
		self.assertTrue(file.exists())
		self.assertEqual(file.read(), '')
		self.assertEqual(file.read_binary(), b'')

		file.write('test 123\n')
		self.assertEqual(file.read(), 'test 123\n')
		self.assertEqual(list(file.readlines()), ['test 123\n'])
		self.assertEqual(list(file), ['test 123\n'])

		file.touch()
		self.assertEqual(file.read(), 'test 123\n') # no trucation!

		mylines = ['lines1\n', 'lines2\n', 'lines3\n']
		file.writelines(mylines)
		self.assertEqual(list(file), mylines)

		file.remove()
		self.assertFalse(file.exists())
		self.assertRaises(FileNotFoundError, file.read)

	def testFileOverwrite(self):
		root = self.get_root_folder('testFileOverwrite')

		# Check we can write without reading
		file = root.file('test.txt')
		etag1 = file.write_with_etag('test 123\n', None)
		self.assertEqual(file.read_with_etag(), ('test 123\n', etag1))

		# Now write again
		import time
		if isinstance(etag1[0], float):
			time.sleep(0.1) # Ensure mtime change
		else: # int
			time.sleep(1) # Ensure mtime change
		etag2 = file.writelines_with_etag(['test 567\n'], etag1)
		self.assertNotEqual(etag2, etag1)
		self.assertEqual(file.readlines_with_etag(), (['test 567\n'], etag2))

		# Check raises without etag
		self.assertRaises(FileChangedError, file.write_with_etag, 'foo!', etag1)
		self.assertRaises(AssertionError, file.write_with_etag, 'foo!', None)
		self.assertEqual(file.readlines_with_etag(), (['test 567\n'], etag2))

		# Check md5 fallback
		etag2x = (-1, etag2[1])
		etag3 = file.write_with_etag('test 890\n', etag2x)
		self.assertEqual(file.read_with_etag(), ('test 890\n', etag3))

		# Check edge case where file goes missing after read or write
		file.remove()
		self.assertFalse(file.exists())
		etag4 = file.write_with_etag('test 890\n', etag3)
		self.assertEqual(file.read_with_etag(), ('test 890\n', etag4))

	def testFolderAccess(self):
		# Folder access: list, touch, remove, file, folder, child -- including unicode in path

		folder = self.get_root_folder('testFolderAccess').folder('test-αβγ')

		# Start empty
		self.assertFalse(folder.exists())
		self.assertRaises(FileNotFoundError, list, folder)
		self.assertRaises(FileNotFoundError, folder.list_names)
		self.assertRaises(FileNotFoundError, folder.list_files)
		self.assertRaises(FileNotFoundError, folder.list_folders)

		# Test listing with only files
		file1 = folder.file('foo.txt')
		file2 = folder.file('bar.txt')
		file1.touch()
		file2.touch()
		self.assertTrue(folder.exists())

		self.assertEqual(list(folder.list_names()), ['bar.txt', 'foo.txt'])
		self.assertTrue(any(isinstance(f, File) for f in folder))
		self.assertEqual([f.basename for f in folder], ['bar.txt', 'foo.txt'])
		self.assertTrue(any(isinstance(f, File) for f in folder.list_files()))
		self.assertEqual([f.basename for f in folder.list_files()], ['bar.txt', 'foo.txt'])
		self.assertEqual(list(folder.list_folders()), [])

		# Add folders
		subfolder1 = folder.folder('foo')
		subfolder2 = folder.folder('bar/')
		self.assertFalse(subfolder1.exists())
		self.assertFalse(subfolder2.exists())
		subfolder1.touch()
		subfolder2.touch()
		self.assertTrue(subfolder1.exists())
		self.assertTrue(subfolder2.exists())

		self.assertEqual(list(folder.list_names()), ['bar', 'bar.txt', 'foo', 'foo.txt'])
		self.assertEqual([f.basename for f in folder], ['bar', 'bar.txt', 'foo', 'foo.txt'])
		self.assertTrue(any(isinstance(f, File) for f in folder.list_files()))
		self.assertEqual([f.basename for f in folder.list_files()], ['bar.txt', 'foo.txt'])
		self.assertTrue(any(isinstance(f, Folder) for f in folder.list_folders()))
		self.assertEqual([f.basename for f in folder.list_folders()], ['bar', 'foo'])

		# Test child()
		wanted = {'bar': Folder, 'bar.txt': File, 'foo': Folder, 'foo.txt': File}
		for name in folder.list_names():
			child = folder.child(name)
			self.assertIsInstance(child, wanted[name])

		# Test new_file()
		newfile1 = folder.new_file('foo.txt')
		self.assertEqual(newfile1.dirname, folder.path)
		self.assertEqual(newfile1.basename, 'foo001.txt')

		newfile1.touch()
		newfile2 = folder.new_file('foo.txt')
		self.assertEqual(newfile2.basename, 'foo002.txt')

		# Test new_folder()
		newfolder = folder.new_folder('foo')
		self.assertEqual(newfolder.dirname, folder.path)
		self.assertEqual(newfolder.basename, 'foo001')

		# Remove one by one
		self.assertEqual(folder.list_names(), ['bar', 'bar.txt', 'foo', 'foo.txt', 'foo001.txt'])
		self.assertRaises(FolderNotEmptyError, folder.remove)
		self.assertTrue(folder.exists())

		for child in (newfile1, file1, subfolder1, subfolder2):
			child.remove()
			self.assertTrue(folder.exists())

		file2.remove()
		self.assertFalse(folder.exists()) # cleanup automatically

		# Remove all
		sub = folder.folder('sub1')
		for name in ('foo.txt', 'bar.txt'):
			sub.file(name).touch()
		self.assertTrue(folder.exists())
		self.assertTrue(sub.exists())
		folder.remove_children()
		self.assertFalse(folder.exists())


	def testTreeAccess(self):
		root = self.get_root_folder('testTreeAccess')
		data = {
			P('foo.txt'): 'test 123\n',
			P('foo/bar.txt'): 'test 123\n',
			P('a/b/c/test.txt'): 'test 123\n',
			P('unicode.txt'): '\u2022 test 123\n',
		}

		for path, text in list(data.items()):
			root.file(path).write(text)

		# Direct access
		for path, text in list(data.items()):
			file = root.file(path)
			self.assertTrue(file.exists())
			self.assertEqual(file.read(), text)

		# Tree access by list
		found = {}
		def walk(folder):
			for child in folder:
				self.assertTrue(child.exists())
				self.assertTrue(child.ischild(folder))
				if isinstance(child, File):
					self.assertNotIn(child.path, found)
					key = P(child.relpath(root))
					found[key] = child.read()
				else:
					walk(child)

		walk(root)
		self.assertEqual(found, data)

		# Tree access by walk
		found = {}
		for child in root.walk():
			self.assertTrue(child.exists())
			self.assertTrue(child.ischild(root))
			if isinstance(child, File):
				self.assertNotIn(child.path, found)
				key = P(child.relpath(root))
				found[key] = child.read()
		self.assertEqual(found, data)

	def testMoveFile(self):
		root = self.get_root_folder('testMoveFile')
		file = root.file('test.txt')
		file.write('test 123\n')
		ctime = file.ctime()
		mtime = file.mtime()

		newfile = root.file('newfile.txt')

		self.assertTrue(file.exists())
		self.assertFalse(newfile.exists())

		re = file.moveto(newfile)
		self.assertIsInstance(re, File)
		self.assertEqual(re.path, newfile.path)
		self.assertEqual(newfile.read(), 'test 123\n')
		#~ self.assertEqual(newfile.ctime(), ctime)
		self.assertEqual(newfile.mtime(), mtime)
		self.assertFalse(file.exists())

		re = newfile.moveto(file)
		self.assertIsInstance(re, File)
		self.assertEqual(re.path, file.path)
		self.assertEqual(file.read(), 'test 123\n')
		#~ self.assertEqual(file.ctime(), ctime)
		self.assertEqual(file.mtime(), mtime)
		self.assertFalse(newfile.exists())

		efile = root.file('exists.txt')
		efile.touch()
		self.assertRaises(FileExistsError, file.moveto, efile)

		efolder = root.folder('exists')
		efolder.touch()
		re = file.moveto(efolder)
		self.assertIsInstance(re, File)
		self.assertTrue(re.exists())
		self.assertEqual(re.path, efolder.file(file.basename).path)


	def testMoveFolder(self):
		root = self.get_root_folder('testMoveFolder')
		folder = root.folder('test')
		folder.file('somefile.txt').write('test 123\n')
		ctime = folder.ctime()
		mtime = folder.mtime()

		newfolder = root.folder('newfolder')

		self.assertTrue(folder.exists())
		self.assertFalse(newfolder.exists())

		re = folder.moveto(newfolder)
		self.assertIsInstance(re, Folder)
		self.assertEqual(re.path, newfolder.path)
		self.assertEqual(newfolder.list_names(), ['somefile.txt'])
		#~ self.assertEqual(newfolder.ctime(), ctime)
		self.assertEqual(newfolder.mtime(), mtime)
		self.assertFalse(folder.exists())

		re = newfolder.moveto(folder)
		self.assertIsInstance(re, Folder)
		self.assertEqual(re.path, folder.path)
		self.assertEqual(folder.list_names(), ['somefile.txt'])
		#~ self.assertEqual(folder.ctime(), ctime)
		self.assertEqual(folder.mtime(), mtime)
		self.assertFalse(newfolder.exists())

		efolder = root.folder('exists')
		efolder.touch()
		self.assertRaises(FileExistsError, folder.moveto, efolder)

		file = root.file('file.txt')
		self.assertRaises(AssertionError, folder.moveto, file)


	def testMoveCaseSensitive(self):
		root = self.get_root_folder('testMoveCaseSensitive')

		file = root.file('foo.txt')
		file.touch()
		self.assertEqual(root.list_names(), ['foo.txt'])
		re = file.moveto(root.file('FOO.txt'))
		self.assertEqual(re.basename, 'FOO.txt')
		self.assertEqual(root.list_names(), ['FOO.txt'])

		dir = root.folder('FOO')
		dir.touch()
		self.assertEqual(root.list_names(), ['FOO', 'FOO.txt'])
		re = dir.moveto(root.folder('foo'))
		self.assertEqual(re.basename, 'foo')
		self.assertEqual(root.list_names(), ['FOO.txt', 'foo'])

	def testCopyFile(self):
		root = self.get_root_folder('testCopyFile')
		file = root.file('test.txt')
		file.write('test 123\n')

		newfile = root.file('newfile.txt')

		self.assertTrue(file.exists())
		self.assertFalse(newfile.exists())

		re = file.copyto(newfile)
		self.assertIsInstance(re, File)
		self.assertEqual(re.path, newfile.path)
		self.assertEqual(newfile.read(), 'test 123\n')
		self.assertEqual(file.read(), 'test 123\n')
		#~ self.assertEqual(newfile.mtime(), file.mtime()) # FIXME
		#~ self.assertEqual(newfile.ctime(), file.ctime()) # FIXME

		efile = root.file('exists.txt')
		efile.touch()
		self.assertRaises(FileExistsError, file.copyto, efile)

		efolder = root.folder('exists')
		efolder.touch()
		re = file.copyto(efolder)
		self.assertIsInstance(re, File)
		self.assertTrue(re.exists())
		self.assertEqual(re.path, efolder.file(file.basename).path)

	def testCopyFolder(self):
		root = self.get_root_folder('testCopyFolder')
		folder = root.folder('test')
		folder.file('somefile.txt').write('test 123\n')

		newfolder = root.folder('newfolder')

		self.assertTrue(folder.exists())
		self.assertFalse(newfolder.exists())

		re = folder.copyto(newfolder)
		self.assertIsInstance(re, Folder)
		self.assertEqual(re.path, newfolder.path)
		self.assertEqual(newfolder.list_names(), ['somefile.txt'])
		self.assertEqual(folder.list_names(), ['somefile.txt'])
		#~ self.assertEqual(newfolder.mtime(), folder.mtime()) # FIXME
		#~ self.assertEqual(newfolder.ctime(), folder.ctime()) # FIXME

		efolder = root.folder('exists')
		efolder.touch()
		self.assertRaises(FileExistsError, folder.copyto, efolder)

		file = root.file('file.txt')
		self.assertRaises(AssertionError, folder.copyto, file)

	def testFileTreeWatcher(self):
		root = self.get_root_folder('testFileTreeWatcher')

		from functools import partial
		class Recorder(object):

			def __init__(self, watcher):
				self.watcher = watcher
				self.calls = []

			def record(self, signal, watcher, *files):
				self.calls.append((signal,) + tuple(P(f.relpath(root)) for f in files))

			def __enter__(self):
				self._ids = []
				for signal in self.watcher.__signals__:
					handler = partial(self.record, signal)
					id = self.watcher.connect(signal, handler)
					self._ids.append(id)
				return self

			def __exit__(self, *exc_info):
				for id in self._ids:
					self.watcher.disconnect(id)

		root.touch()
		root.file('sticky.txt').touch() # prevent cleanup
		root.watcher = FileTreeWatcher()

		file = root.file('a/b/c/test.txt')
		with Recorder(root.watcher) as rec:
			file.touch()
			self.assertEqual(rec.calls, [
				('created', 'a'),
				('created', P('a/b')),
				('created', P('a/b/c')),
				('created', P('a/b/c/test.txt')),
			])

		with Recorder(root.watcher) as rec:
			file.remove()
			self.assertEqual(rec.calls, [
				('removed', P('a/b/c/test.txt')),
				('removed', P('a/b/c')),
				('removed', P('a/b')),
				('removed', 'a'),
			])

		file = root.file('test.txt')
		with Recorder(root.watcher) as rec:
			file.write('test 1\n')
			file.write('test 2\n')
			self.assertEqual(rec.calls, [
				('created', P('test.txt')),
				('changed', P('test.txt')),
			])

		copy = root.file('copy.txt')
		move = root.file('move.txt')
		with Recorder(root.watcher) as rec:
			file.copyto(copy)
			file.moveto(move)
			self.assertEqual(rec.calls, [
				('created', P('copy.txt')),
				('moved', P('test.txt'), P('move.txt')),
			])

		folder = root.folder('test')
		folder.touch()
		copy = root.folder('copy')
		move = root.folder('move')
		with Recorder(root.watcher) as rec:
			folder.copyto(copy)
			folder.moveto(move)
			self.assertEqual(rec.calls, [
				('created', P('copy')),
				('moved', P('test'), P('move')),
			])



class TestMockFS(tests.TestCase, TestFS):

	def get_root_folder(self, name):
		return MockFolder(P('/mock_folder/') + name)

	@tests.slowTest
	def testCrossFSCopy(self):
		root = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)

		# File
		lfile = root.file('file.txt')
		mfile = MockFile('/mock/file.txt')

		mfile.write('foo 123')
		mfile.copyto(lfile)
		self.assertEqual(lfile.read(), 'foo 123')
		#~ self.assertEqual(lfile.mtime(), mfile.mtime())

		self.assertRaises(FileExistsError, mfile.copyto, lfile)
		self.assertRaises(FileExistsError, lfile.copyto, mfile)

		mfile.remove()
		lfile.write('bar 123')
		lfile.copyto(mfile)
		self.assertEqual(mfile.read(), 'bar 123')
		self.assertEqual(mfile.mtime(), lfile.mtime())

		# Folder
		lfolder = root.folder('folder')
		mfolder = MockFolder('/mock/folder')

		for path in ('file1.txt', 'file2.txt', 'subfolder/file3.txt'):
			mfolder.file(path).write('foo 123')
		mfolder.copyto(lfolder)
		self.assertTrue(lfolder.file('subfolder/file3.txt').exists())

		self.assertRaises(FileExistsError, mfolder.copyto, lfolder)
		self.assertRaises(FileExistsError, lfolder.copyto, mfolder)

		mfolder.remove_children()
		lfolder.copyto(mfolder)
		self.assertTrue(mfolder.file('subfolder/file3.txt').exists())

	#~ @tests.slowTest
	#~ def testCrossFSMove(self):
		#~ pass


@tests.slowTest
class TestLocalFS(tests.TestCase, TestFS):

	def get_root_folder(self, name):
		folder = self.setUpFolder(name=name, mock=tests.MOCK_ALWAYS_REAL)
		assert isinstance(folder, LocalFolder)
		return folder

	def get_test_data(self, path):
		cwd = LocalFolder(os.getcwd())
		return LocalFolder(cwd.get_abspath(r'./tests/data')).child(path)

	def get_package_data(self, path):
		cwd = LocalFolder(os.getcwd())
		return LocalFolder(cwd.get_abspath(r'./data')).child(path)

	def testAtomicWriteContext(self):
		file = self.get_root_folder('testAtomicWriteContext').file('test.txt')

		file.write('test 123\n')
		self.assertEqual(file.read(), 'test 123\n')

		try:
			with AtomicWriteContext(file) as fh:
				fh.write('truncate!')
				raise AssertionError
		except:
			pass

		self.assertEqual(file.read(), 'test 123\n') # No truncated on error

	def testImageFile(self):
		file = self.get_package_data('zim.png')
		self.assertTrue(file.isimage())
		self.assertIn(file.mimetype(), ('image/png', 'image/x-png'))
		blob = file.read_binary()
		self.assertIsInstance(blob, bytes)
		with open(file.path, 'rb') as fh:
			raw = fh.read()
		self.assertEqual(blob, raw)

	def testFindLocalObject(self):
		root = self.get_root_folder('testFindLocalObject')
		file = root.file('a/b/c/test.txt')
		self.assertRaises(FileNotFoundError, localFileOrFolder, file.path)

		file.touch()
		rfile = localFileOrFolder(file.path)
		self.assertIsInstance(rfile, File)
		self.assertEqual(rfile.path, file.path)

		rfile = localFileOrFolder(file.dirname)
		self.assertIsInstance(rfile, Folder)
		self.assertEqual(rfile.path, file.dirname)

	def testFilePermissions(self):
		root = self.get_root_folder('testFilePermissions')
		file = root.file('read-only-file.txt')
		file.write('test 123\n')

		os.chmod(file.path, 0o444)
		try:
			self.assertRaises(FileNotWritableError, file.write, 'Overwritten!')
			self.assertEqual(file.read(), 'test 123\n')
		finally:
			os.chmod(file.path, 0o644) # make it removable again
			file.remove()

	def testFileEncoding(self):
		root = self.get_root_folder('testFileEncoding')
		root.touch()

		# test line-ends option - dos
		file = root.file('newlines_dos.txt')
		file.endofline = 'dos'
		file.write('Some lines\nWith win32 newlines\n')
		self.assertEqual(file.read(), 'Some lines\nWith win32 newlines\n')
		with open(file.path, 'r', newline='') as fh:
			self.assertEqual(fh.read(), 'Some lines\r\nWith win32 newlines\r\n')

		file.writelines(['Some lines\n', 'With win32 newlines2\n'])
		self.assertEqual(file.read(), 'Some lines\nWith win32 newlines2\n')

		with open(file.path, 'r', newline='') as fh:
			self.assertEqual(fh.read(), 'Some lines\r\nWith win32 newlines2\r\n')

		# test line-ends option - unix
		file = root.file('newlines_unix.txt')
		file.endofline = 'unix'
		file.write('Some lines\nWith unix newlines\n')
		self.assertEqual(file.read(), 'Some lines\nWith unix newlines\n')
		with open(file.path, 'r', newline='') as fh:
			self.assertEqual(fh.read(), 'Some lines\nWith unix newlines\n')

		file.writelines(['Some lines\n', 'With unix newlines2\n'])
		self.assertEqual(file.read(), 'Some lines\nWith unix newlines2\n')
		with open(file.path, 'r', newline='') as fh:
			self.assertEqual(fh.read(), 'Some lines\nWith unix newlines2\n')

		# test encoding error
		non_utf8_file = self.get_test_data('non-utf8.txt')
		self.assertRaises(FileUnicodeError, non_utf8_file.read)

		# test byte order mark
		file = self.get_test_data('byteordermark.txt')
		self.assertEqual(file.read(), 'foobar\n')
		self.assertEqual(file.readlines(), ['foobar\n'])

	@tests.skipUnless(hasattr(os, 'symlink') and os.name != 'nt', 'OS does not support symlinks')
	def testSymlinks(self):
		# Set up a file structue with a symlink
		root = self.get_root_folder('testSymlinks')
		targetdir = root.folder('target/')
		targetdir.file('foo.txt').touch()
		targetfile = root.file('target.txt')
		targetfile.write('foo\n')

		dir = root.folder('data/')
		file = dir.file('bar.txt').touch()
		os.symlink(targetdir.path, dir.path + '/link')
		os.symlink(targetfile.path, dir.path + '/link.txt')

		# Now we have:
		# ../target/foo.txt		(real)
		# ../target.txt			(real)
		# ../data/bar.txt		(real)
		# ../data/link/			--> ../target/
		# ../data/link/foo.txt	--> ../target/foo.txt
		# ../data/link.txt		--> ../target.txt

		# Test transparent access to the linked data
		linkedfile = dir.file('link.txt')
		self.assertTrue(linkedfile.read(), 'foo\n')
		self.assertEqual(dir.list_names(), ['bar.txt', 'link', 'link.txt'])
		linkeddir = dir.folder('link')
		self.assertEqual(linkeddir.list_names(), ['foo.txt'])

		# Test writing to a linked file
		linkedfile.write('bar\n')
		self.assertTrue(linkedfile.read(), 'bar\n')
		self.assertTrue(targetfile.read(), 'bar\n')

		# Here we rename the link, NOT the target file
		linkedfile = linkedfile.moveto(dir.file('renamed_link.txt'))
		self.assertEqual(dir.list_names(), ['bar.txt', 'link', 'renamed_link.txt'])
		linkedfile.write('foobar\n')
		self.assertTrue(linkedfile.read(), 'foobar\n')
		self.assertTrue(targetfile.read(), 'foobar\n')

		# Test removing the links (but not the data)
		linkedfile.remove()
		self.assertFalse(linkedfile.exists())
		self.assertTrue(targetfile.exists())
		self.assertTrue(targetfile.read(), 'foobar\n')

		# Test linked dir is treated like any other
		self.assertRaises(FolderNotEmptyError, linkeddir.remove)
		self.assertTrue(targetdir.exists())


class TestTmpFile(tests.TestCase):

	def runTest(self):
		dir = get_tmpdir()
		file = TmpFile('foo.txt')
		file.write('test 123\n')
		self.assertTrue(file.ischild(dir))

		path = file.path
		self.assertTrue(os.path.isfile(path))
		del file
		self.assertFalse(os.path.isfile(path)) # not persistent


class TestFunc(tests.TestCase):

	def testFormatSize(self):
		for size, text in (
			(2000000000, '2.00Gb'),
			(20000000, '20.0Mb'),
			(200000, '200kb'),
			(2, '2b'),
		):
			self.assertEqual(format_file_size(size), text)

	def testCleanFileName(self):
		self.assertEqual(
			cleanup_filename('foo/%bar\t.txt'),
			'foo%bar.txt'
		)


try:
	from gi.repository import Gio
except ImportError:
	Gio = None

from zim.newfs.helpers import TrashHelper

@tests.slowTest
@tests.skipUnless(Gio, 'Trashing not supported, \'gio\' is missing')
class TestTrash(tests.TestCase):

	def runTest(self):
		root = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		helper = TrashHelper()

		file = root.file('test.txt')
		file.touch()
		self.assertTrue(file.exists())
		self.assertTrue(helper.trash(file))
		self.assertFalse(file.exists())

		dir = root.folder('test')
		dir.touch()
		self.assertTrue(dir.exists())
		self.assertTrue(helper.trash(dir))
		self.assertFalse(dir.exists())

		# fails silent if file does not exist
		self.assertFalse(helper.trash(file))
		self.assertFalse(helper.trash(dir))

		# How can we cause gio to give an error and test that case ??
