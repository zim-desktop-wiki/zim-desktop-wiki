
# Copyright 2013-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module defines the L{main()} function for executing the zim
application. It also defines a number of command classes that implement
specific commandline commands and an singleton application object that
takes core of the process life cycle.
'''

# TODO:
# - implement weakvalue dict to ensure uniqueness of notebook objects


import os
import sys
import logging
import signal

logger = logging.getLogger('zim')

import zim
import zim.fs
import zim.errors
import zim.config
import zim.config.basedirs

from zim import __version__

from zim.utils import get_module, lookup_subclass
from zim.errors import Error
from zim.notebook import Notebook, Path, \
	get_notebook_list, resolve_notebook, build_notebook
from zim.formats import get_format

from zim.config import ConfigManager
from zim.plugins import PluginManager

from .command import Command, GtkCommand, UsageError, GetoptError
from .ipc import dispatch as _ipc_dispatch
from .ipc import start_listening as _ipc_start_listening


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
		print(self.usagehelp)
		print(self.optionhelp)  # TODO - generate from commands


class VersionCommand(Command):
	'''Class implementing the C{--version} command'''

	def run(self):
		print('zim %s\n' % zim.__version__)
		print(zim.__copyright__, '\n')
		print(zim.__license__)


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
			uri = notebooks.default.uri
		elif len(notebooks) == 1:
			uri = notebooks[0].uri
		else:
			return None

		return resolve_notebook(uri, pwd=self.pwd) # None if not found

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
			if self.arguments[0] == 'NOTEBOOK': # not optional
				raise NotebookLookupError(_('Please specify a notebook'))
					# T: Error when looking up a notebook
			else:
				return None, None

		notebookinfo = resolve_notebook(notebook, pwd=self.pwd)
		if not notebookinfo:
			raise NotebookLookupError(_('Could not find notebook: %s') % notebook)
				# T: error message

		if len(self.arguments) > 1 \
		and self.arguments[1] in ('PAGE', '[PAGE]') \
		and args[1] is not None:
			pagename = Path.makeValidPageName(args[1])
			return notebookinfo, Path(pagename)
		else:
			return notebookinfo, None

	def build_notebook(self, ensure_uptodate=True):
		'''Get the L{Notebook} object for this command
		Tries to automount the file location if needed.
		@param ensure_uptodate: if C{True} index is updated when needed.
		Only set to C{False} when index update is handled explicitly
		(e.g. in the main gui).
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
			raise NotebookLookupError(_('Please specify a notebook'))
		notebook, uripage = build_notebook(notebookinfo) # can raise FileNotFound

		if ensure_uptodate and not notebook.index.is_uptodate:
			for info in notebook.index.update_iter():
				#logger.info('Indexing %s', info)
				pass # TODO meaningful info for above message

		return notebook, page or uripage


