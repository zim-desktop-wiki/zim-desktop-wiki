
# Copyright 2009-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests

from tests.mainwindow import setUpMainWindow

import os
import tempfile
from gi.repository import Gtk

from zim.newfs import LocalFolder, LocalFile
from zim.applications import Application
from zim.notebook import Path
from zim.notebook.operations import ongoing_operation

from zim.plugins import PluginManager
from zim.plugins.versioncontrol import *

import zim.plugins.versioncontrol.bzr
import zim.plugins.versioncontrol.hg
import zim.plugins.versioncontrol.git
import zim.plugins.versioncontrol.fossil


# We define our own tmp dir here instead of using tests.create_tmp_dir
# because sources are probably under change control already - want to
# avoid mixing up the files
def get_tmp_dir(name):
	if 'REAL_TMP' in os.environ: # Set in tests/__init__.py
		dir = LocalFolder(os.environ['REAL_TMP'])
	else:
		dir = LocalFolder(tempfile.gettempdir())
	#~ print("TMPDIR:", dir)

	dir = dir.folder('test_versioncontrol').folder(name)
	if dir.exists():
		dir.remove_children()
		dir.remove()
	assert not dir.exists()
	dir.touch()
	return dir


with open('./tests/data/formats/wiki.txt', encoding='UTF-8') as fh:
	WIKITEXT = fh.read() # Contains some unicode
UTF8_COMMENT = 'Commit \u03b1\u03b2\u03b3'


@tests.slowTest
class TestVCS(tests.TestCase):

	def testDetectVCS(self):
		root = LocalFolder(self.create_tmp_dir())
		root.folder('.bzr').touch()
		self.assertEqual(VCS._detect_in_folder(root), ('bzr', root))

		folder = root.folder('Foo/Bar')
		folder.touch()
		self.assertEqual(VCS._detect_in_folder(folder), ('bzr', root))

		subroot = root.folder('subroot')
		subroot.folder('.git').touch()
		self.assertEqual(VCS._detect_in_folder(subroot), ('git', subroot))

		folder = subroot.folder('Foo/Bar')
		folder.touch()
		self.assertEqual(VCS._detect_in_folder(folder), ('git', subroot))

		subroot = root.folder('subfold')
		subroot.file('.fslckout').touch()
		self.assertEqual(VCS._detect_in_folder(subroot), ('fossil', subroot))

		folder = subroot.folder('Foo/Bar')
		folder.touch()
		self.assertEqual(VCS._detect_in_folder(folder), ('fossil', subroot))


@tests.slowTest
@tests.skipUnless(
	any(
		map(VCS.check_dependencies, (VCS.BZR, VCS.GIT, VCS.HG))
	), 'Missing dependencies')
class TestMainWindowExtension(tests.TestCase):

	def runTest(self):
		plugin = PluginManager.load_plugin('versioncontrol')

		dir = get_tmp_dir('versioncontrol_TestMainWindowExtension')
		notebook = self.setUpNotebook(
			mock=tests.MOCK_ALWAYS_REAL,
			content=('Test',),
			folder=LocalFolder(dir.path)
		)
		mainwindow = setUpMainWindow(notebook)

		notebook_ext = find_extension(notebook, NotebookExtension)
		window_ext = find_extension(mainwindow, VersionControlMainWindowExtension)

		op = ongoing_operation(notebook)
		assert op is None # check no opperation ongoing

		## init & save version
		self.assertIsNone(notebook_ext.vcs)

		def init(dialog):
			self.assertIsInstance(dialog, VersionControlInitDialog)
			choice = dialog.combobox.get_active_text()
			self.assertTrue(choice and not choice.isspace())
			dialog.assert_response_ok()

		with tests.DialogContext(init, SaveVersionDialog):
			window_ext.save_version()

		self.assertIsNotNone(notebook_ext.vcs)

		self.assertFalse(notebook_ext.vcs.is_modified())

		## save version again
		page = notebook.get_page(Path('Foo'))
		page.parse('wiki', 'foo!')
		notebook.store_page(page)

		self.assertTrue(notebook_ext.vcs.is_modified())

		with tests.DialogContext(SaveVersionDialog):
			window_ext.save_version()

		self.assertFalse(notebook_ext.vcs.is_modified())

		## show versions
		with tests.DialogContext(VersionsDialog):
			window_ext.show_versions()

		## auto-save
		plugin.preferences['autosave'] = True

		page = notebook.get_page(Path('Fooooo'))
		page.parse('wiki', 'foo!')
		notebook.store_page(page)

		self.assertTrue(notebook_ext.vcs.is_modified())
		mainwindow.emit('close')
		self.assertFalse(notebook_ext.vcs.is_modified())

		tests.gtk_process_events()
		assert ongoing_operation(notebook) is None


