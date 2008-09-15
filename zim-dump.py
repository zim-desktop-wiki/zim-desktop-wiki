#!/usr/bin/python

import sys

from zim.formats import wiki, html
from zim.formats.base import ParserError

if not (len(sys.argv) >= 2 and len(sys.argv[1]) > 0):
	print >>sys.stderr, 'Usage: %s FILE [FORMAT]' % __file__
	sys.exit(1)

path = sys.argv[1]
print "PATH: %s" % path

format = None
if len(sys.argv) == 3:
	format = sys.argv[2]
	print "FORMAT: %s" % format

try:
	tree = wiki.Parser().parse_file(path)
except ParserError, error:
	print "BUG in WikiParser:\n"+error
	sys.exit(1)

if not format:
	tree.dump()
	sys.exit()

try:
	# TODO actually use the format para to do a lookup
	html.Dumper().dump(tree, sys.stdout)
except ParserError, error:
	print 'BUG in HTMLDumper:\n'+error
	sys.exit(1)

# vim: tabstop=4
