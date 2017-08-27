#!/usr/bin/python

# This script is a wrapper around zim.main.main() for running zim as
# an application.


import sys
import logging
import os

# Check if we run the correct python version
try:
    version_info = sys.version_info
    assert version_info >= (2, 6)
    assert version_info < (3, 0)
except:
    print >> sys.stderr, 'ERROR: zim needs python >= 2.6   (but < 3.0)'
    sys.exit(1)


# Win32: must setup log file or it tries to write to $PROGRAMFILES
# See http://www.py2exe.org/index.cgi/StderrLog
# If startup is OK, this will be overruled in zim/main with per user log file
if os.name == "nt" and (
        sys.argv[0].endswith('.exe')
        or sys.executable.endswith('pythonw.exe')
):
    import tempfile
    dir = tempfile.gettempdir()
    if not os.path.isdir(dir):
        os.makedirs(dir)
    err_stream = open(dir + "\\zim.exe.log", "w")
    sys.stdout = err_stream
    sys.stderr = err_stream

# Preliminary initialization of logging because modules can throw warnings at import
logging.basicConfig(level=logging.WARN, format='%(levelname)s: %(message)s')
logging.captureWarnings(True)

# Try importing our modules
try:
    import zim
    import zim.main
except ImportError:
    sys.excepthook(*sys.exc_info())
    print >>sys.stderr, 'ERROR: Could not find python module files in path:'
    print >>sys.stderr, ' '.join(map(str, sys.path))
    print >>sys.stderr, '\nTry setting PYTHONPATH'
    sys.exit(1)


# Run the application and handle some exceptions
try:
    encoding = sys.getfilesystemencoding()  # not 100% sure this is correct
    argv = [arg.decode(encoding) for arg in sys.argv]
    exitcode = zim.main.main(*argv)
    sys.exit(exitcode)
except zim.main.GetoptError as err:
    print >>sys.stderr, sys.argv[0] + ':', err
    sys.exit(1)
except zim.main.UsageError as err:
    print >>sys.stderr, err.msg
    sys.exit(1)
except KeyboardInterrupt:  # e.g. <Ctrl>C while --server
    print >>sys.stderr, 'Interrupt'
    sys.exit(1)
else:
    sys.exit(0)