class GuiCommand(NotebookCommand, GtkCommand):
	'''Class implementing the C{--gui} command and run the gtk interface'''

	arguments = ('[NOTEBOOK]', '[PAGE]')
	options = (
		('list', '', 'show the list with notebooks instead of\nopening the default notebook'),
		('geometry=', '', 'window size and position as WxH+X+Y'),
		('fullscreen', '', 'start in fullscreen mode'),
		('standalone', '', 'start a single instance, no background process'),
	)

	def build_notebook(self, ensure_uptodate=False):
		# Bit more complicated here due to options to use default and
		# allow using notebookdialog to prompt

		# Explicit page argument has priority over implicit from uri
		# mounting is attempted by zim.notebook.build_notebook()

		from zim.notebook import FileNotFoundError

		def prompt_notebook_list():
			import zim.gui.notebookdialog
			return zim.gui.notebookdialog.prompt_notebook()
				# Can return None if dialog is cancelled

		used_default = False
		page = None
		if self.opts.get('list'):
			notebookinfo = prompt_notebook_list()
		else:
			notebookinfo, page = self.get_notebook_argument()

			if notebookinfo is None:
				notebookinfo = self.get_default_or_only_notebook()
				used_default = notebookinfo is not None

				if notebookinfo is None:
					notebookinfo = prompt_notebook_list()

		if notebookinfo is None:
			return None, None # Cancelled prompt

		try:
			notebook, uripage = build_notebook(notebookinfo) # can raise FileNotFound
		except FileNotFoundError:
			if used_default:
				# Default notebook went missing? Fallback to dialog to allow changing it
				notebookinfo = prompt_notebook_list()
				if notebookinfo is None:
					return None, None # Cancelled prompt
				notebook, uripage = build_notebook(notebookinfo) # can raise FileNotFound
			else:
				raise

		if ensure_uptodate and not notebook.index.is_uptodate:
			for info in notebook.index.update_iter():
				#logger.info('Indexing %s', info)
				pass # TODO meaningful info for above message

		return notebook, page or uripage

	def run(self):
		from gi.repository import Gtk

		from zim.gui.mainwindow import MainWindow

		windows = [
			w for w in Gtk.Window.list_toplevels()
				if isinstance(w, MainWindow)
		]

		notebook, page = self.build_notebook()
		if notebook is None:
			logger.debug('NotebookDialog cancelled - exit')
			return

		for window in windows:
			if window.notebook.uri == notebook.uri:
				self._present_window(window, page)
				return window
		else:
			return self._run_new_window(notebook, page)

	def _present_window(self, window, page):
		window.present()

		if page:
			window.open_page(page)

		geometry = self.opts.get('geometry', None)
		if geometry is not None:
			window.parse_geometry(geometry)

		if self.opts.get('fullscreen', False):
			window.toggle_fullscreen(True)

	def _run_new_window(self, notebook, page):
		from gi.repository import GObject

		from zim.gui.mainwindow import MainWindow

		pluginmanager = PluginManager()

		preferences = ConfigManager.preferences['General']
		preferences.setdefault('plugins_list_version', 'none')
		if preferences['plugins_list_version'] != '0.70':
			if not preferences['plugins']:
				pluginmanager.load_plugins_from_preferences(
					[ # Default plugins
						'pageindex', 'pathbar',
						'insertsymbol', 'printtobrowser',
						'versioncontrol',
					]
				)
			else:
				# Upgrade version <0.70 where these were core functions
				pluginmanager.load_plugins_from_preferences(['pageindex', 'pathbar'])

			if 'calendar' in pluginmanager.failed:
				ConfigManager.preferences['JournalPlugin'] = \
						ConfigManager.preferences['CalendarPlugin']
				pluginmanager.load_plugins_from_preferences(['journal'])

			preferences['plugins_list_version'] = '0.70'

		window = MainWindow(
			notebook,
			page=page,
			**self.get_options('geometry', 'fullscreen')
		)
		window.present()

		if not window.notebook.index.is_uptodate:
			window._uiactions.reload_index(update_only=True) # XXX
		else:
			# Start a lightweight background check of the index
			# put a small delay to ensure window is shown before we start
			def start_background_check():
				notebook.index.start_background_check(notebook)
				return False # only run once
			GObject.timeout_add(500, start_background_check)

		return window


class ManualCommand(GuiCommand):
	'''Like L{GuiCommand} but always opens the manual'''

	arguments = ('[PAGE]',)
	options = tuple(t for t in GuiCommand.options if t[0] != 'list')
		# exclude --list

	def run(self):
		from zim.config import data_dir
		self.arguments = ('NOTEBOOK', '[PAGE]') # HACK
		self.args.insert(0, data_dir('manual').path)
		return GuiCommand.run(self)


class ServerCommand(NotebookCommand):
	'''Class implementing the C{--server} command and running the web
	server.
	'''

	arguments = ('NOTEBOOK',)
	options = (
		('port=', 'p', 'port number to use (defaults to 8080)'),
		('template=', 't', 'name or path of the template to use'),
		('standalone', '', 'start a single instance, no background process'),
	)

	def run(self):
		import zim.www
		self.opts['port'] = int(self.opts.get('port', 8080))
		self.opts.setdefault('template', 'Default')
		notebook, page = self.build_notebook()

		self.server = httpd = zim.www.make_server(notebook, public=True, **self.get_options('template', 'port'))
			# server attribute used in testing to stop sever in thread
		logger.info("Serving HTTP on %s port %i...", httpd.server_name, httpd.server_port)
		httpd.serve_forever()


