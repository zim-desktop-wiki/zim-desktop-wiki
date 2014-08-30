# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


import tests

from tests.gui import setupGtkInterface

import os
import tempfile
import gtk

from zim.fs import File, Dir
from zim.applications import Application
from zim.notebook import Path

from zim.plugins.versioncontrol import *

import zim.plugins.versioncontrol.bzr
import zim.plugins.versioncontrol.hg
import zim.plugins.versioncontrol.git


# We define our own tmp dir here instead of using tests.create_tmp_dir
# because sources are probably under change control already - want to
# avoid mixing up the files
def get_tmp_dir(name):
	if 'REAL_TMP' in os.environ: # Set in tests/__init__.py
		dir = Dir(os.environ['REAL_TMP'])
	else:
		dir = Dir(tempfile.gettempdir())
	#~ print "TMPDIR:", dir

	dir = dir.subdir('test_versioncontrol').subdir(name)
	if dir.exists():
		dir.remove_children()
		dir.remove()
	assert not dir.exists()

	return dir


WIKITEXT = File('tests/data/formats/wiki.txt').read() # Contains some unicode
UTF8_COMMENT = u'Commit \u03b1\u03b2\u03b3'


@tests.slowTest
class TestVCS(tests.TestCase):

	def testDetectVCS(self):
		root = Dir(self.create_tmp_dir())
		root.subdir('.bzr').touch()
		self.assertEqual(VCS._detect_in_folder(root), ('bzr', root))

		subdir = root.subdir('Foo/Bar')
		subdir.touch()
		self.assertEqual(VCS._detect_in_folder(subdir), ('bzr', root))

		subroot = root.subdir('subroot')
		subroot.subdir('.git').touch()
		self.assertEqual(VCS._detect_in_folder(subroot), ('git', subroot))

		subdir = subroot.subdir('Foo/Bar')
		subdir.touch()
		self.assertEqual(VCS._detect_in_folder(subdir), ('git', subroot))


@tests.slowTest
@tests.skipUnless(
	any(
		map(VCS.check_dependencies, (VCS.BZR, VCS.GIT, VCS.HG))
	), 'Missing dependencies')
class TestMainWindowExtension(tests.TestCase):

	def runTest(self):
		plugin = VersionControlPlugin()

		dir = get_tmp_dir('versioncontrol_TestMainWindowExtension')
		notebook = tests.new_files_notebook(dir)
		ui = setupGtkInterface(self, notebook=notebook)
		plugin.extend(notebook)
		plugin.extend(ui.mainwindow)

		notebook_ext = plugin.get_extension(NotebookExtension)
		self.assertIsInstance(notebook_ext, NotebookExtension)

		window_ext = plugin.get_extension(MainWindowExtension)
		self.assertIsInstance(window_ext, MainWindowExtension)

		## init & save version
		self.assertIsNone(notebook_ext.vcs)

		def init(dialog):
			self.assertIsInstance(dialog, VersionControlInitDialog)
			choice = dialog.combobox.get_active_text()
			self.assertTrue(choice and not choice.isspace())
			dialog.emit('response', gtk.RESPONSE_YES)

		with tests.DialogContext(init, SaveVersionDialog):
			window_ext.save_version()

		self.assertIsNotNone(notebook_ext.vcs)

		window_ext._autosave_thread.join()
		self.assertFalse(notebook_ext.vcs.modified)

		## save version again
		page = notebook.get_page(Path('Foo'))
		page.parse('wiki', 'foo!')
		notebook.store_page(page)

		self.assertTrue(notebook_ext.vcs.modified)

		with tests.DialogContext(SaveVersionDialog):
			window_ext.save_version()

		window_ext._autosave_thread.join()

		self.assertFalse(notebook_ext.vcs.modified)

		## show versions
		with tests.DialogContext(VersionsDialog):
			window_ext.show_versions()

		## auto-save
		plugin.preferences['autosave'] = True

		page = notebook.get_page(Path('Fooooo'))
		page.parse('wiki', 'foo!')
		notebook.store_page(page)

		self.assertTrue(notebook_ext.vcs.modified)
		ui.emit('quit')
		self.assertFalse(notebook_ext.vcs.modified)


