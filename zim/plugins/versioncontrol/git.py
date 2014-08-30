# -*- coding: utf-8 -*-

# Copyright 2009-2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# Copyright 2010,2011 John Drinkwater <john@nextraweb.com>
# Copyright 2012 Damien Accorsi <damien.accorsi@free.fr>

from __future__ import with_statement

import os
import logging

from zim.plugins.versioncontrol import VCSApplicationBase
from zim.applications import Application


logger = logging.getLogger('zim.vcs.git')


class GITApplicationBackend(VCSApplicationBase):

	@classmethod
	def build_bin_application_instance(cls):
		return Application(('git',), encoding='utf-8')

	def build_revision_arguments(self, versions, is_for_diff=False):
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
		if is_for_diff==True:
			if len(versions) == 2:
				versions.reverse()
				return ['..'.join(versions)]
			elif len(versions) == 1:
				return [versions[0] + '^']
			else:
				return []
		else:
			if isinstance(versions, (tuple, list)):
				assert 1 <= len(versions) <= 2
				if len(versions) == 2:
					return map(str, versions)
				else:
					versions = versions[0]

			if not versions is None:
				version = str(versions)
				return [version]
			else:
				return []


	########
	#
	# NOW ARE ALL REVISION CONTROL SYSTEM SHORTCUTS

	def add(self, path=None):
		"""
		Runs: git add {{PATH}}
		"""
		if path is None:
			return self.run(['add', self.notebook_dir])
		else:
			return self.run(['add', path])


	def annotate(self, file, version):
		"""FIXME Document
		return
		0: line1
		2: line1
		...
		"""
		revision_args = self.build_revision_arguments(version)
		return self.pipe(['blame', '-s', file] + revision_args)

	def cat(self, path, version):
		"""
		Runs: git cat {{PATH}} {{REV_ARGS}}
		"""
		revision_args = self.build_revision_arguments(version)
		return self.pipe(['show', ''.join( [ ''.join(revision_args), ':', path.relpath(self.root) ] )])

	def commit(self, path, msg):
		"""
		Runs: git commit -a -m {{MSG}} {{PATH}}
		"""
		if self.is_modified():
			params = ['commit', '-a']
			if msg!='' and msg!=None:
				params.append('-m')
				params.append(msg)
			if path!='' and path!=None:
				params.append('--')
				params.append(path)
			return self.run(params)

	def diff(self, versions, path=None):
		"""
		Runs:
			git diff --no-ext-diff {{REVISION_ARGS}}
		or
			git diff --no-ext-diff {{REVISION_ARGS}} -- {{PATH}}
		"""
		revision_args = self.build_revision_arguments(versions)
		revision_args = self.build_revision_arguments(revision_args, is_for_diff=True)
		if path==None:
			return self.pipe(['diff', '--no-ext-diff'] + revision_args)
		else:
			return self.pipe(['diff', '--no-ext-diff'] + revision_args + ['--', path])

	def ignore(self, file_to_ignore_regexp):
		"""
		Build a .gitignore file including the file_to_ignore_content
		"""
		#TODO: append the rule instead of overwrite the full content
		self.root.file( '.gitignore' ).write( file_to_ignore_regexp )

	def init_repo(self):
		self.init()
		self.ignore(".zim/\n")
		self.add('.') # add all existing files

	def repo_exists(self):
		return self.root.subdir('.git').exists() or self.root.file('.git').exists()

	def init(self):
		"""
		Runs: git init
		"""
		return self.run(['init'])

	def is_modified(self):
		"""Returns true if the repo is not up-to-date, or False
		@returns: True if the repo is not up-to-date, or False
		"""
		# If status return an empty answer, this means the local repo is up-to-date
		status = ''.join( self.pipe(['status', '--porcelain']) )
		return bool(status.strip())

	def log(self, path=None):
		"""
		Runs:
			git log --date=iso --follow {{PATH}}
		or
			git log --date=iso
		"""
		if path:
			return self.pipe(['log', '--date=iso', '--follow', path])
		else:
			return self.pipe(['log', '--date=iso'])

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
			if line.startswith('commit '):
				if not rev is None:
					versions.append((rev, date, user, msg))
				(rev, date, user, msg) = (None, None, None, None)
				seenmsg = False
				rev = line[7:].strip()
			elif line.startswith('Author: '):
				user = line[7:].strip()
			elif line.startswith('Date: '):
				date = line[7:].strip()
				seenmsg = True
				msg = u''
			elif seenmsg and line.startswith(' '):
				msg += line[4:]

		if not rev is None:
			versions.append((rev, date, user, msg))

		versions.reverse()
		return versions


	def move(self, oldpath, newpath):
		"""
		Runs: git mv --after {{OLDPATH}} {{NEWPATH}}
		"""
		return self.run(['mv', '--after', oldpath, newpath])

	def remove(self, path):
		"""
		Runs: git rm {{PATH}}
		"""
		return self.run(['rm', path])

	def revert(self, path, version):
		"""
		Runs:
			hg revert {{PATH}} {{REV_ARGS}}
			is equivalent to
			git checkout {{REV_ARGS}} -- {{PATH}}

		or
			hg revert --no-backup --all {{REV_ARGS}}
			is equivalent to
			git reset --hard HEAD
		"""
		revision_params = self.build_revision_arguments(version)
		if path:
			self.run(['checkout'] + revision_params + ['--', path])
		else:
			self.run(['reset', '--hard', 'HEAD'])

	def stage(self):
		self.run(['add', '-u'])
		self.run(['add', '-A'])

	def status(self, porcelain=False):
		"""
		Runs: git status
		@param porcelain: see --porcelain in git documentation, used for testing
		"""
		if porcelain:
			return self.pipe(['status', '--porcelain'])
		else:
			return self.pipe(['status'])
