# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''TODO some docs here'''

import logging

logger = logging.getLogger('zim')

from zim import __version__, __copyright__, __license__
from zim.command import Command, UsageError, GetoptError
from zim.notebook import get_notebook_list, resolve_notebook, get_notebook, Path
from zim.fs import File, Dir
from zim.errors import Error


class HelpCommand(Command):

	usagehelp = '''\
usage: zim [OPTIONS] [NOTEBOOK [PAGE]]
   or: zim --server [OPTIONS] [NOTEBOOK]
   or: zim --export [OPTIONS] NOTEBOOK [PAGE]
   or: zim --search NOTEBOOK QUERY
   or: zim --index  NOTEBOOK
   or: zim --plugin PLUGIN [ARGUMENTS]
   or: zim --manual [OPTIONS] [PAGE]
   or: zim --help
'''
	optionhelp = '''\
General Options:
  --gui           run the editor (this is the default)
  --server        run the web server
  --export        export to a different format
  --search        run a search query on a notebook
  --index         build an index for a notebook
  --plugin        call a specific plugin function
  --manual        open the user manual
  -V, --verbose   print information to terminal
  -D, --debug     print debug messages
  -v, --version   print version and exit
  -h, --help      print this text

GUI Options:
  --list          show the list with notebooks instead of
                  opening the default notebook
  --geometry      window size and position as WxH+X+Y
  --fullscreen    start in fullscreen mode
  --standalone     start a single instance, no background process

Server Options:
  --port          port to use (defaults to 8080)
  --template      name of the template to use
  --gui           run the gui wrapper for the server

Export Options:
  --format        format to use (defaults to 'html')
  --template      name of the template to use
  -o, --output    output directory
  --root-url      url to use for the document root
  --index-page    index page name

  You can use the export option to print a single page to stdout.
  When exporting a whole notebook you need to provide a directory.

Search Options:
  None

Index Options:
  None

Try 'zim --manual' for more help.
'''

	def run(self):
		print self.usagehelp
		print self.optionhelp  # TODO - generate from commands


class VersionCommand(Command):

	def run(self):
		print 'zim %s\n' % __version__
		print __copyright__, '\n'
		print __license__


class NotebookLookupError(Error):
	'''Error when failing to locate a notebook'''

	description = _('Could not find the file or folder for this notebook')
		# T: Error verbose description


class NotebookCommand(Command):

	def get_default_or_only_notebook(self):
		# Helper used below to decide a good default to open
		notebooks = get_notebook_list()
		if notebooks.default:
			return notebooks.default.uri
		elif len(notebooks) == 1:
			return notebooks[0].uri
		else:
			return None

	def get_notebook(self, _raise=True):
		'''Returns a notebook object and optionally a path.
		First inspects the commandline arguments, if the notebook
		is optional it will look for a default notebook
		@returns: a L{Notebook} object and a L{Path} object or C{None}
		@raises NotebookLookupError: if the file can not be found
		'''
		assert self.arguments[0] in ('NOTEBOOK', '[NOTEBOOK]')
		args = self.get_arguments()
		notebook = args[0]

		if notebook is None:
			notebook = self.get_default_or_only_notebook()
			if notebook:
				logger.info('Using default notebook: %s', notebook)
			elif _raise:
				raise NotebookLookupError, _('Please specify a notebook')
					# T: Error when looking up a notebook
			else:
				return None, None

		# XXX - hook for plugins like automount !!

		# FIXME - do this before or after "resolve_notebook" ?
		#         resolve already checks existance of the path :S
		#~ self.emit('initialize-notebook', nb.uri)

		file, page = resolve_notebook(notebook)
		if file is None or not file.exists():
			raise NotebookLookupError, _('Could not find notebook: %s') % notebook
				# T: Error when looking up a notebook

		obj = get_notebook(notebook)

		if len(self.arguments) > 1 \
		and self.arguments[1] in ('PAGE', '[PAGE]'):
			page = args[1]
			# prefer the explicit arg over implicit from filepath

		if page:
			pagename = obj.cleanup_pathname(page, purge=True)
			return obj, Path(pagename)
		else:
			return obj, None


class GuiCommand(NotebookCommand):

	arguments = ('[NOTEBOOK]', '[PAGE]')
	options = (
		('list', '', 'show the list with notebooks instead of\nopening the default notebook'),
		('geometry=', '', 'window size and position as WxH+X+Y'),
		('fullscreen', '', 'start in fullscreen mode'),
		('standalone', '', 'start a single instance, no background process'),
	)

	def get_notebook(self):
		def prompt():
			import zim.gui.notebookdialog
			notebook = zim.gui.notebookdialog.prompt_notebook()
			# XXX - hook for plugins like automount !!
			return notebook, None

		if self.opts.get('list'):
			return prompt()
		else:
			notebook, page = NotebookCommand.get_notebook(self, _raise=False)
			if notebook:
				return notebook, page
			else:
				return prompt()

	def run(self):
		# TODO wrap ErrorDialog
		notebook, page = self.get_notebook()
		if not notebook:
			return # Cancelled notebook dialog

		if self.opts.get('standalone'):
			import zim.gui
			handler = zim.gui.GtkInterface(notebook=notebook, page=page, **self.get_options('geometry', 'fullscreen'))
			handler.main()
		else:
			import zim.ipc
			zim.ipc.start_server_if_not_running()
			server = zim.ipc.ServerProxy()
			gui = server.get_notebook(notebook)
			gui.present(page, **optsdict)
			logger.debug('''
NOTE FOR BUG REPORTS:
	At this point zim has send the command to open a notebook to a
	background process and the current process will now quit.
	If this is the end of your debug output it is probably not useful
	for bug reports. Please close all zim windows, quit the
	zim trayicon (if any), and try again.
''')


