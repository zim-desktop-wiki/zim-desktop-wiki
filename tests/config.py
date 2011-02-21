# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests
from tests import TestCase, LoggingFilter

import os

from zim.fs import *
from zim.config import *
from zim.notebook import Path
import zim.config


class FilterInvalidConfigWarning(LoggingFilter):

	logger = 'zim.config'
	message = 'Invalid config value'


class TestDirsTestSetup(TestCase):

	def runTest(self):
		'''Test config environment setup of test'''
		for k, v in (
			('XDG_DATA_HOME', './tests/tmp/data_home'),
			('XDG_CONFIG_HOME', './tests/tmp/config_home'),
			('XDG_CACHE_HOME', './tests/tmp/cache_home')
		): self.assertEqual(getattr(zim.config, k), Dir(v))

		for k, v in (
			('XDG_DATA_DIRS', './tests/tmp/data_dir'),
			('XDG_CONFIG_DIRS', './tests/tmp/config_dir'),
		): self.assertEqual(getattr(zim.config, k), map(Dir, v.split(':')))


class TestDirsDefault(TestCase):

	def setUp(self):
		for k in (
			'XDG_DATA_HOME', 'XDG_DATA_DIRS',
			'XDG_CONFIG_HOME', 'XDG_CONFIG_DIRS', 'XDG_CACHE_HOME'
		):
			if k in os.environ: del os.environ[k]

		zim.config._set_basedirs() # refresh

	def tearDown(self):
		tests.set_environ() # re-set the environment
		zim.config._set_basedirs() # refresh

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

	def testCorrect(self):
		'''Test default basedir paths'''
		for k, v in (
			('XDG_DATA_HOME', '~/.local/share'),
			('XDG_CONFIG_HOME', '~/.config'),
			('XDG_CACHE_HOME', '~/.cache')
		): self.assertEqual(getattr(zim.config, k), Dir(v))

		for k, v in (
			('XDG_DATA_DIRS', '/usr/share:/usr/local/share'),
			('XDG_CONFIG_DIRS', '/etc/xdg'),
		): self.assertEqual(getattr(zim.config, k), map(Dir, v.split(':')))


class TestDirsEnvironment(TestDirsDefault):

	def setUp(self):
		os.environ.update( (
			('XDG_DATA_HOME', '/foo/data/home'),
			('XDG_DATA_DIRS', '/foo/data/dir1:/foo/data/dir2'),
			('XDG_CONFIG_HOME', '/foo/config/home'),
			('XDG_CONFIG_DIRS', '/foo/config/dir1:/foo/config/dir2'),
			('XDG_CACHE_HOME', '/foo/cache')
		) )

		zim.config._set_basedirs() # refresh

	def testCorrect(self):
		'''Test config environemnt with non-default basedir paths'''
		for k, v in (
			('XDG_DATA_HOME', '/foo/data/home'),
			('XDG_CONFIG_HOME', '/foo/config/home'),
			('XDG_CACHE_HOME', '/foo/cache')
		): self.assertEqual(getattr(zim.config, k), Dir(v))

		for k, v in (
			('XDG_DATA_DIRS', '/foo/data/dir1:/foo/data/dir2'),
			('XDG_CONFIG_DIRS', '/foo/config/dir1:/foo/config/dir2'),
		): self.assertEqual(getattr(zim.config, k), map(Dir, v.split(':')))


