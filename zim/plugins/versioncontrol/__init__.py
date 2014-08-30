# -*- coding: utf-8 -*-

# Copyright 2009-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# Copyright 2012 Damien Accorsi <damien.accorsi@free.fr>

from __future__ import with_statement

import gobject
import gtk

import os
import logging

from zim.fs import FS, File, TmpFile
from zim.plugins import PluginClass, extends, WindowExtension, ObjectExtension
from zim.actions import action
from zim.signals import ConnectorMixin
from zim.errors import Error
from zim.applications import Application
from zim.gui.applications import DesktopEntryFile
from zim.config import value_is_coord, data_dirs
from zim.gui.widgets import ErrorDialog, QuestionDialog, Dialog, \
	PageEntry, IconButton, SingleClickTreeView, \
	ScrolledWindow, ScrolledTextView, VPaned
from zim.utils import natural_sort_key, FunctionThread


if os.environ.get('ZIM_TEST_RUNNING'):
	TEST_MODE = True
else:
	TEST_MODE = False

# FUTURE allow vcs modules like bzr to have their own UI classes
# these can add additional menu items e.g. Tools->Bazaar-> ...
# or use their own graphical interfaces, like bzr gdiff

# FUTURE add option to also pull & push versions automatically

# FUTURE add versions... menu item to note right-click

logger = logging.getLogger('zim.plugins.versioncontrol')


