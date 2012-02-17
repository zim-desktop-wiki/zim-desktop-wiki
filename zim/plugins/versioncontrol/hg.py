# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from __future__ import with_statement

import os
import logging

from zim.fs import FS
from zim.applications import Application
from zim.async import AsyncOperation
from zim.plugins.versioncontrol import NoChangesError
from zim.plugins.versioncontrol.generic import VersionControlSystemBackend

logger = logging.getLogger('zim.vcs.hg')

# TODO document API - use base class
class HG(object):
	App = Application(('hg',))

class MercurialVCS(VersionControlSystemBackend):
	
	def __init__(self, dir):
		super(MercurialVCS, self).__init__(dir)


	@classmethod
	def _vcs_specific_check_dependencies(klass):
		"""@see VersionControlSystemBackend.check_dependencies"""
		return HG.App.tryexec()

	def _vcs_specific_ignored(self, path):
		"""Return True if we should ignore this path
		TODO add bzrignore patterns here

		@see VersionControlSystemBackend._vcs_specific_ignored
		     and VersionControlSystemBackend._ignored
		"""
		return False

	def _vcs_specific_init(self):
		"""Init a repository, here are operations specific to the VCS
		@see VersionControlSystemBackend._vcs_specific_init()
		"""
		print "agaga", self.root
		HG.App.run(['init'], cwd=self.root)
		# Mercurial has no option to tell to ignore some files,
		# so we have to tell it by writting a .hgignore file
		# at the repo root
		hgignore_filepath = os.path.join(self.root.__str__(), '.hgignore')
		hgignore_fh = open(hgignore_filepath, 'w')
		hgignore_fh.write('\.zim*$\n')
		hgignore_fh.close()
		HG.App.run(['add', '.'], cwd=self.root) # add all existing files

	def _vcs_specific_on_path_created(self, fs, path):
		"""@see VersionControlSystemBackend.on_path_created"""
		if path.ischild(self.root) and not self._ignored(path):
				def wrapper():
					HG.App.run(['add', path], cwd=self.root)
				AsyncOperation(wrapper, lock=self.lock).start()

	def _vcs_specific_on_path_moved(self, fs, oldpath, newpath):
		"""@see VersionControlSystemBackend.on_path_moved"""
		if newpath.ischild(self.root) and not self._ignored(newpath):
			def wrapper():
				if oldpath.ischild(self.root):
					# Parent of newpath needs to be versioned in order to make mv succeed
					HG.App.run(['mv', '--after', oldpath, newpath], cwd=self.root) # --after tells that the operation has already been done on the file system
				else:
					HG.App.run(['add', newpath], cwd=self.root)
			AsyncOperation(wrapper, lock=self.lock).start()
		elif oldpath.ischild(self.root) and not self._ignored(oldpath):
			self.on_path_deleted(self, fs, oldpath)


	def _vcs_specific_on_path_deleted(self, path):
		"""@see VersionControlSystemBackend.on_path_deleted"""
		def wrapper():
			HG.App.run(['rm', path], cwd=self.root)
		AsyncOperation(wrapper, lock=self.lock).start()
		
	def _vcs_specific_get_status(self):
		"""Returns last operation status as a list of text lines
		@see VersionControlSystemBackend._vcs_specific_get_status()
		     and VersionControlSystemBackend.get_status()
		"""
		return HG.App.pipe(['status'], cwd=self.root)


	def _vcs_specific_get_diff(self, versions=None, file=None):
		"""FIXME Document this
		Returns the diff operation result of a repo or file
		@param versions: couple of version numbers (integer)
		@param file: L{UnixFile} object of the file to check, or None
		@returns the diff result
		"""
		diff = None
		rev = self._revision_arg(versions)
		print "REVISION STRING", rev
		nc = ['=== No Changes\n']
		if file is None:
			diff = HG.App.pipe(['diff', '--git'] + rev, cwd=self.root) or nc
			# Using --git option allow to show the renaming of files
		else:
			diff = HG.App.pipe(['diff', '--git', file] + rev, cwd=self.root) or nc
		return diff

	def _vcs_specific_get_annotated(self, file, version=None):
		"""FIXME Document
		return
		0: line1
		2: line1
		...
		"""
		rev = self._revision_arg(version)
		annotated = HG.App.pipe(['annotate', file] + rev, cwd=self.root)
		return annotated

	def _vcs_specific_commit(self, msg):
		stat = ''.join( HG.App.pipe(['st'], cwd=self.root) ).strip()
		if not stat:
			raise NoChangesError(self.root)
		else:
			HG.App.run(['add'], cwd=self.root)
			HG.App.run(['commit', '-m', msg], cwd=self.root)

	def _vcs_specific_revert(self, version=None, file=None):
		"""FIXME Document this"""
		rev = self._revision_arg(version)
		if file is None:
			HG.App.run(['revert', '--no-backup', '--all'] + rev, cwd=self.root)
		else:
			HG.App.run(['revert', '--no-backup', file] + rev, cwd=self.root)
	

	def _vcs_specific_list_versions(self, file=None):
		"""FIXME Document"""
		# TODO see if we can get this directly from bzrlib as well
		if file is None:
			lines = HG.App.pipe(['log', '-r', ':', '--verbose'], cwd=self.root)
			# --verbose show complete commit message
			# -r : will reverse the history order
		else:
			lines = HG.App.pipe(['log', '-r', ':', '--verbose', file], cwd=self.root)

		versions = []
		(rev, date, user, msg) = (None, None, None, None)
		seenmsg = False
		# seenmsg allow to get the complete commit message which is presented like this:
		#
		# [...]
		# description:
		# here is the
		# commit message
		# the end of it may be detected
		# because of the apparition of a line
		# starting by "changeset:"
		#
		# FIXME: there is a bug which will stop parsing if a blank line is included
		# in the commit message
		for line in lines:
			if len(line.strip())==0:
				if not rev is None:
					versions.append((rev, date, user, msg))
				(rev, date, user, msg) = (None, None, None, None)
				seenmsg = False
			elif line.startswith('changeset: '):
				logger.info("LINE IS #%s#" % line)
				value = line[13:].strip()
				logger.info("THE REV. IS #%s#" % value)
				# In case of mercurial, the revision number line
				# is something like this:
				# changeset:   6:1d4a428e22d9
				#
				# instead of (for bzr) like that:
				# e.g. "revno: 48 [merge]\n"
				value = value.split(":")[0]
				rev = int(value)
			elif line.startswith('user: '):
				user = line[13:].strip()
			elif line.startswith('date: '):
				date = line[13:].strip()
			elif line.startswith('description:'):
				seenmsg = True
				msg = u''
			elif seenmsg:
				msg += line

		if not rev is None:
			versions.append((rev, date, user, msg))

		return versions

	def _vcs_specifc_get_version(self, file, version):
		rev = self._revision_arg(version)
		version = HG.App.pipe(['cat', file] + rev, cwd=self.root)
		return version

	def _revision_arg(self, versions):
		# Accepts: None, int, string, (int,), (int, int)
		# Always returns a list

		if isinstance(versions, (tuple, list)):
			assert 1 <= len(versions) <= 2
			if len(versions) == 2:
				versions = map(int, versions)
				versions.sort()
				return ['-r', '%i..%i' % tuple(versions)]
			else:
				versions = versions[0]

		if not versions is None:
			version = int(versions)
			return ['-r', '%i' % version]
		else:
			return []
			
