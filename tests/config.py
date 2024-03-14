
# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests
from tests import os_native_path

import os

from zim.config import *
from zim.fs import adapt_from_oldfs
from zim.newfs import File, Folder, LocalFolder
from zim.notebook import Path

import zim.config


# Check result of lookup functions does not return files outside of
# source to be tested -- just being paranoid here...
# Note that this marshalling remains in place for any subsequent tests

_cwd = tests.ZIM_SRC_FOLDER
def marshal_path_lookup(function):
	def marshalled_path_lookup(*arg, **kwarg):
		value = function(*arg, **kwarg)
		if isinstance(value, ConfigFile):
			p = value.file
		else:
			p = value

		p = adapt_from_oldfs(p)
		if not p is None:
			assert isinstance(p, (File, Folder)), 'BUG: get %r' % p
			assert p.ischild(_cwd), "ERROR: \"%s\" not below \"%s\"" % (p, _cwd)
		return value
	return marshalled_path_lookup

zim.config.data_file = marshal_path_lookup(zim.config.data_file)
zim.config.data_dir = marshal_path_lookup(zim.config.data_dir)
#~ zim.config.config_file = marshal_path_lookup(zim.config.config_file)

##


def value_to_folder(v):
	return LocalFolder(os_native_path(v))


class FilterInvalidConfigWarning(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self, 'zim.config', 'Invalid config value')


class EnvironmentConfigContext(object):
	'''Context manager to be able to run test cases for
	environment parameters and restore the previous values on
	exit or error.
	'''
	environ = os.environ

	def __init__(self, environ_context):
		self.environ_context = environ_context
		self.environ_backup = {}
		self.environ = os.environ

	def __enter__(self):
		for k, v in self.environ_context.items():
			self.environ_backup[k] = self.environ.get(k)
			if v:
				self.environ[k] = v
			elif k in self.environ:
				del self.environ[k]
			else:
				pass

		zim.config.set_basedirs(_ignore_test=True) # refresh

	def __exit__(self, *exc_info):
		for k, v in self.environ_backup.items():
			if v:
				self.environ[k] = v
			elif k in self.environ:
				del self.environ[k]
			else:
				pass

		zim.config.set_basedirs() # refresh
		return False # Raise


class TestDirsTestSetup(tests.TestCase):

	def runTest(self):
		'''Test config environment setup of test'''
		zim.config.log_basedirs()

		for k, v in (
			('XDG_DATA_HOME', os.path.join(tests.TMPDIR, 'data_home')),
			('XDG_CONFIG_HOME', os.path.join(tests.TMPDIR, 'config_home')),
			('XDG_CACHE_HOME', os.path.join(tests.TMPDIR, 'cache_home'))
		):
			self.assertEqual(adapt_from_oldfs(getattr(zim.config, k)), LocalFolder(v))

		for k, v in (
			#~ ('XDG_DATA_DIRS', os.path.join(tests.TMPDIR, 'data_dir')),
			('XDG_CONFIG_DIRS', os.path.join(tests.TMPDIR, 'config_dir')),
		):
			self.assertEqual(
				list(map(adapt_from_oldfs, getattr(zim.config, k))),
				list(map(LocalFolder, v.split(os.pathsep)))
			)


