# -*- coding: utf-8 -*-

# Copyright 2009-2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# Copyright 2012 Damien Accorsi <damien.accorsi@free.fr>

from __future__ import with_statement

import os
import re
import logging

from zim.plugins.versioncontrol import VCSApplicationBase
from zim.applications import Application


logger = logging.getLogger('zim.vcs.fossil')

RE_Date = re.compile(r"===\s*([0-9]+-[0-9]+-[0-9]+)\s*===")
# 23:03:33 [8cf3ffde61] *MERGE* *BRANCH* Stas Bushuev wrote this message. (user: Xitsa tags: trunk)
RE_LogRecord = re.compile(r"([0-9:-]+)\s*\[([0-9a-fA-F]+)\]\s*(\*\S+\* *)*(.*)\((.*)\)")
RE_Tag = re.compile(r"(?:,\s*)?(\S+:)")
RE_Time = re.compile(r"[0-9][0-9]:[0-9][0-9]:[0-9][0-9]")

class FOSSILApplicationBackend(VCSApplicationBase):

	@classmethod
	def build_bin_application_instance(cls):
		return Application(('fossil',))

	def build_revision_arguments(self, versions):
		"""Build a list including required string/int for running an VCS command
		# Accepts: None, int, string, (string,), (string, string)
		# Always returns a list
		# versions content:
		  - None: return an empty list
		  - string: return ['--from', int]
		  - tuple or list: return ['--from', from, '--to', to]

		It's all based on the fact that defining revision with current VCS is:
		--from revision
		--from rev1 --to rev2
		"""
		if isinstance(versions, (tuple, list)):
			assert 1 <= len(versions) <= 2
			if len(versions) == 2:
				return ['-r', versions[0], '--to', versions[1]]
			else:
				return ['-r', versions[0]]
		if versions is None:
			return []
		return ['-r', versions]

	########
	#
	# NOW ARE ALL REVISION CONTROL SYSTEM SHORTCUTS

	def add(self, path=None):
		"""
		Runs: fossil add {{PATH}}
		"""
		if path is None:
			return self.run(['addremove', self.notebook_dir])
		else:
			return self.run(['add', path])


	def annotate(self, file, version):
		"""FIXME Document
		return
		0: line1
		2: line1
		...
		"""
		# Annotate doesn't take a version
		return self.pipe(['annotate', file])

	def cat(self, path, version):
		"""
		Runs: fossil cat {{PATH}} {{REV_ARGS}}
		"""
		revision_args = self.build_revision_arguments(version)
		return self.pipe(['cat', path] + revision_args)

	def commit(self, path, msg):
		"""
		Runs: fossil commit -m {{MSG}} {{PATH}}
		"""
		params = ['commit']
		if msg!='' and msg!=None:
			params.append('-m')
			params.append(msg)
		# To minimize interaction
		params.append('--no-warnings')
		if path!='' and path!=None:
			params.append(path)
		return self.run(params)

	def diff(self, versions, path=None):
		"""
		Runs:
			fossil diff {{REVISION_ARGS}}
		or
			fossil diff {{REVISION_ARGS}} {{PATH}}
		"""
		revision_args = self.build_revision_arguments(versions)
		if path==None:
			return self.pipe(['diff'] + revision_args)
			# Using --git option allow to show the renaming of files
		else:
			return self.pipe(['diff'] + revision_args + [path])

	def ignore(self, file_to_ignore_regexp):
		"""
		Configure settings for files to ignore
		@param file_to_ignore_regexp: str representing the ignore-glob content.
		       this must be a list of regexp defining the file / path to ignore,
		       separated by a comma.
		@returns: nothing
		"""
		return self.run(['settings', 'ignore-glob', file_to_ignore_regexp])


	def init_repo(self):
		"""Initialize a new repo
		The init operation consists in:
		- running the VCS init command
		- defining files to ignore
		- adding all other existing files
		@returns: nothing
		"""
		self.init()
		self.ignore('\.zim*/*,notebook.fossil')
		self.add('.') # add all existing files

	def repo_exists(self):
		"""Returns True if a repository is already setup, or False

		@returns: a boolean True if a repo is already setup, or False
		"""
		return self.root.file('.fslckout').exists() or self.root.file('_FOSSIL_').exists()

	def init(self):
		"""
		Runs: fossil init
		Usually, the repository is located in some other place than
		checkout folder, but we put it in the notepad folder and then checkout it.
		"""
		infolder_repo = self.root.file('notebook.fossil')
		self.run(['init', infolder_repo])
		return self.checkout(infolder_repo)

	def checkout(self, file):
		# Create working folder
		return self.run(['open', file])

	def is_modified(self):
		"""Returns true if the repo is not up-to-date, or False
		@returns: True if the repo is not up-to-date, or False
		"""
		# If status return an empty answer, this means the local repo is up-to-date
		return ''.join( self.status() ).strip() != ''

	def log(self, path=None):
		"""
		Runs: fossil timeline --type ci {{PATH}}
		"--type ci" option for file commits only
		"""
		options = ['--limit', '1000']
		if not path is None:
			return self.pipe(['finfo'] + options + [path])
		return self.pipe(['timeline', '--type', 'ci'] + options)

	def log_to_revision_list(self, log_op_output):
		# returns a list of tuple (revision-id, date, user, commit-message)

		def ExtractUserName(line):
			tags = RE_Tag.split(line)
			if len(tags) > 2:
				if tags[1] == "user:":
					return tags[2].strip()
			return ""
		def CombineDateTime(CurDate, TimeOrDate):
			if RE_Time.match(TimeOrDate):
				return CurDate + " " + TimeOrDate
			return TimeOrDate

		versions = []
		CurDate = ""
		for line in log_op_output:
			(rev, date, user, msg) = (None, None, None, None)
			DateMatch = RE_Date.search(line)
			if DateMatch:
				CurDate = DateMatch.group(1)
			else:
				RecordMatch = RE_LogRecord.search(line)
				if RecordMatch:
					date = CombineDateTime(CurDate, RecordMatch.group(1))
					rev = RecordMatch.group(2)
					msg = RecordMatch.group(4)
					user = ExtractUserName(RecordMatch.group(5))
					versions.append((rev, date, user, msg))
		return versions

	def move(self, oldpath, newpath):
		"""
		Runs: fossil mv {{OLDPATH}} {{NEWPATH}}
		"""
		return self.run(['mv', oldpath, newpath])

	def remove(self, path):
		"""
		Runs: fossil rm {{PATH}}
		"""
		return self.run(['rm', path])

	def revert(self, path, version):
		"""
		Runs:
			fossil revert {{PATH}} {{REV_ARGS}}
		or
			fossil revert {{REV_ARGS}}
		"""
		revision_params = self.build_revision_arguments(version)
		if path:
			return self.run(['revert', path] + revision_params)
		else:
			return self.run(['revert'] + revision_params)

	def status(self):
		"""
		Runs: fossil changes
		"""
		return self.pipe(['changes'])
