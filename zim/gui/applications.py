# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''This module contains utilities to work with external applications
it is based on the Freedesktop.org (XDG) Desktop Entry specification
with some additional logic based on status quo on Gnome / XFCE.

The desktop entry class subclasses the Apllication class from zim.applications,
see there for methods to run or spawn applications.
'''

import os
import logging
import gtk
import gobject

from zim.fs import *
from zim.config import data_dirs, XDG_DATA_HOME, XDG_DATA_DIRS, \
	ConfigDict, ConfigFile, json
from zim.parsing import split_quoted_strings
from zim.applications import Application, WebBrowser, StartFile
from zim.gui.widgets import Dialog, ErrorDialog


logger = logging.getLogger('zim.gui.applications')


def _application_dirs():
	# Generator for application directories, first check zim specific paths,
	# then general applications
	for dir in data_dirs('applications'):
		yield dir

	yield XDG_DATA_HOME.subdir('applications')

	for dir in XDG_DATA_DIRS:
		yield dir.subdir('applications')


def _application_file(path, dirs):
	# Some logic to chekc multiple options, e.g. a path of kde-foo.desktop
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


def get_application(name):
	file = _application_file(name + '.desktop', _application_dirs())
	if file:
		return DesktopEntryFile(File(file))
	elif name == 'webbrowser':
		return WebBrowser()
	elif name == 'startfile':
		return StartFile()
	else:
		return None


def get_applications(mimetype):
	seen = set()
	entries = []
	key = '%s=' % mimetype
	for dir in _application_dirs():
		cache = dir.file('mimeinfo.cache')
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


def get_default_application(mimetype):
	pass # TODO: get default from defaults.list


def set_default_application(mimetype, name):
	pass # TODO: set new value for mimetype in default.list


def get_helper_applications(type):
	'''Returns a list of known applications that can be used as a helper
	of a certain type.
	Type can e.g. be 'web_browser', 'file_browser' or 'email_client'.
	'''
	# Be aware that X-Zim-AppType can be a list of types
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
				if ('X-Zim-AppType' in entry['Desktop Entry']
				and type in entry['Desktop Entry']['X-Zim-AppType']):
					helpers.append(entry)

	if type == 'web_browser':
		for entry in get_applications('text/html'):
			if not entry.key in seen:
				helpers.append(entry)
				seen.add(entry.key)
	
	if not 'startfile' in seen:
		helpers.append( get_application('startfile') )

	helpers = [helper for helper in helpers if helper.tryexec()]
	return helpers


def create_application(mimetype, Name, Exec, **param):
	'''Creates a desktop entry file for a new usercreated desktop entry
	which defines a custom command to handle a certain file type.
	Returns the DesktopEntryFile object with some
	sensible defaults for a user created application entry.
	To know the key to retrieve this application later look at the
	'key' property of the entry object.
	'''
	dir = XDG_DATA_HOME.subdir('applications')
	param['MimeType'] = mimetype
	file = _create_application(dir, Name, Exec, **param)
	set_default_application(mimetype, key)
	return file


def create_helper_application(type, Name, Exec, **param):
	'''Like create_mime_application() but defines a zim specific helper.
	Type can e.g. be 'web_browser', 'file_browser' or 'email_client'.
	'''
	dir = XDG_DATA_HOME.subdir('zim/applications')
	param['X-Zim-AppType'] = type
	return _create_application(dir, Name, Exec, **param)


def _create_application(dir, Name, Exec, **param):
	n = Name.lower() + '-usercreated'
	key = n
	file = dir.file('applications', key + '.desktop')
	i = 0
	while file.exists():
		assert i < 1000, 'BUG: Infinite loop ?'
		i += 1
		key = n + '-' + str(i)
		file = dir.file('applications', key + '.desktop')
	entry = DesktopEntryFile(file)
	entry['Desktop Entry'].update(
		Type='Application',
		Version=1.0,
		NoDisplay=True,
		Name=Name,
		Exec=Exec
		**param
	)
	assert entry.isvalid(), 'BUG: created invalid desktop entry'
	entry.write()
	return entry


class DesktopEntryDict(ConfigDict, Application):
	'''Base class for DesktopEntryFile. Defines all the logic to work with
	desktop entry files. A desktop entry files describes all you need to know
	about an external application.
	'''

	def isvalid(self):
		'''Validate all the required fields are set. Assumes we only
		use desktop files to describe applications. Returns boolean
		for success.
		'''
		entry = self['Desktop Entry']
		try:
			assert 'Type' in entry and entry['Type'] == 'Application', '"Type" missing or invalid'
			assert 'Name' in entry, '"Name" missing'
			assert 'Exec' in entry, '"Exec" missing'
			if 'Version' in entry:
				assert entry['Version'] == 1.0, 'Version invalid'
		except AssertionError:
			logger.exception('Invalid desktop entry:')
			return False
		else:
			return True

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

	def get_pixbuf(self):
		if 'Icon' in self['Desktop Entry']:
			icon = self['Desktop Entry']['Icon']
		else:
			return None

		w, h = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)
		if '/' in icon:
			if os.path.isfile(icon):
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
		'''Returns a list of command and arguments that can be used to
		open this application. Args can be either File objects or urls.
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

	def _decode_desktop_value(self, value):
		if value == 'true': return True
		elif value == 'false': return False
		else:
			try:
				value = float(value)
				return value
			except:
				return json.loads('"%s"' % value.replace('"', '\\"')) # force string

	def _encode_value(self, value):
		if value is True: return 'true'
		elif value is False: return 'false'
		elif isinstance(value, int) or isinstance(value, float):
			value = value.__str__()
		else:
			assert isinstance(value, basestring), 'Desktop files can not store complex data'
			return json.dumps(value)[1:-1] # get rid of quotes


class DesktopEntryFile(ConfigFile, DesktopEntryDict):

	@property
	def key(self):
		return self.file.basename[:-8] # len('.desktop') is 8


class OpenWithMenu(gtk.Menu):

	def __init__(self, file, mimetype=None):
		gtk.Menu.__init__(self)
		self. file = file
		if mimetype is None:
			mimetype = file.get_mimetype()

		for entry in get_applications(mimetype):
			item = DesktopEntryMenuItem(entry)
			self.append(item)
			item.connect('activate', self.on_activate)

	def on_activate(self, menuitem):
		entry = menuitem.entry
		entry.spawn((self.file,))


class DesktopEntryMenuItem(gtk.ImageMenuItem):

	def __init__(self, entry):
		text = _('Open with "%s"') % entry.name
			# T: menu item to open a file with an application, %s is the app name
		gtk.ImageMenuItem.__init__(self, text)
		self.entry = entry

		if hasattr(entry, 'get_pixbuf'):
			pixbuf = entry.get_pixbuf()
			if pixbuf:
				self.set_image(gtk.image_new_from_pixbuf(pixbuf))


class CustomCommandDialog(Dialog):

	def __init__(self, ui, type):
		Dialog.__init__(self, ui, _('Custom Command')) # T: Dialog title
		assert type in ('file_browser', 'web_browser', 'email_client')
		self.type = type
		self.add_fields(
			('name', 'string', _('Name'), ''), # T: Field in 'custom command' dialog
			('exec', 'string', _('Command'), ''), # T: Field in 'custom command' dialog
		)

	def do_response_ok(self):
		fields = self.get_fields()
		file = create_helper_application(self.type, fields['name'], fields['exec'])
		self.result = file
		return True
