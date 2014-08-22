# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

from tests.environ import EnvironmentContext

import os

from zim.fs import File, Dir
from zim.config import *
from zim.notebook import Path

import zim.environ
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


class EnvironmentConfigContext(EnvironmentContext):
	# Here we use zim.environ rather than os.environ
	# to make sure encoding etc. is correct

	environ = zim.environ.environ

	def __enter__(self):
		EnvironmentContext.__enter__(self)
		zim.config.set_basedirs() # refresh

	def __exit__(self, *exc_info):
		EnvironmentContext.__exit__(self, *exc_info)
		zim.config.set_basedirs() # refresh


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


class TestXDGDirs(tests.TestCase):

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
		with EnvironmentConfigContext({
			'XDG_DATA_HOME': None,
			'XDG_DATA_DIRS': None,
			'XDG_CONFIG_HOME': None,
			'XDG_CONFIG_DIRS': None,
			'XDG_CACHE_HOME': None,
		}):
			for k, v in (
				('XDG_DATA_HOME', '~/.local/share'),
				('XDG_CONFIG_HOME', '~/.config'),
				('XDG_CACHE_HOME', '~/.cache')
			): self.assertEqual(getattr(zim.config.basedirs, k), Dir(v))

			for k, v in (
				('XDG_DATA_DIRS', '/usr/share:/usr/local/share'),
				('XDG_CONFIG_DIRS', '/etc/xdg'),
			): self.assertEqual(getattr(zim.config.basedirs, k), map(Dir, v.split(':')))

	def testCorrect(self):
		'''Test config environemnt with non-default basedir paths'''
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

		with EnvironmentConfigContext(my_environ):
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