class TestConfigFile(TestCase):

	def testParsing(self):
		'''Test config file format'''
		file = XDG_CONFIG_HOME.file('zim/config_TestConfigFile.conf')
		if file.exists():
			file.remove()
		assert not file.exists()
		conf = ConfigDictFile(file)
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
		self.assertEqualDiff(file.read(), text)

		del conf
		conf = ConfigDictFile(file)
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

		conf.set_modified(False)
		with FilterInvalidConfigWarning():
			self.assertEqual(
			conf['Bar'].setdefault('hmmm', 'foo', set(('foo', 'bar'))),
			'foo')
		self.assertTrue(conf.modified)

		conf.set_modified(False)
		with FilterInvalidConfigWarning():
			self.assertEqual(conf['Bar'].setdefault('check', 10, int), 10)
		self.assertTrue(conf.modified)

		conf['Bar']['string'] = ''
		conf.set_modified(False)
		with FilterInvalidConfigWarning():
			self.assertEqual(conf['Bar'].setdefault('string', 'foo'), 'foo')
		self.assertTrue(conf.modified)

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
		self.assertTrue(conf.modified)


	def testLookup(self):
		'''Test lookup of config files'''
		home = XDG_CONFIG_HOME.file('zim/preferences.conf')
		default =  XDG_CONFIG_DIRS[0].file('zim/preferences.conf')
		self.assertFalse(home.exists())
		self.assertFalse(default.exists())

		default.write('[TestData]\nfile=default\n')
		file = config_file('preferences.conf')
		self.assertTrue(isinstance(file, ConfigDictFile))
		self.assertEqual(file.file, home)
		self.assertEqual(file.default, default)
		self.assertEqual(file['TestData']['file'], 'default')

		home.write('[TestData]\nfile=home\n')
		file = config_file('preferences.conf')
		self.assertTrue(isinstance(file, ConfigDictFile))
		self.assertEqual(file['TestData']['file'], 'home')

		file = config_file('notebooks.list')
		#~ self.assertTrue(isinstance(file, ConfigListFile))
		self.assertTrue(isinstance(file, TextConfigFile))
		#~ file = config_file('accelarators')
		#~ self.assertTrue(isinstance(file, File))

	def testListDict(self):
		'''Test ListDict class'''
		keys = ['foo', 'bar', 'baz']
		mydict = ListDict()
		self.assertFalse(mydict.modified)
		for k in keys:
			mydict[k] = 'dusss'
		self.assertTrue(mydict.modified)

		val = mydict.get('newkey')
		self.assertEqual(val, None)
		# get() does _not_ set the key if it doesn't exist

		val = mydict.setdefault('dus', 'ja')
		self.assertEqual(val, 'ja')
		val = mydict.setdefault('dus', 'hmm')
		self.assertEqual(val, 'ja')
		keys.append('dus')

		self.assertEquals(mydict.keys(), keys)
		self.assertEquals([k for k in mydict], keys)

		mykeys = [k for k, v in mydict.items()]
		self.assertEquals(mykeys, keys)
		myval = [v for k, v in mydict.items()]
		self.assertEquals(myval, ['dusss', 'dusss', 'dusss', 'ja'])

		val = mydict.pop('bar')
		self.assertEqual(val, 'dusss')
		self.assertEqual(mydict.keys(), ['foo', 'baz', 'dus'])

		mydict.update({'bar': 'barrr'}, tja='ja ja')
		self.assertEquals(mydict.items(), (
			('foo', 'dusss'),
			('baz', 'dusss'),
			('dus', 'ja'),
			('bar', 'barrr'),
			('tja', 'ja ja'),
		))

		del mydict['tja']
		self.assertEquals(mydict.items(), (
			('foo', 'dusss'),
			('baz', 'dusss'),
			('dus', 'ja'),
			('bar', 'barrr'),
		))

		mydict.update((('tja', 'ja ja'), ('baz', 'bazzz')))
		self.assertEquals(mydict.items(), (
			('foo', 'dusss'),
			('baz', 'bazzz'),
			('dus', 'ja'),
			('bar', 'barrr'),
			('tja', 'ja ja'),
		))

		newdict = mydict.copy()
		self.assertTrue(isinstance(newdict, ListDict))
		self.assertEquals(newdict.items(), mydict.items())

		mydict.set_order(('baz', 'bar', 'foo', 'boooo', 'dus'))
		self.assertEquals(mydict.items(), (
			('baz', 'bazzz'),
			('bar', 'barrr'),
			('foo', 'dusss'),
			('dus', 'ja'),
			('tja', 'ja ja'),
		))
		self.assertTrue(isinstance(mydict.order, list))


class TestHeaders(TestCase):

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
		self.assertEqualDiff(headers.dump(), text.splitlines(True))

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
		self.assertEqualDiff(headers.dump(), text.splitlines(True))
		self.assertEqualDiff(lines, ['test 123\n', 'test 456\n'])

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


class TestUserDirs(TestCase):

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


class TestHierarchicDict(TestCase):

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

