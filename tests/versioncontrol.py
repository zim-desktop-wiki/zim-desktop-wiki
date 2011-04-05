# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests
from tests import TestCase

import os
import tempfile

from zim.fs import *
from zim.plugins.versioncontrol import VersionControlPlugin
from zim.plugins.versioncontrol.bzr import BazaarVCS


# We define our own tmp dir here instead of using tests.create_tmp_dir
# because sources are probably under change control already - want to
# avoid mixing up the files
def get_tmp_dir(name):
	testtmp = os.environ['TMP']
	del os.environ['TMP']
	dir = Dir(tempfile.gettempdir())
	os.environ['TMP'] = testtmp
	
	dir = dir.subdir('test_versioncontrol').subdir(name)
	if dir.exists():
		dir.remove_children()
		dir.remove()
	assert not dir.exists()

	return dir


class TestBazaar(TestCase):

	slowTest = True

	@classmethod
	def skipTestZim(klass):
		if not BazaarVCS.check_dependencies():
			return 'Missing dependencies'
		else:
			return False

	def runTest(self):
		'''Test Bazaar version control'''
		print '\n!! Some raw output from Bazaar expected here !!'

		root = get_tmp_dir('versioncontrol_TestBazaar')
		vcs = BazaarVCS(root)
		vcs.init()

		#~ for notebookdir in (root, root.subdir('foobar')):
			#~ detected = VersionControlPlugin._detect_vcs(notebookdir)
			#~ self.assertEqual(detected.__class__, BazaarVCS)
			#~ del detected # don't keep multiple instances around

		subdir = root.subdir('foo/bar')
		file = subdir.file('baz.txt')
		file.write('foo\nbar\n')

		self.assertEqualDiff(''.join(vcs.get_status()), '''\
added:
  .bzrignore
  foo/
  foo/bar/
  foo/bar/baz.txt
''' )

		vcs.commit('test 1')

		ignorelines = lambda line: not (line.startswith('+++') or line.startswith('---'))
			# these lines contain time stamps
		diff = vcs.get_diff(versions=(0, 1))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqualDiff(diff, '''\
=== added file '.bzrignore'
@@ -0,0 +1,1 @@
+**/.zim

=== added directory 'foo'
=== added directory 'foo/bar'
=== added file 'foo/bar/baz.txt'
@@ -0,0 +1,2 @@
+foo
+bar

''' )

		file.write('foo\nbaz\n')
		diff = vcs.get_diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqualDiff(diff, '''\
=== modified file 'foo/bar/baz.txt'
@@ -1,2 +1,2 @@
 foo
-bar
+baz

''' )

		vcs.revert()
		self.assertEqual(vcs.get_diff(), ['=== No Changes\n'])

		file.write('foo\nbaz\n')
		vcs.commit_async('test 2')
		diff = vcs.get_diff(versions=(1, 2))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqualDiff(diff, '''\
=== modified file 'foo/bar/baz.txt'
@@ -1,2 +1,2 @@
 foo
-bar
+baz

''' )

		versions = vcs.list_versions()
		#~ print 'VERSIONS>>', versions
		self.assertTrue(len(versions) == 2)
		self.assertTrue(len(versions[0]) == 4)
		self.assertEqual(versions[0][0], 1)
		self.assertEqual(versions[0][3], u'test 1\n')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][0], 2)
		self.assertEqual(versions[1][3], u'test 2\n')

		lines = vcs.get_version(file, version=1)
		self.assertEqualDiff(''.join(lines), '''\
foo
bar
''' )

		annotated = vcs.get_annotated(file)
		lines = []
		for line in annotated:
			# get rid of user name
			ann, text = line.split('|')
			lines.append(ann[0]+' |'+text)
		self.assertEqualDiff(''.join(lines), '''\
1 | foo
2 | baz
''' )

		#~ print 'TODO - test moving a file'
		file.rename(root.file('bar.txt'))
		diff = vcs.get_diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqualDiff(diff, '''\
=== renamed file 'foo/bar/baz.txt' => 'bar.txt'
''' )
