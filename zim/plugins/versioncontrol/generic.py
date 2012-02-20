# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from __future__ import with_statement

import os
import logging

from zim.fs import FS
from zim.applications import Application
from zim.async import AsyncOperation
#from zim.plugins.versioncontrol import NoChangesError, TEST_MODE
from zim.plugins.versioncontrol import NoChangesError

if os.environ.get('ZIM_TEST_RUNNING'):
	TEST_MODE = True
else:
	TEST_MODE = False

logger = logging.getLogger('zim.vcs.generic')

class VCSApplication(object):
	"""
		This class will implement the part of the algorithm which is specific
		to a version control system.
		
		This means especially the commands/options to execute, but also the way,
		for example to initialize a repository.
		
		This class is abstract and should be inherited
	"""

	def __init__(self, root):
		"""Constructor.
		
		@param root: a L{Dir} instance representing the notebook root folder
		@implementation: must be implemented by sub classes. \
		Parent constructor must be called
		"""
		self._app = self.build_bin_application_instance()
		self.root = root
	
	@classmethod
	def build_bin_application_instance(cls):
		"""return the command to run for each command.
		@returns: str() representing the command to execute
		@implementation: must be implemented in child classes. \
		                 examples:
		                 - returns "hg" for mercurial
		                 - returns "bzr" for bazaar
		                 - returns "git" for git
		"""
		raise NotImplementedError
	
	@classmethod
	def tryexec(cls):
		"""FIXME Document"""
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

	def build_revision_arguments(self, versions):
		"""Build a list including required string/int for running an VCS command
		# Accepts: None, int, string, (int,), (int, int)
		# Always returns a list
		# versions content:
		  - None: return an empty list
		  - int ou string: return ['-r', int]
		  - tuple or list: return ['-r', '%i..%i']
		  
		It's all based on the fact that defining revision with current VCS is:
		-r revision
		-r rev1..rev2
		
		@param versions: a None, int, string, (int,), (int, int) representing \
		                 one or two revision ids
		@returns: a list of str() representing the parameters to add to the execution
		@implementation: must be overriden by child classes \
		(this is the case for example for the git support)
		"""
		raise NotImplementedError

	def _ignored(self, file):
		"""return True if the file should be ignored by the version control system
		@param: a L{File} representing the file that we want to know if it should be ignored
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
		@return $C{True} if the command was successfull
		
		Exemple: for Mercurial, the implementation will run "hg add <file>" or
		"hg add" if file=None (meaning the entire repository
		
		@implementation: must be overridden by child classes
		"""
		raise NotImplementedError
		
	def annotate(self, file, version):
		"""return the annotated version of a file. This is commonly related
		to the VCS command annotate
		
		@param file: a L{File} instance representing the file
		@version: a  None/int/str representing the revision of the file
		@returns: a list of lines representing the command result output
		
		Eg. for mercurial, it will return something like:
		  0: line1
		  2: line1
		  ...
		
		@implementation: must be implemented in child classes
		"""
		raise NotImplementedError

	def cat(self, file, version):
		"""
		FIXME
		Runs: hg cat {{PATH}} {{REV_ARGS}}
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


	def init_repo(self, lock_object):
		"""initialize a repository in the associated folder.
		@params lock_object: is the instance of $L{FSSingletonClass}
		@returns: nothing.
		
		@implementation: must be implemented in the child class. \
		                 the lock_object will be used for running commands, \
		                 like for example the  init command : \
		                   with lock_object: \
		                   	 self.init() \
		                 \
		                 The lock should not be used for creating the ignore \
		                 file for example, because the L{File} class already
		                 use a lock (so you'd end with a dead-lock) \
		                 \
		                 Note: the implementation should take care of the fact \
		                 that maybe the init() operation would fail if the repo \
		                 already exist. This may be tested by a call \
		                 to the repo_exists() method. \
		                 \
		                 Note2: The init should also add all existing items. \
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
		return self.run(['init'])

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
		  
		@implementation: must be implemented in child class
		"""
		raise NotImplementedError
		
	def status(self):
		"""Returns the status of the repository
		@returns: a list of str() representing the output of a "status" command
		related to the repository
		@implementation: must be implemented in child classes
		"""
		raise NotImplementedError

class VersionControlSystemBackend(object):
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
		"""
		"""Initialize the instance in normal or test mode
		- in case of TEST_MODE off, it checks the file system
		  for creation, move or delete of files
		- in case of TEST_MODE on, it does not check anything
		  in order to avoid to interfer with dev environment

		@param dir: a L{Dir} object representing the repository working directory path
		"""
		self._root = dir
		self._lock = FS.get_async_lock(self._root)
		self._app  = vcs_specific_app
		if not TEST_MODE:
			# Avoid touching the bazaar repository with zim sources
			# when we write to tests/tmp etc.
			FS.connect('path-created', self.on_path_created)
			FS.connect('path-moved', self.on_path_moved)
			FS.connect('path-deleted', self.on_path_deleted)

	# TODO: disconnect method - callbacks keep object alive even when plugin is disabled !

	@property
	def vcs(self):
		return self._app

	@property
	def root(self):
		return self._root

	@property
	def lock(self):
		return self._lock


	@classmethod
	def check_dependencies(klass):
		"""Checks the VCS dependencies.
		
		@returns: True in case of success (eg. : in case of Bazaar, the check consists in running the 'bzr' command) or False
		"""
		return klass._check_dependencies()

	@classmethod
	def _check_dependencies(klass):
		raise NotImplementedError

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
		if not self.root.exists():
			self.root.touch()

		self.vcs.init_repo(self.lock)

	def on_path_created(self, fs, path):
		"""Callback to add a new file or folder when added to the wiki
		Note: the VCS operation is asynchronous
		
		@param fs: the L{FSSingletonClass} instance representing the file system
		@param path: the L{UnixFile} object representing the newly created file or folder
		@returns: nothing
		"""
		if path.ischild(self.root) and not self._ignored(path):
			def wrapper():
				self.vcs.add(path)
			AsyncOperation(wrapper, lock=self.lock).start()


	def on_path_moved(self, fs, oldpath, newpath):
		"""Callback to move the file in Bazaar when moved in the wiki
		Note: the VCS operation is asynchronous
		
		@param fs: the L{FSSingletonClass} instance representing the file system
		@param oldpath: the L{UnixFile} object representing the old path of the file or folder
		@param newpath: the L{UnixFile} object representing the new path of the file or folder
		@returns: nothing
		"""
		if newpath.ischild(self.root) and not self._ignored(newpath):
			def wrapper():
				if oldpath.ischild(self.root):
					# Parent of newpath needs to be versioned in order to make mv succeed
					self.vcs.move(oldpath, newpath)
				else:
					self.vcs.add(newpath)
			AsyncOperation(wrapper, lock=self.lock).start()
		elif oldpath.ischild(self.root) and not self._ignored(oldpath):
			self.on_path_deleted(self, fs, oldpath)
		
	def on_path_deleted(self, path):
		"""Callback to remove a file from Bazaar when deleted from the wiki
		Note: the VCS operation is asynchronous
		
		@param path: the L{UnixFile} object representing the path of the file or folder to delete
		@returns: nothing
		"""
		def wrapper():
			self.vcs.remove(path)
		AsyncOperation(wrapper, lock=self.lock).start()


	@property
	def modified(self):
		"""return True if changes are detected, or False"""
		return ''.join( self.get_status() ).strip() != ''
		with self.lock:
			return self.vcs.is_modified()

	def get_status(self):
		"""Returns repo status as a list of text lines
		
		@returns: list of text lines (like a shell command result)
		"""
		status = list()
		with self.lock:
			status = self.vcs.status()
		return status
		
	def get_diff(self, versions=None, file=None):
		"""Returns the diff operation result of a repo or file
		@param versions: couple of version numbers (integer)
		@param file: L{UnixFile} object of the file to check, or None
		@returns the diff result
		"""
		with self.lock:
			nc = ['=== No Changes\n']
			diff = self.vcs.diff(versions, file) or nc
		return diff

	def get_annotated(self, file, version=None):
		"""Returns the annotated version of a file
		@param file: L{UnixFile} object of the file to check, or None
		@param version: required version number (integer) or None
		@returns the annotated version of the file result
		"""
		with self.lock:
			annotated = self.vcs.annotate(file, version)
		return annotated

	def commit(self, msg):
		"""Run a commit operation.
		
		@param msg: commit message (str)
		@returns nothing
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

	def commit_async(self, msg, callback=None, data=None):
		# TODO in generic baseclass have this default to using
		# commit() + the wrapper call the callback
		#~ print '!! ASYNC COMMIT'
		operation = AsyncOperation(self._commit, (msg,),
			lock=self._lock, callback=callback, data=data)
		operation.start()

	def revert(self, version=None, file=None):
		with self.lock:
			self.vcs.revert(file, version)


	def list_versions(self, file=None):
		"""Returns a list of all versions, for a file or for the entire repo
		
		@param file: a L{UnixFile} object representing the path to the file, or None
		@returns a list of tuples (revision (int), date, user (str), msg (str))
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

