# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''TODO some docs here'''

import sys
import logging

logger = logging.getLogger('zim')

from zim import __version__, __copyright__, __license__
from zim.fs import FS, File, Dir
from zim.errors import Error
from zim.environ import environ
from zim.command import Command, UsageError, GetoptError
from zim.config import ConfigManager, XDGConfigDirsIter
from zim.notebook import Notebook, Path, NotebookInfo, \
	get_notebook_list, resolve_notebook, build_notebook

import zim.config
import zim.config.basedirs


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
		return notebook, uripage or page


class GuiCommand(NotebookCommand):

	arguments = ('[NOTEBOOK]', '[PAGE]')
	options = (
		('list', '', 'show the list with notebooks instead of\nopening the default notebook'),
		('geometry=', '', 'window size and position as WxH+X+Y'),
		('fullscreen', '', 'start in fullscreen mode'),
		('standalone', '', 'start a single instance, no background process'),
	)

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
		try:
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
		except Exception, error:
			from zim.gui.widgets import ErrorDialog
			ErrorDialog(None, error).run()
				# error dialog also does logging automatically
			return 1
		else:
			return 0


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
		notebook, page = self.build_notebook()
		zim.www.main(notebook, **self.get_options('template', 'port'))


class ServerGuiCommand(NotebookCommand):

	arguments = ('[NOTEBOOK]',)
	options = (
		('port=', 'p', 'port number to use (defaults to 8080)'),
		('template=', 't', 'name or path of the template to use'),
		#~ ('gui', '', 'run the gui wrapper for the server'),
		('standalone', '', 'start a single instance, no background process'),
	)
	# For now "--standalone" is ignored - server does not use ipc

	def run(self):
		import zim.gui.server
		self.opts['port'] = int(self.opts.get('port', 8080))
		notebookinfo, page = self.get_notebook_argument()
		zim.gui.server.main(notebookinfo, **self.get_options('template', 'port'))


class ExportCommand(NotebookCommand):

	arguments = ('NOTEBOOK', '[PAGE]')
	options = (
		('format=', '', 'format to use (defaults to \'html\')'),
		('template=', '', 'name or path of the template to use'),
		('output=', 'o', 'output directory'),
		('root-url=', '', 'url to use for the document root'),
		('index-page=', '', 'index page name'),
	)

	def run(self):
		import zim.exporter
		import zim.fs

		notebook, page = self.build_notebook()
		exporter = zim.exporter.Exporter(
			notebook,
			format=self.opts.get('format', 'html'),
			template=self.opts.get('template', 'Default'),
			document_root_url=self.opts.get('root-url'),
			index_page=self.opts.get('index-page'),
		)

		if page:
			page = notebook.get_page(page)

		if self.opts.get('output'):
			dir = zim.fs.Dir(self.opts.get('output'))
			if page:
				exporter.export_page(dir, page)
			else:
				notebook.index.update()
				exporter.export_all(dir)
		elif page:
			exporter.export_page_to_fh(sys.stdout, page)
		else:
			raise UsageError, 'Need output directory to export notebook'


class SearchCommand(NotebookCommand):

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

	if argv and argv[0] == '--plugin':
		# XXX - port to command objects as well
		if '-D' in argv:
			argv.remove('-D')
			level = logging.DEBUG
		elif '-V' in argv:
			argv.remove('-V')
			level = logging.INFO
		else:
			level = logging.WARN

		root = logging.getLogger()
		root.setLevel(level)

		logger.info('This is zim %s', __version__)

		import zim.plugins
		try:
			pluginname = argv[1]
		except IndexError:
			raise UsageError, 'Missing plugin name'
		module = zim.plugins.get_module('zim.plugins.' + pluginname)

		init_zim_application(exe)
		module.main(*argv[2:])
		return

	obj = build_command(argv)

	if not isinstance(obj, (VersionCommand, HelpCommand)):
		init_zim_application(exe)

	obj.set_logging()
	exitcode = obj.run()
	return exitcode or 0


def build_command(argv):
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
	# elif --plugin TODO
	else:
		cmd = 'gui' # default

	if cmd == 'server' and '--gui' in argv:
		argv.remove('--gui')
		cmd = 'servergui'

	klass = commands[cmd]
	obj = klass(cmd)
	obj.parse_options(*argv)

	return obj


