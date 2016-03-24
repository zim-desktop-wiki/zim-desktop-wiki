# -*- coding: utf-8 -*-

# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Helper classes for file system related functions'''


from zim.signals import SignalEmitter, SIGNAL_NORMAL


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