@tests.slowTest
class TestVersionsDialog(tests.TestCase):

	def testSideBySide(self):
		app = get_side_by_side_app()
		if Application('meld').tryexec():
			self.assertIsNotNone(app)

		if app is None:
			print '\nCould not find an application for side-by-side comparison'
		else:
			self.assertTrue(app.tryexec)

	def testDialog(self):
		pass # TODO test other dialog functions



#####################################################
#
# BAZAAR BACKEND TEST
#
#####################################################
@tests.slowTest
@tests.skipUnless(VCS.check_dependencies(VCS.BZR), 'Missing dependencies')
class TestBazaar(tests.TestCase):

	def setUp(self):
		zim.plugins.versioncontrol.TEST_MODE = False

	def tearDown(self):
		zim.plugins.versioncontrol.TEST_MODE = True

	def runTest(self):
		'''Test Bazaar version control'''
		print '\n!! Some raw output from Bazaar expected here !!'

		root = get_tmp_dir('versioncontrol_TestBazaar')
		vcs = VCS.create(VCS.BZR, root, root)
		vcs.init()

		#~ for notebookdir in (root, root.subdir('foobar')):
			#~ detected = VersionControlPlugin._detect_vcs(notebookdir)
			#~ self.assertEqual(detected.__class__, BazaarVCS)
			#~ del detected # don't keep multiple instances around

		subdir = root.subdir('foo/bar')
		file = subdir.file('baz.txt')
		file.write('foo\nbar\n')

		self.assertEqual(''.join(vcs.get_status()), '''\
added:
  .bzrignore
  foo/
  foo/bar/
  foo/bar/baz.txt
''' )

		vcs.commit('test 1')
		self.assertRaises(NoChangesError, vcs.commit, 'test 1')

		ignorelines = lambda line: not (line.startswith('+++') or line.startswith('---'))
			# these lines contain time stamps
		diff = vcs.get_diff(versions=(0, 1))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
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
		self.assertEqual(diff, '''\
=== modified file 'foo/bar/baz.txt'
@@ -1,2 +1,2 @@
 foo
-bar
+baz

''' )

		vcs.revert()
		self.assertEqual(vcs.get_diff(), ['=== No Changes\n'])

		file.write('foo\nbaz\n')
		vcs.commit('test 2')
		diff = vcs.get_diff(versions=(1, 2))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
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
		self.assertEqual(versions[0][0], '1')
		self.assertEqual(versions[0][3], u'test 1\n')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][0], '2')
		self.assertEqual(versions[1][3], u'test 2\n')

		lines = vcs.get_version(file, version=1)
		self.assertEqual(''.join(lines), '''\
foo
bar
''' )

		annotated = vcs.get_annotated(file)
		lines = []
		for line in annotated:
			# get rid of user name
			ann, text = line.split('|')
			lines.append(ann[0]+' |'+text)
		self.assertEqual(''.join(lines), '''\
1 | foo
2 | baz
''' )

		#~ print 'TODO - test moving a file'
		file.rename(root.file('bar.txt'))
		diff = vcs.get_diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
