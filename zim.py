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

'''This script parses commandline options for zim and hands them off
to the apropriate class to run the application.
'''

import sys
import logging

from getopt import gnu_getopt, GetoptError

try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
except:
	print >> sys.stderror, 'zim needs python >= 2.5'
	sys.exit(1)


logger = logging.getLogger('zim')


# All commandline options in various groups
longopts = ('verbose', 'debug')
cmdopts = ('help', 'version', 'gui', 'server', 'export', 'manual')
guiopts = ()
serveropts = ('port=', 'template=', 'gui')
exportopts = ('format=', 'template=', 'output=')
shortopts = {
	'v': 'version', 'h': 'help',
	'V': 'verbose', 'D': 'debug',
}

# Inline help - do not use __doc__ for this !
usagehelp = '''\
usage: zim [OPTIONS] [NOTEBOOK [PAGE]]
   or: zim --export [OPTIONS] [NOTEBOOK [PAGE]]
   or: zim --server [OPTIONS] [NOTEBOOK]
   or: zim --manual [OPTIONS] [PAGE]
   or: zim --help
'''
optionhelp = '''\
General Options:
  --gui       run the editor (this is the default)
  --server    run the web server
  --export    export to a different format
  --manual    open the user manual
  --verbose   print information to terminal
  --debug     print debug messages
  --version   print version and exit
  --help      print this text

Server Options:
  --port      port to use (defaults to 8080)
  --template  name of the template to use
  --gui       run the gui wrapper for the server

Export Options: FIXME
  --format    format to use (defaults to 'html')
  --template  name of the template to use
  --output    output file or directory

Try 'zim --manual' for more help.
'''

class UsageError(Exception):
	pass

def main(argv):
	'''Run the main program.'''

	import zim
	zim.executable = argv[0]

	# Let getopt parse the option list
	short = ''.join(shortopts.keys())
	long = list(longopts)
	long.extend(cmdopts)
	long.extend(guiopts)
	long.extend(serveropts)
	long.extend(exportopts)

	opts, args = gnu_getopt(argv[1:], short, long)

	# First figure out which command to execute
	cmd = 'gui' # default
	if opts:
		o = opts[0][0].lstrip('-')
		if o in shortopts:
			o = shortopts[o]
		if o in cmdopts:
			opts.pop(0)
			cmd = o


	# If it is a simple command execute it and return
	if cmd == 'version':
		print 'zim %s\n' % zim.__version__
		print zim.__copyright__, '\n'
		print zim.__license__
		return
	elif cmd == 'help':
		print usagehelp.replace('zim', zim.executable)
		print optionhelp
		return

	# Otherwise check the number of arguments
	if (cmd in ('server', 'manual') and len(args) > 1) or (len(args) > 2):
		raise UsageError

	if cmd == 'manual':
		# --manual is an alias for --gui _manual_
		cmd = 'gui'
		args.insert(0, '_manual_')

	# Now figure out which options are allowed for this command
	allowedopts = list(longopts)
	if cmd == 'server':
		allowedopts.extend(serveropts)
	elif cmd == 'export':
		allowedopts.extend(exportopts)
	else:
		assert cmd == 'gui' or cmd == 'manual'
		allowedopts.extend(guiopts)

	# Convert options into a proper dict
	optsdict = {}
	for o, a in opts:
		o = o.lstrip('-')
		if o in shortopts:
			o = shortopts[o]

		if o+'=' in allowedopts:
			optsdict[o] = a
		elif o in allowedopts:
			optsdict[o] = True
		else:
			raise GetoptError, ("--%s no allowed in combination with --%s" % (o, cmd), o)

	# --port is the only option that is not of type string
	if 'port' in optsdict and not optsdict['port'] is None:
		try:
			optsdict['port'] = int(optsdict['port'])
		except ValueError:
			raise GetoptError, ("--port takes an integer argument", 'port')

	# set loggin output level for logging root
	level = logging.WARNING
	if optsdict.pop('verbose', False): level = logging.INFO
	if optsdict.pop('debug', False): level = logging.DEBUG # no "elif" !
	logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

	# Now we determine the class to handle this command
	# and start the application ...
	logger.debug('run command: %s', cmd)
	if cmd == 'export':
		handler = zim.NotebookInterface(notebook=args[0])
		if len(args) == 2:
			optsdict['page'] = args[1]
		handler.export(**optsdict)
	elif cmd == 'gui':
		import zim.gui
		handler = zim.gui.GtkInterface(*args, **optsdict)
		handler.main()
	elif cmd == 'server':
		import zim.www
		handler = zim.www.Server(*args, **optsdict)
		handler.main()


if __name__ == '__main__':
	try:
		main(sys.argv)
	except GetoptError, err:
		print >>sys.stderr, sys.argv[0]+':', err
		sys.exit(1)
	except UsageError, err:
		print >>sys.stderr, usagehelp.replace('zim', sys.argv[0])
		sys.exit(1)
	except KeyboardInterrupt: # e.g. <Ctrl>C while --server
		print >>sys.stderr, 'Interrupt'
		sys.exit(1)
	else:
		sys.exit(0)