@tests.slowTest
class TestVersionsDialog(tests.TestCase):

	def testSideBySide(self):
		app = get_side_by_side_app()
		if Application('meld').tryexec():
			self.assertIsNotNone(app)

		if app is None:
			print('\nCould not find an application for side-by-side comparison')
		else:
			self.assertTrue(app.tryexec)

	def testDialog(self):
		pass # TODO test other dialog functions


class VersionControlBackendTests(object):

	def setUp(self):
		zim.plugins.versioncontrol.TEST_MODE = False

	def tearDown(self):
		zim.plugins.versioncontrol.TEST_MODE = True

	# TODO - unify test cases with single interface test



#####################################################
#
# BAZAAR BACKEND TEST
#
#####################################################
@tests.slowTest
@tests.skipUnless(VCS.check_dependencies(VCS.BZR), 'Missing dependencies')
class TestBazaar(VersionControlBackendTests, tests.TestCase):


	def runTest(self):
		'''Test Bazaar version control'''
		root = get_tmp_dir('versioncontrol_TestBazaar')
		vcs = VCS.create(VCS.BZR, root, root)
		self.addCleanup(vcs.disconnect_all)
		with tests.LoggingFilter('zim.applications'):
			vcs.init_repo()

		folder = root.folder('foo/bar')
		file = folder.file('baz.txt')
		file.write('foo\nbar\n')

		self.assertEqual(''.join(vcs.status()), '''\
added:
  .bzrignore
  foo/
  foo/bar/
  foo/bar/baz.txt
''' )

		vcs.commit_version('test 1')
		self.assertRaises(NoChangesError, vcs.commit_version, 'test 1')

		ignorelines = lambda line: not (line.startswith('+++') or line.startswith('---'))
			# these lines contain time stamps
		diff = vcs.diff(versions=(0, 1))
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
		diff = vcs.diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
=== modified file 'foo/bar/baz.txt'
@@ -1,2 +1,2 @@
 foo
-bar
+baz

''' )

		vcs.revert()
		self.assertEqual(vcs.diff(), [])

		file.write('foo\nbaz\n')
		vcs.commit_version('test 2')
		diff = vcs.diff(versions=(1, 2))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
=== modified file 'foo/bar/baz.txt'
@@ -1,2 +1,2 @@
 foo
-bar
+baz

''' )

		versions = vcs.list_versions()
		#~ print('VERSIONS>>', versions)
		self.assertTrue(len(versions) == 2)
		self.assertTrue(len(versions[0]) == 4)
		self.assertEqual(versions[0][0], '1')
		self.assertEqual(versions[0][3], 'test 1\n')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][0], '2')
		self.assertEqual(versions[1][3], 'test 2\n')

		lines = vcs.cat(file, version=1)
		self.assertEqual(''.join(lines), '''\
foo
bar
''' )

		annotated = vcs.annotate(file)
		lines = []
		for line in annotated:
			# get rid of user name
			ann, text = line.split('|')
			lines.append(ann[0] + ' |' + text)
		self.assertEqual(''.join(lines), '''\
1 | foo
2 | baz
''' )

		#~ print('TODO - test moving a file')
		file.moveto(root.file('bar.txt'))
		diff = vcs.diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
