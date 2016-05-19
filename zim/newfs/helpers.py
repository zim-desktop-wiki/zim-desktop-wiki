# -*- coding: utf-8 -*-

# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Helper classes for file system related functions'''

try:
	import gio
	import gobject
except ImportError:
	gio = None


from zim.signals import SignalEmitter, SIGNAL_NORMAL
from zim.errors import TrashNotSupportedError, TrashNotSupportedError

import os
import logging

logger = logging.getLogger('zim.newfs.helpers')


from .local import LocalFSObjectBase


class FileTreeWatcher(SignalEmitter):
	'''Helper object that adds signals for file changes. It can be
	used for the C{watcher} attribute for file system objects.

	When use the object itself will call the "watcher" on changes
	and if the object is a folder it will pass on the "watcher" to
	child objects. So you can effectively watch a whole tree.
	'''

	__signals__ = {
		'created': (SIGNAL_NORMAL, None, (object,)),
		'changed': (SIGNAL_NORMAL, None, (object,)),
		'moved':   (SIGNAL_NORMAL, None, (object, object)),
		'removed': (SIGNAL_NORMAL, None, (object,)),
	} #: signals supported by this class



class TrashHelper(object):

	def trash(self, file):
		'''Trash a file or folder by moving it to the system trashcan
		if supported. Depends on the C{gio} library.
		@param file: a C{LocalFile} object
		@returns: C{True} when succesful
		@raises TrashNotSupportedError: if trashing is not supported
		or failed.
		@raises TrashCancelledError: if trashing was cancelled by the
		user
		'''
		if not gio:
			raise TrashNotSupportedError, 'gio not imported'
		elif not isinstance(file, LocalFSObjectBase):
			raise TrashNotSupportedError, 'cannot trash a non-local file or folder'

		if file.exists():
			logger.info('Move %s to trash' % file)
			f = gio.File(uri=file.uri)
			try:
				ok = f.trash()
			except gobject.GError, error:
				if error.code == gio.ERROR_CANCELLED \
				or (os.name == 'nt' and error.code == 0):
					# code 0 observed on windows for cancel
					logger.info('Trash operation cancelled')
					raise TrashCancelledError, 'Trashing cancelled'
				elif error.code == gio.ERROR_NOT_SUPPORTED:
					raise TrashNotSupportedError, 'Trashing failed'
				else:
					raise error
			else:
				if not ok:
					raise TrashNotSupportedError, 'Trashing failed'
			file._cleanup()
			return True
		else:
			return False

