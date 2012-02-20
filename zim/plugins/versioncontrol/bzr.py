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

logger = logging.getLogger('zim.vcs.bzr')

# TODO document API - use base class
class BZR(object):
	#FIXME Bin = 'bzr'
	App = Application(('bzr',))
	
	def __init__(self, root):
		self._app = Application(('bzr',))
		self.root = root
		
	@classmethod
	def tryexec(cls):
		return BZR.App.tryexec()
	
	def run(self, params):
		return self._app.run(params, self.root)

	def pipe(self, params):
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
		"""
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

	def _ignored(self, path):
		"""return True if the path should be ignored by the version control system
		"""
		return False


	########
	#
	# NOW ARE ALL REVISION CONTROL SYSTEM SHORTCUTS
	
	def add(self, path=None):
		"""
		Runs: bzr add {{PATH}}
		"""
		if path is None:
			return self.run(['add'])
		else:
			return self.run(['add', path])
		

	def annotate(self, file, version):
		"""FIXME Document
		return
		1 | line1
		2 | line2
		...
		"""
		revision_args = self.build_revision_arguments(version)
		return self.pipe(['annotate', file] + revision_args)

	def cat(self, path, version):
		"""
		Runs: bzr cat {{PATH}} {{REV_ARGS}}
		"""
		revision_args = self.build_revision_arguments(version)
		return self.pipe(['cat', path] + revision_args)

	def commit(self, path, msg):
		"""
		Runs: bzr commit -m {{MSG}} {{PATH}}
		"""
		params = ['commit']
		if msg!='' and msg!=None:
			params.append('-m')
			params.append(msg)
		if path!='' and path!=None:
			params.append(path)
		return self.run(params)
			
	def diff(self, versions, path=None):
		"""
		Runs:
			bzr diff {{REVISION_ARGS}} 
		or
			bzr diff {{REVISION_ARGS}} {{PATH}}
		"""
		revision_args = self.build_revision_arguments(versions)
		if path==None:
			return self.pipe(['diff'] + revision_args)
			# Using --git option allow to show the renaming of files
		else:
			return self.pipe(['diff', path] + revision_args)

	def ignore(self, file_to_ignore_regexp):
		"""
		Build a .bzrignore file including the file_to_ignore_content
		"""
		return self.run(['ignore', file_to_ignore_regexp])


	def init_repo(self, lock_object):
		if self.repo_exists()==False:
			with lock_object:
				self.init()
			#self.whoami('zim') # set a dummy user "zim"
			self.ignore('**/.zim/')
			with lock_object:
				self.add('.')

	def repo_exists(self):
		return self.root.subdir('.bzr').exists()

	def init(self):
		"""
		Runs: bzr init
		"""
		return self.run(['init'])

	def log(self, path=None):
		"""
		Runs: bzr log --forward {{PATH}}
		the "--forward" option allows to reverse order
		"""
		if path:
			return self.pipe(['log', '--forward', path])
		else:
			return self.pipe(['log', '--forward'])

	def log_to_revision_list(self, log_op_output):
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
		for line in log_op_output:
			if line.startswith('----'):
				if not rev is None:
					versions.append((rev, date, user, msg))
				(rev, date, user, msg) = (None, None, None, None)
			elif line.startswith('revno: '):
				value = line[7:].strip()
				if ' ' in value:
					# e.g. "revno: 48 [merge]\n"
					i = value.index(' ')
					value = value[:i]
				rev = int(value)
			elif line.startswith('committer: '):
				user = line[11:].strip()
			elif line.startswith('timestamp: '):
				date = line[11:].strip()
			elif line.startswith('message:'):
				seenmsg = True
				msg = u''
			elif seenmsg and line.startswith('  '):
				msg += line[2:]

		if not rev is None:
			versions.append((rev, date, user, msg))

		return versions


	def move(self, oldpath, newpath):
		"""
		Runs: bzr mv --after {{OLDPATH}} {{NEWPATH}}
		"""
		self.run(['add', '--no-recurse', newpath.dir])
		return self.run(['mv', oldpath, newpath])


	def remove(self, path):
		"""
		Runs: bzr rm {{PATH}}
		"""
		return self.run(['rm', path])

	def revert(self, path, version):
		"""
		Runs:
			bzr revert {{PATH}} {{REV_ARGS}}
		or
			bzr revert {{REV_ARGS}}
		"""
		revision_params = self.build_revision_arguments(version)
		if path:
			return self.run(['revert', path] + revision_params)
		else:
			return self.run(['revert'] + revision_params)

	def stage(self):
		# Generic interface required by Git.
		pass
		
	def status(self):
		"""
		Runs: bzr status
		"""
		return self.pipe(['status'])

	def whoami(self, user):
		"""
		Runs: bzr whoami zim
		"""
		return self.pipe(['whoami', user])



class BazaarVCS(VersionControlSystemBackend):
	
	def __init__(self, dir):
		vcs_app = BZR(dir)
		super(BazaarVCS, self).__init__(dir, vcs_app)

	@classmethod
	def _check_dependencies(klass):
		"""@see VersionControlSystemBackend.check_dependencies"""
		return BZR.tryexec()