class TestConfigDefinitions(tests.TestCase):

	def testBuildDefinition(self):
		self.assertRaises(AssertionError, build_config_definition)

		for default, check, klass in (
			('foo', None, String),
			('foo', basestring, String),
			(True, None, Boolean),
			(10, None, Integer),
			(1.0, None, Float),
			('foo', ('foo', 'bar', 'baz'), Choice),
			(10, (1, 100), Range),
			((10, 20), value_is_coord, Coordinate),
		):
			definition = build_config_definition(default, check)
			self.assertIsInstance(definition, klass)

	def testConfigDefinitionByClass(self):
		for value, klass in (
			([1,2,3], list),
			(Path('foo'), Path),
		):
			definition = build_config_definition(value)
			self.assertIsInstance(definition, ConfigDefinitionByClass)
			self.assertEqual(definition.klass, klass)

		# Test input by json struct
		definition = ConfigDefinitionByClass([1,2,3])
		self.assertEqual(definition.check('[true,200,null]'), [True,200,None])

		# Test converting to tuple
		definition = ConfigDefinitionByClass((1,2,3))
		self.assertEqual(definition.check([5,6,7]), (5,6,7))

		# Test new_from_zim_config
		definition = ConfigDefinitionByClass(Path('foo'))
		self.assertEqual(definition.check('bar'), Path('bar'))
		self.assertEqual(definition.check(':foo::bar'), Path('foo:bar'))
		self.assertRaises(ValueError, definition.check, ":::")

	def testBoolean(self):
		definition = Boolean(True)
		self.assertEqual(definition.check(False), False)
		self.assertEqual(definition.check('True'), True)
		self.assertRaises(ValueError, definition.check, 'XXX')
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

	def testString(self):
		definition = String('foo')
		self.assertEqual(definition.check('foo'), 'foo')
		self.assertRaises(ValueError, definition.check, 10)
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

		definition = String('foo', allow_empty=True)
		self.assertEqual(definition.check('foo'), 'foo')
		self.assertEqual(definition.check(''), None)
		self.assertEqual(definition.check(None), None)
		self.assertRaises(ValueError, definition.check, 10)

		definition = String(None)
		self.assertTrue(definition.allow_empty)

	def testInteger(self):
		definition = Integer(10)
		self.assertEqual(definition.check(20), 20)
		self.assertEqual(definition.check('20'), 20)
		self.assertEqual(definition.check('-20'), -20)
		self.assertRaises(ValueError, definition.check, 'XXX')
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

	def testFloat(self):
		definition = Float(10)
		self.assertEqual(definition.check(20), 20)
		self.assertEqual(definition.check('2.0'), 2.0)
		self.assertEqual(definition.check('-2.0'), -2.0)
		self.assertRaises(ValueError, definition.check, 'XXX')
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

	def testChoice(self):
		definition = Choice('xxx', ('xxx', 'foo', 'bar'))
		self.assertEqual(definition.check('foo'), 'foo')
		self.assertEqual(definition.check('Foo'), 'foo') # case independent
		self.assertRaises(ValueError, definition.check, 'YYY')
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

		definition = Choice('xxx', ('xxx', 'foo', 'bar'), allow_empty=True)
		self.assertRaises(ValueError, definition.check, 'YYY')
		self.assertEqual(definition.check('foo'), 'foo')
		self.assertEqual(definition.check('Foo'), 'foo') # case independent
		self.assertEqual(definition.check(''), None)
		self.assertEqual(definition.check(None), None)

		# test list conversion
		definition = Choice((1,2), ((1,2), (3,4), (5,6)))
		self.assertEqual(definition.check([3,4]), (3,4))

		# test hack for preferences with label
		pref = [
			('xxx', 'XXX'),
			('foo', 'Foo'),
			('bar', 'Bar'),
		]
		definition = Choice('xxx', pref)
		self.assertEqual(definition.check('foo'), 'foo')

	def testRange(self):
		definition = Range(10, 1, 100)
		self.assertEqual(definition.check(20), 20)
		self.assertEqual(definition.check('20'), 20)
		self.assertRaises(ValueError, definition.check, -10)
		self.assertRaises(ValueError, definition.check, 200)
		self.assertRaises(ValueError, definition.check, 'XXX')
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

	def testCoordinate(self):
		definition = Coordinate((1,2))
		self.assertEqual(definition.check((2,3)), (2,3))
		self.assertEqual(definition.check([2,3]), (2,3))
		self.assertRaises(ValueError, definition.check, 'XXX')
		self.assertRaises(ValueError, definition.check, (1,2,3))
		self.assertRaises(ValueError, definition.check, (1,'XXX'))
		self.assertRaises(ValueError, definition.check, ('XXX', 2))
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

		definition = Coordinate((1,2), allow_empty=True)
		self.assertEqual(definition.check(''), None)
		self.assertEqual(definition.check(None), None)