class TestXDGDirs(tests.TestCase):

	def testAllValid(self):
		'''Test config environment is valid'''
		for var in (
			ZIM_DATA_DIR,	# should always be set when running as test
			XDG_DATA_HOME,
			XDG_CONFIG_HOME,
			XDG_CACHE_HOME
		):
			self.assertTrue(isinstance(adapt_from_oldfs(var), Folder))

		for var in (
			XDG_DATA_DIRS,
			XDG_CONFIG_DIRS,
		):
			self.assertTrue(isinstance(var, list) and isinstance(adapt_from_oldfs(var[0]), Folder))

		self.assertEqual(adapt_from_oldfs(ZIM_DATA_DIR), tests.ZIM_DATA_FOLDER)
		self.assertTrue(ZIM_DATA_DIR.file('zim.png').exists())
		self.assertTrue(data_file('zim.png').exists())
		self.assertTrue(data_dir('templates').exists())
		self.assertTrue(len(list(data_dirs(('templates')))) > 0)
		self.assertEqual(
				list(data_dirs(('templates'))),
				[d.folder('templates') for d in data_dirs() if d.exists()])

	@tests.skipIf(os.name == 'nt', 'No standard defaults for windows')
	def testDefaults(self):
		'''Test default basedir paths'''
		with EnvironmentConfigContext({
			'XDG_DATA_HOME': None,
			'XDG_DATA_DIRS': '   ',
			'XDG_CONFIG_HOME': None,
			'XDG_CONFIG_DIRS': '',
			'XDG_CACHE_HOME': None,
		}):
			for k, v in (
				('XDG_DATA_HOME', '~/.local/share'),
				('XDG_CONFIG_HOME', '~/.config'),
				('XDG_CACHE_HOME', '~/.cache')
			):
				self.assertEqual(adapt_from_oldfs(getattr(zim.config.basedirs, k)), LocalFolder(v))

			for k, v in (
				('XDG_DATA_DIRS', '/usr/share:/usr/local/share'),
				('XDG_CONFIG_DIRS', '/etc/xdg'),
			):
				self.assertEqual(
					list(map(adapt_from_oldfs, getattr(zim.config.basedirs, k))),
					list(map(LocalFolder, v.split(':')))
				)

	def testInitializedEnvironment(self):
		'''Test config environment with non-default basedir paths'''
		if os.name == 'nt':
			my_sep = ';'
			my_environ = {
				'XDG_DATA_HOME': 'C:/foo/data/home',
				'XDG_DATA_DIRS': 'C:/foo/data/dir1:/foo/data/dir2   ',
				'XDG_CONFIG_HOME': 'C:/foo/config/dir1;C:/foo/config/dir2',
				'XDG_CONFIG_DIRS': 'C:/foo/data/dir1;C:/foo/data/dir2',
				'XDG_CACHE_HOME': 'C:/foo/cache',
			}
		else:
			my_sep = ':'
			my_environ = {
				'XDG_DATA_HOME': '/foo/data/home',
				'XDG_DATA_DIRS': '/foo/data/dir1:/foo/data/dir2   ',
				'XDG_CONFIG_HOME': '/foo/config/home',
				'XDG_CONFIG_DIRS': '/foo/config/dir1:/foo/config/dir2',
				'XDG_CACHE_HOME': '/foo/cache',
			}

		with EnvironmentConfigContext(my_environ):
			for k in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
				v = my_environ[k].strip()
				self.assertEqual(adapt_from_oldfs(getattr(zim.config.basedirs, k)), value_to_folder(v))

			for k in ('XDG_DATA_DIRS', 'XDG_CONFIG_DIRS'):
				v = my_environ[k].strip()
				self.assertEqual(
					list(map(adapt_from_oldfs, getattr(zim.config.basedirs, k))),
					list(map(value_to_folder, v.split(my_sep)))
				)


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
			('foo', str, String),
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
			([1, 2, 3], list),
			(Path('foo'), Path),
		):
			definition = build_config_definition(value)
			self.assertIsInstance(definition, ConfigDefinitionByClass)
			self.assertEqual(definition.klass, klass)

		# Test input by json struct
		definition = ConfigDefinitionByClass([1, 2, 3])
		self.assertEqual(definition.check('[true,200,null]'), [True, 200, None])

		# Test converting to tuple
		definition = ConfigDefinitionByClass((1, 2, 3))
		self.assertEqual(definition.check([5, 6, 7]), (5, 6, 7))

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
		definition = Choice((1, 2), ((1, 2), (3, 4), (5, 6)))
		self.assertEqual(definition.check([3, 4]), (3, 4))

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
		definition = Coordinate((1, 2))
		self.assertEqual(definition.check((2, 3)), (2, 3))
		self.assertEqual(definition.check([2, 3]), (2, 3))
		self.assertRaises(ValueError, definition.check, 'XXX')
		self.assertRaises(ValueError, definition.check, (1, 2, 3))
		self.assertRaises(ValueError, definition.check, (1, 'XXX'))
		self.assertRaises(ValueError, definition.check, ('XXX', 2))
		self.assertRaises(ValueError, definition.check, '')
		self.assertRaises(ValueError, definition.check, None)

		definition = Coordinate((1, 2), allow_empty=True)
		self.assertEqual(definition.check(''), None)
		self.assertEqual(definition.check(None), None)


