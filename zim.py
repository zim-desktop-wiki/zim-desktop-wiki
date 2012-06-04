#!/usr/bin/python

import sys
import logging
import os

# Check if we run the correct python version
try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
	assert version_info < (3, 0)
except:
	print >> sys.stderr, 'ERROR: zim needs python >= 2.5   (but < 3.0)'
	sys.exit(1)

# Win32: must setup log file or it tries to write to $PROGRAMFILES
if os.name == "nt" and sys.argv[0].endswith('.exe'):
	import tempfile
	dir = tempfile.gettempdir()
	if not os.path.isdir(dir):
		os.makedirs(dir)
	err_stream = open(dir + "\\zim.log", "w")
	sys.stdout = err_stream
	sys.stderr = err_stream

# Preliminary initialization of logging because modules can throw warnings at import
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


# Coverage support - triggered by the test suite
#~ if True:
	#~ print 'Start coverage !'
	#~ import atexit
	#~ import coverage
	#~ cov = coverage.coverage(data_suffix=True, auto_data=True)
	#~ cov.start()
	#~ atexit.register(cov.stop)


# Try importing our modules
try:
	import zim
	import zim.config
except ImportError:
	print >>sys.stderr, 'ERROR: Could not find python module files in path:'
	print >>sys.stderr, ' '.join(map(str, sys.path))
	print >>sys.stderr, '\nTry setting PYTHONPATH'
	sys.exit(1)


# Check if we can find our data files
try:
	icon = zim.config.data_file('zim.png')
	assert not icon is None
except:
	print >>sys.stderr, 'ERROR: Could not find data files in path:'
	print >>sys.stderr, ' '.join(map(str, zim.config.data_dirs()))
	print >>sys.stderr, '\nTry setting XDG_DATA_DIRS'
	sys.exit(1)


# Run the application and handle some exceptions
try:
	encoding = sys.getfilesystemencoding() # not 100% sure this is correct
	argv = [arg.decode(encoding) for arg in sys.argv]
	zim.main(argv)
except zim.GetoptError, err:
	print >>sys.stderr, sys.argv[0]+':', err
	sys.exit(1)
except zim.UsageError, err:
	print >>sys.stderr, err.msg
	sys.exit(1)
except KeyboardInterrupt: # e.g. <Ctrl>C while --server
	print >>sys.stderr, 'Interrupt'
	sys.exit(1)
else:
	sys.exit(0)