class ManualCommand(GuiCommand):
	'''Like L{GuiCommand} but always opens the manual'''

	arguments = ('[PAGE]',)
	options = filter(lambda t: t[0] != 'list', GuiCommand.options)
		# exclude --list

	def run(self):
		from zim.config import data_dir
		self.arguments = ('NOTEBOOK', '[PAGE]') # HACK
		self.args.insert(0, data_dir('manual').path)
		GuiCommand.run(self)


class ServerCommand(NotebookCommand):

	arguments = ('[NOTEBOOK]',)
	options = (
		('port=', 'p', 'port number to use (defaults to 8080)'),
		('template=', 't', 'name or path of the template to use'),
		('gui', '', 'run the gui wrapper for the server'),
		('standalone', '', 'start a single instance, no background process'),
	)
	# For now "--standalone" is ignored - server does not use ipc

	def run(self):
		notebook, page = self.get_notebook()
		self.opts['port'] = int(self.opts.get('port', 8080))
		if self.opts.get('gui'):
			# TODO wrap ErrorDialog
			import zim.gui.server
			zim.gui.server.main(notebook, **self.get_options('template', 'port'))
		else:
			import zim.www
			if not notebook:
				raise UsageError, 'no notebook specified'
			zim.www.main(notebook, **self.get_options('template', 'port'))


class ExportCommand(NotebookCommand):

	arguments = ('NOTEBOOK', '[PAGE]')
	options = (
		('format', '', 'format to use (defaults to \'html\')'),
		('template', '', 'name or path of the template to use'),
		('output', 'o', 'output directory'),
		('root-url', '', 'url to use for the document root'),
		('index-page', '', 'index page name'),
	)

	def run(self):
		import zim.exporter
		import zim.fs

		notebook, page = self.get_notebook()
		exporter = zim.exporter.Exporter(
			notebook,
			format=self.opts.get('format', 'html'),
			template=self.opts.get('template', 'Default'),
			document_root_url=self.opts.get('root-url'),
			index_page=self.opts.get('index-page'),
		)

		if page:
			page = self.notebook.get_page(page)

		if self.opts.get('output'):
			dir = zim.fs.Dir(self.opts.get('output'))
			if page:
				exporter.export_page(dir, page)
			else:
				self.notebook.index.update()
				exporter.export_all(dir)
		elif page:
			exporter.export_page_to_fh(sys.stdout, page)
		else:
			raise UsageError, 'Need output directory to export notebook'


class SearchCommand(NotebookCommand):

	arguments = ('NOTEBOOK', 'QUERY')

	def run(self):
		from zim.search import SearchSelection, Query

		notebook, p = self.get_notebook()
		n, query = self.get_arguments()

		if query and not query.isspace():
			logger.info('Searching for: %s', query)
			query = Query(query)
		else:
			raise ValueError, 'Empty query'

		selection = SearchSelection(notebook)
		selection.search(query)
		for path in sorted(selection, key=lambda p: p.name):
			print path.name


class IndexCommand(NotebookCommand):

	arguments = ('NOTEBOOK',)

	def run(self):
		notebook, p = self.get_notebook()
		index = notebook.index
		index.flush()
		def on_callback(path):
			logger.info('Indexed %s', path.name)
			return True
		index.update(callback=on_callback)


commands = {
	'help':  HelpCommand,
	'version': VersionCommand,
	'gui': GuiCommand,
	'manual': ManualCommand,
	'server': ServerCommand,
	'export': ExportCommand,
	'search': SearchCommand,
	'index': IndexCommand,
}


def main(*argv):
	'''Parse all commandline options
	@returns: a L{Command} object
	@raises UsageError: if argv is not correct
	'''
	argv = list(argv)
	if argv and argv[0].startswith('--') and argv[0][2:] in commands:
		cmd = argv.pop(0)[2:]
	elif argv and argv[0] == '-v':
		argv.pop(0)
		cmd = 'version'
	elif argv and argv[0] == '-h':
		argv.pop(0)
		cmd = 'help'
	elif argv and argv[0] == '--plugin':
		# XXX - port to command objects as well
		import zim.plugins
		try:
			pluginname = argv[1]
		except IndexError:
			raise UsageError, 'Missing plugin name'
		module = zim.plugins.get_module('zim.plugins.' + pluginname)
		module.main(*argv[2:])
		return
	else:
		cmd = 'gui' # default

	klass = commands[cmd]
	obj = klass(cmd)
	obj.parse_options(*argv)
	obj.set_logging()
	obj.run()


if __name__ == '__main__':
	import sys
	import zim.ipc
	zim.ipc.handle_argv()
	logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
	#~ zim.set_executable(argv[0])
	main(*sys.argv[1:])
