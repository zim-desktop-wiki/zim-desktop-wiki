# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from __future__ import with_statement

import os
import logging

from zim.fs import FS
from zim.applications import Application
from zim.async import AsyncOperation
from zim.plugins.versioncontrol import NoChangesError, TEST_MODE

logger = logging.getLogger('zim.vcs.generic')

class VersionControlSystemBackend(object):
	"""Parent class for all VCS backend implementations.
	It implements the required API.
	"""
	def __init__(self, dir):
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
		print "LOCK", self._lock, self.lock
		print "ROOT", self._root, self.root
		print "TEST MODE ?", TEST_MODE
		# FIXME - The following test should be executed
		# if not TEST_MODE:
		if True: #FIXME 
			# Avoid touching the bazaar repository with zim sources
			# when we write to tests/tmp etc.
			FS.connect('path-created', self.on_path_created)
			FS.connect('path-moved', self.on_path_moved)
			FS.connect('path-deleted', self.on_path_deleted)

	# TODO: disconnect method - callbacks keep object alive even when plugin is disabled !

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
		return klass._vcs_specific_check_dependencies()

	@classmethod
	def _vcs_specific_check_dependencies(klass):
		raise NotImplementedError

	def _ignored(self, path):
		"""Return True if we should ignore this path
		TODO add specific ignore patterns in the _ignored_vcs_specific method
		for now we just hardcode zim specific logic
		
		@param path: a L{UnixFile} object representing the file path to check
		@returns: True if the path should be ignored or False
		"""
		return '.zim' in path.split() or self._vcs_specific_ignored(path)

	def _vcs_specific_ignored(self, path):
		"""similar to _ignored except that this must be implemented in child class
		
		If you don't want to ignore specific files,
		then implement this method always returning False
		"""
		raise NotImplementedError

	def init(self):
		"""Initialize a Bazaar repository in the self.root directory.
		If the directory does not exist, then create it
		@returns: nothing
		"""
		if not self.root.exists():
			self.root.touch()

		with self.lock:
			self._vcs_specific_init()

	def _vcs_specific_init(self):
		"""Implements init operations specific the the concrete VCS.
		Eg: with bzr, it will run a "bzr init" command, etc
		
		Note: this methond is called through a "with self.lock()"
		"""
		raise NotImplementedError


	def on_path_created(self, fs, path):
		"""Callback to add a new file or folder when added to the wiki
		Note: the VCS operation is asynchronous
		
		@param fs: the L{FSSingletonClass} instance representing the file system
		@param path: the L{UnixFile} object representing the newly created file or folder
		@returns: nothing
		"""
		print "CREATED:", path
		self._vcs_specific_on_path_created(fs, path)

	def _vcs_specific_on_path_created(self, fs, path):
		raise NotImplementedError


	def on_path_moved(self, fs, oldpath, newpath):
		"""Callback to move the file in Bazaar when moved in the wiki
		Note: the VCS operation is asynchronous
		
		@param fs: the L{FSSingletonClass} instance representing the file system
		@param oldpath: the L{UnixFile} object representing the old path of the file or folder
		@param newpath: the L{UnixFile} object representing the new path of the file or folder
		@returns: nothing
		"""
		print "MOVED:", oldpath, newpath
		self._vcs_specific_on_path_moved(fs, oldpath, newpath)
		
	def _vcs_specific_on_path_moved(self, fs, oldpath, newpath):
		raise NotImplementedError

	def on_path_deleted(self, path):
		"""Callback to remove a file from Bazaar when deleted from the wiki
		Note: the VCS operation is asynchronous
		
		@param path: the L{UnixFile} object representing the path of the file or folder to delete
		@returns: nothing
		"""
		self._vcs_specific_on_path_deleted(path)

	def _vcs_specific_on_path_deleted(self, path):
		raise NotImplementedError


	@property
	def modified(self):
		"""return True if changes are detected, or False"""
		return ''.join( self.get_status() ).strip() != ''

	def get_status(self):
		"""Returns last operation status as a list of text lines
		
		Note: the status content is really get through the
		_vcs_specific_get_status() method which is called through a "with self.lock"
		
		@returns: list of text lines (like a shell command result)
		"""
		status = list()
		with self.lock:
			status = self._vcs_specific_get_status()
		return status
		
	def _vcs_specific_get_status(self):
		raise NotImplementedError
		
	def get_diff(self, versions=None, file=None):
		"""Returns the diff operation result of a repo or file
		@param versions: couple of version numbers (integer)
		@param file: L{UnixFile} object of the file to check, or None
		@returns the diff result
		"""
		print "VERSIONS", versions, versions.__class__
		print "FILE", file, file.__class__
		with self.lock:
			diff = self._vcs_specific_get_diff(versions, file)
		return diff

	def get_annotated(self, file, version=None):
		"""Returns the annotated version of a file
		@param file: L{UnixFile} object of the file to check, or None
		@param version: required version number (integer) or None
		@returns the annotated version of the file result
		"""
		with self.lock:
			annotated = self._vcs_specific_get_annotated(file, version)
		return annotated

	def _vcs_specific_get_annotated(self, file, version=None):
		raise NotImplementedError

	def commit(self, msg):
		"""Run a commit operation.
		
		@param msg: commit message (str)
		@returns nothing
		"""
		with self.lock:
			self._vcs_specific_commit(msg)

	def commit_async(self, msg, callback=None, data=None):
		# TODO in generic baseclass have this default to using
		# commit() + the wrapper call the callback
		#~ print '!! ASYNC COMMIT'
		operation = AsyncOperation(self._vcs_specific_commit, (msg,),
			lock=self._lock, callback=callback, data=data)
		operation.start()

	def _vcs_specific_commit(self, msg):
		"""FIXME Document this"""
		raise NotImplementedError

	def revert(self, version=None, file=None):
		with self.lock:
			self._vcs_specific_revert(version, file)

	def _vcs_specific_revert(version=None, file=None):
		"""FIXME Document this"""
		raise NotImplementedError


	def list_versions(self, file=None):
		"""Returns a list of all versions, for a file or for the entire repo
		
		@param file: a L{UnixFile} object representing the path to the file, or None
		@returns a list of tuples (revision (int), date, user (str), msg (str))
		"""
		# TODO see if we can get this directly from bzrlib as well
		with self.lock:
			versions = self._vcs_specific_list_versions(file)
		return versions
	
	def _vcs_specific_list_versions(self, file=None):
		"""FIXME Document"""
		raise NotImplementedError

	def get_version(self, file, version):
		"""FIXME Document"""
		with self.lock:
			version = self._vcs_specifc_get_version(file, version)
		return version