=== renamed file 'foo/bar/baz.txt' => 'bar.txt'
''' )

		# Test unicode support
		file.write(WIKITEXT)
		diff = vcs.get_diff()
		diff = ''.join(diff)
		self.assertIsInstance(diff, unicode)
		vcs.commit(UTF8_COMMENT)
		versions = vcs.list_versions()
		self.assertTrue(UTF8_COMMENT in versions[-1][-1])
		self.assertIsInstance(versions[-1][-1], unicode)


#####################################################
#
# GIT BACKEND TEST
#
#####################################################
@tests.slowTest
@tests.skipUnless(VCS.check_dependencies(VCS.GIT), 'Missing dependencies')
class TestGit(tests.TestCase):

	def setUp(self):
		zim.plugins.versioncontrol.TEST_MODE = False

	def tearDown(self):
		zim.plugins.versioncontrol.TEST_MODE = True

	def runTest(self):
		'''Test Git version control'''
		print '\n!! Some raw output from Git could appear here !!'

		root = get_tmp_dir('versioncontrol_TestGit')
		vcs = VCS.create(VCS.GIT, root, root)
		vcs.init()

		#~ for notebookdir in (root, root.subdir('foobar')):
			#~ detected = VersionControlPlugin._detect_vcs(notebookdir)
			#~ self.assertEqual(detected.__class__, BazaarVCS)
			#~ del detected # don't keep multiple instances around

		subdir = root.subdir('foo/bar')
		file = subdir.file('baz.txt')
		file.write('foo\nbar\n')
		self.assertEqual(''.join(vcs.get_status(porcelain=True)),
			'A  .gitignore\n'
			'A  foo/bar/baz.txt\n'
		)
		vcs.update_staging()
		vcs.commit('test 1')
#[master 0f4132e] test 1
# 1 files changed, 3 insertions(+), 0 deletions(-)
# create mode 100644 foo/bar/baz.txt

		# git plugin doesnt support this atm
		#self.assertRaises(NoChangesError, vcs.commit, 'test 1')

		file = subdir.file('bar.txt')
		file.write('second\ntest\n')

		self.assertEqual(''.join(vcs.get_status(porcelain=True)),
			'A  foo/bar/bar.txt\n'
		)

		vcs.update_staging()
		vcs.commit('test 2')
#[master dbebdf1] test 2
# 0 files changed, 0 insertions(+), 0 deletions(-)
# create mode 100644 foo/bar/bar.txt

		# git plugin doesnt support this atm
		#self.assertRaises(NoChangesError, vcs.commit, 'test 2')

		# these lines contain file perms & hashes
		ignorelines = lambda line: not (line.startswith('new') or line.startswith('index'))
		diff = vcs.get_diff(versions=('HEAD'))
# john@joran:~/code/zim/TEST$ git diff master^
# diff --git a/foo/bar/bar.txt b/foo/bar/bar.txt
# new file mode 100644
# index 0000000..e69de29
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/bar.txt b/foo/bar/bar.txt
--- /dev/null
+++ b/foo/bar/bar.txt
@@ -0,0 +1,2 @@
+second
+test
''' )

		file.write('second\nbaz\n')
		diff = vcs.get_diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/bar.txt b/foo/bar/bar.txt
--- a/foo/bar/bar.txt
+++ b/foo/bar/bar.txt
@@ -1,2 +1,2 @@
 second
-test
+baz
''' )

		vcs.revert()
		self.assertEqual(vcs.get_status(porcelain=True), [])

		file.write('second\nbaz\n')
		vcs.commit('test 3')
		diff = vcs.get_diff(versions=('HEAD', 'HEAD^'))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/bar.txt b/foo/bar/bar.txt
--- a/foo/bar/bar.txt
+++ b/foo/bar/bar.txt
@@ -1,2 +1,2 @@
 second
-test
+baz
''' )

		versions = vcs.list_versions()

		self.assertTrue(isinstance(versions,list))
		#~ print 'VERSIONS>>', versions
		self.assertTrue(len(versions) == 3)
		self.assertTrue(isinstance(versions[0],tuple))
		self.assertTrue(len(versions[0]) == 4)
		self.assertTrue(isinstance(versions[0][0],basestring))
		self.assertTrue(isinstance(versions[0][1],basestring))
		self.assertTrue(isinstance(versions[0][2],basestring))
		self.assertTrue(isinstance(versions[0][3],basestring))
		self.assertEqual(versions[0][3], u'test 1\n')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][3], u'test 2\n')
		self.assertTrue(len(versions[2]) == 4)
		self.assertEqual(versions[2][3], u'test 3\n')

		# slightly different, we check the 2nd file
		lines = vcs.get_version(file, version='HEAD^')
		self.assertEqual(''.join(lines), '''\
second
test
''' )

#john@joran:/tmp/test_versioncontrol/versioncontrol_TestGit$ git annotate -t foo/bar/bar.txt
#09be0483        (John Drinkwater        1309533637 +0100        1)second
#526fb2b5        (John Drinkwater        1309533637 +0100        2)baz
#john@joran:/tmp/test_versioncontrol/versioncontrol_TestGit$ git blame -s foo/bar/bar.txt
#09be0483 1) second
#526fb2b5 2) baz

		annotated = vcs.get_annotated(file)
		lines = []
		for line in annotated:
			# get rid of commit hash, its unique
			commit, num, text = line.split(' ')
			lines.append(num+' '+text)
		self.assertEqual(''.join(lines), '''\
1) second
2) baz
''' )


		# Test unicode support
		file.write(WIKITEXT)
		diff = vcs.get_diff()
		diff = ''.join(diff)
		self.assertIsInstance(diff, unicode)
		vcs.commit(UTF8_COMMENT)
		versions = vcs.list_versions()
		self.assertIn(UTF8_COMMENT, versions[-1][-1])
		self.assertIsInstance(versions[-1][-1], unicode)


