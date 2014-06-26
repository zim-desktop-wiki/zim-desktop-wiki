# -*- coding: utf-8 -*-

# Copyright 2009,2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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

import os
import logging
import gtk
import gobject

import zim.fs
from zim.fs import File, Dir, TmpFile, cleanup_filename
from zim.config import XDG_DATA_HOME, XDG_DATA_DIRS, XDG_CONFIG_HOME, \
	data_dirs, SectionedConfigDict, INIConfigFile, json, ConfigManager
from zim.parsing import split_quoted_strings, uri_scheme
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


def _create_application(dir, Name, Exec, klass=None, NoDisplay=True, **param):
	n = cleanup_filename(Name.lower()) + '-usercreated'
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
	entry.update(
		Type=param.pop('Type', 'Application'),
		Version=1.0,
		NoDisplay=NoDisplay,
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


def get_mimetype(obj):
	'''Convenience method to get the mimetype for a file or url.
	For URLs this method results in "x-scheme-handler" mimetypes.
	@param obj: a L{File} object, or an URL
	@returns: mimetype or C{None}
	'''
	if isinstance(obj, File):
		return obj.get_mimetype()
	else:
		scheme = uri_scheme(obj)
		if scheme in (None, 'file'):
			try:
				return File(obj).get_mimetype()
			except:
				return None
		else:
			return "x-scheme-handler/%s" % scheme


class ApplicationManager(object):
	'''Manager object for dealing with desktop applications. Uses the
	freedesktop.org (XDG) system to locate desktop entry files for
	installed applications.
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
		if name.endswith('.desktop'):
			key = name
		else:
			key = name + '.desktop'

		file = _application_file(key, _application_dirs())
		if file:
			return DesktopEntryFile(File(file))
		elif name == 'webbrowser':
			return WebBrowser()
		elif name == 'startfile':
			return StartFile()
		else:
			return None

	@classmethod
	def get_default_application(klass, mimetype):
		'''Get the default application to open a file with a specific mimetype.
		It searches C{applications/defaults.list} files to lookup the application.
		@param mimetype: the mime-type of the file (e.g. "text/html")
		@returns: an L{Application} object or C{None}
		'''
		## Based on logic from xdg-mime defapp_generic()
		## Obtained from http://portland.freedesktop.org/wiki/ (2012-05-31)
		##
		## Considered calling xdg-mime directly with code below as fallback.
		## But xdg-mime has only a special case for KDE, all others are generic.
		## Our purpose is to be able to set defaults ourselves and read them back.
		## If we fail we fallback to opening files with the file browser which
		## defaults to xdg-open. So even if the system does not support the
		## generic implementation, it will behave sanely and fall back to system
		## defaults.

		## TODO: optimize for being called very often ?

		for dir in _application_dirs():
			default_file = dir.file('defaults.list')
			if not default_file.exists():
				continue

			for line in default_file.readlines():
				if line.startswith(mimetype + '='):
					_, key = line.strip().split('=', 1)
					for k in key.split(';'):
						# Copied logic from xdg-mime, apparently entries
						# can be ";" seperated lists
						k = k.strip()
						application = klass.get_application(k)
						if application is not None:
							return application
						# else continue searching
		else:
			return None

	@staticmethod
	def set_default_application(mimetype, application):
		'''Set the default application to open a file with a specific
		mimetype. Updates the C{applications/defaults.list} file.
		As a special case when you set the default to C{None} it will
		remove the entry from C{defauts.list} allowing system defaults
		to be used again.
		@param mimetype: the mime-type of the file (e.g. "text/html")
		@param application: an L{Application} object or C{None}
		'''
		## Based on logic from xdg-mime make_default_generic()
		## Obtained from http://portland.freedesktop.org/wiki/ (2012-05-31)
		##
		## See comment in get_default_application()

		if application is not None:
			if not isinstance(application, basestring):
				application = application.key

			if not application.endswith('.desktop'):
				application += '.desktop'

		default_file = XDG_DATA_HOME.file('applications/defaults.list')
		if default_file.exists():
			lines = default_file.readlines()
			lines = [l for l in lines if not l.startswith(mimetype + '=')]
		else:
			lines = ['[Default Applications]\n']

		if application:
			lines.append('%s=%s\n' % (mimetype, application))
		default_file.writelines(lines)

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
		return file

	@classmethod
	def get_fallback_filebrowser(klass):
		# Don't use mimetype lookup here, this is a fallback
		# should handle all file types
		if os.name == 'nt':
			return StartFile()
		elif os.name == 'darwin':
			app = Application('open')
		else: # linux and friends
			app = Application('xdg-open')

		if app.tryexec():
			return app
		else:
			return WebBrowser()
			# the webbrowser module uses many fallbacks that know
			# how to handle arbitrary files as well as URLs
			# We don't use it by default in all cases, because it
			# could be configured to an application that doesn't

	@classmethod
	def get_fallback_emailclient(klass):
		# Don't use mimetype lookup here, this is a fallback
		if os.name == 'nt':
			return StartFile()
		elif os.name == 'darwin':
			app = Application('open')
		else: # linux and friends
			app = Application('xdg-email')

		if app.tryexec():
			return app
		else:
			return WebBrowser()
			# the webbrowser module uses many fallbacks that know
			# how to handle "mailto:" URLs
			# We don't use it by default in all cases, because it
			# could be configured to an application that doesn't

	@classmethod
	def get_fallback_webbrowser(klass):
		# Don't use mimetype lookup here, this is a fallback
		# should handle all URL types
		# The webbrowser module knows about utils like xdg-open
		# so will find the right thing to do one way or the other
		return WebBrowser()

	@classmethod
	def list_applications(klass, mimetype, nodisplay=False):
		'''Get a list of applications that can handle a specific file
		type.
		@param mimetype: the mime-type of the file (e.g. "text/html")
		@param nodisplay: if C{True} also entries that have the
		C{NoDisplay} flag are included
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

		if mimetype in ('x-scheme-handler/http', 'x-scheme-handler/https'):
			# Since "x-scheme-handler" is not in the standard, some browsers
			# only identify themselves with "text/html".
			for entry in klass.list_applications('text/html', nodisplay): # recurs
				basename = entry.key + '.desktop'
				if not basename in seen:
					entries.append(entry)
					seen.add(basename)

		if not nodisplay:
			entries = [e for e in entries if not e.nodisplay]

		return entries


from zim.config import String as BaseString
from zim.config import Boolean as BaseBoolean
from zim.config import Float as Numeric

class String(BaseString):

	def check(self, value):
		# Only ascii chars allowed in these keys
		value = BaseString.check(self, value)
		if isinstance(value, unicode) \
		and value.encode('utf-8') != value:
			raise ValueError, 'ASCII string required'
		return value


class LocaleString(BaseString):
	pass # utf8 already supported by default


class Boolean(BaseBoolean):

	def tostring(self, value):
		# Desktop entry specs "true" and "false"
		return str(value).lower()



class DesktopEntryDict(SectionedConfigDict, Application):
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

	__repr__ = Application.__repr__

	_definitions = (
		# Data types for all keys are defined in spec - see freedesktop.org
		# Don't define all keys in the spec, just define the ones that we might use
		('Type',		String('Application')),
		('Version',		Numeric(1.0)),
		('GenericName',	LocaleString(None)),
		('Name',		LocaleString(None)),
		('Comment',		LocaleString(None)),
		('Exec',		String(None)),
		('TryExec',		String(None)),
		('Icon',		LocaleString(None)),
		('MimeType',	String(None)),
		('Terminal',	Boolean(False)),
		('NoDisplay',	Boolean(False)),
	)

	def __init__(self):
		SectionedConfigDict.__init__(self)
		self['Desktop Entry'].define(self._definitions)
		self.encoding = zim.fs.ENCODING
		if self.encoding == 'mbcs':
			self.encoding = 'utf-8'

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
		return self['Desktop Entry']['Comment'] or ''

	@property
	def nodisplay(self):
		return self['Desktop Entry'].get('NoDisplay', False)

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
			if 'Icon' in self['Desktop Entry'] \
			and self['Desktop Entry']['Icon']:
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

	def update(self, E=(), **F):
		'''Same as C{dict.update()}'''
		self['Desktop Entry'].update(E, **F)


class DesktopEntryFile(DesktopEntryDict, INIConfigFile):
	'''Class implementing a single desktop entry file with the
	definition of an external application.
	'''

	def __init__(self, file):
		DesktopEntryDict.__init__(self)
		INIConfigFile.__init__(self, file)

	@property
	def key(self):
		return self.file.basename[:-8] # len('.desktop') is 8


class OpenWithMenu(gtk.Menu):
	'''Sub-class of C{gtk.Menu} implementing an "Open With..." menu with
	applications to open a specific file. Also has an item
	"Customize...", which opens a L{CustomizeOpenWithDialog}
	and allows the user to add custom commands.
	'''

	CUSTOMIZE = _('Customize...')
		# T: label to customize 'open with' menu

	def __init__(self, ui, file, mimetype=None):
		'''Constructor

		@param ui: main ui object, needed to pop dialogs correctly
		@param file: a L{File} object or URL
		@param mimetype: the mime-type of the application, if already
		known. Providing this arguments prevents redundant lookups of
		the type (which is slow).
		'''
		gtk.Menu.__init__(self)
		self.ui = ui
		self.file = file
		if mimetype is None:
			mimetype = get_mimetype(file)
		self.mimetype = mimetype

		manager = ApplicationManager()
		for entry in manager.list_applications(mimetype):
			item = DesktopEntryMenuItem(entry)
			self.append(item)
			item.connect('activate', self.on_activate)

		if not self.get_children():
			item = gtk.MenuItem(_('No Applications Found'))
				# T: message when no applications in "Open With" menu
			item.set_sensitive(False)
			self.append(item)

		self.append(gtk.SeparatorMenuItem())

		item = gtk.MenuItem(self.CUSTOMIZE)
		item.connect('activate', self.on_activate_customize, mimetype)
		self.append(item)

	def on_activate(self, menuitem):
		entry = menuitem.entry
		entry.spawn((self.file,))

	def on_activate_customize(self, o, mimetype):
		CustomizeOpenWithDialog(self.ui, mimetype=mimetype).run()


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


def _mimetype_dialog_text(mimetype):
		if mimetype.startswith('x-scheme-handler/'):
			x, scheme = mimetype.split('/', 1)
			scheme += '://'
			return '<b>' + _('Configure an application to open "%s" links') % scheme + '</b>'
			# T: Text in the 'custom command' dialog, "%s" will be URL scheme like "http://" or "ssh://"
		else:
			return '<b>' + _('Configure an application to open files\nof type "%s"') % mimetype + '</b>'
			# T: Text in the 'custom command' dialog, "%s" will be mimetype like "text/plain"


class CustomizeOpenWithDialog(Dialog):

	def __init__(self, ui, mimetype):
		'''Constructor
		@param ui: the parent window or C{GtkInterface} object
		@param mimetype: mime-type for which we want to create a new
		application
		'''
		Dialog.__init__(self, ui, _('Configure Applications'),  # T: Dialog title
			buttons=gtk.BUTTONS_CLOSE, help='Help:Default Applications')
		self.mimetype = mimetype
		self.add_text(_mimetype_dialog_text(mimetype))

		# Combo to set default
		self.default_combo = ApplicationComboBox()
		self.default_combo.connect('changed', self.on_default_changed)
		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)
		hbox.pack_start(gtk.Label(_('Default')+':'), False) # T: label for default application
		hbox.pack_start(self.default_combo)

		# Button to add new
		button = gtk.Button(_('Add Application'))
			# T: Button for adding a new application to the 'open with' menu
		button.connect('clicked', self.on_add_application)
		self.add_extra_button(button)

		self.reload()

	def reload(self):
		combo = self.default_combo
		combo.handler_block_by_func(self.on_default_changed)
		combo.clear()

		default = ApplicationManager.get_default_application(self.mimetype)
		sysdefault = SystemDefault()
		if default:
			combo.append(default)
		else:
			combo.append(sysdefault)

		for app in ApplicationManager.list_applications(self.mimetype, nodisplay=True):
			# list all custom commands, including those that have NoDisplay set
			if default and app.key == default.key:
				continue
			else:
				combo.append(app)

		if default:
			combo.append(sysdefault) # append to end

		combo.set_active(0)
		combo.handler_unblock_by_func(self.on_default_changed)

	def on_default_changed(self, combo):
		app = combo.get_active()
		logger.info('Default application for type "%s" changed to: %s', self.mimetype, app.name)
		if isinstance(app, SystemDefault):
			ApplicationManager.set_default_application(self.mimetype, None)
		else:
			ApplicationManager.set_default_application(self.mimetype, app)

	def on_add_application(self, button):
		AddApplicationDialog(self, self.mimetype).run()
		self.reload()


