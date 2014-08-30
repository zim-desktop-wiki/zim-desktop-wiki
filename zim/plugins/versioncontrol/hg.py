# -*- coding: utf-8 -*-

# Copyright 2009-2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# Copyright 2012 Damien Accorsi <damien.accorsi@free.fr>

from __future__ import with_statement

import os
import logging

import xml.etree.ElementTree # needed to compile with cElementTree
import xml.etree.cElementTree as ET


from zim.plugins.versioncontrol import VCSApplicationBase
from zim.applications import Application


logger = logging.getLogger('zim.vcs.hg')


class HGApplicationBackend(VCSApplicationBase):

	@classmethod
	def build_bin_application_instance(cls):
		return Application(('hg', '--noninteractive', '--encoding', 'utf8'), encoding='utf-8')
			# force hg to run in non-interactive mode
			# which will force user name to be auto-setup

	def get_mandatory_params(self):
		return ['--noninteractive'] # force hg to run in non-interactive mode
		                            # which will force user name to be auto-setup

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

	########
	#
	# NOW ARE ALL REVISION CONTROL SYSTEM SHORTCUTS

	def add(self, path=None):
		"""
		Runs: hg add {{PATH}}
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
		return self.pipe(['annotate', file] + revision_args)

	def cat(self, path, version):
		"""
		Runs: hg cat {{PATH}} {{REV_ARGS}}
		"""
		revision_args = self.build_revision_arguments(version)
		return self.pipe(['cat', path] + revision_args)

	def commit(self, path, msg):
		"""
		Runs: hg commit -m {{MSG}} {{PATH}}
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
			hg diff --git {{REVISION_ARGS}}
		or
			hg diff --git {{REVISION_ARGS}} {{PATH}}
		"""
		revision_args = self.build_revision_arguments(versions)
		if path==None:
			return self.pipe(['diff', '--git'] + revision_args)
			# Using --git option allow to show the renaming of files
		else:
			return self.pipe(['diff', '--git', path] + revision_args)

	def ignore(self, file_to_ignore_regexp):
		"""
		Build a .hgignore file including the file_to_ignore_content
		@param file_to_ignore_regexp: str representing the .hgignore file content.
		       this must be a list of regexp defining the file / path to ignore,
		       separated by a\n char
		@returns: nothing
		"""
		#TODO: append the rule instead of overwrite the full content
		self.root.file( '.hgignore' ).write( file_to_ignore_regexp )


	def init_repo(self):
		"""Initialize a new repo
		The init operation consists in:
		- running the VCS init command
		- defining files to ignore
		- adding all other existing files
		@returns: nothing
		"""
		self.init()
		self.ignore('\.zim*$\n')
		self.add('.') # add all existing files

	def repo_exists(self):
		"""Returns True if a repository is already setup, or False

		@returns: a boolean True if a repo is already setup, or False
		"""
		return self.root.subdir('.hg').exists()

	def init(self):
		"""
		Runs: hg init
		"""
		return self.run(['init'])

	def is_modified(self):
		"""Returns true if the repo is not up-to-date, or False
		@returns: True if the repo is not up-to-date, or False
		"""
		# If status return an empty answer, this means the local repo is up-to-date
		return ''.join( self.status() ).strip() != ''

	def log(self, path=None):
		"""
		Runs: hg log --style xml {{PATH}}
		"""
		if path:
			return self.pipe(['log', '--style', 'xml', path])
		else:
			return self.pipe(['log', '--style', 'xml'])

	def log_to_revision_list(self, log_op_output):
		# returns a list of tuple (revision-id, date, user, commit-message)
		versions = []
		xml = ET.fromstring(''.join(log_op_output))
		if not (xml and xml.tag == 'log'):
			raise AssertionError, 'Could not parse log'
		for entry in xml:
			rev = entry.attrib['revision']
			date = entry.findtext('date')
			user = entry.findtext('author')
			msg = entry.findtext('msg')
			versions.append((rev, date, user, msg))

		versions.sort()
		return versions

	def move(self, oldpath, newpath):
		"""
		Runs: hg mv --after {{OLDPATH}} {{NEWPATH}}
		"""
		return self.run(['mv', '--after', oldpath, newpath])

	def remove(self, path):
		"""
		Runs: hg rm {{PATH}}
		"""
		return self.run(['rm', path])

	def revert(self, path, version):
		"""
		Runs:
			hg revert --no-backup {{PATH}} {{REV_ARGS}}
		or
			hg revert --no-backup --all {{REV_ARGS}}
		"""
		revision_params = self.build_revision_arguments(version)
		if path:
			return self.run(['revert', '--no-backup', path] + revision_params)
		else:
			return self.run(['revert', '--no-backup', '--all'] + revision_params)

	def status(self):
		"""
		Runs: hg status
		"""
		return self.pipe(['status'])
