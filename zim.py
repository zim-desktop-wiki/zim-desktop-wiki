#!/usr/bin/python

# -*- coding: utf8 -*-

# Copyright 2008, 2009 Jaap Karssenberg <pardus@cpan.org>
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
commands = ('help', 'version', 'gui', 'server', 'export', 'index', 'manual')
commandopts = {
	'gui': (),
	'server': ('port=', 'template=', 'gui'),
	'export': ('format=', 'template=', 'output='),
	'index': ('output=',),
}
shortopts = {
	'v': 'version', 'h': 'help',
	'V': 'verbose', 'D': 'debug',
	'o': 'output'
}
maxargs = {
	'gui': 2, 'server': 1, 'manual': 1,
	'export': 2, 'index': 1
}

# Inline help - do not use __doc__ for this !
usagehelp = '''\
usage: zim [OPTIONS] [NOTEBOOK [PAGE]]
   or: zim --export [OPTIONS] NOTEBOOK [PAGE]
   or: zim --index  [OPTIONS] NOTEBOOK
   or: zim --server [OPTIONS] [NOTEBOOK]
   or: zim --manual [OPTIONS] [PAGE]
   or: zim --help
'''
optionhelp = '''\
General Options:
  --gui           run the editor (this is the default)
  --server        run the web server
  --export        export to a different format
  --index         build an index for a notebook
  --manual        open the user manual
  -V, --verbose   print information to terminal
  -D, --debug     print debug messages
  -v, --version   print version and exit
  -h, --help      print this text

Server Options:
  --port          port to use (defaults to 8080)
  --template      name of the template to use
  --gui           run the gui wrapper for the server

Export Options:
  --format        format to use (defaults to 'html')
  --template      name of the template to use
  -o, --output    output file or directory

Index Options:
  --output    output file

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
	long = list(longopts) + list(commands)
	for opts in commandopts.values():
		long.extend(opts)

	opts, args = gnu_getopt(argv[1:], short, long)

	# First figure out which command to execute
	cmd = 'gui' # default
	if opts:
		o = opts[0][0].lstrip('-')
		if o in shortopts:
			o = shortopts[o]
		if o in commands:
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
	if len(args) > maxargs[cmd]:
		raise UsageError

	# --manual is an alias for --gui _manual_
	if cmd == 'manual':
		cmd = 'gui'
		args.insert(0, '_manual_')

	# Now figure out which options are allowed for this command
	allowedopts = list(longopts)
	allowedopts.extend(commandopts[cmd])

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
	if cmd in ('export', 'index'):
		if not len(args) >= 1:
			raise UsageError
		handler = zim.NotebookInterface(notebook=args[0])
		if len(args) == 2: optsdict['page'] = args[1]
		method = getattr(handler, 'cmd_' + cmd)
		method(**optsdict)
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
