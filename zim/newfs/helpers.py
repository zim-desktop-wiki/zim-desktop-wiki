
# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Helper classes for file system related functions'''

try:
	from gi.repository import Gio
	from gi.repository import GObject
except ImportError:
	Gio = None


import os
import logging

logger = logging.getLogger('zim.newfs.helpers')


from zim.signals import SignalEmitter, SIGNAL_NORMAL
from zim.errors import Error

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
		'moved': (SIGNAL_NORMAL, None, (object, object)),
		'removed': (SIGNAL_NORMAL, None, (object,)),
	} #: signals supported by this class


class TrashNotSupportedError(Error):
	'''Error raised when trashing is not supported and delete should
	be used instead
	'''
	pass


class TrashCancelledError(Error):
	'''Error raised when a trashing operation is cancelled. (E.g. on
	windows the system will prompt the user with a confirmation
	dialog which has a Cancel button.)
	'''
	pass


class TrashHelper(object):

	def trash(self, file):
		'''Trash a file or folder by moving it to the system trashcan
		if supported. Depends on the C{gio} library.
		@param file: a C{LocalFile} object
		@returns: C{True} when successful
		@raises TrashNotSupportedError: if trashing is not supported
		or failed.
		@raises TrashCancelledError: if trashing was cancelled by the
		user
		'''
		if not Gio:
			raise TrashNotSupportedError('Gio not imported')
		elif not isinstance(file, LocalFSObjectBase):
			raise TrashNotSupportedError('cannot trash a non-local file or folder')

		if file.exists():
			logger.info('Move %s to trash' % file)
			f = Gio.File.new_for_uri(file.uri)
			try:
				ok = f.trash()
			except GObject.GError as error:
				if error.code == Gio.IOErrorEnum.CANCELLED \
				or (os.name == 'nt' and error.code == 0):
					# code 0 observed on windows for cancel
					logger.info('Trash operation cancelled')
					raise TrashCancelledError('Trashing cancelled')
				elif error.code == Gio.IOErrorEnum.NOT_SUPPORTED:
					raise TrashNotSupportedError('Trashing failed')
				else:
					raise error
			else:
				if not ok:
					raise TrashNotSupportedError('Trashing failed')
			file._cleanup()
			return True
		else:
			return False



class FSObjectMonitor(SignalEmitter):

	__signals__ = {
		'changed': (None, None, (None, None)),
	}

	def __init__(self, path):
		self.path = path
		self._gio_file_monitor = None

	def _setup_signal(self, signal):
		if signal == 'changed' \
		and self._gio_file_monitor is None \
		and Gio:
			try:
				file = Gio.File.new_for_uri(self.path.uri)
				self._gio_file_monitor = file.monitor(0, None)
				self._gio_file_monitor.connect('changed', self._on_changed)
			except:
				logger.exception('Error while setting up file monitor')

	def _teardown_signal(self, signal):
		if signal == 'changed' \
		and self._gio_file_monitor:
			try:
				self._gio_file_monitor.cancel()
			except:
				logger.exception('Error while tearing down file monitor')
			finally:
				self._gio_file_monitor = None

	def _on_changed(self, filemonitor, file, other_file, event_type):
		# 'FILE_MONITOR_EVENT_CHANGED' is always followed by
		# a 'FILE_MONITOR_EVENT_CHANGES_DONE_HINT' when the filehandle
		# is closed (or after timeout). Idem for "created", assuming it
		# is not created empty.
		#
		# TODO: do not emit changed on CREATED - separate signal that
		#       can be used when monitoring a file list, but reserve
		#       changed for changes-done-hint so that we ensure the
		#       content is complete.
		#       + emit on write and block redundant signals here
		#
		# Also note that in many cases "moved" will not be used, but a
		# sequence of deleted, created will be signaled
		#
		# For Dir objects, the event will refer to files contained in
		# the dir.

		#~ print('MONITOR:', self, event_type)
		if event_type in (
			Gio.FileMonitorEvent.CREATED,
			Gio.FileMonitorEvent.CHANGES_DONE_HINT,
			Gio.FileMonitorEvent.DELETED,
			Gio.FileMonitorEvent.MOVED,
		):
			self.emit('changed', None, None) # TODO translate otherfile and eventtype


def format_file_size(bytes):
	'''Returns a human readable label  for a file size
	E.g. C{1230} becomes C{"1.23kb"}, idem for "Mb" and "Gb"
	@param bytes: file size in bytes as integer
	@returns: size as string
	'''
	for unit, label in (
		(1000000000, 'Gb'),
		(1000000, 'Mb'),
		(1000, 'kb'),
	):
		if bytes >= unit:
			size = float(bytes) / unit
			if size < 10:
				return "%.2f%s" % (size, label)
			elif size < 100:
				return "%.1f%s" % (size, label)
			else:
				return "%.0f%s" % (size, label)
	else:
		return str(bytes) + 'b'