class TestConfigDict(tests.TestCase):

	def testDefinitions(self):
		mydict = ConfigDict((
			('a', 'AAA'),
			('b', 'BBB'),
			('c', 'CCC'),
		))

		self.assertFalse(mydict.modified)
		self.assertEqual(len(mydict), 0)
		self.assertEqual(list(mydict.keys()), [])
		self.assertEqual(list(mydict.values()), [])
		self.assertEqual(list(mydict.items()), [])

		self.assertRaises(KeyError, mydict.__getitem__, 'a')
		self.assertRaises(KeyError, mydict.__setitem__, 'a', 'XXX')

		# Set simple string value - use value as is
		self.assertEqual(mydict.setdefault('a', 'foo'), 'AAA')
		self.assertEqual(len(mydict), 1)
		self.assertEqual(list(mydict.keys()), ['a'])
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
		self.assertEqual(list(mydict.keys()), ['a', 'b'])
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
		self.assertEqual(list(mydict.keys()), ['a', 'b', 'c'])
		self.assertEqual(mydict['c'], 'xxx')
		self.assertFalse(mydict.modified)

		# Define a new key - test default and input
		self.assertEqual(mydict.setdefault('d', 'foo'), 'foo')
		self.assertEqual(len(mydict), 4)
		self.assertEqual(list(mydict.keys()), ['a', 'b', 'c', 'd'])
		self.assertEqual(mydict['d'], 'foo')
		self.assertFalse(mydict.modified)

		with FilterInvalidConfigWarning():
			mydict.input(d=10)
		self.assertEqual(mydict['d'], 'foo')
		mydict.input(d='bar')
		self.assertEqual(mydict['d'], 'bar')
		self.assertFalse(mydict.modified)

	def testCopy(self):
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

	def testSelectors(self):
		values = (('a', 'AAA'), ('a[darktheme]', 'BBB'))
		mydict = ConfigDict(values)
		mydict.define(a=String(None))
		self.assertEqual(mydict['a'], 'AAA')
		self.assertEqual(list(mydict.items_by_selectors()), [('a', 'AAA')])

		# Test various selectors, everytime the "all_items" output should be the same
		mydict.set_selectors(('darktheme',))
		self.assertEqual(mydict['a'], 'BBB')
		self.assertEqual(mydict.get('a', 'CCC'), 'BBB')
		self.assertEqual(list(mydict.items_by_selectors()), [('a', 'BBB')])
		self.assertEqual(list(mydict.all_items()), list(values))

		mydict.set_selectors(('foo',))
		self.assertEqual(mydict['a'], 'AAA')
		self.assertEqual(list(mydict.items_by_selectors()), [('a', 'AAA')])
		self.assertEqual(list(mydict.all_items()), list(values))

		mydict.set_selectors(('foo', 'darktheme'))
		self.assertEqual(mydict['a'], 'BBB')
		self.assertEqual(list(mydict.items_by_selectors()), [('a', 'BBB')])
		self.assertEqual(list(mydict.all_items()), list(values))

		mydict.set_selectors(None)
		self.assertEqual(mydict['a'], 'AAA')
		self.assertEqual(list(mydict.items_by_selectors()), [('a', 'AAA')])
		self.assertEqual(list(mydict.all_items()), list(values))

		# Test adding new definition after selectors are defined
		mydict.set_selectors(('darktheme',))
		mydict.input({'b': 'ligth', 'b[darktheme]': 'dark'})
		mydict.define(b=String(None))
		self.assertEqual(mydict['b'], 'dark')
		self.assertEqual(list(mydict.items_by_selectors()), [('a', 'BBB'), ('b', 'dark')])