class ServerGuiCommand(NotebookCommand, GtkCommand):
	'''Like L{ServerCommand} but uses the graphical interface for the
	server defined in L{zim.gui.server}.
	'''

	arguments = ('[NOTEBOOK]',)
	options = (
		('port=', 'p', 'port number to use (defaults to 8080)'),
		('template=', 't', 'name or path of the template to use'),
		('standalone', '', 'start a single instance, no background process'),
	)

	def run(self):
		import zim.gui.server
		self.opts['port'] = int(self.opts.get('port', 8080))
		notebookinfo, page = self.get_notebook_argument()
		if notebookinfo is None:
			# Prefer default to be selected in drop down, user can still change
			notebookinfo = self.get_default_or_only_notebook()

		window = zim.gui.server.ServerWindow(
			notebookinfo,
			public=True,
			**self.get_options('template', 'port')
		)
		window.show_all()
		return window


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
			raise UsageError(_('Output location needed for export')) # T: error in export command
		output = Dir(self.opts['output'])
		if not output.isdir():
			output = File(self.opts.get('output'))
		template = self.opts.get('template', 'Default')

		if output.exists() and not self.opts.get('overwrite'):
			if output.isdir():
				if len(output.list()) > 0:
					raise Error(_('Output folder exists and not empty, specify "--overwrite" to force export'))  # T: error message for export
				else:
					pass
			else:
				raise Error(_('Output file exists, specify "--overwrite" to force export'))  # T: error message for export

		if format == 'mhtml':
			self.ignore_options('index-page')
			if output.isdir():
				raise UsageError(_('Need output file to export MHTML')) # T: error message for export

			exporter = build_mhtml_file_exporter(
				output, template,
				document_root_url=self.opts.get('root-url'),
			)
		elif self.opts.get('singlefile'):
			self.ignore_options('index-page')
			if output.exists() and output.isdir():
				ext = get_format(format).info['extension']
				output = output.file(page.basename) + '.' + ext

			exporter = build_single_file_exporter(
				output, format, template, namespace=page,
				document_root_url=self.opts.get('root-url'),
			)
		elif page:
			self.ignore_options('index-page')
			if output.exists() and output.isdir():
				ext = get_format(format).info['extension']
				output = output.file(page.basename) + '.' + ext

			exporter = build_page_exporter(
				output, format, template, page,
				document_root_url=self.opts.get('root-url'),
			)
		else:
			if not output.exists():
				output = Dir(output.path)
			elif not output.isdir():
				raise UsageError(_('Need output folder to export full notebook')) # T: error message for export

			exporter = build_notebook_exporter(
				output, format, template,
				index_page=self.opts.get('index-page'),
				document_root_url=self.opts.get('root-url'),
			)

		return exporter

	def run(self):
		from zim.export.selections import AllPages, SinglePage, SubPages

		notebook, page = self.build_notebook()
		notebook.index.check_and_update()

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
			raise ValueError('Empty query')

		selection = SearchSelection(notebook)
		selection.search(query)
		for path in sorted(selection, key=lambda p: p.name):
			print(path.name)


class IndexCommand(NotebookCommand):
	'''Class implementing the C{--index} command'''

	arguments = ('NOTEBOOK',)

	def run(self):
		notebook, p = self.build_notebook(ensure_uptodate=False)
		notebook.index.flush()
		for info in notebook.index.update_iter():
			#logger.info('Indexing %s', info)
			pass # TODO meaningful info for above message


commands = {
	'help': HelpCommand,
	'version': VersionCommand,
	'gui': GuiCommand,
	'manual': ManualCommand,
	'server': ServerCommand,
	'servergui': ServerGuiCommand,
	'export': ExportCommand,
	'search': SearchCommand,
	'index': IndexCommand,
}


def build_command(args, pwd=None):
	'''Parse all commandline options
	@returns: a L{Command} object
	@raises UsageError: if args is not correct
	'''
	args = list(args)

	if args and args[0] == '--plugin':
		args.pop(0)
		try:
			cmd = args.pop(0)
		except IndexError:
			raise UsageError('Missing plugin name')

		try:
			mod = get_module('zim.plugins.' + cmd)
			klass = lookup_subclass(mod, Command)
		except:
			if '-D' in args or '--debug' in args:
				logger.exception('Error while loading: zim.plugins.%s.Command', cmd)
				# Can't use following because log level not yet set:
				# logger.debug('Error while loading: zim.plugins.%s.Command', cmd, exc_info=sys.exc_info())
			raise UsageError('Could not load commandline command for plugin "%s"' % cmd)
	else:
		if args and args[0].startswith('--') and args[0][2:] in commands:
			cmd = args.pop(0)[2:]
			if cmd == 'server' and '--gui' in args:
				args.remove('--gui')
				cmd = 'servergui'
		elif args and args[0] == '-v':
			args.pop(0)
			cmd = 'version'
		elif args and args[0] == '-h':
			args.pop(0)
			cmd = 'help'
		else:
			cmd = 'gui' # default

		klass = commands[cmd]

	obj = klass(cmd, pwd=pwd)
	obj.parse_options(*args)
	return obj



