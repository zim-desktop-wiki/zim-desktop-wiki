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

'''FIXME doc string with usage'''


import sys
import getopt


try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
except:
	print >> sys.stderror, 'zim needs python >= 2.5'
	sys.exit(1)


class OptionError(Exception):

	def __init__(self, msg=None):
		if msg: msg = '%s: %s\n' % (__file__, msg)
		self.msg = msg

	def __str__(self):
		if self.msg is None: return __doc__
		tryhelp = 'Try `%s --help` for more information' % __file__
		return self.msg + tryhelp


class UsageError(OptionError):

	def __init__(self, msg=None):
		if msg: msg =  'Usage: %s %s\n' % (__file__, msg)
		self.msg = msg



def main(argv=None):
	'''Run the main program.'''
	if argv is None: argv = sys.argv[1:]

	short  = 'hv'
	long   = ['help', 'version']
	long  += ['export', 'format=', 'template=', 'output=']
	long  += ['server', 'port=']
	long  += ['dump-page']

	try:
		opts, args = getopt.gnu_getopt(argv, short, long)
	except getopt.GetoptError, err:
		raise OptionError, err.__str__()

	for o, a in opts:
		if o in ('-v', '--version'):
			import zim
			print "zim %s\n" % zim.__version__
			print zim.__copyright__
			return
		elif o in ('-h', '--help'):
			print __doc__
			return
		elif o == '--export':
			return export(opts, args)
		elif o == '--server':
			return server(opts, args)
		elif o == '--dump-page':
			return dump_page(opts, args)
		else:
			continue

	return gui(opts, args)


def gui(opts, args):
	'''Start graphical interface'''
	assert False, 'TODO: gui interface'


def export(opts, args):
	'''Process export options'''
	import zim.notebook

	format = None
	template = None
	output = None
	for o, a in opts:
		if   o == '--export': pass
		elif o == '--format': format = a
		elif o == '--template': template = a
		elif o == '--output': output = a
		else:
			raise OptionError, 'can not use %s with --export' % o

	if format is None:
		raise OptionError, '--export needs at least --format'
	elif not output is None:
		assert False, 'TODO: output to file not implemented'

	if len(args) == 0 or len(args) > 2:
		raise UsageError, '--export NOTEBOOK [PAGE]'
	elif len(args) == 1:
		if output is None:
			raise OptionError, '--export needs --output for multiple pages'
		assert False, 'TODO: export whole notebook'

	notebook = zim.notebook.get_notebook(args[0])
	page = notebook.get_page(args[1])

	if template is None:
		print page.get_text(format=format)
	else:
		import zim.templates
		try:
			tmpl = zim.templates.get_template(format, template)
		except zim.templates.TemplateSyntaxError, error:
			print error
		else:
			tmpl.process(page, sys.stdout)


def server(opts, args):
	'''Process server options'''
	import zim.www

	print '''\
WARNING: Serving zim notes as a webserver. Unless you have some
kind of firewall your notes are now open to the whole wide world.
'''

	port = 8888
	template=None
	for o, a in opts:
		if o == '--server': pass
		elif o == '--port':
			try: port = int(a)
			except ValueError:
				raise OptionError, "--port takes an integer argument"
		elif o == '--template': template = a
		else:
			raise OptionError, 'can not use %s with --server' % o

	if not len(args) == 1:
		raise UsageError, '--server NOTEBOOK'

	if not template is None:
		import zim.templates
		template = zim.templates.get_template('html', template)

	server = zim.www.Server(port, template=template)
	server.open_notebook(args[0])
	server.main()


def dump_page(opts, args):
	'''Debug routing to dump the parse tree for a page.'''
	import zim.notebook

	if len(args) != 2:
		raise UsageError, '--dump-page NOTEBOOK PAGE'

	notebook = zim.notebook.get_notebook(args[0])
	page = notebook.get_page(args[1])

	print page.get_parsetree().write(sys.stdout)



if __name__ == '__main__':
	try:
		main()
	except OptionError, err:
		print >> sys.stderr, err
		sys.exit(1)
	except KeyboardInterrupt: # e.g. <Ctrl>C while --server
		print >> sys.stderr, 'Interrupt'
		sys.exit(1)
	else:
		sys.exit(0)
else:
	raise ImportError, "The zim script can not be imported"
