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
to the apropriate application object.
'''

import sys
from getopt import gnu_getopt, GetoptError

try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
except:
	print >> sys.stderror, 'zim needs python >= 2.5'
	sys.exit(1)

# Used in error messages and is passed on the the app as
# the command to call to spawn a new instance.
executable = 'zim'

# All commandline options in various groups
longopts = ('verbose', 'debug')
cmdopts = ('help', 'version', 'gui', 'server', 'export', 'doc')
guiopts = ()
serveropts = ('port=', 'template=', 'gui')
exportopts = ('format=', 'template=', 'output=')
shortopts = {
	'v': 'version', 'h': 'help',
	'V': 'verbose', 'D': 'debug',
}

# Inline help - do not use __doc__ for this !
helptext = '''\
Usage: %s [OPTIONS] [NOTEBOOK] [PAGE]

Options: FIXME

Server Options: FIXME

Export Options: FIXME

Try 'zim --doc' for more help.
'''

class UsageError(Exception):

	def __init__(self, msg):
		Exception.__init__(self, 'Usage: %s %s' % (executable, msg))


def main(argv):
	'''Run the main program.'''
	executable = argv[0]

	# Let getopt parse the option list
	short = ''.join(shortopts.keys())
	long = list(longopts)
	long.extend(cmdopts)
	long.extend(guiopts)
	long.extend(serveropts)
	long.extend(exportopts)

	opts, args = gnu_getopt(argv[1:], short, long)

	# First figure out which command to execute
	try:
		cmd = opts[0][0].lstrip('-')
		if cmd in shortopts:
			cmd = shortopts[cmd]
		assert cmd in cmdopts
		opts.pop(0)
	except:
		cmd = 'gui' # default command

	# If it is a simple command execute it and return
	if cmd == 'version':
		import zim
		print 'zim %s\n' % zim.__version__
		print zim.__copyright__, '\n'
		print zim.__license__
		return
	elif cmd == 'help':
		print helptext % executable
		return

	# Otherwise check the number of arguments
	if cmd == 'server' and len(args) > 1:
		raise UsageError, 'zim --server [OPTIONS] [NOTEBOOK]'
	elif cmd == 'doc' and len(args) > 1:
		raise UsageError, 'zim --doc [OPTIONS] [PAGE]'
	elif len(args) > 2:
		raise UsageError, 'zim --%s [OPTIONS] [NOTEBOOK [PAGE]]' % cmd

	if cmd == 'doc':
		# --doc is an alias for --gui _doc_
		cmd = 'gui'
		args.insert(0, '_doc_')

	# Now figure out which options are allowed for this command
	allowedopts = list(longopts)
	if cmd == 'server':
		allowedopts.extend(serveropts)
	elif cmd == 'export':
		allowedopts.extend(exportopts)
	else:
		assert cmd == 'gui' or cmd == 'doc'
		allowedopts.extend(guiopts)

	# Convert options into a proper dict
	optsdict = {'executable': executable}
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

	# Now we can create an Application object
	if cmd == 'gui':
		import zim.gui
		app = zim.gui.GtkApplication(**optsdict)
	elif cmd == 'server':
		if 'gui' in optsdict and optsdict['gui']:
			import zim.gui.www
			app = zim.gui.www.GtkWWWAplication(**optsdict)
		else:
			import zim.www
			app = zim.www.Server(**optsdict)
	elif cmd == 'export':
		import zim.exporter
		app = zim.exporter.Exporter(**optsdict)

	if args:
		app.open_notebook(args[0])
		if len(args) == 2 and not cmd == 'server':
			app.open_page(args[1])

	# and start the application ...
	app.main()


if __name__ == '__main__':
	try:
		main(sys.argv)
	except (GetoptError, UsageError), err:
		print >> sys.stderr, executable+':', err
		sys.exit(1)
	except KeyboardInterrupt: # e.g. <Ctrl>C while --server
		print >> sys.stderr, 'Interrupt'
		sys.exit(1)
	else:
		sys.exit(0)
