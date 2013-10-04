# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

import os

from zim.fs import File, Dir
from zim.config import *
from zim.notebook import Path
import zim.config


# Check result of lookup functions does not return files outside of
# source to be tested -- just being paranoid here...
# Note that this marshalling remains in place for any subsequent tests

_cwd = Dir('.')
def marshal_path_lookup(function):
	def marshalled_path_lookup(*arg, **kwarg):
		value = function(*arg, **kwarg)
		if isinstance(value, ConfigFile):
			p = value.file
		else:
			p = value
		if not p is None:
			assert isinstance(p, (File, Dir)), 'BUG: get %r' % p
			assert p.ischild(_cwd), "ERROR: \"%s\" not below \"%s\"" % (p, _cwd)
		return value
	return marshalled_path_lookup

zim.config.data_file = marshal_path_lookup(zim.config.data_file)
zim.config.data_dir = marshal_path_lookup(zim.config.data_dir)
#~ zim.config.config_file = marshal_path_lookup(zim.config.config_file)

##


class FilterInvalidConfigWarning(tests.LoggingFilter):

	logger = 'zim.config'
	message = 'Invalid config value'


class TestDirsTestSetup(tests.TestCase):

	def runTest(self):
		'''Test config environment setup of test'''
		zim.config.log_basedirs()

		for k, v in (
			('XDG_DATA_HOME', os.path.join(tests.TMPDIR, 'data_home')),
			('XDG_CONFIG_HOME', os.path.join(tests.TMPDIR, 'config_home')),
			('XDG_CACHE_HOME', os.path.join(tests.TMPDIR, 'cache_home'))
		): self.assertEqual(getattr(zim.config, k), Dir(v))

		for k, v in (
			#~ ('XDG_DATA_DIRS', os.path.join(tests.TMPDIR, 'data_dir')),
			('XDG_CONFIG_DIRS', os.path.join(tests.TMPDIR, 'config_dir')),
		): self.assertEqual(getattr(zim.config, k), map(Dir, v.split(os.pathsep)))

		self.assertEqual(
			zim.config.XDG_DATA_DIRS[0],
			Dir(os.path.join(tests.TMPDIR, 'data_dir'))
		)


class TestDirsDefault(tests.TestCase):

	def setUp(self):
		old_environ = {}
		for k in (
			'XDG_DATA_HOME', 'XDG_DATA_DIRS',
			'XDG_CONFIG_HOME', 'XDG_CONFIG_DIRS', 'XDG_CACHE_HOME'
		):
			if k in os.environ:
				old_environ[k] = os.environ[k]
				del os.environ[k]

		def restore_environ():
			for k, v in old_environ.items():
				os.environ[k] = v
			zim.config.set_basedirs() # refresh

		self.addCleanup(restore_environ)

		zim.config.set_basedirs() # refresh

	def testValid(self):
		'''Test config environment is valid'''
		for var in (
			ZIM_DATA_DIR,	# should always be set when running as test
			XDG_DATA_HOME,
			XDG_CONFIG_HOME,
			XDG_CACHE_HOME
		): self.assertTrue(isinstance(var, Dir))

		for var in (
			XDG_DATA_DIRS,
			XDG_CONFIG_DIRS,
		): self.assertTrue(isinstance(var, list) and isinstance(var[0], Dir))

		self.assertEqual(ZIM_DATA_DIR, Dir('./data'))
		self.assertTrue(ZIM_DATA_DIR.file('zim.png').exists())
		self.assertTrue(data_file('zim.png').exists())
		self.assertTrue(data_dir('templates').exists())
		self.assertEqual(
				list(data_dirs(('foo', 'bar'))),
				[d.subdir(['foo', 'bar']) for d in data_dirs()])

	@tests.skipIf(os.name == 'nt', 'No standard defaults for windows')
	def testCorrect(self):
		'''Test default basedir paths'''
		for k, v in (
			('XDG_DATA_HOME', '~/.local/share'),
			('XDG_CONFIG_HOME', '~/.config'),
			('XDG_CACHE_HOME', '~/.cache')
		): self.assertEqual(getattr(zim.config.basedirs, k), Dir(v))

		for k, v in (
			('XDG_DATA_DIRS', '/usr/share:/usr/local/share'),
			('XDG_CONFIG_DIRS', '/etc/xdg'),
		): self.assertEqual(getattr(zim.config.basedirs, k), map(Dir, v.split(':')))


