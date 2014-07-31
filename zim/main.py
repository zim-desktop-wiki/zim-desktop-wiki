# -*- coding: utf-8 -*-

# Copyright 2013,2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module defines the L{main()} function for executing the zim
application. It also defines a number of command classes that implement
specific commandline commands.
'''

import sys
import logging

logger = logging.getLogger('zim')

import zim
import zim.errors
import zim.config
import zim.config.basedirs

from zim.utils import get_module, lookup_subclass
from zim.errors import Error
from zim.command import Command, UsageError, GetoptError
from zim.notebook import Notebook, Path, \
	get_notebook_list, resolve_notebook, build_notebook


class HelpCommand(Command):
	'''Class implementing the C{--help} command'''

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
  --gui            run the editor (this is the default)
  --server         run the web server
  --export         export to a different format
  --search         run a search query on a notebook
  --index          build an index for a notebook
  --plugin         call a specific plugin function
  --manual         open the user manual
  -V, --verbose    print information to terminal
  -D, --debug      print debug messages
  -v, --version    print version and exit
  -h, --help       print this text

GUI Options:
  --list           show the list with notebooks instead of
                   opening the default notebook
  --geometry       window size and position as WxH+X+Y
  --fullscreen     start in fullscreen mode
  --standalone     start a single instance, no background process

Server Options:
  --port           port to use (defaults to 8080)
  --template       name of the template to use
  --gui            run the gui wrapper for the server

Export Options:
  -o, --output     output directory (mandatory option)
  --format         format to use (defaults to 'html')
  --template       name of the template to use
  --root-url       url to use for the document root
  --index-page     index page name
  -r, --recursive  when exporting a page, also export sub-pages
  -s, --singlefile export all pages to a single output file
  -O, --overwrite  force overwriting existing file(s)

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
	'''Class implementing the C{--version} command'''

	def run(self):
		print 'zim %s\n' % zim.__version__
		print zim.__copyright__, '\n'
		print zim.__license__


class NotebookLookupError(Error):
	'''Error when failing to locate a notebook'''

	description = _('Could not find the file or folder for this notebook')
		# T: Error verbose description


class NotebookCommand(Command):
	'''Base class for commands that act on a notebook'''

	def get_default_or_only_notebook(self):
		'''Helper to get a default notebook'''
		notebooks = get_notebook_list()
		if notebooks.default:
			return notebooks.default.uri
		elif len(notebooks) == 1:
			return notebooks[0].uri
		else:
			return None

	def get_notebook_argument(self):
		'''Get the notebook and page arguments for this command
		@returns: a 2-tuple of an L{NotebookInfo} object and an
		optional L{Path} or C{(None, None)} if the notebook
		argument is optional and not given
		@raises NotebookLookupError: if the notebook is mandatory and
		not given, or if it is given but could not be resolved
		'''
		assert self.arguments[0] in ('NOTEBOOK', '[NOTEBOOK]')
		args = self.get_arguments()
		notebook = args[0]

		if notebook is None:
			notebook = self.get_default_or_only_notebook()
			if notebook:
				logger.info('Using default notebook: %s', notebook)
			elif self.arguments[0] == 'NOTEBOOK': # not optional
				raise NotebookLookupError, _('Please specify a notebook')
					# T: Error when looking up a notebook
			else:
				return None, None

		notebookinfo = resolve_notebook(notebook)
		if not notebookinfo:
			raise NotebookLookupError, _('Could not find notebook: %s') % notebook
				# T: error message

		if len(self.arguments) > 1 \
		and self.arguments[1] in ('PAGE', '[PAGE]') \
		and args[1] is not None:
			pagename = Notebook.cleanup_pathname(args[1], purge=True)
			return notebookinfo, Path(pagename)
		else:
			return notebookinfo, None

	def build_notebook(self):
		'''Get the L{Notebook} object for this command
		Tries to automount the file location if needed.
		@returns: a L{Notebook} object and a L{Path} object or C{None}
		@raises NotebookLookupError: if the notebook could not be
		resolved or is not given
		@raises FileNotFoundError: if the notebook location does not
		exist and could not be mounted.
		'''
		# Explicit page argument has priority over implicit from uri
		# mounting is attempted by zim.notebook.build_notebook()
		notebookinfo, page = self.get_notebook_argument() 	# can raise NotebookLookupError
		if not notebookinfo:
			raise NotebookLookupError, _('Please specify a notebook')
		notebook, uripage = build_notebook(notebookinfo) # can raise FileNotFound
		return notebook, page or uripage


class GuiCommand(NotebookCommand):
	'''Class implementing the C{--gui} command and run the gtk interface'''

	arguments = ('[NOTEBOOK]', '[PAGE]')
	options = (
		('list', '', 'show the list with notebooks instead of\nopening the default notebook'),
		('geometry=', '', 'window size and position as WxH+X+Y'),
		('fullscreen', '', 'start in fullscreen mode'),
		('standalone', '', 'start a single instance, no background process'),
	)

	use_gtk = True

	def get_notebook_argument(self):
		def prompt():
			import zim.gui.notebookdialog
			notebookinfo = zim.gui.notebookdialog.prompt_notebook()
			return notebookinfo, None

		if self.opts.get('list'):
			return prompt()
		else:
			notebookinfo, page = NotebookCommand.get_notebook_argument(self)
			if not notebookinfo:
				return prompt()
			else:
				return notebookinfo, page

	def run(self):
		notebook, page = self.build_notebook()
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
			gui.present(page=page, **self.get_options('geometry', 'fullscreen'))
			logger.debug(
				'NOTE FOR BUG REPORTS:\n'
				'	At this point zim has send the command to open a notebook to a\n'
				'	background process and the current process will now quit.\n'
				'	If this is the end of your debug output it is probably not useful\n'
				'	for bug reports. Please close all zim windows, quit the\n'
				'	zim trayicon (if any), and try again.\n'
			)


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
	'''Class implementing the C{--server} command and running the web
	server.
	'''

	arguments = ('NOTEBOOK',)
	options = (
		('port=', 'p', 'port number to use (defaults to 8080)'),
		('template=', 't', 'name or path of the template to use'),
		#~ ('gui', '', 'run the gui wrapper for the server'),
		('standalone', '', 'start a single instance, no background process'),
	)
	# For now "--standalone" is ignored - server does not use ipc
	# --gui is special cased to switch to ServerGuiCommand

	def run(self):
		import zim.www
		self.opts['port'] = int(self.opts.get('port', 8080))
		self.opts.setdefault('template', 'Default')
		notebook, page = self.build_notebook()
		zim.www.main(notebook, **self.get_options('template', 'port'))


class ServerGuiCommand(NotebookCommand):
	'''Like L{ServerCommand} but uses the graphical interface for the
	server defined in L{zim.gui.server}.
	'''

	arguments = ('[NOTEBOOK]',)
	options = (
		('port=', 'p', 'port number to use (defaults to 8080)'),
		('template=', 't', 'name or path of the template to use'),
		#~ ('gui', '', 'run the gui wrapper for the server'),
		('standalone', '', 'start a single instance, no background process'),
	)
	# For now "--standalone" is ignored - server does not use ipc

	use_gtk = True

	def run(self):
		import zim.gui.server
		self.opts['port'] = int(self.opts.get('port', 8080))
		notebookinfo, page = self.get_notebook_argument()
		zim.gui.server.main(notebookinfo, **self.get_options('template', 'port'))


class ExportCommand(NotebookCommand):
	'''Class implementing the C{--export} command'''

	arguments = ('NOTEBOOK', '[PAGE]')
	options = (
		('format=', '', 'format to use (defaults to \'html\')'),
		('template=', '', 'name or path of the template to use'),
		('output=', 'o', 'output folder, or output file name'),
		('root-url=', '', 'url to use for the document root'),
		('index-page=', '', 'index page name'),
		('recursive', 'r', 'when exporting a page, also export sub-pages'),
		('singlefile', 's', 'export all pages to a single output file'),
		('overwrite', 'O', 'overwrite existing file(s)'),
	)

	def get_exporter(self, page):
		from zim.fs import File, Dir
		from zim.export import \
			build_mhtml_file_exporter, \
			build_single_file_exporter, \
			build_page_exporter, \
			build_notebook_exporter

		format = self.opts.get('format', 'html')
		if not 'output' in self.opts:
			raise UsageError, _('Output location needed for export') # T: error in export command
		output = Dir(self.opts['output'])
		if not output.isdir():
			output = File(self.opts.get('output'))
		template = self.opts.get('template', 'Default')

		if output.exists() and not self.opts.get('overwrite'):
			if output.isdir():
				if len(output.list()) > 0:
					raise Error, _('Output folder exists and not empty, specify "--overwrite" to force export')  # T: error message for export
				else:
					pass
			else:
				raise Error, _('Output file exists, specify "--overwrite" to force export')  # T: error message for export

		if format == 'mhtml':
			self.ignore_options('index-page')
			if output.isdir():
				raise UsageError, _('Need output file to export MHTML') # T: error message for export

			exporter = build_mhtml_file_exporter(
				output, template,
				document_root_url=self.opts.get('root-url'),
			)
		elif page:
			self.ignore_options('index-page')
			if output.exists() and output.isdir():
				ext = 'html'
				output = output.file(page.basename) + '.' + ext

			if self.opts.get('singlefile'):
				exporter = build_single_file_exporter(
					output, format, template, namespace=page,
					document_root_url=self.opts.get('root-url'),
				)
			else:
				exporter = build_page_exporter(
					output, format, template, page,
					document_root_url=self.opts.get('root-url'),
				)
		else:
			if not output.exists():
				output = Dir(output.path)
			elif not output.isdir():
				raise UsageError, _('Need output folder to export full notebook') # T: error message for export

			exporter = build_notebook_exporter(
				output, format, template,
				index_page=self.opts.get('index-page'),
				document_root_url=self.opts.get('root-url'),
			)

		return exporter

	def run(self):
		from zim.export.selections import AllPages, SinglePage, SubPages

		notebook, page = self.build_notebook()
		#~ notebook.index.update()

		if page and self.opts.get('recursive'):
			selection = SubPages(notebook, page)
		elif page:
			selection = SinglePage(notebook, page)
		else:
			selection = AllPages(notebook)

		exporter = self.get_exporter(page)
		exporter.export(selection)



class SearchCommand(NotebookCommand):
	'''Class implementing the C{--search} command'''

	arguments = ('NOTEBOOK', 'QUERY')

	def run(self):
		from zim.search import SearchSelection, Query

		notebook, p = self.build_notebook()
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
	'''Class implementing the C{--index} command'''

	arguments = ('NOTEBOOK',)

	def run(self):
		notebook, p = self.build_notebook()
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
	'servergui': ServerGuiCommand,
	'export': ExportCommand,
	'search': SearchCommand,
	'index': IndexCommand,
}

def main(*argv):
	'''Run full zim application
	@returns: exit code (if error handled, else just raises)
	'''
	argv = list(argv)
	exe = argv.pop(0)

	obj = build_command(argv)
	import zim.errors # !???
	zim.errors.set_use_gtk(obj.use_gtk)

	obj.set_logging()
	try:
		obj.run()
	except KeyboardInterrupt:
		# Don't show error dialog for this error..
		logger.error('KeyboardInterrupt')
		return 1
	except Exception:
		zim.errors.exception_handler('Exception in main()')
		return 1
	else:
		return 0


def build_command(argv):
	'''Parse all commandline options
	@returns: a L{Command} object
	@raises UsageError: if argv is not correct
	'''
	argv = list(argv)

	if argv and argv[0] == '--plugin':
		argv.pop(0)
		try:
			cmd = argv.pop(0)
		except IndexError:
			raise UsageError, 'Missing plugin name'

		try:
			mod = get_module('zim.plugins.' + cmd)
			klass = lookup_subclass(mod, Command)
		except:
			raise UsageError, 'Could not load commandline command for plugin "%s"' % cmd
	else:
		if argv and argv[0].startswith('--') and argv[0][2:] in commands:
			cmd = argv.pop(0)[2:]
			if cmd == 'server' and '--gui' in argv:
				argv.remove('--gui')
				cmd = 'servergui'
		elif argv and argv[0] == '-v':
			argv.pop(0)
			cmd = 'version'
		elif argv and argv[0] == '-h':
			argv.pop(0)
			cmd = 'help'
		else:
			cmd = 'gui' # default

		klass = commands[cmd]

	obj = klass(cmd)
	obj.parse_options(*argv)
	return obj


########################################################################
# Not sure where this function belongs

def get_zim_application(command, *args):
	'''Constructor to get a L{Application} object for zim itself
	Use this object to spawn new instances of zim from inside the zim
	application.

	@param command: the first commandline argument for zim, e.g.
	"C{--gui}", "C{--manual}" or "C{--server}"
	@param args: additional commandline arguments.
	@returns: a L{Application} object for zim itself
	'''
	# TODO: if not standalone, make object call IPC directly rather than
	#       first spawning a process
	assert command is not None

	from zim import ZIM_EXECUTABLE
	from zim.applications import Application
	from zim.ipc import in_child_process

	args = [command] + list(args)
	if not command.startswith('--ipc'):
		if not in_child_process():
			args.append('--standalone',)

		# more detailed logging has lower number, so WARN > INFO > DEBUG
		loglevel = logging.getLogger().getEffectiveLevel()
		if loglevel <= logging.DEBUG:
			args.append('-D',)
		elif loglevel <= logging.INFO:
			args.append('-V',)

	return Application([ZIM_EXECUTABLE] + args)