class TestConfigDict(tests.TestCase):

	def runTest(self):
		mydict = ConfigDict({
			'a': 'AAA',
			'b': 'BBB',
			'c': 'CCC',
		})

		self.assertEqual(mydict.__getitem__, mydict._values.__getitem__)
			# optimization still in place..

		self.assertFalse(mydict.modified)
		self.assertEqual(len(mydict), 0)
		self.assertEqual(mydict.keys(), [])
		self.assertEqual(mydict.values(), [])
		self.assertEqual(mydict.items(), [])

		self.assertRaises(KeyError, mydict.__getitem__, 'a')
		self.assertRaises(KeyError, mydict.__setitem__, 'a', 'XXX')

		# Set simple string value - use value as is
		self.assertEqual(mydict.setdefault('a', 'foo'), 'AAA')
		self.assertEqual(len(mydict), 1)
		self.assertEqual(mydict.keys(), ['a'])
		self.assertEqual(mydict['a'], 'AAA')
		self.assertFalse(mydict.modified)

		mydict['a'] = 'FOO'
		self.assertEqual(mydict['a'], 'FOO')
		self.assertTrue(mydict.modified)

		mydict.set_modified(False)
		self.assertRaises(ValueError, mydict.__setitem__, 'a', 10)
		self.assertFalse(mydict.modified)

		# Set Path object - convert value
		self.assertEqual(mydict.setdefault('b', Path('foo')), Path('BBB'))
		self.assertEqual(len(mydict), 2)
		self.assertEqual(mydict.keys(), ['a', 'b'])
		self.assertEqual(mydict['b'], Path('BBB'))
		self.assertFalse(mydict.modified)

		mydict['b'] = 'FOO'
		self.assertEqual(mydict['b'], Path('FOO'))
		self.assertTrue(mydict.modified)

		mydict.set_modified(False)
		self.assertRaises(ValueError, mydict.__setitem__, 'b', '::')
		self.assertFalse(mydict.modified)

		# Set a choice - reject value, use default
		with FilterInvalidConfigWarning():
			self.assertEqual(
				mydict.setdefault('c', 'xxx', ('xxx', 'yyy', 'zzz')),
				'xxx'
			)
		self.assertEqual(len(mydict), 3)
		self.assertEqual(mydict.keys(), ['a', 'b', 'c'])
		self.assertEqual(mydict['c'], 'xxx')
		self.assertFalse(mydict.modified)

		# Define a new key - test default and input
		self.assertEqual(mydict.setdefault('d', 'foo'), 'foo')
		self.assertEqual(len(mydict), 4)
		self.assertEqual(mydict.keys(), ['a', 'b', 'c', 'd'])
		self.assertEqual(mydict['d'], 'foo')
		self.assertFalse(mydict.modified)

		with FilterInvalidConfigWarning():
			mydict.input(d=10)
		self.assertEqual(mydict['d'], 'foo')
		mydict.input(d='bar')
		self.assertEqual(mydict['d'], 'bar')
		self.assertFalse(mydict.modified)

		# Test copying
		values = {
			'a': 'AAA',
			'b': 'BBB',
			'c': 'CCC',
		}
		mydict = ConfigDict(values)
		mydict.define(
			a=String(None),
			b=String(None),
			c=String(None),
		)
		self.assertEqual(dict(mydict), values)

		mycopy = mydict.copy()
		self.assertEqual(dict(mycopy), values)
		self.assertEqual(mycopy, mydict)


class TestINIConfigFile(tests.TestCase):

	def runTest(self):
		'''Test config file format'''
		file = XDG_CONFIG_HOME.file('zim/config_TestConfigFile.conf')
		if file.exists():
			file.remove()
		assert not file.exists()
		conf = INIConfigFile(file)
		conf['Foo'].setdefault('xyz', 'foooooo')
		conf['Foo'].setdefault('foobar', 0)
		conf['Foo'].setdefault('test', True)
		conf['Foo'].setdefault('tja', (3, 4))
		conf['Bar'].setdefault('hmmm', 'tja')
		conf['Bar'].setdefault('check', 1.333)
		conf['Bar'].setdefault('empty', '', basestring, allow_empty=True)
		conf['Bar'].setdefault('none', None, basestring, allow_empty=True)
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
none=