class TestDirsEnvironment(TestDirsDefault):

	def setUp(self):
		my_environ = {
			'XDG_DATA_HOME': '/foo/data/home',
			'XDG_DATA_DIRS': '/foo/data/dir1:/foo/data/dir2',
			'XDG_CONFIG_HOME': '/foo/config/home',
			'XDG_CONFIG_DIRS': '/foo/config/dir1:/foo/config/dir2',
			'XDG_CACHE_HOME': '/foo/cache',
		}
		if os.name == 'nt':
			my_environ['XDG_DATA_DIRS'] = '/foo/data/dir1;/foo/data/dir2'
			my_environ['XDG_CONFIG_DIRS'] = '/foo/config/dir1;/foo/config/dir2'

		old_environ = dict((name, os.environ.get(name)) for name in my_environ)

		def restore_environ():
			for k, v in old_environ.items():
				if v:
					os.environ[k] = v
			zim.config.set_basedirs() # refresh

		self.addCleanup(restore_environ)

		os.environ.update(my_environ)
		zim.config.set_basedirs() # refresh

	def testCorrect(self):
		'''Test config environemnt with non-default basedir paths'''
		for k, v in (
			('XDG_DATA_HOME', '/foo/data/home'),
			('XDG_CONFIG_HOME', '/foo/config/home'),
			('XDG_CACHE_HOME', '/foo/cache')
		): self.assertEqual(getattr(zim.config.basedirs, k), Dir(v))

		for k, v in (
			('XDG_DATA_DIRS', '/foo/data/dir1:/foo/data/dir2'),
			('XDG_CONFIG_DIRS', '/foo/config/dir1:/foo/config/dir2'),
		): self.assertEqual(getattr(zim.config.basedirs, k), map(Dir, v.split(':')))


class TestControlledDict(tests.TestCase):

	def runTest(self):
		mydict = ControlledDict({'foo': 'bar'})
		self.assertFalse(mydict.modified)

		mydict['bar'] = 'dus'
		self.assertTrue(mydict.modified)
		mydict.set_modified(False)

		mydict['section'] = ControlledDict()
		mydict['section']['dus'] = 'ja'
		self.assertTrue(mydict['section'].modified)
		self.assertTrue(mydict.modified)

		mydict.set_modified(False)
		self.assertFalse(mydict.modified)

		mydict['section'].set_modified(False)
		self.assertFalse(mydict['section'].modified)
		self.assertFalse(mydict.modified)

		mydict['section'] = ControlledDict() # nested dict
		mydict['section']['dus'] = 'FOO!'
		self.assertTrue(mydict['section'].modified)
		self.assertTrue(mydict.modified)

		mydict.set_modified(False)
		self.assertFalse(mydict['section'].modified)
		self.assertFalse(mydict.modified)

		mydict.update({'nu': 'ja'})
		self.assertTrue(mydict.modified)
		mydict.set_modified(False)

		mydict.setdefault('nu', 'XXX')
		self.assertFalse(mydict.modified)
		mydict.setdefault('new', 'XXX')
		self.assertTrue(mydict.modified)

		counter = [0]
		def handler(o):
			counter[0] += 1

		mydict.connect('changed', handler)
		mydict['nu'] = 'YYY'
		self.assertEqual(counter, [1])

		mydict.update({'a': 'b', 'c': 'd', 'e': 'f'})
		self.assertEqual(counter, [2]) # signal only emitted once

		mydict['section']['foo'] = 'zzz'
		self.assertEqual(counter, [3]) # recursive signal
		mydict.set_modified(False)

		v = mydict.pop('nu')
		self.assertEqual(v, 'YYY')
		self.assertTrue(mydict.modified)
		self.assertRaises(KeyError, mydict.__getitem__, v)


class TestConfigDict(tests.TestCase):

	def runTest(self):
		'''Test ConfigDict class'''
		keys = ['foo', 'bar', 'baz']
		mydict = ConfigDict()
		for k in keys:
			mydict[k] = 'dusss'

		val = mydict.setdefault('dus', 'ja')
		self.assertEqual(val, 'ja')
		val = mydict.setdefault('dus', 'hmm')
		self.assertEqual(val, 'ja')
		keys.append('dus')
		# TODO much more validation of the setdefault logic !

		newdict = mydict.copy()
		self.assertTrue(isinstance(newdict, ConfigDict))
		self.assertEquals(newdict.items(), mydict.items())


