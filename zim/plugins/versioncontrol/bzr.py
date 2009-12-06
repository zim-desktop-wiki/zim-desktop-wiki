# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import os
import logging

from zim.fs import FS
from zim.applications import Application

logger = logging.getLogger('zim.vcs.bzr')
# TODO check if bzrlib also uses logging for output

try:
    import bzrlib.commands as bzrlib
except ImportError:
	logger.warn('Could not load bzrlib - falling back to calling bzr as external program')
	bzrlib = None


class BzrlibApplication(Application):
	'''This class is a wrapper around the bzrlib library which supports the same
	API as an Application object for an external application. It gives command
	arguments directly to the library to handle instead of actually spawning a
	process to call the executable.

	Falling back to using "Application(('bzr',))" instead should give the exact
	same results. 
	''' 

	def __init__(self):
		Application.__init__(self, ('bzr',))

	def run(self, args, cwd=None):
		if bzrlib:
			cwd = unicode(cwd).encode('utf-8')
			self._bzrlib(args, cwd)
		else:
			Application.run(self, cwd=cwd)

	# TODO find out how to implement pipe() using bzrlib

	def _bzrlib(self, args, cwd):
		ourcwd = os.getcwdu()
		os.chdir(cwd)
		try:
			args = [unicode(a).encode('utf-8') for a in args]
			args.insert(1, '-q') # --quiet
			logger.info('Running through bzrlib: %s', args)
			#~ bzrlib.run_bzr(args)
			bzrlib.main([None] + args)
		except:
			logger.exception('Error thrown by bzrlib')
		os.chdir(ourcwd)


if bzrlib:
    _bzr = BzrlibApplication()
else:
    _bzr = Application(('bzr',))


# TODO document API - use base class

class BazaarVCS(object):

	def __init__(self, dir):
		self.root = dir
		FS.connect('path-created', self.on_path_created)
		FS.connect('path-moved', self.on_path_moved)

	@classmethod
	def check_dependencies(klass):
		return _bzr.tryexec()

	def _ignored(self, path):
		# Return True if we should ignore this path
		# TODO add bzrignore patterns here
		# for now we just hardcode zim specific logic
		return '.zim' in path.split()

	def init(self):
		if not self.root.exists():
			self.root.touch()
		_bzr.run(['init'], cwd=self.root)
		_bzr.run(['ignore', '**/.zim/'], cwd=self.root) # ignore cache
		_bzr.run(['add', '.'], cwd=self.root) # add all existing files

	def on_path_created(self, fs, path):
		if path.ischild(self.root) and not self._ignored(path):
			_bzr.run(['add', path], cwd=self.root)

	def on_path_moved(self, fs, oldpath, newpath):
		if newpath.ischild(self.root) and not self._ignored(newpath):
			if oldpath.ischild(self.root):
				# Parent of newpath needs to be versioned in order to make mv succeed
				_bzr.run(['add', '--no-recurse', newpath.dir], cwd=self.root)
				_bzr.run(['mv', oldpath, newpath], cwd=self.root)
			else:
				_bzr.run(['add', newpath], cwd=self.root)
		# if only oldpath is ours, it is now deleted - don't need to do anything

	@property
	def modified(self):
		return ''.join( self.get_status() ).strip() != ''

	def get_status(self):
		return _bzr.pipe(['status'], cwd=self.root)

	def get_diff(self, versions=None, file=None):
		rev = self._revision_arg(versions)
		nc = ['=== No Changes\n']
		if file is None:
			return _bzr.pipe(['diff'] + rev, cwd=self.root) or nc
		else:
			return _bzr.pipe(['diff', file] + rev, cwd=self.root) or nc

	def get_annotated(self, file, version=None):
		rev = self._revision_arg(version)
		return _bzr.pipe(['annotate', file] + rev, cwd=self.root)

	def commit(self, msg):
		_bzr.run(['add'], cwd=self.root)
		_bzr.run(['commit', '-m', msg], cwd=self.root)

	def revert(self, version=None, file=None):
		rev = self._revision_arg(version)
		if file is None:
			_bzr.run(['revert'] + rev, cwd=self.root)
		else:
			_bzr.run(['revert', file] + rev, cwd=self.root)

	def list_versions(self, file=None):
		# TODO see if we can get this directly from bzrlib as well
		if file is None:
			lines = _bzr.pipe(['log', '--forward'], cwd=self.root)
		else:
			lines = _bzr.pipe(['log', '--forward', file], cwd=self.root)

		versions = []
		(rev, date, user, msg) = (None, None, None, None)
		seenmsg = False
		for line in lines:
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

	def get_version(self, file, version):
		rev = self._revision_arg(version)
		return _bzr.pipe(['cat', file] + rev, cwd=self.root)

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