# XXX ignore renames and deletions?

# Below is a test that we dont need to handle, as we can be quite ignorant of them. Especially considering
# how git tracks file moves, ie, it doesnt.

#		file.rename(root.file('bar.txt'))
#		diff = vcs.get_diff()
#john@joran:~/code/zim/TEST$ git diff
#diff --git a/foo/bar/bar.txt b/foo/bar/bar.txt
#deleted file mode 100644
#…

#john@joran:~/code/zim/TEST$ git commit -a -m "Moved test 4"
#[master b099d98] Moved test 4
# 1 files changed, 0 insertions(+), 0 deletions(-)
# rename foo/bar/{bar.txt => boo.txt} (100%)


#####################################################
#
# MERCURIAL BACKEND TEST
#
#####################################################
@tests.slowTest
@tests.skipUnless(VCS.check_dependencies(VCS.HG), 'Missing dependencies')
class TestMercurial(tests.TestCase):

	def setUp(self):
		zim.plugins.versioncontrol.TEST_MODE = False

	def tearDown(self):
		zim.plugins.versioncontrol.TEST_MODE = True

	def runTest(self):
		'''Test Mercurial version control'''
		print '\n!! Some raw output from Mercurial expected here !!'

		root = get_tmp_dir('versioncontrol_TestMercurial')
		vcs = VCS.create(VCS.HG, root, root)
		vcs.init()

		#~ for notebookdir in (root, root.subdir('foobar')):
			#~ detected = VersionControlPlugin._detect_vcs(notebookdir)
			#~ self.assertEqual(detected.__class__, BazaarVCS)
			#~ del detected # don't keep multiple instances around

		subdir = root.subdir('foo/bar')
		file = subdir.file('baz.txt')
		file.write('foo\nbar\n')

		self.assertEqual(''.join(vcs.get_status()), '''\
A .hgignore
A foo/bar/baz.txt
''' )

		vcs.commit('test 1')
		self.assertRaises(NoChangesError, vcs.commit, 'test 1')

		ignorelines = lambda line: not (line.startswith('+++') or line.startswith('---'))
		# these lines contain time stamps

		file.write('foo\nbaz\n')
		diff = vcs.get_diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/baz.txt b/foo/bar/baz.txt
@@ -1,2 +1,2 @@
 foo
-bar
+baz
''' )

		vcs.revert()
		self.assertEqual(vcs.get_diff(), ['=== No Changes\n'])


		file.write('foo\nbaz\n')
		vcs.commit('test 2')
		diff = vcs.get_diff(versions=(0, 1))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/baz.txt b/foo/bar/baz.txt
@@ -1,2 +1,2 @@
 foo
-bar
+baz
''' )

		versions = vcs.list_versions()
		#~ print 'VERSIONS>>', versions
		self.assertTrue(len(versions) == 2)
		self.assertTrue(len(versions[0]) == 4)
		self.assertEqual(versions[0][0], str(0))
		self.assertEqual(versions[0][3], u'test 1')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][0], str(1))
		self.assertEqual(versions[1][3], u'test 2')


		lines = vcs.get_version(file, version=0)
		self.assertEqual(''.join(lines), '''\
foo
bar
''' )

		annotated = vcs.get_annotated(file)
		lines = []
		for line in annotated:
			# get rid of user name
			ann, text = line.split(':')
			lines.append(ann[0]+':'+text)
		self.assertEqual(''.join(lines), '''\
0: foo
1: baz
''' )

		#~ print 'TODO - test moving a file'
		file.rename(root.file('bar.txt'))

		diff = vcs.get_diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/baz.txt b/bar.txt
rename from foo/bar/baz.txt
rename to bar.txt
''' )



		# Test unicode support
		file.write(WIKITEXT)
		diff = vcs.get_diff()
		diff = ''.join(diff)
		self.assertIsInstance(diff, unicode)
		vcs.commit(UTF8_COMMENT)
		versions = vcs.list_versions()
		self.assertTrue(UTF8_COMMENT in versions[-1][-1])
		self.assertIsInstance(versions[-1][-1], unicode)
