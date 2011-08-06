# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module read .gjots files. The format is the format used by the
gjots2(1) program. According to the man page of this program the
format is also the same as used for the (old) kjots(1) and jots(1)
programs.

The format is very simple, there are just 3 directives:

	- C{\NewEntry} start a new page
	- C{\NewFolder} start a new namespace
	- C{\EndFolder} end of the namespace

Pages do not have any formatting and the first line, which may be
empty, is used as the page title. Titles do not have to be unique, so
we add a number for each title to make them unique.

We read the whole file to memory, which puts certain limits on
scalability, however the gjots format seems to be mainly used for large
numbers of very short entries, which may take a lot of
overhead when saved as individual files.
'''

# FUTURE: This module only read gjots file but does not write them.
# Creating a read/write version is left as an exercise to the reader.

import zim.stores.memory
	# importing class from this module makes get_store() fail

from zim.formats import get_format


# TODO needs parser and dumper routines
# TODO needs base.has_file()
# TODO needs test
# TODO needs way to pass file notebook to main script

class GjotsStore(zim.stores.memory.MemoryStore):

	properties = {
		'read-only': True
	}

	def __init__(self, **args):
		zim.stores.memory.MemoryStore.__init__(self,  **args)
		self.format = get_format('plain')
		if 'file' in args:
			self.file = file
		if not self.has_file():
			raise AssertionError, 'Gjots store needs file'
			# not using assert here because it could be optimized away
		self.read_file()

	def read_file(self):
		path = [self.file.basename, '']
		buffer = []
		for line in self.file:
			if line.rstrip() in ('\\NewEntry', '\\NewFolder', '\\EndFolder'):
				if buffer:
					title = Notebook.cleanup_pathname(buffer[0].replace(':', ' ')) # FIXME: title unused
					p = Path(':'.join(path))
							# Any '' at the end of path drops out, this is intended behavior
					self._set_node(p, ''.join(buffer))
					buffer = []

				if line.rstrip() == '\\NewFolder':
					path.append('')
				elif line.rstrip == '\\EndFolder':
					path.pop()
			else:
				buffer.append(line)


	#~ def store_page(page):
		#~ memory.Store.store_page(self, page)
		#~ self.write_file()

	#~ def write_file(self):
		#~ pass