class ZimApplication(object):
	'''This object is repsonsible for managing the life cycle of the
	application process.

	To do so, it decides whether to dispatch a command to an already
	running zim process or to handle it in the current process.
	For gtk based commands it keeps track of the toplevel objects
	for re-use and to be able to end the process when no toplevel
	objects are left.
	'''

	def __init__(self):
		self._running = False
		self._log_started = False
		self._standalone = False
		self._windows = set()

	@property
	def toplevels(self):
		return iter(self._windows)

	@property
	def notebooks(self):
		return frozenset(
			w.notebook for w in self.toplevels
				if hasattr(w, 'notebook')
		)

	def get_mainwindow(self, notebook, _class=None):
		'''Returns an existing L{MainWindow} for C{notebook} or C{None}'''
		from zim.gui.mainwindow import MainWindow
		_class = _class or MainWindow # test seam
		for w in self.toplevels:
			if isinstance(w, _class) and w.notebook.uri == notebook.uri:
				return w
		else:
			return None

	def present(self, notebook, page=None):
		'''Present notebook and page in a mainwindow, may not return for
		standalone processes.
		'''
		uri = notebook if isinstance(notebook, str) else notebook.uri
		pagename = page if isinstance(page, str) else page.name
		self.run('--gui', uri, pagename)

	def add_window(self, window):
		if not window in self._windows:
			logger.debug('Add window: %s', window.__class__.__name__)

			assert hasattr(window, 'destroy')
			window.connect('destroy', self._on_destroy_window)
			self._windows.add(window)

	def remove_window(self, window):
		logger.debug('Remove window: %s', window.__class__.__name__)
		try:
			self._windows.remove(window)
		except KeyError:
			pass

	def _on_destroy_window(self, window):
		self.remove_window(window)
		if not self._windows:
			from gi.repository import Gtk

			logger.debug('Last toplevel destroyed, quit')
			if Gtk.main_level() > 0:
				Gtk.main_quit()

	def run(self, *args, **kwargs):
		'''Run a commandline command, either in this process, an
		existing process, or a new process.
		@param args: commandline arguments
		@param kwargs: optional arguments for L{build_command}
		'''
		PluginManager().load_plugins_from_preferences(
			ConfigManager.preferences['General']['plugins']
		)
		cmd = build_command(args, **kwargs)
		self._run_cmd(cmd, args) # test seam

	def _run_cmd(self, cmd, args):
		self._setup_logging(cmd)

		if self._running:
			# This is not the first command that we process
			if isinstance(cmd, GtkCommand):
				if self._standalone or cmd.standalone_process:
					self._spawn_standalone(args)
				else:
					w = cmd.run()
					if w is not None:
						self.add_window(w)
						w.present()
			else:
				cmd.run()
		else:
			# Although a-typical, this path could be re-entrant if a
			# run_local() dispatches another command - therefore we set
			# standalone before calling run_local()
			if isinstance(cmd, GtkCommand):
				self._standalone = self._standalone or cmd.standalone_process
				if cmd.run_local():
					return

				if not self._standalone and self._try_dispatch(args, cmd.pwd):
					pass # We are done
				else:
					self._running = True
					self._run_main_loop(cmd)
			else:
				cmd.run()

	def _run_main_loop(self, cmd):
		# Run for the 1st gtk command in a primary process,
		# but can still be standalone process
		from gi.repository import Gtk
		from gi.repository import GObject

		#######################################################################
		# WARNING: commented out "GObject.threads_init()" because it leads to
		# various segfaults on linux. See github issue #7
		# However without this init, gobject does not properly release the
		# python GIL during C calls, so threads may block while main loop is
		# waiting. Thus threads become very slow and unpredictable unless we
		# actively monitor them from the mainloop, causing python to run
		# frequently. So be very carefull relying on threads.
		# Re-evaluate when we are above PyGObject 3.10.2 - threading should
		# wotk bettter there even without this statement. (But even then,
		# no Gtk calls from threads, just "GObject.idle_add()". )
		# Kept for windows, because we need thread to run ipc listener, and no
		# crashes observed there.
		if os.name == 'nt':
			GObject.threads_init()
		#######################################################################

		from zim.gui.widgets import gtk_window_set_default_icon
		gtk_window_set_default_icon()

		zim.errors.set_use_gtk(True)
		self._setup_signal_handling()

		if self._standalone:
			logger.debug('Starting standalone process')
		else:
			logger.debug('Starting primary process')
			self._daemonize()
			if not _ipc_start_listening(self._handle_incoming):
				logger.warn('Failure to setup socket, falling back to "--standalone" mode')
				self._standalone = True

		w = cmd.run()
		if w is not None:
			self.add_window(w)

		while self._windows:
			Gtk.main()

			for toplevel in list(self._windows):
				try:
					toplevel.destroy()
				except:
					logger.exception('Exception while destroying window')
					self.remove_window(toplevel) # force removal

			# start main again if toplevels remaining ..

		# exit immediatly if no toplevel created

	def _setup_logging(self, cmd):
		if cmd.opts.get('debug'):
			level = logging.DEBUG
		elif cmd.opts.get('verbose'):
			level = logging.INFO
		else:
			level = logging.WARN

		root = logging.getLogger() # root
		if level < root.getEffectiveLevel():
			root.setLevel(level)

		if not self._log_started:
			self._log_start()

	def _log_start(self):
		self._log_started = True

		logger.info('This is zim %s', __version__)
		level = logger.getEffectiveLevel()
		if level == logging.DEBUG:
			import sys
			import os
			import zim.config

			logger.debug('Python version is %s', str(sys.version_info))
			logger.debug('Platform is %s', os.name)
			zim.config.log_basedirs()

	def _setup_signal_handling(self):
		def handle_sigterm(signal, frame):
			from gi.repository import Gtk

			logger.info('Got SIGTERM, quit')
			if Gtk.main_level() > 0:
				Gtk.main_quit()

		signal.signal(signal.SIGTERM, handle_sigterm)

	def _spawn_standalone(self, args):
		from zim import ZIM_EXECUTABLE
		from zim.applications import Application

		args = list(args)
		if not '--standalone' in args:
			args.append('--standalone')

		# more detailed logging has lower number, so WARN > INFO > DEBUG
		loglevel = logging.getLogger().getEffectiveLevel()
		if loglevel <= logging.DEBUG:
			args.append('-D',)
		elif loglevel <= logging.INFO:
			args.append('-V',)

		Application([ZIM_EXECUTABLE] + args).spawn()

	def _try_dispatch(self, args, pwd):
		try:
			_ipc_dispatch(pwd, *args)
		except AssertionError as err:
			logger.debug('Got error in dispatch: %s', str(err))
			return False
		except Exception:
			logger.exception('Got error in dispatch')
			return False
		else:
			logger.debug('Dispatched command %r', args)
			return True

	def _handle_incoming(self, pwd, *args):
		self.run(*args, pwd=pwd)

	def _daemonize(self):
		# Decouple from parent environment
		# and redirect standard file descriptors
		os.chdir(zim.fs.Dir('~').path)
			# Using HOME because this folder will not disappear normally
			# and because it is a sane starting point for file choosers etc.

		try:
			si = file(os.devnull, 'r')
			os.dup2(si.fileno(), sys.stdin.fileno())
		except:
			pass

		loglevel = logging.getLogger().getEffectiveLevel()
		if loglevel <= logging.INFO and sys.stdout.isatty() and sys.stderr.isatty():
			# more detailed logging has lower number, so WARN > INFO > DEBUG
			# log to file unless output is a terminal and logging <= INFO
			pass
		else:
			# Redirect output to file
			dir = zim.fs.get_tmpdir()
			err_stream = open(os.path.join(dir.path, "zim.log"), "w")

			# Try to flush standards out and error, if there
			for pipe in (sys.stdout, sys.stderr):
				if pipe is not None:
					try:
						pipe.flush()
					except OSError:
						pass

			# First try to dup handles for anyone who still has a reference
			# if that fails, just set them (maybe not real files in the first place)
			try:
				os.dup2(err_stream.fileno(), sys.stdout.fileno())
				os.dup2(err_stream.fileno(), sys.stderr.fileno())
			except:
				sys.stdout = err_stream
				sys.stderr = err_stream

			# Re-initialize logging handler, in case it keeps reference
			# to the old stderr object
			try:
				rootlogger = logging.getLogger()
				for handler in rootlogger.handlers:
					rootlogger.removeHandler(handler)

				handler = logging.StreamHandler()
				handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
				rootlogger.addHandler(handler)
			except:
				pass


ZIM_APPLICATION = ZimApplication() # Singleton per process


def main(*argv):
	'''Run full zim application
	@returns: exit code (if error handled, else just raises)
	'''

	import zim.config

	# Check if we can find our own data files
	_file = zim.config.data_file('zim.png')
	if not (_file and _file.exists()): #pragma: no cover
		raise AssertionError(
			'ERROR: Could not find data files in path: \n'
			'%s\n'
			'Try setting XDG_DATA_DIRS'
				% list(map(str, zim.config.data_dirs()))
		)

	try:
		ZIM_APPLICATION.run(*argv[1:])
	except KeyboardInterrupt:
		# Don't show error dialog for this error..
		logger.error('KeyboardInterrupt')
		return 1
	except Exception:
		zim.errors.exception_handler('Exception in main()')
		return 1
	else:
		return 0