class TestINIConfigFile(tests.TestCase):

	def runTest(self):
		'''Test config file format'''
		file = XDG_CONFIG_HOME.file('zim/config_TestConfigFile.conf')
		if file.exists():
			file.remove()
		assert not file.exists()
		conf = INIConfigFile(file)
		conf['Foo']['xyz'] = 'foooooo'
		conf['Foo']['foobar'] = 0
		conf['Foo']['test'] = True
		conf['Foo']['tja'] = (3, 4)
		conf['Bar']['hmmm'] = 'tja'
		conf['Bar']['check'] = 1.333
		conf['Bar']['empty'] = ''
		conf['Bar']['none'] = None
		conf.write()
		text = u'''\
[Foo]
xyz=foooooo
foobar=0
test=True
tja=[3,4]

[Bar]
hmmm=tja
check=1.333
empty=
none=None

'''
		self.assertEqual(file.read(), text)

		del conf
		conf = INIConfigFile(file)
		self.assertFalse(conf.modified)
		self.assertEqual(conf, {
			'Foo': {
				'xyz': 'foooooo',
				'foobar': 0,
				'test': True,
				'tja': [3, 4],
			},
			'Bar': {
				'hmmm': 'tja',
				'check': 1.333,
				'empty': '',
				'none': None
			}
		})
		conf['Foo']['tja'] = (33, 44)
		self.assertTrue(conf.modified)

		# Check enforcing default type
		conf.set_modified(False)
		self.assertEqual(conf['Foo'].setdefault('foobar', 5), 0)
		self.assertEqual(conf['Bar'].setdefault('check', 3.14), 1.333)
		self.assertEqual(conf['Bar'].setdefault('check', None, float), 1.333)
		self.assertEqual(conf['Foo'].setdefault('tja', (3,4), value_is_coord), (33,44))
		self.assertEqual(conf['Bar'].setdefault('hmmm', 'foo', set(('foo', 'tja'))), 'tja')
		self.assertFalse(conf.modified)

		conf['Foo']['tja'] = [33, 44]
		conf.set_modified(False)
		self.assertEqual(conf['Foo'].setdefault('tja', (3,4)), (33,44))
		self.assertEqual(conf['Foo'].setdefault('tja', (3,4), tuple), (33,44))
		self.assertFalse(conf.modified)

		conf['Foo']['tja'] = [33, 44]
		conf.set_modified(False)
		self.assertEqual(conf['Foo'].setdefault('tja', (3,4), allow_empty=True), (33,44))
		self.assertFalse(conf.modified)

		with FilterInvalidConfigWarning():
			self.assertEqual(
			conf['Bar'].setdefault('hmmm', 'foo', set(('foo', 'bar'))),
			'foo')
		self.assertFalse(conf.modified)

		with FilterInvalidConfigWarning():
			self.assertEqual(conf['Bar'].setdefault('check', 10, int), 10)
		self.assertFalse(conf.modified)

		conf['Bar']['string'] = ''
		conf.set_modified(False)
		with FilterInvalidConfigWarning():
			self.assertEqual(conf['Bar'].setdefault('string', 'foo'), 'foo')
		self.assertFalse(conf.modified)

		conf['Bar']['string'] = ''
		conf.set_modified(False)
		self.assertEqual(conf['Bar'].setdefault('string', 'foo', allow_empty=True), '')
		self.assertFalse(conf.modified)

		conf['Bar']['string'] = ''
		conf.set_modified(False)
		self.assertEqual(conf['Bar'].setdefault('string', 'foo', check_class_allow_empty), '')
		self.assertFalse(conf.modified)

		conf['Bar']['string'] = 3
		conf.set_modified(False)
		with FilterInvalidConfigWarning():
			self.assertEqual(conf['Bar'].setdefault('string', 'foo', check_class_allow_empty), 'foo')
		self.assertFalse(conf.modified)


class TestHeaders(tests.TestCase):

	def runTest(self):
		'''Test HeadersDict class'''
		# normal operation
		text='''\
Foobar: 123
More-Lines: test
	1234
	test
Aaa: foobar
'''
		headers = HeadersDict(text)
		self.assertEqual(headers['Foobar'], '123')
		self.assertEqual(headers['More-Lines'], 'test\n1234\ntest')
		self.assertEqual(headers.dump(), text.splitlines(True))

		moretext='''\
Foobar: 123
More-Lines: test
	1234
	test
Aaa: foobar

test 123
test 456
'''
		lines = moretext.splitlines(True)
		headers = HeadersDict()
		headers.read(lines)
		self.assertEqual(headers.dump(), text.splitlines(True))
		self.assertEqual(lines, ['test 123\n', 'test 456\n'])

		# error tolerance and case insensitivity
		text = '''\
more-lines: test
1234
test
'''
		self.assertRaises(HeaderParsingError, HeadersDict, text)

		text = '''\
fooo
more-lines: test
1234
test
'''
		self.assertRaises(HeaderParsingError, HeadersDict, text)

		text = 'foo-bar: test\n\n\n'
		headers = HeadersDict(text)
		self.assertEqual(headers['Foo-Bar'], 'test')
		self.assertEqual(headers.dump(), ['Foo-Bar: test\n'])


