# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module read .gjots files. The format is the format used by the
gjots2(1) program. According to the man page of this program the
format is also the same as used for the (old) kjots(1) and jots(1)
programs.

The format is very simple, there are just 3 directives:

	\NewEntry	start a new page
	\NewFolder	start a new namespace
	\EndFolder	end of the namespace

Pages do not have any formatting and the first line, which may be
empty, is used as the page title. Titles do not have to be unique, so
we add a number for each title to make them unique.

We read the whole file to memory, which puts certain limits on
scalebility, however the gjots format seems to be mainly used for l
arge numbers of very short entries, which may take a lot of
overhead when saved as individual files.
'''

from zim import formats
from zim.stores import memory

__store__ = 'gjots'

# TODO needs stub format "plain" - DONE
# TODO needs parser and dumper routines
# TODO needs base.has_file()
# TODO needs test
# TODO needs way to pass file notebook to main script

class Store(memory.Store):

	def __init__(self, **args):
		'''FIXME'''
		memory.Store.__init__(self,  **args)
		self.format = zim.formats.get_format('plain')
		if 'file' in args:
			self.file = file
		assert self.has_file()
		self._read_file()

	def _read_file(self):
		'''FIXME'''
		# TODO gjots parser code goes here

	def _write_file(self):
		'''FIXME'''
		# TODO gjots dumper code goes here

	def _on_write(self, buffer):
		'''FIXME'''
		memory.Store._on_write(self, buffer)
		self._write_file()
