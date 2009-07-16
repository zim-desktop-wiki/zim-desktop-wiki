#!/usr/bin/python

import sys
import zim


try:
	version_info = sys.version_info
	assert version_info >= (2, 6)
	assert version_info < (3, 0)
except:
	print >> sys.stderr, 'zim needs python >= 2.5   (but < 3.0)'
	sys.exit(1)


try:
	zim.main(sys.argv)
except zim.GetoptError, err:
	print >>sys.stderr, sys.argv[0]+':', err
	sys.exit(1)
except zim.UsageError, err:
	print >>sys.stderr, zim.usagehelp.replace('zim', sys.argv[0])
	sys.exit(1)
except KeyboardInterrupt: # e.g. <Ctrl>C while --server
	print >>sys.stderr, 'Interrupt'
	sys.exit(1)
else:
	sys.exit(0)