class TestINIConfigFile(tests.TestCase):

	def testAPI(self):
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
		conf['Bar'].setdefault('empty', '', str, allow_empty=True)
		conf['Bar'].setdefault('none', None, str, allow_empty=True)
		conf.write()
		text = '''\
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

		# Get a non-existing section
		conf.set_modified(False)
		section = conf['NewSection']
		self.assertEqual(section, ConfigDict())
		self.assertFalse(section.modified)
		self.assertFalse(conf.modified)

	def testNonInitializedValuesArePreserved(self):
		text = '[Foo]\nb=test\na=test\n\n'
		file = tests.MockObject()
		file.readlines = lambda: text.splitlines(1)
		conf = INIConfigFile(file)
		self.assertEqual(conf['Foo'], {})
		self.assertEqual(list(conf['Foo'].all_items()), [('b', 'test'), ('a', 'test')])
		self.assertEqual(conf.dump(), text.splitlines(1))

	def testSelectors(self):
		text = '[Foo]\na=AAA\na[darktheme]=BBB\n\n'
		file = tests.MockObject()
		file.readlines = lambda: text.splitlines(1)
		conf = INIConfigFile(file)
		conf['Foo'].define(a=String(None))
		self.assertEqual(conf['Foo']['a'], 'AAA')
		conf.set_selectors(('darktheme',))
		self.assertEqual(conf['Foo']['a'], 'BBB')


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
		self.assertEqual(adapt_from_oldfs(dirs['XDG_DOCUMENTS_DIR']), LocalFolder('~/Documents'))


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


class TestXDGConfigDirsIter(tests.TestCase):

	def runTest(self):
		# During application init it is important that changes in
		# environment take effect immediately
		iter = XDGConfigDirsIter()

		path = os_native_path('/non-existing/dir')
		zimdir = LocalFolder(path + '/zim')
		self.assertNotIn(zimdir, list(map(adapt_from_oldfs, iter)))

		with EnvironmentConfigContext({
			'XDG_CONFIG_HOME': path
		}):
			self.assertIn(zimdir, list(map(adapt_from_oldfs, iter)))


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
		self.assertIsInstance(adapt_from_oldfs(files[0]), File)
		self.assertEqual(files[0].basename, 'foo.conf')


class TestConfigFile(tests.TestCase):

	def testExistingFile(self):
		from zim.newfs.mock import MockFile

		file = ConfigFile(MockFile('/<mock>/foo.conf'))
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
		from zim.newfs.mock import MockFolder
		folder = MockFolder('/<mock>/config/')
		userfile = folder.file('foo.conf')
		defaultfile = folder.file('default.conf')
		defaultfile.write('default!\n')
		file = ConfigFile(userfile, [defaultfile])

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

	mockConfigManager = False  # breaks hack in customtools

	FILES = {
		'foo.conf': 'FOO!\n',
		'dict.conf': '''\
[FOO]
foo=test
bar=test123
''',
	}

	def assertMatchPath(self, file, path):
		if not file.path.startswith('<virtual>'):
			path = os_native_path(path)
		assert file.path.endswith(path), '"%s" does not match "%s"' % (file.path, path)

	def runTest(self):
		manager = self.manager

		## Test basic file
		file = manager.get_config_file('foo.conf')
		self.assertIsInstance(file, ConfigFile)
		self.assertEqual(file.read(), 'FOO!\n')

		newfile = manager.get_config_file('foo.conf')
		self.assertEqual(id(file), id(newfile))

		## Test basic dict
		dict = manager.get_config_dict('dict.conf')
		self.assertIsInstance(dict, INIConfigFile)
		dict['FOO'].setdefault('foo', 'xxx')
		self.assertEqual(dict['FOO']['foo'], 'test')

		newdict = manager.get_config_dict('dict.conf')
		self.assertEqual(id(dict), id(newdict))

		dict['FOO'].setdefault('bar', 'yyy')
		dict['FOO'].setdefault('newkey', 'ja')
		dict['FOO']['foo'] = 'dus'
		text = manager.get_config_file('dict.conf').read()
			# We implicitly test that updates are stored already automatically
		self.assertEqual(text, '''\
[FOO]
foo=dus
bar=test123
newkey=ja

''')

		# Test backward compatibility
		with tests.LoggingFilter('zim.config', 'Use of "<profile>/"'):
			newdict = manager.get_config_dict('<profile>/dict.conf')
			self.assertEqual(id(dict), id(newdict))


@tests.slowTest
class TestConfigManager(tests.TestCase, ConfigManagerTests):

	def setUp(self):
		for basename, content in list(self.FILES.items()):
			XDG_CONFIG_HOME.file('zim/' + basename).write(content)

		self.manager = ConfigManager()
		self.prefix = 'zim'
