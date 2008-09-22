#!/usr/bin/python

# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

'''FIXME doc string with usage'''

import sys

from zim.notebook import Notebook
from zim import formats

def main(argv=None):
	'''Run the program.

	Returns the exit code for sys.exit() and 'argv' defaults to sys.argv
	'''
	if argv is None:
		argv = sys.argv

	if not (len(argv) >= 2 and len(argv[1]) > 0):
		print __doc__
		print >>sys.stderr, 'Usage: %s DIR [PAGE [FORMAT]]' % __file__
		return 1

	path = argv[1]
	print "Notebook: %s" % path

	notebook = Notebook(path)

	if len(argv) == 2:
		# Only notebook - dump index
		print "Pages:"
		for page in notebook.get_root().walk():
			print page.name
		return 0

	page = argv[2]
	print "Page: %s" % page

	format = None
	if len(argv) == 4:
		format = argv[3]
		print "Format: %s" % format


	pageobj = notebook.get_page(page)
	print "File: %s" % pageobj.source.path

	tree = pageobj.get_parse_tree()

	if not format:
		print tree
		return 0
	else:
		mod = formats.get_format(format)
		mod.Dumper().dump(tree, sys.stdout)
		pass

#	try:
#	except UsageError, err:
#		print >>sys.stderr, err.msg
#		print >>sys.stderr, "for help use --help"
#		return 2
	return 0

if __name__ == '__main__':
	sys.exit( main() )