class VersionControlPlugin(PluginClass):

	plugin_info = {
		'name': _('Version Control'), # T: plugin name
		'description': _('''\
This plugin adds version control for notebooks.

This plugin supports the Bazaar, Git and Mercurial version control systems.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg & John Drinkwater & Damien Accorsi',
		'help': 'Plugins:Version Control',
	}

	plugin_preferences = (
		('autosave', 'bool', _('Autosave version on regular intervals'), False), # T: Label for plugin preference
	)

	@classmethod
	def check_dependencies(klass):
		has_bzr = VCS.check_dependencies(VCS.BZR)
		has_git  = VCS.check_dependencies(VCS.GIT)
		has_hg  = VCS.check_dependencies(VCS.HG)
		#TODO parameterize the return, so that a new backend will be automatically available
		return has_bzr|has_hg|has_git, [('bzr', has_bzr, False), ('hg', has_hg, False), ('git', has_git, False)]

	def extend(self, obj):
		name = obj.__class__.__name__
		if name == 'MainWindow':
			nb = obj.ui.notebook # XXX
			nb_ext = self.get_extension(NotebookExtension, notebook=nb)
			assert nb_ext, 'No notebook extension found for: %s' % nb
			mw_ext = MainWindowExtension(self, obj, nb_ext)
			self.extensions.add(mw_ext)
		else:
			PluginClass.extend(self, obj)


@extends('Notebook')
class NotebookExtension(ObjectExtension):

	def __init__(self, plugin, notebook):
		ObjectExtension.__init__(self, plugin, notebook)
		self.plugin = plugin
		self.notebook = notebook
		self.detect_vcs()

	def _get_notebook_dir(self):
		if self.notebook.dir:
			return self.notebook.dir
		elif self.notebook.file:
			return self.notebook.file.dir
		else:
			assert False, 'Notebook is not based on a file or folder'

	def detect_vcs(self):
		dir = self._get_notebook_dir()
		self.vcs = VCS.detect_in_folder(dir)
		if self.vcs:
			# HACK - FIXME use proper FS signals here
			# git requires changes to be added to staging, bzr does not
			# so add a hook for when page is written, to update staging.
			#
			# For a more generic behavior, the update_staging is implemented
			# for all version control systems. If not required - eg. bzr, hg,
			# then nothing is done
			self.notebook.connect_after('stored-page', lambda o, n: self.vcs.update_staging() )

	def init_vcs(self, vcs):
		dir = self._get_notebook_dir()
		self.vcs = VCS.create(vcs, dir, dir)

		if self.vcs:
			with self.notebook.lock:
				self.vcs.init()

	def teardown(self):
		if self.vcs:
			self.vcs.disconnect_all()


def _monitor_thread(thread):
	if thread.done:
		if thread.error:
			error = thread.exc_info[1]
			logger.error('Error during async commit', exc_info=thread.exc_info)
			ErrorDialog(None, error, thread.exc_info).run() # XXX None should be window
		return False # stop signal
	else:
		return True # keep handler

def monitor_thread(thread):
	gobject.idle_add(_monitor_thread, thread)


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
	<ui>
	<menubar name='menubar'>
		<menu action='file_menu'>
			<placeholder name='versioning_actions'>
				<menuitem action='save_version'/>
				<menuitem action='show_versions'/>
			</placeholder>
		</menu>
	</menubar>
	</ui>
	'''

	def __init__(self, plugin, window, notebook_ext):
		WindowExtension.__init__(self, plugin, window)
		self.notebook_ext = notebook_ext
		self._autosave_thread = None

		if self.notebook_ext.vcs is None:
			gaction = self.actiongroup.get_action('show_versions')
			gaction.set_sensitive(False)
		else:
			if self.plugin.preferences['autosave']:
				self.do_save_version_async()

		def on_quit(o):
			if self._autosave_thread and not self._autosave_thread.done:
				self._autosave_thread.join()

			if self.plugin.preferences['autosave']:
				self.do_save_version()

		self.window.ui.connect('quit', on_quit) # XXX

	def do_save_version_async(self, msg=None):
		if not self.notebook_ext.vcs:
			return

		if self._autosave_thread and not self._autosave_thread.done:
			self._autosave_thread.join()

		self._autosave_thread = FunctionThread(self.do_save_version, (msg,))
		self._autosave_thread.start()
		monitor_thread(self._autosave_thread)

	def do_save_version(self, msg=None):
		if not self.notebook_ext.vcs:
			return

		if not msg:
			msg = _('Automatically saved version from zim')
				# T: default version comment for auto-saved versions

		self.window.ui.assert_save_page_if_modified() # XXX
		try:
			self.notebook_ext.vcs.commit(msg)
		except NoChangesError:
			logger.debug('No autosave version needed - no changes')

	@action(_('S_ave Version...'), 'gtk-save-as', '<ctrl><shift>S', readonly=False) # T: menu item
	def save_version(self):
		self.window.ui.assert_save_page_if_modified() # XXX

		if not self.notebook_ext.vcs:
			vcs = VersionControlInitDialog().run()
			if vcs is None:
				return # Canceled

			self.notebook_ext.init_vcs(vcs)
			if self.notebook_ext.vcs:
				gaction = self.actiongroup.get_action('show_versions')
				gaction.set_sensitive(True)

		with self.notebook_ext.notebook.lock:
			SaveVersionDialog(self.window, self, self.notebook_ext.vcs).run()

	@action(_('_Versions...')) # T: menu item
	def show_versions(self):
		self.window.ui.assert_save_page_if_modified() # XXX

		dialog = VersionsDialog.unique(self, self.window,
			self.notebook_ext.vcs,
			self.notebook_ext.notebook,
			self.window.ui.page # XXX
		)
		dialog.present()


class NoChangesError(Error):

	description = _('There are no changes in this notebook since the last version that was saved') # T: verbose error description

	def __init__(self, root):
		self.msg = _('No changes since last version')
		# T: Short error descriotion


class VCS(object):
	"""
	This class is the main entry for all Version Control System Stuff.
	It is a factory, a dependencies checker, the enumeration of supported VCS.

	@implementation: If you add a VCS backend, then you have to: \
	- add a file named <your_backend>.py
	- create there a class inheriting from VCSApplicationBase \
	- add here the stuff to manage it
	"""

	# Enumeration of all available backends
	BZR = _('Bazaar') # T: option value
	HG  = _('Mercurial') # T: option value
	GIT = _('Git') # T: option value

	@classmethod
	def detect_in_folder(klass, dir):
		"""Detect if a version control system has already been setup in the folder.
		It also create the instance by calling the VCS.create() method
		@param dir: a L{Dir} instance representing the notebook root folder
		@returns: a L{VCSBackend} instance which will manage the versioning or C{None}
		"""
		name, root = klass._detect_in_folder(dir)

		if name == 'bzr':
			vcs = VCS.create(VCS.BZR, root, dir)
		elif name == 'hg':
			vcs = VCS.create(VCS.HG, root, dir)
		elif name == 'git':
			vcs = VCS.create(VCS.GIT, root, dir)
		else:
			# else maybe detected something, but no backend available
			vcs = None

		if vcs:
			logger.info('VCS detected: %s - %s', name, root)
			return vcs
		else:
			logger.info('No VCS detected')
			return None

	@classmethod
	def _detect_in_folder(klass, dir):
		# split off because it is easier to test this way
		#
		# Included unsupported systems as well, to make sure we stop
		# looking for parents if these are detected.
		for path in reversed(list(dir)):
			if path.subdir('.bzr').exists():
				return 'bzr', path
			elif path.subdir('.hg').exists():
				return 'hg', path
			elif path.subdir('.git').exists() or path.file('.git').exists():
				return 'git', path
			elif path.subdir('.svn').exists():
				return 'svn', path
			## Commented CVS out since it potentially
			## conflicts with like-named pages
			# elif path.subdir('CVS').exists():
				# return 'cvs', path
			##
			else:
				continue
		else:
			return None, None

	@classmethod
	def get_backend(klass, vcs):
		"""Return the class of backend to instantiate according to vcs given as parameter.
		@param vcs: the wanted vcs backend (VCS.BZR, VCS.GIT, VCS.HG, ...)
		@returns: the related backend class. The returned class is a VCSApplicationBase child class
		"""
		vcs_klass = None
		if vcs == VCS.BZR:
			from zim.plugins.versioncontrol.bzr import BZRApplicationBackend
			vcs_klass = BZRApplicationBackend
		elif vcs == VCS.HG:
			from zim.plugins.versioncontrol.hg import HGApplicationBackend
			vcs_klass = HGApplicationBackend
		elif vcs == VCS.GIT:
			from zim.plugins.versioncontrol.git import GITApplicationBackend
			vcs_klass = GITApplicationBackend
		else:
			assert False, 'Unkown VCS: %s' % vcs

		return vcs_klass


	@classmethod
	def create(klass, vcs, vcs_dir, notebook_dir):
		"""Build the required instance of a Version Control System

		@param vcs: Version Control System to build (choose between VCS.BZR, VCS.HG, VCS.GIT)
		@param vcs_dir: a L{Dir} instance representing the VCS root folder
		@param notebook_dir: a L{Dir} instance representing the notebook root folder
		(must be equal to or below vcs_dir)
		@returns: a C{VCSBackend} instance setup with the required backend
		"""
		if not (notebook_dir == vcs_dir or notebook_dir.ischild(vcs_dir)):
			raise AssertionError, 'Notebook %s is not part of version control dir %s' % (notebook_dir, vcs_dir)

		vcs_backend_klass = VCS.get_backend(vcs)
		return VCSBackend(vcs_dir, vcs_backend_klass(vcs_dir, notebook_dir))

	@classmethod
	def check_dependencies(klass, vcs):
		"""Check if the dependencies for the requested vcs are ok
		@param vcs: the requested vcs: VCS.BZR, VCS.GIT or VCS.HG
		@returns: C{True} if dependencies are checked ok.
		"""
		return VCS.get_backend(vcs).tryexec()



class VCSBackend(ConnectorMixin):
	"""Parent class for all VCS backend implementations.
	It implements the required API.
	"""

	def __init__(self, dir, vcs_specific_app):
		"""Initialize the instance in normal or test mode
		- in case of TEST_MODE off, it checks the file system
		  for creation, move or delete of files
		- in case of TEST_MODE on, it does not check anything
		  in order to avoid to interfer with dev environment

		@param dir: a L{Dir} object representing the repository working directory path
		@param vcs_specific_app: a backend object
		"""
		self._root = dir
		self._lock = FS.get_async_lock(self._root)
		self._app  = vcs_specific_app
		if not TEST_MODE:
			# Avoid touching the bazaar repository with zim sources
			# when we write to tests/tmp etc.
			self.connectto_all(FS, (
				'path-created',
				'path-moved',
				'path-deleted'
			) )

	@property
	def vcs(self):
		return self._app

	@property
	def root(self):
		return self._root

	@property
	def lock(self):
		return self._lock


	def _ignored(self, path):
		"""Return True if we should ignore this path
		TODO add specific ignore patterns in the _ignored_vcs_specific method
		for now we just hardcode zim specific logic

		@param path: a L{UnixFile} object representing the file path to check
		@returns: True if the path should be ignored or False
		"""
		return '.zim' in path.split() or self.vcs._ignored(path)

	def init(self):
		"""Initialize a Bazaar repository in the self.root directory.
		If the directory does not exist, then create it
		@returns: nothing
		"""
		if self.vcs.repo_exists():
			return

		if not self.root.exists():
			self.root.touch()

		#~ with self.lock: # FIXME - conflicts with "git init" !???
		self.vcs.init_repo()

	def on_path_created(self, fs, path):
		"""Callback to add a new file or folder when added to the wiki
		Note: the VCS operation is asynchronous

		@param fs: the L{FSSingletonClass} instance representing the file system
		@param path: the L{UnixFile} object representing the newly created file or folder
		@returns: nothing
		"""
		if path.ischild(self.root) and not self._ignored(path):
			FunctionThread(self.vcs.add, (path,), lock=self._lock).start()


	def on_path_moved(self, fs, oldpath, newpath):
		"""Callback to move the file in Bazaar when moved in the wiki
		Note: the VCS operation is asynchronous

		@param fs: the L{FSSingletonClass} instance representing the file system
		@param oldpath: the L{UnixFile} object representing the old path of the file or folder
		@param newpath: the L{UnixFile} object representing the new path of the file or folder
		@returns: nothing
		"""
		if newpath.ischild(self.root) and not self._ignored(newpath):
			if oldpath.ischild(self.root):
				# Parent of newpath needs to be versioned in order to make mv succeed
				FunctionThread(self.vcs.move, (oldpath, newpath), lock=self._lock).start()
			else:
				FunctionThread(self.vcs.add, (newpath,), lock=self._lock).start()
		elif oldpath.ischild(self.root) and not self._ignored(oldpath):
			self.on_path_deleted(self, fs, oldpath)

	def on_path_deleted(self, path):
		"""Callback to remove a file from Bazaar when deleted from the wiki
		Note: the VCS operation is asynchronous

		@param path: the L{UnixFile} object representing the path of the file or folder to delete
		@returns: nothing
		"""
		FunctionThread(self.vcs.remove, (path,), lock=self._lock).start()

	@property
	def modified(self):
		"""return True if changes are detected, or False"""
		return ''.join( self.get_status() ).strip() != ''
		with self.lock:
			return self.vcs.is_modified()

	def get_status(self, **kwarg):
		"""Returns repo status as a list of text lines

		@returns: list of text lines (like a shell command result)
		"""
		status = list()
		with self.lock:
			status = self.vcs.status(**kwarg)
		return status

	def get_diff(self, versions=None, file=None):
		"""Returns the diff operation result of a repo or file
		@param versions: couple of version numbers (integer)
		@param file: L{UnixFile} object of the file to check, or None
		@returns: the diff result
		"""
		with self.lock:
			nc = ['=== No Changes\n']
			diff = self.vcs.diff(versions, file) or nc
		return diff

	def get_annotated(self, file, version=None):
		"""Returns the annotated version of a file
		@param file: L{UnixFile} object of the file to check, or None
		@param version: required version number (integer) or None
		@returns: the annotated version of the file result
		"""
		with self.lock:
			annotated = self.vcs.annotate(file, version)
		return annotated

	def commit(self, msg):
		"""Run a commit operation.

		@param msg: commit message (str)
		@returns: nothing
		"""
		with self.lock:
			self._commit(msg)

	def _commit(self, msg):
		stat = ''.join(self.vcs.status()).strip()
		if not stat:
			raise NoChangesError(self.root)
		else:
			self.vcs.add()
			self.vcs.commit(None, msg)

	def revert(self, version=None, file=None):
		with self.lock:
			self.vcs.revert(file, version)


	def list_versions(self, file=None):
		"""Returns a list of all versions, for a file or for the entire repo

		@param file: a L{UnixFile} object representing the path to the file, or None
		@returns: a list of tuples (revision (int), date, user (str), msg (str))
		"""
		# TODO see if we can get this directly from bzrlib as well
		with self.lock:
			lines = self.vcs.log(file)
			versions = self.vcs.log_to_revision_list(lines)
		return versions


	def get_version(self, file, version):
		"""FIXME Document"""
		with self.lock:
			version = self.vcs.cat(file, version)
		return version

	def update_staging(self):
		with self.lock:
			self.vcs.stage()


class VCSApplicationBase(object):
	"""This class is the base class for the classes representing the
	specific version control applications.

	This class is abstract and must be inherited. Subclasses of this
	class can be used by L{VCSBackend} to apply version control to
	a folder.
	"""

	def __init__(self, vcs_dir, notebook_dir):
		"""Constructor.
		@param vcs_dir: a L{Dir} instance representing the VCS root folder
		@param notebook_dir: a L{Dir} instance representing the notebook root folder
		(must be equal to or below vcs_dir)
		"""
		if not (notebook_dir == vcs_dir or notebook_dir.ischild(vcs_dir)):
			raise AssertionError, 'Notebook %s is not part of version control dir %s' % (notebook_dir, vcs_dir)
		self._app = self.build_bin_application_instance()
		self.root = vcs_dir
		self.notebook_dir = notebook_dir

	@classmethod
	def build_bin_application_instance(cls):
		"""Builds an L{Application} object for the backend command
		@returns: an L{Application} object
		@implementation: must be implemented in child classes.
		"""
		raise NotImplementedError

	@classmethod
	def tryexec(cls):
		"""Check if the command associated with the backend is available.
		@returns: C{True} if the command is available
		"""
		return cls.build_bin_application_instance().tryexec()

	def run(self, params):
		"""Execute a command with the associated binary with 'params' parameters.
		Note: the working directory is the root associated to the repository

		@param params: a list of parameters to be added to the command line
		@returns: nothing
		@implementation: should not be overriden by child classes
		"""
		self._app.run(params, self.root)

	def pipe(self, params):
		"""Execute a command with the associated binary with 'params' parameters
		and return the command line output.
		@param params: a list of parameters to be added to the command line
		@returns: a list of str() representing each line of the output
		@implementation: should not be overriden by child classes
		"""
		return self._app.pipe(params, self.root)

	def _ignored(self, file):
		"""return True if the file should be ignored by the version control system
		@param file: a L{File} representing the file that we want to know if it should be ignored
		@returns: C{True} if the file should be ignored by the VCS.
		@implementation: may be overridden if some files are to be ignored \
		                 specifically for the backend
		"""
		return False

	########
	#
	# NOW ARE ALL REVISION CONTROL SYSTEM SHORTCUTS

	def add(self, file=None):
		"""Add a file to the repository. If None, then the add must be for the \
		entire repository
		@param file: a L{File} instance representing the file to add.
		@returns: C{True} if the command was successfull

		Exemple: for Mercurial, the implementation will run "hg add <file>" or
		"hg add" if file=None (meaning the entire repository

		@implementation: must be implemented in child classes
		"""
		raise NotImplementedError

	def annotate(self, file, version):
		"""return the annotated version of a file. This is commonly related
		to the VCS command annotate

		@param file: a L{File} instance representing the file
		@param version: a  None/int/str representing the revision of the file
		@returns: a list of lines representing the command result output

		Eg. for mercurial, it will return something like:
		  0: line1
		  2: line1
		  ...

		@implementation: must be implemented in child classes
		"""
		raise NotImplementedError

	def cat(self, file, version):
		"""Return the context of a file at a specific version
		@param file: a L{File} object in this repository
		@param version: a version id
		@returns: a list of lines
		"""
		raise NotImplementedError

	def commit(self, file, msg):
		"""Execute a commit for the file or for the entire repository
		@param file: a L{File} instance representing the file or None for the entire repository
		@param msg: a str() representing the commit message
		@returns: C{True} if the command was successfull

		Example for Mercurial. It will run:
		- hg commit -m <msg> <file>    (file not None and message not empty
		- hg commit -m <msg>           (file=None and message not empty)
		- hg commit <file>             (file not None and message empty)
		- hg commit                    (file=None and message empty)

		@implementation: must be implemented in child class
		"""
		raise NotImplementedError

	def diff(self, versions, file=None):
		"""Returns the result of a diff between two revisions as a list of str()
		representing the diff operation output.
		@param versions: int, str, couple or tuple representing the versions to compare
		@param file: a L{File} instance representing the file, or None
		@returns: a list of str() representing the output of the diff operation

		Example for Mercurial. It could run:
		- hg diff --git <version1> <version2> <file>
		- hg diff --git <version1> <file>
		- ...

		Note: the --git option allow to show the result a better way
		@implementation: must be implemented in child class
		"""
		raise NotImplementedError

	def ignore(self, file_to_ignore_regexp):
		"""initialize the .XXignore file used by the VCS.

		@param file_to_ignore_regexp: a str() representing the content of the \
		                              .XXignore file. It's commonly a set of
		                              regular expressions separated by a line end.

		Note: the behavior is to overwrite the entire file content, so you must
		first concatenate the regexp if you need several.
		@returns: nothing

		@implementation: must be implemented in child class. The ignore file may
		                 be easyly created by running simply the following line
		                 of code:
		                 self.root.file('nameoftheignorefile').write(file_to_ignore_regexp)

		Example: for Mercurial, the content of the method is:
		  self.root.file('.hgignore').write(file_to_ignore_regexp)
		"""
		#TODO: append the rule instead of overwrite the full content
		raise NotImplementedError


	def init_repo(self):
		"""initialize a repository in the associated folder.
		Runs L{init()}, adds existing files etc.
		@returns: nothing.
		@implementation: must be implemented in the child class.
		"""
		raise NotImplementedError

	def repo_exists(self):
		"""Returns True if a repository is already setup
		@returns: C{True} if a repository is already setup in the root directory
		@implementation: must be implemented in child classes.
		"""
		raise NotImplementedError

	def init(self):
		""" runs the VCS init command
		@returns: C{True} if the command was successfull
		@implementation: must be implemented in child class

		Example: for mercurial or bazaar it runs "hg init" (or "bzr init")
		"""
		raise NotImplementedError

	def is_modified(self):
		"""Returns True if the repo is not up-to-date, or False
		@returns: C{True} if the repo is not up-to-date, or False
		@implementation: must be implemented in the child class.
		"""
		raise NotImplementedError

	def log(self, file=None):
		"""Returns the history related to a file.
		@param file: a L{File} instance representing the file or None (for the entire repository)
		@returns: a list of str() representing the output of the command. (not parsed)
		@implementation: must be implemented in child class. It must return the \
		                 output for a file or for the entire repository, and the \
		                 order must be from the oldest to the newest commits
		"""
		raise NotImplementedError

	def log_to_revision_list(self, log_op_output):
		"""Converts the result of a log() call into a list of tuples representing \
		the commits.
		@param log_op_output: a list of str() representing the log operation output
		                      before being parsed.
		@returns: a list of tuple (revision-id, date, user, commit-message) \
		          representing the entire life.
		@implementation: must be implemented in the child class. \
		                 Actually, this method is a "log" operation parser which
		                 will convert str lines into list of 4-str tuples :
		                 (revision-id, date, user, commit-message)
		"""
		raise NotImplementedError

	def move(self, oldfile, newfile):
		"""Must implement the VCS operation required after a file has been moved
		into the repository.

		Note: this is only for files being move from somewhere in the repository
		to somewhere in the repository
		@param oldfile: a L{File} representing the old location of the file
		@param newfile: a L{File} representing the new location of the file
		@returns : C{True} if the VCS operation representing this move was successfull
		@implementation: must be implemented in child class. \
		                 CAUTION: this must not implement a move operation but \
		                 a "a file has moved on the filesystem" operation, \
		                 ordering the VCS to take into account the new state.

		                 Example: with mercurial, it is implemented by running:
		                   hg mv --after <oldfile> <newfile>
		"""
		raise NotImplementedError


	def remove(self, file):
		"""Remove a file from the repository.
		@param file: a L{File} instance representing the file that have been deleted from the FS
		@returns: C{True} if the command was successfull
		@implementation: must be implemented in child class. \
		                 CAUTION: this must implement the VCS operation required \
		                 after a versionned file has been deleted from the file system. \
		                 \
		                 Example: in mercurial it has been implemented with:
		                   hg rm <file>
		"""
		raise NotImplementedError

	def revert(self, file, version):
		"""Reverts a file to an older version
		@param file: a L{File} instance representing the file or None for the entire repo
		@param version: a str() or int() representing the expected version
		@returns: C{True} if the command was successfull
		@implementation: must be implemented in child class

		Example: in mercurial it will run:
		- hg revert --no-backup <file> <version>     if file is not None
		- hg revert --no-backup --all                if file=None
		"""
		raise NotImplementedError

	def stage(self):
		"""Fixme - to be documented
		Usefull for git, runs:
		  git add -u
		  git add -A

		@implementation: optional to be implemented in child class
		"""
		pass

	def status(self):
		"""Returns the status of the repository
		@returns: a list of str() representing the output of a "status" command
		related to the repository
		@implementation: must be implemented in child classes
		"""
		raise NotImplementedError


def get_side_by_side_app():
	for dir in data_dirs('helpers/compare_files/'):
		for name in dir.list(): # XXX need object list
			file = dir.file(name)
			if name.endswith('.desktop') and file.exists():
				app = DesktopEntryFile(file)
				if app.tryexec():
					return app
	else:
		return None


class VersionControlInitDialog(QuestionDialog):

	def __init__(self):
		QuestionDialog.__init__(self,
			_("Enable Version Control?"), # T: Question dialog
			_("Version control is currently not enabled for this notebook.\n"
			  "Do you want to enable it?" ) # T: Detailed question
		)

		self.combobox = gtk.combo_box_new_text()
		for option in (VCS.BZR, VCS.GIT, VCS.HG):
			if VCS.check_dependencies(option):
				self.combobox.append_text(option)
		self.combobox.set_active(0)

		hbox = gtk.HBox(spacing=5)
		hbox.pack_end(self.combobox, False)
		hbox.pack_end(gtk.Label(_('Backend') + ':'), False)
			# T: option to chose versioncontrol backend
		self.vbox.pack_start(hbox, False)
		hbox.show_all()

	def run(self):
		if QuestionDialog.run(self):
			return self.combobox.get_active_text()
		else:
			return None


class SaveVersionDialog(Dialog):

	def __init__(self, ui, window_ext, vcs):
		Dialog.__init__(self, ui, _('Save Version'), # T: dialog title
			button=(None, 'gtk-save'), help='Plugins:Version Control')
		self.window_ext = window_ext
		self.vcs = vcs

		self.vbox.pack_start(
			gtk.Label(_("Please enter a comment for this version")), False)  # T: Dialog text

		vpaned = VPaned()
		self.vbox.add(vpaned)

		window, self.textview = ScrolledTextView(_('Saved version from zim'))
			# T: default version comment in the "save version" dialog
		self.textview.set_editable(True)
		vpaned.add1(window)

		vbox = gtk.VBox()
		vpaned.add2(vbox)

		label = gtk.Label('<b>'+_('Details')+'</b>')
			# T: section for version details in "save version" dialog
		label.set_use_markup(True)
		label.set_alignment(0, 0.5)
		vbox.pack_start(label, False)

		status = self.vcs.get_status()
		window, textview = ScrolledTextView(text=''.join(status), monospace=True)
		vbox.add(window)

	def do_response_ok(self):
		# notebook.lock already set by plugin.save_version()
		buffer = self.textview.get_buffer()
		start, end = buffer.get_bounds()
		msg = buffer.get_text(start, end, False).strip()
		if msg:
			self.window_ext.do_save_version_async(msg)
			return True
		else:
			return False


class VersionsDialog(Dialog):

	def __init__(self, ui, vcs, notebook, page=None):
		Dialog.__init__(self, ui, _('Versions'), # T: dialog title
			buttons=gtk.BUTTONS_CLOSE, help='Plugins:Version Control')
		self.notebook = notebook
		self.vcs = vcs
		self._side_by_side_app = get_side_by_side_app()

		self.uistate.setdefault('windowsize', (600, 500), check=value_is_coord)
		self.uistate.setdefault('vpanepos', 300)

		self.vpaned = VPaned()
		self.vpaned.set_position(self.uistate['vpanepos'])
		self.vbox.add(self.vpaned)

		vbox = gtk.VBox(spacing=5)
		self.vpaned.pack1(vbox, resize=True)

		# Choice between whole notebook or page
		label = gtk.Label('<b>'+_('Versions')+':</b>') # section label
		label.set_use_markup(True)
		label.set_alignment(0, 0.5)
		vbox.pack_start(label, False)

		self.notebook_radio = gtk.RadioButton(None, _('Complete _notebook'))
			# T: Option in versions dialog to show version for complete notebook
		self.page_radio = gtk.RadioButton(self.notebook_radio, _('_Page')+':')
			# T: Option in versions dialog to show version for single page
		#~ recursive_box = gtk.CheckButton('Recursive')
		vbox.pack_start(self.notebook_radio, False)

		# Page entry
		hbox = gtk.HBox(spacing=5)
		vbox.pack_start(hbox, False)
		hbox.pack_start(self.page_radio, False)
		self.page_entry = PageEntry(self.notebook)
		if page:
			self.page_entry.set_path(page)
		hbox.pack_start(self.page_entry, False)

		# View annotated button
		ann_button = gtk.Button(_('View _Annotated')) # T: Button label
		ann_button.connect('clicked', lambda o: self.show_annotated())
		hbox.pack_start(ann_button, False)

		# Help text
		label = gtk.Label('<i>\n'+_( '''\
Select a version to see changes between that version and the current
state. Or select multiple versions to see changes between those versions.
''' ).strip()+'</i>') # T: Help text in versions dialog
		label.set_use_markup(True)
		#~ label.set_alignment(0, 0.5)
		vbox.pack_start(label, False)

		# Version list
		self.versionlist = VersionsTreeView()
		self.versionlist.load_versions(vcs.list_versions())
		scrolled = ScrolledWindow(self.versionlist)
		vbox.add(scrolled)

		col = self.uistate.setdefault('sortcol', self.versionlist.REV_SORT_COL)
		order = self.uistate.setdefault('sortorder', gtk.SORT_DESCENDING)
		try:
			self.versionlist.get_model().set_sort_column_id(col, order)
		except:
			logger.exception('Invalid sort column: %s %s', col, order)

		# -----
		vbox = gtk.VBox(spacing=5)
		self.vpaned.pack2(vbox, resize=False)

		label = gtk.Label('<b>'+_('Comment')+'</b>') # T: version details
		label.set_use_markup(True)
		label.set_alignment(0.0, 0.5)
		vbox.pack_start(label, False)

		# Comment text
		window, textview = ScrolledTextView()
		self.comment_textview = textview
		vbox.add(window)

		buttonbox = gtk.HButtonBox()
		buttonbox.set_layout(gtk.BUTTONBOX_END)
		vbox.pack_start(buttonbox, False)

		# Restore version button
		revert_button = gtk.Button(_('_Restore Version')) # T: Button label
		revert_button.connect('clicked', lambda o: self.restore_version())
		buttonbox.add(revert_button)

		# Notebook Changes button
		diff_button = gtk.Button(_('Show _Changes'))
			# T: button in versions dialog for diff
		diff_button.connect('clicked', lambda o: self.show_changes())
		buttonbox.add(diff_button)

		# Compare page button
		comp_button = gtk.Button(_('_Side by Side'))
			# T: button in versions dialog for side by side comparison
		comp_button.connect('clicked', lambda o: self.show_side_by_side())
		buttonbox.add(comp_button)


		# UI interaction between selections and buttons

		def on_row_activated(o, iter, path):
			model = self.versionlist.get_model()
			comment = model[iter][VersionsTreeView.MSG_COL]
			buffer = textview.get_buffer()
			buffer.set_text(comment)

		self.versionlist.connect('row-activated', on_row_activated)


		def on_ui_change(o):
			usepage = self.page_radio.get_active()
			self.page_entry.set_sensitive(usepage)
			ann_button.set_sensitive(usepage)

			# side by side comparison can only be done for one page
			# revert can only be done to one version, not multiple
			selection = self.versionlist.get_selection()
			model, rows = selection.get_selected_rows()
			if not rows:
				revert_button.set_sensitive(False)
				diff_button.set_sensitive(False)
				comp_button.set_sensitive(False)
			elif len(rows) == 1:
				revert_button.set_sensitive(usepage)
				diff_button.set_sensitive(True)
				comp_button.set_sensitive(bool(usepage and self._side_by_side_app))
			else:
				revert_button.set_sensitive(False)
				diff_button.set_sensitive(True)
				comp_button.set_sensitive(bool(usepage and self._side_by_side_app))

		def on_page_change(o):
			pagesource = self._get_file()
			if pagesource:
				self.versionlist.load_versions(vcs.list_versions(self._get_file()))

		def on_book_change(o):
			self.versionlist.load_versions(vcs.list_versions())

		self.page_radio.connect('toggled', on_ui_change)
		self.notebook_radio.connect('toggled', on_book_change)
		self.page_radio.connect('toggled', on_page_change)
		self.page_entry.connect('changed', on_page_change)
		selection = self.versionlist.get_selection()
		selection.connect('changed', on_ui_change)

		# select last version
		self.versionlist.get_selection().select_path((0,))
		col = self.versionlist.get_column(0)
		self.versionlist.row_activated(0, col)

	def save_uistate(self):
		self.uistate['vpanepos'] = self.vpaned.get_position()

		col, order = self.versionlist.get_model().get_sort_column_id()
		self.uistate['sortcol'] = col
		self.uistate['sortorder'] = order

	def _get_file(self):
		if self.notebook_radio.get_active():
			return None
		else:
			path = self.page_entry.get_path()
			if path:
				page = self.notebook.get_page(path)
			else:
				return None # TODO error message valid page name?

			if page \
			and hasattr(page, 'source') \
			and isinstance(page.source, File) \
			and page.source.ischild(self.vcs.root):
				return page.source
			else:
				return None # TODO error message ?

	def show_annotated(self):
		# TODO check for gannotated
		file = self._get_file()
		assert not file is None
		annotated = self.vcs.get_annotated(file)
		TextDialog(self, _('Annotated Page Source'), annotated).run()
			# T: dialog title

	def restore_version(self):
		file = self._get_file()
		path = self.page_entry.get_path()
		version = self.versionlist.get_versions()[0]
		assert not file is None
		if QuestionDialog(self, (
			_('Restore page to saved version?'), # T: Confirmation question
			_('Do you want to restore page: %(page)s\n'
			  'to saved version: %(version)s ?\n\n'
			  'All changes since the last saved version will be lost !')
			  % {'page': path.name, 'version': str(version)}
			  # T: Detailed question, "%(page)s" is replaced by the page, "%(version)s" by the version id
		) ).run():
			self.vcs.revert(file=file, version=version)
			self.ui.reload_page() # XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
			# TODO trigger vcs autosave here?

	def show_changes(self):
		# TODO check for gdiff
		file = self._get_file()
		versions = self.versionlist.get_versions()
		diff = self.vcs.get_diff(file=file, versions=versions)
		TextDialog(self, _('Changes'), diff).run()
			# T: dialog title

	def show_side_by_side(self):
		file = self._get_file()
		versions = self.versionlist.get_versions()
		if not (file and versions):
			raise AssertionError

		files = map(lambda v: self._get_tmp_file(file, v), versions)
		if len(files) == 1:
			tmp = TmpFile(file.basename + '--CURRENT', persistent=True)
				# need to be persistent, else it is cleaned up before application spawned
			tmp.writelines(file.readlines())
			files.insert(0, tmp)

		self._side_by_side_app.spawn(files)

	def _get_tmp_file(self, file, version):
		text = self.vcs.get_version(file, version)
		tmp = TmpFile(file.basename + '--REV%s' % version, persistent=True)
			# need to be persistent, else it is cleaned up before application spawned
		tmp.writelines(text)
		return tmp


class TextDialog(Dialog):

	def __init__(self, ui, title, lines):
		Dialog.__init__(self, ui, title, buttons=gtk.BUTTONS_CLOSE)
		self.set_default_size(600, 300)
		self.uistate.setdefault('windowsize', (600, 500), check=value_is_coord)
		window, textview = ScrolledTextView(''.join(lines), monospace=True)
		self.vbox.add(window)


class VersionsTreeView(SingleClickTreeView):

	# We are on purpose _not_ a subclass of the BrowserTreeView widget
	# because we utilize multiple selection to select versions for diffs

	REV_SORT_COL = 0
	REV_COL = 1
	DATE_COL = 2
	USER_COL = 3
	MSG_COL = 4

	def __init__(self):
		model = gtk.ListStore(str, str, str, str, str)
			# REV_SORT_COL, REV_COL, DATE_COL, USER_COL, MSG_COL
		gtk.TreeView.__init__(self, model)

		self.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		self.set_rubber_banding(True)

		cell_renderer = gtk.CellRendererText()
		for name, i in (
			(_('Rev'), self.REV_COL), # T: Column header versions dialog
			(_('Date'), self.DATE_COL), # T: Column header versions dialog
			(_('Author'), self.USER_COL), # T: Column header versions dialog
		):
			column = gtk.TreeViewColumn(name, cell_renderer, text=i)
			if i == self.REV_COL:
				column.set_sort_column_id(self.REV_SORT_COL)
			else:
				column.set_sort_column_id(i)

			if i == self.DATE_COL:
				column.set_expand(True)

			self.append_column(column)

		model.set_sort_column_id(self.REV_SORT_COL, gtk.SORT_DESCENDING)
			# By default sort by rev

	def load_versions(self, versions):
		model = self.get_model()
		model.clear() # Empty for when we update
		model.set_sort_column_id(self.REV_SORT_COL, gtk.SORT_DESCENDING)
			# By default sort by rev

		for version in versions:
			#~ print version
			key = natural_sort_key(version[0]) # key for REV_SORT_COL
			model.append((key,) + tuple(version))

	def get_versions(self):
		model, rows = self.get_selection().get_selected_rows()
		if len(rows) == 1:
			rev = model[rows[0]][self.REV_COL]
			return (rev,)
		else:
			revs = [model[path][self.REV_COL] for path in rows]
			return (revs[0], revs[-1])