#: Executable for starting new zim instances, set by main()
ZIM_EXECUTABLE = None

def init_zim_application(exe, config=None):
	'''Initializes the zim application environment.
	This means setting C{ZIM_EXECUTABLE}, loading X{init.conf} and
	X{automount.conf} if present and verify zim can access it's
	data files.
	@param exe: the executable or script that we are running, usually
	C{sys.argv[0]}
	@param config: config manager for lookign up config files,
	defaults to L{ConfigManager}
	'''
	global ZIM_EXECUTABLE
	assert not ZIM_EXECUTABLE, 'init_application already called, can not initialize twice'
	exefile = _set_zim_executable(exe)
	exedir = exefile.dir

	if not config:
		config = ConfigManager(dir=exedir, dirs=XDGConfigDirsIter())
		# Do not use this config for rest of application!

	_load_init_conf(config, exedir)
	_check_data_files()

	# For backward compatibility
	automount = config.get_config_dict('automount.conf')
	_load_mountpoints(automount)


def _set_zim_executable(exe):
	global ZIM_EXECUTABLE
	ZIM_EXECUTABLE = exe
	exefile = File(ZIM_EXECUTABLE)
	if exefile.exists():
		# Make e.g. "./zim.py" absolute
		ZIM_EXECUTABLE = exefile.path
	return exefile


def _load_init_conf(config, exedir):
	init = config.get_config_dict('init.conf')

	# Environment
	for k, v in init['Environment'].items():
		try:
			if v.startswith('~/'):
				v = File(v).path
			elif v.startswith('./') or v.startswith('../'):
				v = exedir.resolve_file(v).path
			else:
				pass
		except:
			logger.exception('Could not parse environment parameter %s = "%s"', k, v)
		else:
			logger.debug('Init environment: %s = %s', k, v)
			environ[k] = v

	zim.config.basedirs.set_basedirs() # Re-initialize constants
	zim.init_gettext()

	# Mountpoints
	_load_mountpoints(init)

	# TODO add keyword to load python script to bootstrap more advanced stuff ?


def _load_mountpoints(configdict):
	groups = [k for k in configdict.keys() if k.startswith('Path')]
	groups.sort() # make order predictable for nested paths
	for group in groups:
		path = group[4:].strip() # len('Path') = 4
		dir = Dir(path)
		handler = ApplicationMountPointHandler(dir, **configdict[group])
		FS.connect('mount', handler)


def _check_data_files():
	# Check if we can find our own data files
	icon = zim.config.data_file('zim.png')
	if not (icon and icon.exists()): #pragma: no cover
		raise AssertionError(
			'ERROR: Could not find data files in path: \n'
			'%s\n'
			'Try setting XDG_DATA_DIRS'
				% map(str, zim.config.data_dirs())
		)


class ApplicationMountPointHandler(object):

	def __init__(self, dir, **opts):
		self.dir = dir
		self.opts = opts

	def __call__(self, fs, path):
		if path.ischild(self.dir) and not path.exists() \
		and 'mount' in self.opts:
			from zim.applications import Application
			#~ if 'passwd' in config:
				#~ passwd = self.prompt
			Application(self.opts['mount']).run()
			return True # cancel other handlers


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

	from zim.applications import Application
	from zim.ipc import in_child_process

	if not ZIM_EXECUTABLE:
		raise AssertionError(
			'ZIM_EXECUTABLE is not set -'
			' function called from outside zim'
			' or zim is not properly initialized'
		)

	if not ZIM_EXECUTABLE.endswith('.exe') and sys.executable:
		# If not an compiled executable, we assume it is python
		# (Application class only does this automatically for scripts
		# ending in .py)
		cmd = (sys.executable, ZIM_EXECUTABLE)
	else:
		# Else should be executable on it's own
		cmd = (ZIM_EXECUTABLE,)

	args = [command] + list(args)
	if not in_child_process():
		args.append('--standalone',)

	# more detailed logging has lower number, so WARN > INFO > DEBUG
	loglevel = logging.getLogger().getEffectiveLevel()
	if loglevel <= logging.DEBUG:
		args.append('-D',)
	elif loglevel <= logging.INFO:
		args.append('-V',)

	return Application(cmd + tuple(args))

