# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains utilities to work with external applications
it is based on the Freedesktop.org (XDG) Desktop Entry specification
with some additional logic based on status quo on Gnome / XFCE.

The main class is the L{DesktopEntryFile} which maps the application
definition in a specific desktop entry. Typically these are not
constructed directly, but requested through the L{ApplicationManager}.

Similar there is the L{CustomTool} class, which defines a custom tool
defined within zim, and the L{CustomToolManager} to manage these
definitions.

Also there is the L{OpenWithMenu} which is the widget to render a menu
with available applications for a specific file plus a dialog so the
user can define a new command on the fly.
'''

# We don't have direct method to get/set the default application this is
# on purpose since there is no Freedesktop.org spec for this and no
# platform independent way to do this. So we can get/set our own helpers
# etc. but for platform default use xdg-open / os.startfile / ...

import os
import logging
import gtk
import gobject

import zim.fs
from zim.fs import File, Dir, TmpFile
from zim.config import XDG_DATA_HOME, XDG_DATA_DIRS, XDG_CONFIG_HOME, \
	config_file, data_dirs, ConfigDict, ConfigFile, json
from zim.parsing import split_quoted_strings
from zim.applications import Application, WebBrowser, StartFile
from zim.gui.widgets import ui_environment, Dialog, ErrorDialog


logger = logging.getLogger('zim.gui.applications')


def _application_file(path, dirs):
	# Some logic to check multiple options, e.g. a path of kde-foo.desktop
	# could also be stored as applications/kde/foo.desktop but not necessarily..
	paths = [path]
	if '-' in path:
		for i in range(1, path.count('-')+1):
			paths.append(path.replace('-', '/', i))

	for dir in dirs:
		for p in paths:
			file = dir.file(p)
			if file.exists():
				return file
	else:
		return None


def _application_dirs():
	# Generator for application directories, first check zim specific paths,
	# then general applications
	for dir in data_dirs('applications'):
		yield dir

	yield XDG_DATA_HOME.subdir('applications')

	for dir in XDG_DATA_DIRS:
		yield dir.subdir('applications')


def _create_application(dir, Name, Exec, klass=None, **param):
	n = Name.lower() + '-usercreated'
	key = n
	file = dir.file(key + '.desktop')
	i = 0
	while file.exists():
		assert i < 1000, 'BUG: Infinite loop ?'
		i += 1
		key = n + '-' + str(i)
		file = dir.file(key + '.desktop')

	if klass is None:
		klass = DesktopEntryFile
	entry = klass(file)
	type = param.pop('Type', 'Application')
	entry.update(
		Type=type,
		Version=1.0,
		NoDisplay=True,
		Name=Name,
		Exec=Exec,
		**param
	)

	assert entry.isvalid(), 'BUG: created invalid desktop entry'
	entry.write()

	if param.get('MimeType'):
		# Update mimetype cache
		cache = dir.file('mimeinfo.cache')
		if not cache.exists():
			lines = ['[MIME Cache]\n']
		else:
			lines = cache.readlines()

		mimetype = param.get('MimeType')
		for i, line in enumerate(lines):
			if line.startswith(mimetype + '='):
				lines[i] = line.strip() + ';' + key + '.desktop\n'
				break
		else:
			lines.append(mimetype + '=' + key + '.desktop\n')

		cache.writelines(lines)

	return entry


class ApplicationManager(object):
	'''Manager object for dealing with desktop applications. Uses the
	freedesktop.org (XDG) system to locate desktop entry files for
	installed applications.

	In addition is supports custom helper applications for zim.
	These helpers are special application definitions used by the
	preferences for "web browser", "file browser" etc.
	They are stored in a zim specific folder (typically
	"share/zim/applications"). They have the same keys as a standard
	desktop entry, but adds the non-standard keys "X-Zim-AppType" and
	X-Zim-ShowOnlyFor". The first is a list of application types, the
	second is an optional platform (e.g. "maemo"), together these are
	used to decide if and where to show this application in the
	preferences dialog.
	'''

	@staticmethod
	def get_application(name):
		'''Get an application by name. Will search installed ".desktop"
		files of the same name
		@param name: the application name (e.g. "firefox"). As a special
		case "webbrowser" maps to a L{WebBrowser} application instance
		and "startfile" to a L{StartFile} application instance
		@returns: an L{Application} object or C{None}
		'''
		file = _application_file(name + '.desktop', _application_dirs())
		if file:
			return DesktopEntryFile(File(file))
		elif name == 'webbrowser':
			return WebBrowser()
		elif name == 'startfile':
			return StartFile()
		else:
			return None

	@staticmethod
	def list_applications(mimetype):
		'''Get a list of applications that can handle a specific file
		type.
		@param mimetype: the mime-type of the file (e.g. "text/html")
		@returns: a list of L{Application} objects that are known to
		be able to handle this file type
		'''
		seen = set()
		entries = []
		key = '%s=' % mimetype
		for dir in _application_dirs():
			cache = dir.file('mimeinfo.cache')
			if not cache.exists():
				continue
			for line in cache.readlines():
				if line.startswith(key):
					for basename in line[len(key):].strip().split(';'):
						if basename in seen:
							continue
						else:
							file = _application_file(basename, (dir,))
							if file:
								entries.append(DesktopEntryFile(File(file)))
								seen.add(basename)

		if mimetype == 'text/html':
			entries.append(WebBrowser())
			entries.append(StartFile())

		return entries

	@classmethod
	def get_default_helper(klass, type):
		'''Get the default helper application on the current platform.

		@note: This is the default set if the user has no preference,
		not the current user preference. Use L{GtkInterface.open_file()}
		and friends to use the preferred application.

		@param type: application type, can be one of:
		  - C{web_browser}
		  - C{file_browser}
		  - C{email_client}
		  - C{text_editor}

		@returns: an L{Application} object or C{None}
		'''
		# Hard coded defaults for various platforms
		preferred = {
			#                linux        windows      mac      maemo
			'email_client': ['xdg-email', 'startfile', 'open', 'modest'],
			'file_browser': ['xdg-open', 'startfile', 'open', 'hildon-mime-summon'],
			'web_browser': ['xdg-open', 'startfile', 'open', 'webbrowser'],
			'text_editor': ['xdg-open', 'startfile', 'open'],
		}

		helpers = klass.list_helpers(type)
		keys = [entry.key for entry in helpers]
		for k in preferred[type]: # preferred keys
			if k in keys:
				return helpers[keys.index(k)]

		if helpers:
			return helpers[0]
		else:
			return None

	@classmethod
	def list_helpers(klass, type):
		'''Get a list of helper applications for the current platform.

		@param type: application type, can be one of:
		  - C{web_browser}
		  - C{file_browser}
		  - C{email_client}
		  - C{text_editor}

		@returns: a list of L{Application} objects
		'''
		# Be aware that X-Zim-AppType can be a list of types
		environment = ui_environment['platform']
		if not environment:
			import platform
			environment = platform.system()

		seen = set()
		helpers = []
		for dir in data_dirs('applications'):
			for basename in [n for n in dir.list() if n.endswith('.desktop')]:
				key = basename[:-8] # len('.desktop') == 8
				if key in seen:
					continue
				seen.add(key)
				entry = DesktopEntryFile(dir.file(basename))
				if entry.isvalid():
					entry_types = entry['Desktop Entry'].get('X-Zim-AppType')
					entry_platform = entry['Desktop Entry'].get('X-Zim-ShowOnlyFor')
					if type in entry_types:
						if environment and entry_platform \
						and environment != entry_platform:
							continue # skip
						else:
							helpers.append(entry)

		if type == 'web_browser':
			for entry in klass.list_applications('text/html'):
				if not entry.key in seen:
					helpers.append(entry)
					seen.add(entry.key)
				# list_applications will include the fallback
				# based on the webbrowser module
		elif type == 'text_editor':
			for entry in klass.list_applications('text/plain'):
				if not entry.key in seen:
					helpers.append(entry)
					seen.add(entry.key)

		if os.name == 'nt' and not 'startfile' in seen:
			helpers.append( klass.get_application('startfile') )

		return [helper for helper in helpers if helper.tryexec()]

	@staticmethod
	def create(mimetype, Name, Exec, **param):
		'''Create a new usercreated desktop entry which defines a
		custom command to handle a certain file type.

		Note that the name under which this definition is stored is not
		the same as C{Name}. Check the 'C{key}' attribute of the
		returned object if you want the name to retrieve this
		application later.

		@param mimetype: the file mime-type to handle with this command
		@param Name: the name to show in e.g. the "Open With.." menu
		@param Exec: the command to run as string (will be split on
		whitespace, so quote arguments that may contain a space).
		@param param: any additional keys for the desktop entry

		@returns: the L{DesktopEntryFile} object with some
		sensible defaults for a user created application entry.
		'''
		dir = XDG_DATA_HOME.subdir('applications')
		param['MimeType'] = mimetype
		file = _create_application(dir, Name, Exec, **param)
		# TODO register mimetype in cache
		return file

	@staticmethod
	def create_helper(type, Name, Exec, **param):
		'''Create a new usercreated desktop entry which defines a
		helper application of a specific type.

		@param type: the application type (see L{list_helpers()})
		@param Name: the name to show in e.g. the preferences dialog
		@param Exec: the command to run as string (will be split on
		whitespace, so quote arguments that may contain a space).
		@param param: any additional keys for the desktop entry

		@returns: the L{DesktopEntryFile} object with some
		sensible defaults for a user created application entry.
		'''
		dir = XDG_DATA_HOME.subdir('zim/applications')
		param['X-Zim-AppType'] = type
		return _create_application(dir, Name, Exec, **param)


class DesktopEntryDict(ConfigDict, Application):
	'''Base class for L{DesktopEntryFile}, defines most of the logic.

	The following keys are supported:
	  - C{%f}: a single file path
	  - C{%F}: a list of file paths
	  - C{%u}: a single URL
	  - C{%U}: a list of URLs
	  - C{%i}: the icon as defined in the desktop entry, if any,
	    prefixed with C{--icon}
	  - C{%c}: the name from the desktop entry
	  - C{%k}: the file path for the desktop entry file

	See L{parse_exec()} for interpolating these keys. If the command
	does not contain any keys, the file paths or URLs to open are
	just appended to the command.

	@ivar key: the name of the ".desktop" file, this is the key needed
	to lookup the application through the L{ApplicationManager}.
	@ivar name: the 'Name' field from the desktop entry
	@ivar comment: the 'Comment' field from the desktop entry
	@ivar cmd: the command and arguments as a tuple, based on the
	'Exec' key (still contains the keys for interpolation)
	@ivar tryexeccmd: the command to check in L{tryexec()}, from the
	'TryExe' key in the desktop entry, if C{None} fall back to first
	item of C{cmd}
	'''

	@property
	def key(self):
		return '__anon__' # no mapping to .desktop file

	def isvalid(self):
		'''Check if all the fields that are required according to the
		spcification are set. Assumes we only use desktop files to
		describe applications (and not links or dirs, which are also
		covered by the spec).
		@returns: C{True} if all required fields are set
		'''
		entry = self['Desktop Entry']
		if entry.get('Type') == 'Application' \
		and entry.get('Version') == 1.0 \
		and entry.get('Name') \
		and entry.get('Exec'):
			return True
		else:
			logger.error('Invalid desktop entry: %s %s', self.key, entry)
			return False

	@property
	def name(self):
		# TODO: localisation of application name
		return self['Desktop Entry']['Name']

	@property
	def comment(self):
		# TODO: localisation of application name
		return self['Desktop Entry']['Comment']

	@property
	def tryexeccmd(self):
		return self['Desktop Entry'].get('TryExec')

	@property
	def cmd(self):
		return split_quoted_strings(self['Desktop Entry']['Exec'])

	def get_pixbuf(self, size):
		'''Get the application icon as a C{gtk.gdk.Pixbuf}.
		@param size: the icon size as gtk constant
		@returns: a pixbuf object or C{None}
		'''
		icon = self['Desktop Entry'].get('Icon', None)
		if not icon:
			return None

		if isinstance(icon, File):
			icon = icon.path

		w, h = gtk.icon_size_lookup(size)

		if '/' in icon or '\\' in icon:
			if zim.fs.isfile(icon):
				return gtk.gdk.pixbuf_new_from_file_at_size(icon, w, h)
			else:
				return None
		else:
			theme = gtk.icon_theme_get_default()
			try:
				pixbuf = theme.load_icon(icon.encode('utf-8'), w, 0)
			except Exception, error:
				#~ logger.exception('Foo')
				return None
			return pixbuf

	def parse_exec(self, args=None):
		'''Parse the 'Exec' string and interpolate the arguments
		according to the keys of the desktop spec.
		@param args: list of either URLs or L{File} objects
		@returns: the full command to execute as a tuple
		'''
		assert args is None or isinstance(args, (list, tuple))

		def uris(args):
			uris = []
			for arg in args:
				if isinstance(arg, (File, Dir)):
					uris.append(arg.uri)
				else:
					uris.append(unicode(arg))
			return uris

		cmd = split_quoted_strings(self['Desktop Entry']['Exec'])
		if args is None or len(args) == 0:
			if '%f' in cmd: cmd.remove('%f')
			elif '%F' in cmd: cmd.remove('%F')
			elif '%u' in cmd: cmd.remove('%u')
			elif '%U' in cmd: cmd.remove('%U')
		elif '%f' in cmd:
			assert len(args) == 1, 'application takes one file name'
			i = cmd.index('%f')
			cmd[i] = unicode(args[0])
		elif '%F' in cmd:
			i = cmd.index('%F')
			for arg in reversed(map(unicode, args)):
				cmd.insert(i, unicode(arg))
			cmd.remove('%F')
		elif '%u' in cmd:
			assert len(args) == 1, 'application takes one url'
			i = cmd.index('%u')
			cmd[i] = uris(args)[0]
		elif '%U' in cmd:
			i = cmd.index('%U')
			for arg in reversed(uris(args)):
				cmd.insert(i, unicode(arg))
			cmd.remove('%U')
		else:
			cmd.extend(map(unicode, args))

		if '%i' in cmd:
			if 'Icon' in self['Desktop Entry']:
				i = cmd.index('%i')
				cmd[i] = self['Desktop Entry']['Icon']
				cmd.insert(i, '--icon')
			else:
				cmd.remove('%i')

		if '%c' in cmd:
			i = cmd.index('%c')
			cmd[i] = self.name

		if '%k' in cmd:
			i = cmd.index('%k')
			if hasattr(self, 'file'):
				cmd[i] = self.file.path
			else:
				cmd[i] = ''

		return tuple(cmd)

	_cmd = parse_exec # To hook into Application.spawn and Application.run

	def update(self, E=None, **F):
		'''Same as C{dict.update()}'''
		self['Desktop Entry'].update(E, **F)

	def _decode_value(self, value):
		if value == 'true': return True
		elif value == 'false': return False
		else:
			try:
				value = float(value)
				return value
			except:
				return json.loads('"%s"' % value.replace('"', '\\"')) # force string

	def _encode_value(self, value):
		if value is None: return ''
		elif value is True: return 'true'
		elif value is False: return 'false'
		elif isinstance(value, int) or isinstance(value, float):
			return value.__str__()
		elif isinstance(value, File):
			return value.path # Icon can be file
		else:
			assert isinstance(value, basestring), 'Desktop files can not store complex data'
			return json.dumps(value)[1:-1].replace('\\"', '"') # get rid of quotes


class DesktopEntryFile(ConfigFile, DesktopEntryDict):
	'''Class implementing a single desktop entry file with the
	definition of an external application.
	'''

	@property
	def key(self):
		return self.file.basename[:-8] # len('.desktop') is 8


class OpenWithMenu(gtk.Menu):
	'''Sub-class of C{gtk.Menu} implementing an "Open With..." menu with
	applications to open a specific file. Also has an item
	"Open with Other Application...", which opens a
	L{NewApplicationDialog} and allows the user to add custom commands.
	'''

	OTHER_APP = _('Open with Other Application') + '...'
		# T: label to pop dialog with more applications in 'open with' menu

	def __init__(self, file, mimetype=None):
		'''Constructor

		@param file: the file to open when a menu item is activated
		@param mimetype: the mime-type of the application, if already
		known. Providing this arguments prevents redundant lookups of
		the type (which is slow).
		'''
		gtk.Menu.__init__(self)
		self. file = file
		if mimetype is None:
			mimetype = file.get_mimetype()

		manager = ApplicationManager()
		for entry in manager.list_applications(mimetype):
			item = DesktopEntryMenuItem(entry)
			self.append(item)
			item.connect('activate', self.on_activate)

		item = gtk.MenuItem(self.OTHER_APP)
		item.connect('activate', self.on_activate_other_app, mimetype)
		self.append(item)

	def on_activate(self, menuitem):
		entry = menuitem.entry
		entry.spawn((self.file,))

	def on_activate_other_app(self, menuitem, mimetype):
		NewApplicationDialog(None, mimetype=mimetype).run()


class DesktopEntryMenuItem(gtk.ImageMenuItem):
	'''Single menu item for the L{OpenWithMenu}. Displays the application
	name and the icon.
	'''

	def __init__(self, entry):
		'''Constructor

		@param entry: the L{DesktopEntryFile}
		'''
		text = _('Open with "%s"') % entry.name
			# T: menu item to open a file with an application, %s is the app name
		gtk.ImageMenuItem.__init__(self, text)
		self.entry = entry

		if hasattr(entry, 'get_pixbuf'):
			pixbuf = entry.get_pixbuf(gtk.ICON_SIZE_MENU)
			if pixbuf:
				self.set_image(gtk.image_new_from_pixbuf(pixbuf))


class NewApplicationDialog(Dialog):
	'''Dialog to prompt the user for a new custom command.
	Allows to input an application name and a command, and calls
	either L{ApplicationManager.create()} or
	L{ApplicationManager.create_helper()} with the correct parameters.
	'''

	def __init__(self, ui, mimetype=None, type=None):
		'''Constructor

		You must provide either C{mimetype} or C{type}.

		@param ui: the parent window or C{GtkInterface} object
		@param mimetype: mime-type for which we want to create a new
		application
		@param type: helper type for which we want to create a new command
		'''
		assert mimetype or type
		Dialog.__init__(self, ui, _('Custom Command')) # T: Dialog title
		self.apptype = type
		self.mimetype = mimetype
		self.add_form( (
			('name', 'string', _('Name')), # T: Field in 'custom command' dialog
			('exec', 'string', _('Command')), # T: Field in 'custom command' dialog
		) )

	def do_response_ok(self):
		name = self.form['name']
		cmd = self.form['exec']
		if not (name and cmd):
			return False

		manager = ApplicationManager()
		if self.mimetype:
			application = manager.create(self.mimetype, name, cmd)
		else:
			application = manager.create_helper(self.apptype, name, cmd)
		self.result = application
		return True


class CustomToolManager(object):
	'''Manager for dealing with the desktop files which are used to
	store custom tools.

	Custom tools are external commands that are intended to show in the
	"Tools" menu in zim (and optionally in the tool bar). They are
	defined as desktop entry files in a special folder (typically
	"~/.local/share/zim/customtools") and use several non standard keys.
	See L{CustomTool} for details.

	This object is iterable and maintains a specific order for tools
	to be shown in in the user interface.
	'''

	def __init__(self):
		self.names = []
		self.tools = {}
		self._read_list()

	def _read_list(self):
		list = config_file('customtools/customtools.list')
		seen = set()
		for line in list:
			name = line.strip()
			if not name in seen:
				seen.add(name)
				self.names.append(name)

	def _write_list(self):
		list = config_file('customtools/customtools.list')
		list[:] = [name + '\n' for name in self.names]
		list.write()

	def __iter__(self):
		for name in self.names:
			tool = self.get_tool(name)
			if tool and tool.isvalid():
				yield tool

	def get_tool(self, name):
		'''Get a L{CustomTool} by name.
		@param name: the tool name
		@returns: a L{CustomTool} object
		'''
		if not name in self.tools:
			tool = config_file('customtools/%s.desktop' % name, klass=CustomTool)
			self.tools[name] = tool

		return self.tools[name]

	def create(self, Name, **properties):
		'''Create a new custom tool

		@param Name: the name to show in the Tools menu
		@param properties: properties for the custom tool, e.g.:
		  - Comment
		  - Icon
		  - X-Zim-ExecTool
		  - X-Zim-ReadOnly
		  - X-Zim-ShowInToolBar

		@returns: a new L{CustomTool} object.
		'''
		properties['Type'] = 'X-Zim-CustomTool'
		dir = XDG_CONFIG_HOME.subdir('zim/customtools')
		tool = _create_application(dir, Name, '', klass=CustomTool, **properties)
		self.tools[tool.key] = tool
		self.names.append(tool.key)
		self._write_list()

		return tool

	def delete(self, tool):
		'''Remove a custom tool from the list and delete the definition
		file.
		@param tool: a custom tool name or L{CustomTool} object
		'''
		if not isinstance(tool, CustomTool):
			tool = self.get_tool(tool)
		tool.file.remove()
		self.tools.pop(tool.key)
		self.names.remove(tool.key)
		self._write_list()

	def index(self, tool):
		'''Get the position of a specific tool in the list.
		@param tool: a custom tool name or L{CustomTool} object
		@returns: an integer for the position
		'''
		if isinstance(tool, CustomTool):
			tool = tool.key
		return self.names.index(tool)

	def reorder(self, tool, i):
		'''Change the position of a tool in the list.
		@param tool: a custom tool name or L{CustomTool} object
		@param i: the new position as integer
		'''
		if not 0 <= i < len(self.names):
			return

		if isinstance(tool, CustomTool):
			tool = tool.key

		j = self.names.index(tool)
		self.names.pop(j)
		self.names.insert(i, tool)
		# Insert before i. If i was before old position indeed before
		# old item at that position. However if i was after old position
		# if shifted due to the pop(), now it inserts after the old item.
		# This is intended behavior to make all moves possible.
		self._write_list()


class CustomToolDict(DesktopEntryDict):
	'''This is a specialized desktop entry type that is used for
	custom tools for the "Tools" menu in zim. It uses a non-standard
	Exec spec with zim specific escapes for "X-Zim-ExecTool".

	The following fields are expanded:
		- C{%f} for source file as tmp file current page
		- C{%d} for attachment directory
		- C{%s} for real source file (if any)
		- C{%n} for notebook location (file or directory)
		- C{%D} for document root
		- C{%t} for selected text or word under cursor
		- C{%T} for the selected text including wiki formatting

	Other additional keys are:
		- C{X-Zim-ReadOnly} - boolean
		- C{X-Zim-ShowInToolBar} - boolean
		- C{X-Zim-ShowInContextMenu} - 'None', 'Text' or 'Page'

	These tools should always be executed with 3 arguments: notebook,
	page & pageview.
	'''

	def isvalid(self):
		'''Check if all required fields are set.
		@returns: C{True} if all required fields are set
		'''
		entry = self['Desktop Entry']
		if entry.get('Type') == 'X-Zim-CustomTool' \
		and entry.get('Version') == 1.0 \
		and entry.get('Name') \
		and entry.get('X-Zim-ExecTool') \
		and not entry.get('X-Zim-ReadOnly') is None \
		and not entry.get('X-Zim-ShowInToolBar') is None \
		and 'X-Zim-ShowInContextMenu' in entry:
			return True
		else:
			logger.error('Invalid custom tool entry: %s %s', self.key, entry)
			return False

	def get_pixbuf(self, size):
		pixbuf = DesktopEntryDict.get_pixbuf(self, size)
		if pixbuf is None:
			pixbuf = gtk.Label().render_icon(gtk.STOCK_EXECUTE, size)
			# FIXME hack to use arbitrary widget to render icon
		return pixbuf

	@property
	def icon(self):
		return self['Desktop Entry'].get('Icon', gtk.STOCK_EXECUTE)

	@property
	def execcmd(self):
		return self['Desktop Entry']['X-Zim-ExecTool']

	@property
	def isreadonly(self):
		return self['Desktop Entry']['X-Zim-ReadOnly']

	@property
	def showintoolbar(self):
		return self['Desktop Entry']['X-Zim-ShowInToolBar']

	@property
	def showincontextmenu(self):
		return self['Desktop Entry']['X-Zim-ShowInContextMenu']

	def parse_exec(self, args=None):
		if not (isinstance(args, tuple) and len(args) == 3):
			raise AssertionError, 'Custom commands needs 3 arguments'
			# assert statement could be optimized away
		notebook, page, pageview = args

		cmd = split_quoted_strings(self['Desktop Entry']['X-Zim-ExecTool'])
		if '%f' in cmd:
			self._tmpfile = TmpFile('tmp-page-source.txt')
			self._tmpfile.writelines(page.dump('wiki'))
			cmd[cmd.index('%f')] = self._tmpfile.path

		if '%d' in cmd:
			dir = notebook.get_attachments_dir(page)
			if dir:
				cmd[cmd.index('%d')] = dir.path
			else:
				cmd[cmd.index('%d')] = ''

		if '%s' in cmd:
			if hasattr(page, 'source') and isinstance(page.source, File):
				cmd[cmd.index('%s')] = page.source.path
			else:
				cmd[cmd.index('%s')] = ''

		if '%n' in cmd:
			cmd[cmd.index('%n')] = File(notebook.uri).path

		if '%D' in cmd:
			dir = notebook.document_root
			if dir:
				cmd[cmd.index('%D')] = dir.path
			else:
				cmd[cmd.index('%D')] = ''

		if '%t' in cmd:
			text = pageview.get_selection() or pageview.get_word()
			cmd[cmd.index('%t')] = text or ''
			# FIXME - need to substitute this in arguments + url encoding

		if '%T' in cmd:
			text = pageview.get_selection(format='wiki') or pageview.get_word(format='wiki')
			cmd[cmd.index('%T')] = text or ''
			# FIXME - need to substitute this in arguments + url encoding

		return tuple(cmd)

	_cmd = parse_exec # To hook into Application.spawn and Application.run

	def run(self, args):
		self._tmpfile = None
		Application.run(self, args)
		if self._tmpfile:
			notebook, page, pageview = args
			page.parse('wiki', self._tmpfile.readlines())
			self._tmpfile = None

	def update(self, E=None, **F):
		self['Desktop Entry'].update(E, **F)

		# Set sane default for X-Zim-ShowInContextMenus
		if not (E and 'X-Zim-ShowInContextMenu' in E) \
		and not 'X-Zim-ShowInContextMenu' in F:
			cmd = split_quoted_strings(self['Desktop Entry']['X-Zim-ExecTool'])
			if any(c in cmd for c in ['%f', '%d', '%s']):
				context = 'Page'
			elif '%t' in cmd:
				context = 'Text'
			else:
				context = None
			self['Desktop Entry']['X-Zim-ShowInContextMenu'] = context


class CustomTool(CustomToolDict, DesktopEntryFile):
	'''Class representing a file defining a custom tool, see
	L{CustomToolDict} for the API documentation.
	'''
	pass
