#!/usr/bin/python

import sys

from zim import www
from zim.notebook import Notebook

if len(sys.argv) != 3:
	print "usage: %s PORT DIR" % __file__
	sys.exit(1)

port = int( sys.argv[1] )
path = sys.argv[2]

www.serve(port, notebook=Notebook(path))