=== renamed file 'foo/bar/baz.txt' => 'bar.txt'
''' )

		# Test unicode support
		file.write(WIKITEXT)
		diff = vcs.diff()
		diff = ''.join(diff)
		self.assertIsInstance(diff, str)
		vcs.commit_version(UTF8_COMMENT)
		versions = vcs.list_versions()
		self.assertTrue(UTF8_COMMENT in versions[-1][-1])
		self.assertIsInstance(versions[-1][-1], str)

		### Test delete ###
		file.remove()
		diff = vcs.diff()
		vcs.commit_version('deleted file')


#####################################################
#
# GIT BACKEND TEST
#
#####################################################
@tests.slowTest
@tests.skipUnless(VCS.check_dependencies(VCS.GIT), 'Missing dependencies')
class TestGit(VersionControlBackendTests, tests.TestCase):

	def runTest(self):
		'''Test Git version control'''
		root = get_tmp_dir('versioncontrol_TestGit')
		vcs = VCS.create(VCS.GIT, root, root)
		self.addCleanup(vcs.disconnect_all)
		vcs.init_repo()

		#~ for notebookdir in (root, root.folder('foobar')):
			#~ detected = VersionControlPlugin._detect_vcs(notebookdir)
			#~ self.assertEqual(detected.__class__, BazaarVCS)
			#~ del detected # don't keep multiple instances around

		folder = root.folder('foo/bar')
		file = folder.file('baz.txt')
		file.write('foo\nbar\n')
		vcs.stage()
		self.assertEqual(''.join(vcs.status(porcelain=True)),
			'A  .gitignore\n'
			'A  foo/bar/baz.txt\n'
		)
		vcs.commit_version('test 1')
#[master 0f4132e] test 1
# 1 files changed, 3 insertions(+), 0 deletions(-)
# create mode 100644 foo/bar/baz.txt

		# git plugin doesnt support this atm
		#self.assertRaises(NoChangesError, vcs.commit_version, 'test 1')

		file = folder.file('bar.txt')
		file.write('second\ntest\n')
		vcs.stage()

		self.assertEqual(''.join(vcs.status(porcelain=True)),
			'A  foo/bar/bar.txt\n'
		)

		vcs.commit_version('test 2')
#[master dbebdf1] test 2
# 0 files changed, 0 insertions(+), 0 deletions(-)
# create mode 100644 foo/bar/bar.txt

		# git plugin doesnt support this atm
		#self.assertRaises(NoChangesError, vcs.commit_version, 'test 2')

		# these lines contain file perms & hashes
		ignorelines = lambda line: not (line.startswith('new') or line.startswith('index'))
		diff = vcs.diff(versions=('HEAD'))
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
		diff = vcs.diff()
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
		self.assertEqual(vcs.status(porcelain=True), [])

		file.write('second\nbaz\n')
		vcs.commit_version('test 3')
		diff = vcs.diff(versions=('HEAD', 'HEAD^'))
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

		self.assertTrue(isinstance(versions, list))
		#~ print('VERSIONS>>', versions)
		self.assertTrue(len(versions) == 3)
		self.assertTrue(isinstance(versions[0], tuple))
		self.assertTrue(len(versions[0]) == 4)
		self.assertTrue(isinstance(versions[0][0], str))
		self.assertTrue(isinstance(versions[0][1], str))
		self.assertTrue(isinstance(versions[0][2], str))
		self.assertTrue(isinstance(versions[0][3], str))
		self.assertEqual(versions[0][3], 'test 1\n')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][3], 'test 2\n')
		self.assertTrue(len(versions[2]) == 4)
		self.assertEqual(versions[2][3], 'test 3\n')

		# slightly different, we check the 2nd file
		lines = vcs.cat(file, version='HEAD^')
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

		annotated = vcs.annotate(file)
		lines = []
		for line in annotated:
			# get rid of commit hash, its unique
			commit, num, text = line.split(' ')
			lines.append(num + ' ' + text)
		self.assertEqual(''.join(lines), '''\
