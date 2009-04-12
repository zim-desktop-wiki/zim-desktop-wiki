# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import tests
from tests import TestCase

import os

from zim.fs import *
from zim.config import *
import zim.config


class TestDirsTestSetup(TestCase):

	def runTest(self):
		'''Test config environment setup of test'''
		for k, v in (
			('XDG_DATA_HOME', './tests/tmp/share'),
			('XDG_CONFIG_HOME', './tests/tmp/config'),
			('XDG_CACHE_HOME', './tests/tmp/cache')
		): self.assertEqual(getattr(zim.config, k), Dir(v))

		for k, v in (
			('XDG_DATA_DIRS', './tests/tmp/share'),
			('XDG_CONFIG_DIRS', './tests/tmp/config'),
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
		conf.write()
		text = u'''\
[Foo]
xyz=foooooo
foobar=0
test=True
tja=(3, 4)

[Bar]
hmmm=tja
check=1.333

'''
		self.assertEqualDiff(file.read(), text)

		del conf
		conf = ConfigDictFile(file)
		self.assertEqual(conf, {
			'Foo': {
				'xyz': 'foooooo',
				'foobar': 0,
				'test': True,
				'tja': (3, 4),
			},
			'Bar': {
				'hmmm': 'tja',
				'check': 1.333,
			}
		})
		conf['Foo'].check_is_int('foobar', None)
		conf['Bar'].check_is_float('check', None)
		conf['Foo'].check_is_coord('tja', None)

	def testLookup(self):
		'''Test lookup of config files'''
		file = config_file('preferences.conf')
		self.assertTrue(isinstance(file, ConfigDictFile))
		self.assertTrue(file.default.exists())
		file = config_file('notebooks.list')
		self.assertTrue(isinstance(file, ConfigListFile))
		file = config_file('accelarators')
		self.assertTrue(isinstance(file, File))


class TestUtils(TestCase):

	def testListDict(self):
		'''Test ListDict class'''
		keys = ['foo', 'bar', 'baz']
		mydict = ListDict()
		for k in keys:
			mydict[k] = 'dusss'
		mykeys = [k for k, v in mydict.items()]
		self.assertEquals(mykeys, keys)

	def testConfigList(self):
		'''Test ConfigList class'''
		input = u'''\
foo	bar
	dusss ja
# comments get taken out
some\ space he\ re # even here
'''
		output = u'''\
foo\tbar
dusss\tja
some\ space\the\ re
'''
		keys = ['foo', 'dusss', 'some space']
		mydict = ConfigList()
		mydict.parse(input)
		mykeys = [k for k, v in mydict.items()]
		self.assertEquals(mykeys, keys)
		result = mydict.dump()
		self.assertEqualDiff(result, output.splitlines(True))

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
		self.assertRaises(ParsingError, HeadersDict, text)

		text = '''\
fooo
more-lines: test
1234
test
'''
		self.assertRaises(ParsingError, HeadersDict, text)

		text = 'foo-bar: test\n\n\n'
		headers = HeadersDict(text)
		self.assertEqual(headers['Foo-Bar'], 'test')
		self.assertEqual(headers.dump(), ['Foo-Bar: test\n'])
