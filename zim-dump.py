#!/usr/bin/python

import sys

from zim.notebook import Notebook
from zim import formats


if not (len(sys.argv) >= 2 and len(sys.argv[1]) > 0):
	print >>sys.stderr, 'Usage: %s DIR [PAGE [FORMAT]]' % __file__
	sys.exit(1)

path = sys.argv[1]
print "Notebook: %s" % path

notebook = Notebook(path)

if len(sys.argv) == 2:
	# Only notebook - dump index
	print "Pages:"
	for page in notebook.get_root().walk():
		print page.name
	sys.exit(0)


if not (len(sys.argv) >= 2 and len(sys.argv[1]) > 0):
	print >>sys.stderr, 'Usage: %s FILE [FORMAT]' % __file__
	sys.exit(1)

page = sys.argv[2]
print "Page: %s" % page

format = None
if len(sys.argv) == 4:
	format = sys.argv[3]
	print "Format: %s" % format


pageobj = notebook.get_page(page)
print "File: %s" % pageobj.source.path

tree = pageobj.get_parse_tree()

if not format:
	tree.dump()
	sys.exit()
else:
	mod = formats.get_format(format)
	mod.Dumper().dump(tree, sys.stdout)
	pass

# vim: tabstop=4