class SystemDefault(object):
	'''Stub object that can be used in L{ApplicationComboBox}'''

	name = _('System Default') # T: Label for default application handler



class ApplicationComboBox(gtk.ComboBox):

	NAME_COL = 0
	APP_COL = 1
	ICON_COL = 2

	def __init__(self):
		model = gtk.ListStore(str, object, gtk.gdk.Pixbuf) # NAME_COL, APP_COL, ICON_COL
		gtk.ComboBox.__init__(self, model)

		cell = gtk.CellRendererPixbuf()
		self.pack_start(cell, False)
		cell.set_property('xpad', 5)
		self.add_attribute(cell, 'pixbuf', self.ICON_COL)

		cell = gtk.CellRendererText()
		self.pack_start(cell, True)
		cell.set_property('xalign', 0.0)
		cell.set_property('xpad', 5)
		self.add_attribute(cell, 'text', self.NAME_COL)

	def clear(self):
		self.get_model().clear()

	def append(self, application):
		model = self.get_model()
		if hasattr(application, 'get_pixbuf'):
			pixbuf = application.get_pixbuf(gtk.ICON_SIZE_MENU)
		else:
			pixbuf = self.render_icon(gtk.STOCK_EXECUTE, gtk.ICON_SIZE_MENU)

		model.append((application.name, application, pixbuf)) # NAME_COL, APP_COL, ICON_COL

	def get_active(self):
		model = self.get_model()
		iter = self.get_active_iter()
		if iter:
			return model[iter][self.APP_COL]
		else:
			return None