'''
		self.assertEqual(file.read(), text)

		del conf
		conf = INIConfigFile(file)
		self.assertFalse(conf.modified)
		self.assertEqual(conf['Foo']._input, {
			'xyz': 'foooooo',
			'foobar': '0',
			'test': 'True',
			'tja': '[3,4]',
		})
		self.assertEqual(conf['Bar']._input, {
			'hmmm': 'tja',
			'check': '1.333',
			'empty': '',
			'none': '',
		})

		conf['Foo'].setdefault('tja', (3, 4))
		self.assertFalse(conf.modified)

		conf['Foo']['tja'] = (33, 44)
		self.assertTrue(conf.modified)

		# Get a non-exiting section (__getitem__ not overloaded)
		conf.set_modified(False)
		section = conf['NewSection']
		self.assertEqual(section, ConfigDict())
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


class TestXDGConfigDirsIter(tests.TestCase):

	def runTest(self):
		# During application init it is important that changes in
		# environment take effect immediately
		iter = XDGConfigDirsIter()

		path = self.get_tmp_name()
		zimdir = Dir(path).subdir('zim')
		self.assertNotIn(zimdir, list(iter))

		with EnvironmentConfigContext({
			'XDG_CONFIG_HOME': path
		}):
			zim.config.set_basedirs() # refresh
			self.assertIn(zimdir, list(iter))


class TestXDGConfigFileIter(tests.TestCase):

	def setUp(self):
		dir = zim.config.XDG_CONFIG_DIRS[0]
		dir.file('zim/foo.conf').touch()

	def tearDown(self):
		dir = zim.config.XDG_CONFIG_DIRS[0]
		dir.file('zim/foo.conf').remove()

	def runTest(self):
		defaults = XDGConfigFileIter('foo.conf')
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
''',

		'profiles/myprofile/dict.conf': '''\
[FOO]
foo=myprofile
''',

		'profiles/oldprofile.conf': '',
		'styles/oldprofile.conf': '',
	}

	def assertMatchPath(self, file, path):
		assert file.path.endswith(path), '"%s" does not match "%s"' % (file.path, path)

	def runTest(self):
		manager = self.manager

		## Test basic file
		file = manager.get_config_file('foo.conf')
		self.assertIsInstance(file, ConfigFile)
		self.assertEquals(file.read(), 'FOO!\n')

		newfile = manager.get_config_file('foo.conf')
		self.assertEqual(id(file), id(newfile))

		## Test basic dict
		dict = manager.get_config_dict('<profile>/dict.conf')
		self.assertIsInstance(dict, INIConfigFile)
		dict['FOO'].setdefault('foo', 'xxx')
		self.assertEqual(dict['FOO']['foo'], 'test')

		newdict = manager.get_config_dict('<profile>/dict.conf')
		self.assertEqual(id(dict), id(newdict))

		dict['FOO'].setdefault('bar', 'yyy')
		dict['FOO'].setdefault('newkey', 'ja')
		dict['FOO']['foo'] = 'dus'
		text = manager.get_config_file('dict.conf').read()
			# We implicitly test that updates are stored already automatically
		self.assertEquals(text, '''\
[FOO]
foo=dus
bar=test123
newkey=ja

''')


		## Test profile switch
		changed_counter = tests.Counter()
		dict['FOO'].connect('changed', changed_counter)

		manager.set_profile('myprofile')
		self.assertEqual(changed_counter.count, 1)

		newfile = manager.get_config_file('foo.conf')
		self.assertEqual(newfile.file, file.file)
		self.assertFalse('myprofile' in newfile.file.path)

		newfile = manager.get_config_file('<profile>/dict.conf')
		self.assertMatchPath(newfile.file, self.prefix+'/profiles/myprofile/dict.conf')

		newdict = manager.get_config_dict('<profile>/dict.conf')
		self.assertEqual(id(newdict), id(dict))
		self.assertEqual(newdict.file, newfile)

		self.assertEqual(dict['FOO']['foo'], 'myprofile')
		self.assertEqual(dict['FOO']['bar'], 'test123')


		## Test profile backward compatibility
		manager.set_profile('oldprofile')
		self.assertEqual(changed_counter.count, 2)

		conffile = manager.get_config_file('<profile>/preferences.conf')
		file, defaults  = conffile.file, list(conffile.defaults)
		self.assertMatchPath(file, self.prefix+'/profiles/oldprofile/preferences.conf')
		self.assertMatchPath(defaults[0], self.prefix+'/profiles/oldprofile.conf')

		conffile = manager.get_config_file('<profile>/style.conf')
		file, defaults  = conffile.file, list(conffile.defaults)
		self.assertMatchPath(file, self.prefix+'/profiles/oldprofile/style.conf')
		self.assertMatchPath(defaults[0], self.prefix+'/styles/oldprofile.conf')


class TestVirtualConfigManager(tests.TestCase, ConfigManagerTests):

	def setUp(self):
		self.manager = VirtualConfigManager(**self.FILES)
		self.prefix = ''


@tests.slowTest
class TestConfigManager(tests.TestCase, ConfigManagerTests):

	def setUp(self):
		for basename, content in self.FILES.items():
			XDG_CONFIG_HOME.file('zim/' + basename).write(content)

		self.manager = ConfigManager()
		self.prefix = 'zim'