1) second
2) baz
''' )


		# Test unicode support
		file.write(WIKITEXT)
		diff = vcs.diff()
		diff = ''.join(diff)
		self.assertIsInstance(diff, str)
		vcs.commit_version(UTF8_COMMENT)
		versions = vcs.list_versions()
		self.assertIsInstance(versions[-1][-1], str)
		self.assertIn(UTF8_COMMENT, versions[-1][-1])

		### Test delete ###
		file.remove()
		diff = vcs.diff()
		vcs.commit_version('deleted file')


# XXX ignore renames and deletions?

# Below is a test that we dont need to handle, as we can be quite ignorant of them. Especially considering
# how git tracks file moves, ie, it doesnt.

#		file.moveto(root.file('bar.txt'))
#		diff = vcs.diff()
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
class TestMercurial(VersionControlBackendTests, tests.TestCase):

	def runTest(self):
		'''Test Mercurial version control'''
		root = get_tmp_dir('versioncontrol_TestMercurial')
		vcs = VCS.create(VCS.HG, root, root)
		self.addCleanup(vcs.disconnect_all)
		vcs.init_repo()

		#~ for notebookdir in (root, root.folder('foobar')):
			#~ detected = VersionControlPlugin._detect_vcs(notebookdir)
			#~ self.assertEqual(detected.__class__, BazaarVCS)
			#~ del detected # don't keep multiple instances around

		folder = root.folder('foo/bar')
		file = folder.file('baz.txt')
		file.write('foo\nbar\n')

		self.assertEqual(''.join(vcs.status()), '''\
A .hgignore
A foo/bar/baz.txt
''' )

		vcs.commit_version('test 1')
		self.assertRaises(NoChangesError, vcs.commit_version, 'test 1')

		ignorelines = lambda line: not (line.startswith('+++') or line.startswith('---'))
		# these lines contain time stamps

		file.write('foo\nbaz\n')
		diff = vcs.diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/baz.txt b/foo/bar/baz.txt
@@ -1,2 +1,2 @@
 foo
-bar
+baz
''' )

		vcs.revert()
		self.assertEqual(vcs.diff(), [])


		file.write('foo\nbaz\n')
		vcs.commit_version('test 2')
		diff = vcs.diff(versions=(0, 1))
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/baz.txt b/foo/bar/baz.txt
@@ -1,2 +1,2 @@
 foo
-bar
+baz
''' )

		versions = vcs.list_versions()
		#~ print('VERSIONS>>', versions)
		self.assertTrue(len(versions) == 2)
		self.assertTrue(len(versions[0]) == 4)
		self.assertEqual(versions[0][0], str(0))
		self.assertEqual(versions[0][3], 'test 1')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][0], str(1))
		self.assertEqual(versions[1][3], 'test 2')


		lines = vcs.cat(file, version=0)
		self.assertEqual(''.join(lines), '''\
foo
bar
''' )

		annotated = vcs.annotate(file)
		lines = []
		for line in annotated:
			# get rid of user name
			ann, text = line.split(':')
			lines.append(ann[0] + ':' + text)
		self.assertEqual(''.join(lines), '''\
0: foo
1: baz
''' )

		#~ print('TODO - test moving a file')
		file.moveto(root.file('bar.txt'))

		diff = vcs.diff()
		diff = ''.join(filter(ignorelines, diff))
		self.assertEqual(diff, '''\
