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

'''FIXME docstring'''

import sys

from zim import www
from zim.notebook import Notebook

def main(argv=None):
	'''FIXME'''
	if argv is None:
		argv = sys.argv

	if len(argv) != 3:
		print >>sys.stderr, __doc__
		print >>sys.stderr, "usage: %s PORT DIR" % __file__
		return 1

	port = int( sys.argv[1] )
	path = sys.argv[2]

	www.serve(port, notebook=Notebook(path))
	return 1 # we do not expect above function to return

if __name__ == '__main__':
	sys.exit( main() )