class TestUserDirs(tests.TestCase):

	def setUp(self):
		XDG_CONFIG_HOME.file('user-dirs.dirs').write('''\
# This file is written by xdg-user-dirs-update
# If you want to change or add directories, just edit the line you're
# interested in. All local changes will be retained on the next run
# Format is XDG_xxx_DIR="$HOME/yyy", where yyy is a shell-escaped
# homedir-relative path, or XDG_xxx_DIR="/yyy", where /yyy is an
# absolute path. No other format is supported.
#
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Desktop"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
''')

	def runTest(self):
		'''Test config for user dirs'''
		dirs = user_dirs()
		self.assertEqual(dirs['XDG_DOCUMENTS_DIR'], Dir('~/Documents'))


class TestHierarchicDict(tests.TestCase):

	def runTest(self):
		'''Test HierarchicDict class'''
		dict = HierarchicDict()
		dict['foo']['key1'] = 'foo'
		self.assertEqual(dict['foo:bar:baz']['key1'], 'foo')
		self.assertEqual(dict['foo:bar:baz'].get('key1'), 'foo')
		self.assertEqual(dict['foo:bar:baz'].get('key7'), None)
		dict['foo:bar']['key1'] = 'bar'
		self.assertEqual(dict['foo:bar:baz']['key1'], 'bar')
		self.assertEqual(dict['foo']['key1'], 'foo')
		dict['foo:bar'].remove('key1')
		self.assertEqual(dict['foo:bar:baz']['key1'], 'foo')
		self.assertEqual(dict[Path('foo:bar:baz')]['key1'], 'foo')
		dict['']['key2'] = 'FOO'
		self.assertEqual(dict[Path('foo:bar:baz')]['key2'], 'FOO')



class TestVirtualConfigBackend(tests.TestCase):

	def runTest(self):
		dir = VirtualConfigBackend()
		file = dir.file('foo.conf')

		self.assertEqual(file.path, '<virtual>/foo.conf')
		self.assertEqual(file.basename, 'foo.conf')
		self.assertFalse(file.exists())
		self.assertRaises(FileNotFoundError, file.read)
		self.assertRaises(FileNotFoundError, file.readlines)

		file.touch()
		self.assertTrue(file.exists())
		self.assertEqual(file.read(), '')
		self.assertEqual(file.readlines(), [])

		file.remove()
		self.assertFalse(file.exists())
		self.assertRaises(FileNotFoundError, file.read)
		self.assertRaises(FileNotFoundError, file.readlines)

		file.write('foo\nbar\n')
		self.assertTrue(file.exists())
		self.assertEqual(file.read(), 'foo\nbar\n')
		self.assertEqual(file.readlines(), ['foo\n', 'bar\n'])

		file.writelines(['bar\n', 'baz\n'])
		self.assertTrue(file.exists())
		self.assertEqual(file.read(), 'bar\nbaz\n')
		self.assertEqual(file.readlines(), ['bar\n', 'baz\n'])

		file.write_async('foo\nbar\n')
		file = dir.file('foo.conf') # test persistence
		self.assertTrue(file.exists())
		self.assertEqual(file.read(), 'foo\nbar\n')
		self.assertEqual(file.readlines(), ['foo\n', 'bar\n'])

		file.writelines_async(['bar\n', 'baz\n'])
		file = dir.file('foo.conf') # test persistence
		self.assertTrue(file.exists())
		self.assertEqual(file.read(), 'bar\nbaz\n')
		self.assertEqual(file.readlines(), ['bar\n', 'baz\n'])


class TestXDGDefaultFileIter(tests.TestCase):

	def setUp(self):
		dir = zim.config.XDG_CONFIG_DIRS[0]
		dir.file('zim/foo.conf').touch()

	def tearDown(self):
		dir = zim.config.XDG_CONFIG_DIRS[0]
		dir.file('zim/foo.conf').remove()

	def runTest(self):
		defaults = XDGDefaultFileIter('foo.conf')
		files = list(defaults)

		self.assertTrue(len(files) > 0)
		self.assertIsInstance(files[0], File)
		self.assertEqual(files[0].basename, 'foo.conf')