diff --git a/foo/bar/baz.txt b/bar.txt
rename from foo/bar/baz.txt
rename to bar.txt
''' )

		# Test deleting file
		root.file('bar.txt').remove()
		vcs.commit_version('test deleting')

		# Test unicode support
		file.write(WIKITEXT)
		diff = vcs.diff()
		diff = ''.join(diff)
		self.assertIsInstance(diff, str)
		vcs.commit_version(UTF8_COMMENT)
		versions = vcs.list_versions()
		self.assertTrue(UTF8_COMMENT in versions[-1][-1])
		self.assertIsInstance(versions[-1][-1], str)

		### Test delete ###
		file.remove()
		diff = vcs.diff()
		vcs.commit_version('deleted file')


#####################################################
#
# FOSSIL BACKEND TEST
#
#####################################################
@tests.slowTest
@tests.skipUnless(VCS.check_dependencies(VCS.FOSSIL), 'Missing dependencies')
class TestFossil(VersionControlBackendTests, tests.TestCase):

	def runTest(self):
		'''Test Fossil version control'''
		root = get_tmp_dir('versioncontrol_TestFossil')
		vcs = VCS.create(VCS.FOSSIL, root, root)
		self.addCleanup(vcs.disconnect_all)
		vcs.init_repo()

		folder = root.folder('foo/bar')
		file = folder.file('baz.txt')
		file.write('foo\nbar\n')

		self.assertEqual(''.join(vcs.status()),
			'ADDED      foo/bar/baz.txt\n'
		)
		vcs.commit_version('test 1')

		file = folder.file('bar.txt')
		file.write('second\ntest\n')

		self.assertEqual(''.join(vcs.status()),
			'ADDED      foo/bar/bar.txt\n'
		)

		vcs.commit_version('test 2')

		versions = vcs.list_versions()

		self.assertTrue(isinstance(versions, list))
		#~ print('VERSIONS>>', versions)
		self.assertTrue(len(versions) == 3)
		self.assertTrue(isinstance(versions[0], tuple))
		self.assertTrue(len(versions[0]) == 4)
		self.assertTrue(isinstance(versions[0][0], str))
		self.assertTrue(isinstance(versions[0][1], str))
		self.assertTrue(isinstance(versions[0][2], str))
		self.assertTrue(isinstance(versions[0][3], str))
		self.assertEqual(versions[0][3], 'test 2 ')
		self.assertTrue(len(versions[1]) == 4)
		self.assertEqual(versions[1][3], 'test 1 ')

		# slightly different, we check the 2nd file
		lines = vcs.cat(file, version=versions[0][0])
		self.assertEqual(''.join(lines), '''\
second
test
''' )

		diff = vcs.diff(versions=(versions[2][0], versions[0][0]))
		diff = ''.join(diff)
		self.assertEqual(diff, '''\
ADDED   foo/bar/bar.txt
ADDED   foo/bar/baz.txt
''' )

		file.write('second\nbaz\n')
		diff = vcs.diff()
		diff = ''.join(diff)
		self.assertEqual(diff, '''\
Index: foo/bar/bar.txt
==================================================================
--- foo/bar/bar.txt
+++ foo/bar/bar.txt
@@ -1,2 +1,2 @@
 second
-test
+baz

''' )

		vcs.revert()
		self.assertEqual(vcs.status(), [])

		file.write('second\nbaz\n')
		vcs.commit_version('test 3')

		versions = vcs.list_versions()

		diff = vcs.diff(versions=(versions[1][0], versions[0][0]))
		diff = ''.join(diff)
		self.assertEqual(diff, '''\
Index: foo/bar/bar.txt
==================================================================
--- foo/bar/bar.txt
+++ foo/bar/bar.txt
@@ -1,2 +1,2 @@
 second
-test
+baz

''' )

		annotated = vcs.annotate(file)
		lines = []
		for line in annotated:
			# get rid of commit hash, its unique
			commit, date, num, text = line.split(None, 4)
			lines.append(num + ' ' + text)

		self.assertEqual('\n'.join(lines), '''\
1: second
2: baz''' )

		# Test unicode support
		file.write(WIKITEXT)
		diff = vcs.diff()
		diff = ''.join(diff)
		self.assertIsInstance(diff, str)
		vcs.commit_version(UTF8_COMMENT)
		versions = vcs.list_versions()
		self.assertIn(UTF8_COMMENT, versions[0][-1])
		self.assertIsInstance(versions[0][-1], str)

		### Test delete ###
		file.remove()
		diff = vcs.diff()
		vcs.commit_version('deleted file')