class AddApplicationDialog(Dialog):
	'''Dialog to prompt the user for a new custom command.
	Allows to input an application name and a command, and calls
	L{ApplicationManager.create()}.
	'''

	def __init__(self, ui, mimetype):
		'''Constructor
		@param ui: the parent window or C{GtkInterface} object
		@param mimetype: mime-type for which we want to create a new
		application
		'''
		Dialog.__init__(self, ui, _('Add Application')) # T: Dialog title
		self.mimetype = mimetype
		self.add_text(_mimetype_dialog_text(mimetype))
		self.add_form( (
			('name', 'string', _('Name')), # T: Field in 'custom command' dialog
			('exec', 'string', _('Command')), # T: Field in 'custom command' dialog
			('default', 'bool', _('Make default application')), # T: Field in 'custom command' dialog
		) )
		self.form['default'] = True

	def do_response_ok(self):
		name = self.form['name']
		cmd = self.form['exec']
		default = self.form['default']
		if not (name and cmd):
			return False

		manager = ApplicationManager()
		application = manager.create(self.mimetype, name, cmd, NoDisplay=default)
			# Default implies NoDisplay, this to keep the list
			# more or less clean.

		if not application.tryexec():
			ErrorDialog(self, _('Could not find executable "%s"') % application.cmd[0]).run()
				# T: Error message for new commands in "open with" dialog
			application.file.remove()
			return False

		if default:
			manager.set_default_application(self.mimetype, application)

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
		self.config = ConfigManager() # XXX should be passed in
		self.names = []
		self.tools = {}
		self._read_list()

	def _read_list(self):
		file = self.config.get_config_file('customtools/customtools.list')
		seen = set()
		for line in file.readlines():
			name = line.strip()
			if not name in seen:
				seen.add(name)
				self.names.append(name)

	def _write_list(self):
		file = self.config.get_config_file('customtools/customtools.list')
		file.writelines([name + '\n' for name in self.names])

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
			file = self.config.get_config_file('customtools/%s.desktop' % name)
			tool = CustomTool(file)
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
		tool = _create_application(dir, Name, '', klass=CustomTool, NoDisplay=False, **properties)
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



from zim.config import Choice

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

	_definitions = DesktopEntryDict._definitions + (
			('X-Zim-ExecTool',			String(None)),
			('X-Zim-ReadOnly',			Boolean(True)),
			('X-Zim-ShowInToolBar',		Boolean(False)),
			('X-Zim-ShowInContextMenu',	Choice(None, ('Text', 'Page'))),
			('X-Zim-ReplaceSelection',	Boolean(False)),
	)

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
		return self['Desktop Entry'].get('Icon') or gtk.STOCK_EXECUTE
			# get('Icon', gtk.STOCK_EXECUTE) still returns empty string if key exists but no value

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

	@property
	def replaceselection(self):
		return self['Desktop Entry']['X-Zim-ReplaceSelection']

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

	def update(self, E=(), **F):
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


class CustomTool(CustomToolDict, INIConfigFile):
	'''Class representing a file defining a custom tool, see
	L{CustomToolDict} for the API documentation.
	'''

	def __init__(self, file):
		CustomToolDict.__init__(self)
		INIConfigFile.__init__(self, file)

	@property
	def key(self):
		return self.file.basename[:-8] # len('.desktop') is 8