class TestConfigFile(tests.TestCase):

	def testExistingFile(self):
		file = ConfigFile(VirtualConfigBackendFile({}, 'foo.conf'))
		self.assertEqual(file.basename, 'foo.conf')

		other = ConfigFile(file.file)
		self.assertTrue(other == file)

		self.assertEqual(file.read(), '')
		self.assertEqual(file.readlines(), [])
		self.assertRaises(FileNotFoundError, file.read, fail=True)
		self.assertRaises(FileNotFoundError, file.readlines, fail=True)

		file.touch()
		self.assertEqual(file.read(), '')
		self.assertEqual(file.readlines(), [])
		self.assertEqual(file.read(fail=True), '')
		self.assertEqual(file.readlines(fail=True), [])

		file.write('foo!\n')
		self.assertEqual(file.read(), 'foo!\n')
		self.assertEqual(file.readlines(), ['foo!\n'])

		file.remove()
		self.assertEqual(file.read(), '')
		self.assertEqual(file.readlines(), [])
		self.assertRaises(FileNotFoundError, file.read, fail=True)
		self.assertRaises(FileNotFoundError, file.readlines, fail=True)


	def testWithDefaults(self):
		data = {'default.conf': 'default!\n'}
		file = ConfigFile(
			VirtualConfigBackendFile(data, 'foo.conf'),
			[VirtualConfigBackendFile(data, 'default.conf')]
		)

		self.assertEqual(file.read(), 'default!\n')
		self.assertEqual(file.readlines(), ['default!\n'])

		file.touch()
		self.assertEqual(file.read(), 'default!\n')
		self.assertEqual(file.readlines(), ['default!\n'])

		file.write('foo!\n')
		self.assertEqual(file.read(), 'foo!\n')
		self.assertEqual(file.readlines(), ['foo!\n'])

		file.remove()
		self.assertEqual(file.read(), 'default!\n')
		self.assertEqual(file.readlines(), ['default!\n'])



class ConfigManagerTests(object):

	FILES = {
		'foo.conf': 'FOO!\n',
		'dict.conf': '''\
[FOO]
foo=test
bar=test123
'''
	}

	def runTest(self):
		manager = self.manager

		file = manager.get_config_file('foo.conf')
		self.assertIsInstance(file, ConfigFile)
		self.assertEquals(file.read(), 'FOO!\n')

		newfile = manager.get_config_file('foo.conf')
		self.assertEqual(id(file), id(newfile))

		dict = manager.get_config_dict('dict.conf')
		self.assertIsInstance(dict, INIConfigFile)
		self.assertEqual(dict['FOO']['foo'], 'test')

		newdict = manager.get_config_dict('dict.conf')
		self.assertEqual(id(dict), id(newdict))

		dict['FOO']['foo'] = 'dus'
		dict['FOO']['newkey'] = 'ja'
		text = manager.get_config_file('dict.conf').read()
			# We implicitly test that updates are stored already automatically
		self.assertEquals(text, '''\
[FOO]
foo=dus
bar=test123
newkey=ja

''')


class TestVirtualConfigManager(tests.TestCase, ConfigManagerTests):

	def setUp(self):
		self.manager = VirtualConfigManager(**self.FILES)


#~ @tests.slowTest
#~ class TestConfigManager(tests.TestCase, ConfigManagerTests):

	#~ def setUp(self):
		#~ self.manager = ...

		#~ def testLookup(self):
		#~ '''Test lookup of config files'''
		#~ home = XDG_CONFIG_HOME.file('zim/preferences.conf')
		#~ default =  XDG_CONFIG_DIRS[0].file('zim/preferences.conf')
		#~ self.assertFalse(home.exists())
		#~ self.assertFalse(default.exists())
#~
		#~ default.write('[TestData]\nfile=default\n')
		#~ self.assertTrue(default.exists())
#~
		#~ file = config_file('preferences.conf')
		#~ defaults = list(file.default_files())
		#~ self.assertTrue(isinstance(file, ConfigFile))
		#~ self.assertEqual(file.file, home)
		#~ self.assertEqual(defaults[0], default)
#~
		#~ dict = get_config('preferences.conf')
		#~ self.assertTrue(isinstance(dict, INIConfigFile))
		#~ self.assertEqual(dict.file, file)
		#~ self.assertEqual(dict['TestData']['file'], 'default')
#~
		#~ home.write('[TestData]\nfile=home\n')
		#~ self.assertTrue(home.exists())
#~
		#~ dict = get_config('preferences.conf')
		#~ self.assertTrue(isinstance(dict, INIConfigFile))
		#~ self.assertEqual(dict['TestData']['file'], 'home')
#~
		#~ file = config_file('notebooks.list')
		#~ self.assertTrue(isinstance(file, ConfigFile))
		#~ file = config_file('accelarators')
		#~ self.assertTrue(isinstance(file, ConfigFile))



