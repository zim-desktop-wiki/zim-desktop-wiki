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

