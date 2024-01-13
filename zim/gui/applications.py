
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains utilities to work with external applications
it is based on the Freedesktop.org (XDG) Desktop Entry specification
with some additional logic based on status quo on Gnome / XFCE.

The main class is the L{DesktopEntryFile} which maps the application
definition in a specific desktop entry. Typically these are not
constructed directly, but requested through the L{ApplicationManager}.

Also there is the L{OpenWithMenu} which is the widget to render a menu
with available applications for a specific file plus a dialog so the
user can define a new command on the fly.
'''

import os
import sys
import re
import logging
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import GdkPixbuf

from zim.fs import adapt_from_oldfs

from zim.errors import Error
from zim.newfs import File, LocalFile, TmpFile, FileNotFoundError, \
	cleanup_filename, get_mimetype_from_path
from zim.config import XDG_CONFIG_HOME, XDG_CONFIG_DIRS, XDG_DATA_HOME, XDG_DATA_DIRS, \
	data_dirs, SectionedConfigDict, INIConfigFile, Boolean, ConfigManager
from zim.parsing import uri_scheme, is_win32_share_re, \
	normalize_win32_share, is_win32_share_re, is_url_re, is_uri_re, is_www_link_re
from zim.applications import Application, WebBrowser, StartFile, split_quoted_strings, ApplicationLookUpError
from zim.gui.widgets import Dialog, ErrorDialog, MessageDialog, QuestionDialog, strip_boolean_result




logger = logging.getLogger('zim.gui.applications')

ui_preferences = (
	# key, type, category, label, default
	('always_create_missing_dirs', 'bool', 'Interface',
		_('Create missing directories automatically\n(If disabled you will be prompted)'), True),
			# T: option in preferences dialog
)

def _application_file(path, dirs):
	# Some logic to check multiple options, e.g. a path of kde-foo.desktop
	# could also be stored as applications/kde/foo.desktop but not necessarily..
	paths = [path]
	if '-' in path:
		for i in range(1, path.count('-') + 1):
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

	yield XDG_DATA_HOME.folder('applications')

	for dir in XDG_DATA_DIRS:
		yield dir.folder('applications')


def _create_application(dir, basename, Name, Exec, NoDisplay=True, **param):
	file = dir.file(basename)
	i = 0
	while file.exists():
		assert i < 1000, 'BUG: Infinite loop ?'
		i += 1
		basename = basename[:-8] + '-' + str(i) + '.desktop'
		file = dir.file(basename)

	entry = DesktopEntryFile(file)
	entry.update(
		Type='Application',
		Version=1.0,
		NoDisplay=NoDisplay,
		Name=Name,
		Exec=Exec,
		**param
	)

	assert entry.isvalid(), 'BUG: created invalid desktop entry'
	entry.write()

	if param.get('MimeType'):
		mimetype = param.get('MimeType')

		# Update mimeapps
		defaults = XDG_CONFIG_HOME.file('mimeapps.list')
		_update_mimeapps_file(defaults, '[Added Associations]', mimetype, basename, replace=False)

		# Update mimetype cache
		cache = dir.file('mimeinfo.cache')
		_update_mimeapps_file(cache, '[MIME Cache]', mimetype, basename, replace=False)

	return entry


def get_mimetype(obj):
	'''Convenience method to get the mimetype for a file or url.
	For URLs this method results in "x-scheme-handler" mimetypes.
	@param obj: a L{File} object, or an URL
	@returns: mimetype or C{None}
	'''
	if hasattr(obj, 'mimetype'):
		return obj.mimetype()
	else:
		scheme = uri_scheme(obj)
		if scheme in (None, 'file'):
			try:
				return get_mimetype_from_path(FilePath(obj).uri)
			except:
				try:
					# Mal-formed or relative path, still valid mimetype from extension
					return get_mimetype_from_path(obj)
				except:
					logger.exception('Failed mimetype for %s')
					return None
		else:
			return "x-scheme-handler/%s" % scheme


try:
	from gi.repository import Gio
except ImportError:
	Gio = None

_last_warning_missing_icon = None
	# used to surpress redundant logging

def get_mime_icon(file, size):
	if not Gio:
		return None

	try:
		f = Gio.File.new_for_uri(file.uri)
		info = f.query_info('standard::*', Gio.FileQueryInfoFlags.NONE, None)
		icon = info.get_icon()
	except:
		logger.exception('Failed to query info for file: %s', file)
		return None

	global _last_warning_missing_icon

	if isinstance(icon, Gio.ThemedIcon):
		names = icon.get_names()
		icon_theme = Gtk.IconTheme.get_default()
		try:
			icon_info = icon_theme.choose_icon(names, size, 0)
			if icon_info:
				return icon_info.load_icon()
			else:
				if _last_warning_missing_icon != names:
					logger.debug('Missing icons in icon theme: %s', names)
					_last_warning_missing_icon = names
				return None
		except (GObject.GError, GLib.Error):
			logger.exception('Could not load icon for file: %s', file)
			return None
	else:
		return None


def get_mime_description(mimetype):
	# Check XML file /usr/share/mime/MEDIA/SUBTYPE.xml
	# Find element "comment" with "xml:lang" attribute for the locale
	from zim.config import XDG_DATA_HOME, XDG_DATA_DIRS

	media, subtype = mimetype.split('/', 1)
	for dir in [XDG_DATA_HOME] + XDG_DATA_DIRS:
		file = dir.file(('mime', media, subtype + '.xml'))
		if file.exists():
			return _read_comment_from(file)
	else:
		return None


def _read_comment_from(file):
	import locale
	from zim.formats import ElementTreeModule as et
	# Etree fills in the namespaces which obfuscates the names

	mylang, enc = locale.getdefaultlocale()
	xmlns = "{http://www.w3.org/XML/1998/namespace}"
	xml = et.parse(file.path)
	fallback = []
	#~ print("FIND COMMENT", file, mylang)
	for elt in xml.getroot():
		if elt.tag.endswith('comment'):
			lang = elt.attrib.get(xmlns + 'lang', '')
			if lang == mylang:
				return elt.text
			elif not lang or mylang and mylang.startswith(lang + '_'):
				fallback.append((lang, elt.text))
			else:
				pass
	else:
		#~ print("FALLBACK", fallback)
		if fallback:
			fallback.sort()
			return fallback[-1][1] # longest match
		else:
			return None

def _update_mimeapps_file(file, section, key, value, replace):
	assert section.startswith('[')
	assert not (not value and not replace)
	assert value is None or value.endswith('.desktop')
	key = key + '='

	if file.exists():
		lines = file.readlines()
	else:
		lines = [section + '\n']

	insert_location = None
	in_section = False
	for i, line in enumerate(lines):
		if line.startswith(section):
			in_section = True
			insert_location = i + 1
		elif in_section:
			if line.startswith(key):
				if replace:
					if value:
						lines[i] = key + value + '\n'
					else:
						lines[i] = ''
				else:
					lines[i] = key + value + ';' + lines[i][len(key):]
				break
			elif line.startswith('['):
				in_section = False
			elif not line.isspace():
				insert_location = i + 1
			else:
				pass # empty lines
	else:
		if value:
			if insert_location is None: # section not found - add it
				lines.extend(['\n', section + '\n', key + value + '\n'])
			else:
				lines.insert(insert_location, key + value + '\n')

	file.writelines(lines)



class ApplicationManager(object):
	'''Manager object for dealing with desktop applications. Uses the
	freedesktop.org (XDG) system to locate desktop entry files for
	installed applications.
	'''

	_defaults_app_cache = {}

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
			return DesktopEntryFile(LocalFile(file))
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
		# TODO: also check timestamp of mimeapps for validity of the cache ?
		if mimetype in klass._defaults_app_cache \
			and klass._defaults_app_cache[mimetype] is not None \
				and not klass._defaults_app_cache[mimetype].file.exists():
					del klass._defaults_app_cache[mimetype]

		if mimetype not in klass._defaults_app_cache:
			klass._defaults_app_cache[mimetype] = klass._get_default_application(mimetype)

		return klass._defaults_app_cache[mimetype]

	@staticmethod
	def _mimeapps_files():
		desktops = []
		if os.environ.get('XDG_CURRENT_DESKTOP'):
			desktops = os.environ['XDG_CURRENT_DESKTOP'].split(';')
		folders = [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS
		folders += [f.folder('applications') for f in [XDG_DATA_HOME] + XDG_DATA_DIRS]

		for folder in folders:
			for desktop in desktops:
				file = folder.file('%s-mimeapps.list' % desktop.lower())
				if file.exists():
					yield file

			file = folder.file('mimeapps.list')
			if file.exists():
				yield file

		for folder in _application_dirs():
			file = folder.file('defaults.list')
			if file.exists():
				yield file

	@classmethod
	def _get_default_application(klass, mimetype):
		## Based on https://specifications.freedesktop.org/mime-apps-spec/latest/
		## Version 1.0 dated 2 April 2014
		##
		## Implemented from scratch to ensure platform independent support
		##
		## Kept "defaults.list" file support for backward compatibility
		## when changing zim versions.

		for default_file in klass._mimeapps_files():
			in_default_section = False
			for line in default_file.readlines():
				if line.startswith('[Default Applications]'):
					in_default_section = True
				elif in_default_section and line.startswith('['):
					break # new group, look no further

				if in_default_section and line.startswith(mimetype + '='):
					_, key = line.strip().split('=', 1)
					for k in key.split(';'):
						k = k.strip()
						application = klass.get_application(k)
						if application is not None:
							return application
						# else continue searching
		else:
			return None

	@classmethod
	def set_default_application(klass, mimetype, application):
		'''Set the default application to open a file with a specific
		mimetype. Updates the C{applications/defaults.list} file.
		As a special case when you set the default to C{None} it will
		remove the entry from C{defauts.list} allowing system defaults
		to be used again.
		@param mimetype: the mime-type of the file (e.g. "text/html")
		@param application: an L{Application} object or C{None}
		'''
		## Based on https://specifications.freedesktop.org/mime-apps-spec/latest/
		## Version 1.0 dated 2 April 2014

		klass._defaults_app_cache[mimetype] = application

		if application is not None:
			if not isinstance(application, str):
				application = application.key

			if not application.endswith('.desktop'):
				application += '.desktop'

		file = XDG_CONFIG_HOME.file('mimeapps.list')
		_update_mimeapps_file(file, '[Default Applications]', mimetype, application, replace=True)

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
		dir = XDG_DATA_HOME.folder('applications')
		param['MimeType'] = mimetype
		basename = cleanup_filename(Name.lower()) + '-usercreated.desktop'
		file = _create_application(dir, basename, Name, Exec, **param)
		return file

	@classmethod
	def get_fallback_filebrowser(klass):
		# Don't use mimetype lookup here, this is a fallback
		# should handle all file types
		if os.name == 'nt':
			return StartFile()
		elif sys.platform == 'darwin':
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
		elif sys.platform == 'darwin':
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
		## Supporting mimapps.list
		## Based on https://specifications.freedesktop.org/mime-apps-spec/latest/
		## Version 1.0 dated 2 April 2014
		##
		## Also using older "mimeinfo.cache" which is deprecated in the spec
		## but still in use at least on Ubuntu as of Jan 2021
		##
		## TODO: cache these as well ?

		seen = set()
		entries = []
		blacklist = set()
		key = '%s=' % mimetype

		def add_entry(basename, dirs):
			if basename not in seen and basename not in blacklist:
				file = _application_file(basename, dirs)
				if file:
					entries.append(DesktopEntryFile(LocalFile(file)))
					seen.add(basename)

		for file in klass._mimeapps_files():
			section=None
			for line in file.readlines():
				if line.startswith('['):
					section=line.strip()
				elif line.startswith(key):
					if section in ('[Default Applications]', '[Added Associations]'):
						for basename in [b for b in line[len(key):].strip().split(';') if b]:
							add_entry(basename, _application_dirs())
					elif section == '[Removed Associations]':
						for basename in [b for b in line[len(key):].strip().split(';') if b]:
							blacklist.add(basename)

		for dir in _application_dirs():
			cache = dir.file('mimeinfo.cache')
			if not cache.exists():
				continue
			for line in cache.readlines():
				if line.startswith(key):
					for basename in [b for b in line[len(key):].strip().split(';') if b]:
						add_entry(basename, (dir,))

		if mimetype in ('x-scheme-handler/http', 'x-scheme-handler/https'):
			# Since "x-scheme-handler" is not in the standard, some browsers
			# only identify themselves with "text/html".
			for entry in klass.list_applications('text/html', nodisplay): # recurs
				basename = entry.key + '.desktop'
				if basename not in seen and basename not in blacklist:
					entries.append(entry)
					seen.add(basename)

		if not nodisplay:
			entries = [e for e in entries if not e.nodisplay]

		return entries


class NoApplicationFoundError(Error):
	'''Exception raised when an application was not found'''
	pass


def open_file(widget, file, mimetype=None, callback=None):
	'''Open a file or folder

	@param widget: parent for new dialogs, C{Gtk.Widget} or C{None}
	@param file: a L{File} or L{Folder} object
	@param mimetype: optionally specify the mimetype to force a
	specific application to open this file
	@param callback: callback function to be passed on to
	L{Application.spawn()} (if the application supports a
	callback, otherwise it is ignored silently)

	@raises FileNotFoundError: if C{file} does not exist
	@raises NoApplicationFoundError: if a specific mimetype was
	given, but no default application is known for this mimetype
	(will not use fallback in this case - fallback would
	ignore the specified mimetype)
	'''
	logger.debug('open_file(%s, %s)', file, mimetype)
	file = adapt_from_oldfs(file)
	if not file.exists():
		raise FileNotFoundError(file)

	if isinstance(file, File):
		manager = ApplicationManager()
		if mimetype is None:
			entry = manager.get_default_application(file.mimetype())
			if entry is not None:
				_open_with(widget, entry, file, callback)
			else:
				_open_with_filebrowser(widget, file.uri, callback)

		else:
			entry = manager.get_default_application(mimetype)
			if entry is not None:
				_open_with(widget, entry, file, callback)
			else:
				raise NoApplicationFoundError('No Application found for: %s' % mimetype)
				# Do not go to fallback, we can not force
				# mimetype for fallback
	else: # Folder
		_open_with_filebrowser(widget, file, callback)


def test_folder_prompt_create(widget, folder):
	'''Test if a folder exists, and prompt to create it if it doesn't exist yet.
	@param widget: parent for new dialogs, C{Gtk.Widget} or C{None}
	@param folder: a L{Folder} object
	@returns: True if the folder already exists or has been created, false otherwise
	'''

	if not folder.exists():
            if QuestionDialog(widget, (
                    _('Create folder?'),
                            # T: Heading in a question dialog for creating a folder
                    _('The folder "%s" does not yet exist.\nDo you want to create it now?') % folder.basename
                            # T: Text in a question dialog for creating a folder, %s will be the folder base name
            )).run():
                    folder.touch()

	return folder.exists()

def open_folder_prompt_create(widget, folder):
	'''Open a folder and prompts to create it if it doesn't exist yet.
	@param widget: parent for new dialogs, C{Gtk.Widget} or C{None}
	@param folder: a L{Folder} object
	'''
	try:
		open_folder(widget, folder)
	except FileNotFoundError:
		config = ConfigManager.preferences['Application']
		config.setdefault('always_create_missing_dirs', False)
		create_dir = config['always_create_missing_dirs']

		# prompt user if we're not asked to always create directories
		if not create_dir:
			create_dir = QuestionDialog(widget, (
				_('Create folder?'),
					# T: Heading in a question dialog for creating a folder
				_('The folder "%s" does not yet exist.\nDo you want to create it now?') % folder.basename
					# T: Text in a question dialog for creating a folder, %s will be the folder base name
				)).run()

		if create_dir:
			folder.touch()
			open_folder(widget, folder)


def open_folder(widget, folder):
	'''Open a folder.
	@param widget: parent for new dialogs, C{Gtk.Widget} or C{None}
	@param folder: a L{Folder} object
	@raises FileNotFoundError: if C{folder} does not exist
	see L{open_folder_prompt_create} for alternative behavior when folder
	does not exist.
	'''
	open_file(widget, folder)


def open_url(widget, url):
	'''Open an URL (or URI) in the web browser or other relevant
	program. The application is determined based on the URL / URI
	scheme. Unkown schemes and "file://" URIs are opened with the
	webbrowser.
	@param widget: parent for new dialogs, C{Gtk.Widget} or C{None}
	@param url: an URL or URI as string
	'''
	logger.debug('open_url(%s)', url)
	assert isinstance(url, str)

	if is_win32_share_re.match(url):
		url = normalize_win32_share(url)
		if os.name == 'nt':
			return _open_with_filebrowser(widget, url)
		# else consider as a x-scheme-handler/smb type URI below
	elif is_www_link_re.match(url):
		url = 'http://' + url
	elif not is_uri_re.match(url):
		raise ValueError('Not an URL: %s' % url)
	else:
		pass

	if url.startswith('file:/'):
		# Special case, force to browser (and not use open_file())
		# even though the result may be the same if the browser is
		# dispatched through xdg-open, gnome-open, ...)
		_open_with_webbrowser(widget, url)
	elif url.startswith('outlook:') and hasattr(os, 'startfile'):
		# Special case for outlook folder paths on windows
		os.startfile(url)
	else:
		manager = ApplicationManager()
		type = get_mimetype(url) # Supports "x-scheme-handler/... for URL schemes"
		logger.debug('Got type "%s" for "%s"', type, url)
		entry = manager.get_default_application(type)
		if entry:
			_open_with(widget, entry, url)
		elif url.startswith('mailto:'):
			_open_with_emailclient(widget, url)
		else:
			_open_with_webbrowser(widget, url)


def _open_with(widget, entry, uri, callback=None):
	def check_error(status):
		if status != 0:
				ErrorDialog(widget, _('Could not open: %s') % uri).run()
				# T: error when external application fails

	if callback is None:
		callback = check_error

	try:
		entry.spawn((uri,), callback=callback)
	except NotImplementedError:
		entry.spawn((uri,)) # E.g. webbrowser module does not support callback


def _open_with_filebrowser(widget, uri, callback=None):
	entry = ApplicationManager.get_fallback_filebrowser()
	_open_with(widget, entry, uri, callback)


def _open_with_emailclient(widget, uri):
	entry = ApplicationManager.get_fallback_emailclient()
	_open_with(widget, entry, uri)


def _open_with_webbrowser(widget, url):
	entry = ApplicationManager.get_fallback_webbrowser()
	_open_with(widget, entry, url)


def edit_config_file(widget, configfile):
	'''Edit a config file in an external editor.
	See L{edit_file()} for details.
	@param widget: a C{gtk} widget to use as parent for dialogs or C{None}
	@param configfile: a L{ConfigFile} object
	'''
	configfile.touch()
	edit_file(widget, configfile.file, istextfile=True)


def edit_file(widget, file, istextfile=None):
	'''Edit a file with and external application.

	This method will show a dialog to block the interface while the
	external application is running. The dialog is closed
	automatically when the application exits _after_ modifying the
	file. If the file is unmodified the user needs to click the
	"Done" button in the dialog because we can not know if the
	application was really done or just forked to another process.

	@param widget: a C{gtk} widget to use as parent for dialogs or C{None}
	@param file: a L{File} object
	@param istextfile: if C{True} the text editor is used, otherwise
	we ask the file browser for the correct application. When
	C{None} we check the mimetype of the file to determine if it
	is text or not.
	'''
	## FIXME force using real text editor, even when file has not
	## text mimetype. This now goes wrong when editing e.g. a html
	## template when the editor is "xdg-open" on linux or default
	## os.startfile() on windows...

	if not file.exists():
		raise FileNotFoundError(file)

	oldmtime = file.mtime()

	dialog = MessageDialog(widget, (
		_('Editing file: %s') % file.basename,
			# T: main text for dialog for editing external files
		_('You are editing a file in an external application. You can close this dialog when you are done')
			# T: description for dialog for editing external files
	))

	def check_close_dialog(status):
		if status != 0:
			dialog.destroy()
			ErrorDialog(widget, _('Could not open: %s') % file.basename).run()
				# T: error when external application fails
		else:
			newmtime = file.mtime()
			if newmtime != oldmtime:
				dialog.destroy()

	if istextfile:
		try:
			open_file(widget, file, mimetype='text/plain', callback=check_close_dialog)
		except NoApplicationFoundError:
			app = AddApplicationDialog(widget, 'text/plain').run()
			if app:
				# Try again
				open_file(widget, file, mimetype='text/plain', callback=check_close_dialog)
			else:
				return # Dialog was cancelled, no default set, ...
	else:
		open_file(widget, file, callback=check_close_dialog)

	dialog.run()


from zim.config import String as BaseString
from zim.config import Boolean as BaseBoolean
from zim.config import Float as Numeric


class XDGString(BaseString):

	def check(self, value):
		if isinstance(value, str):
			value = BaseString.check(self, value)
			if isinstance(value, str):
				# According to the XDG Desktop entry spec we should support
				# the follwoing codes: \s, \n, \t, \r, and \\
				# However, only do \\ to avoid conflicts invalid strings
				# also no use case for other codes in keys we use (?)
				return re.sub(r'\\\\', '\\\\', value)
			else:
				return value
		else:
			return BaseString.check(self, value)

	def tostring(self, value):
		if value is None:
			return ''
		else:
			return value.replace('\\', '\\\\')


class String(XDGString):

	def check(self, value):
		# Only ascii chars allowed in these keys
		value = XDGString.check(self, value)
		if isinstance(value, str):
			try:
				x = value.encode('ascii')
			except UnicodeEncodeError:
				raise ValueError('ASCII string required')
			else:
				pass
		return value


class LocaleString(XDGString):
	pass # utf8 already supported by default


class IconString(LocaleString):

	def check(self, value):
		if hasattr(value, 'path'):
			return value.path  # prevent fallback via serialize_zim_config to userpath
		else:
			return LocaleString.check(self, value)


class Boolean(BaseBoolean):

	def tostring(self, value):
		# Desktop entry specs "true" and "false"
		return str(value).lower()


class TerminalLookUpError(ApplicationLookUpError):

	def __init__(self, cmd):
		self.msg = _('Cound not find terminal emulator to run application: %s') % cmd
			# T: Error message when external application could not be run in terminal, %s is the command


_terminal_commands = (
	('xdg-terminal'),
	#('x-terminal-emulator', '-x'), # Testing shows "-x" does not work as advertised :(
	('gnome-terminal', '-x'),
	('xterm', '-e'),
)

def _get_terminal_command(appcmd):
	# Intended as *minimal* implementation for getting a terminal emulator.
	# Since there is no spec how to do this lookup, don't add any complexity
	# here other than maybe a switch per OS. Instead pull-in xdg-terminal as
	# dependency if more sophisticated logic is needed.
	for cmd in _terminal_commands:
		if Application(cmd).tryexec():
			return cmd + tuple(appcmd)
	else:
		raise TerminalLookUpError(appcmd[0])


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
		('Type', String('Application')),
		('Version', Numeric(1.0)),
		('GenericName', LocaleString(None)),
		('Name', LocaleString(None)),
		('Comment', LocaleString(None)),
		('Exec', String(None)),
		('TryExec', String(None)),
		('Icon', IconString(None)),
		('MimeType', String(None)),
		('Terminal', Boolean(False)),
		('NoDisplay', Boolean(False)),
	)

	def __init__(self):
		SectionedConfigDict.__init__(self)
		self['Desktop Entry'].define(self._definitions)

	@property
	def key(self):
		return '__anon__' # no mapping to .desktop file

	def isvalid(self):
		'''Check if all the fields that are required according to the
		specification are set. Assumes we only use desktop files to
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
	def needsterminal(self):
		return self['Desktop Entry'].get('Terminal', False)

	@property
	def tryexeccmd(self):
		return self['Desktop Entry'].get('TryExec')

	@property
	def cmd(self):
		return split_quoted_strings(self['Desktop Entry']['Exec'])

	def get_pixbuf(self, size):
		'''Get the application icon as a C{GdkPixbuf.Pixbuf}.
		@param size: the icon size as gtk constant
		@returns: a pixbuf object or C{None}
		'''
		icon = self['Desktop Entry'].get('Icon', None)
		if not icon:
			return None

		icon = icon.path if hasattr(icon, 'path') else icon

		w, h = strip_boolean_result(Gtk.icon_size_lookup(size))

		if '/' in icon or '\\' in icon:
			if os.path.isfile(icon):
				return GdkPixbuf.Pixbuf.new_from_file_at_size(icon, w, h)
			else:
				return None
		else:
			theme = Gtk.IconTheme.get_default()
			try:
				pixbuf = theme.load_icon(icon, w, 0)
			except Exception as error:
				#~ logger.exception('Foo')
				return None
			return pixbuf

	def parse_exec(self, args=None):
		'''Parse the 'Exec' string and interpolate the arguments
		according to the keys of the desktop spec.
		@param args: list of either URLs or L{File} objects
		@returns: the full command to execute as a tuple
		'''
		# The XDG Desktop Entry spec specifies replacement of field codes when
		# they appear as a single argument. Handling of field codes inside
		# arguments is explicitly left undefined. Users seem to expect these
		# to work, so at least interpolate the values that expand to a single
		# argument.

		assert args is None or isinstance(args, (list, tuple))

		def uris(args):
			uris = []
			for arg in args:
				if hasattr(arg, 'uri'):
					uris.append(arg.uri)
				else:
					uris.append(str(arg))
			return uris

		cmd = []
		seen_arg_code = False

		def sub_field_code(m):
			nonlocal seen_arg_code
			m = m.group()
			if m == '%f':
				seen_arg_code = True
				return str(args[0]) if args else ''
			elif m == '%u':
				seen_arg_code = True
				return uris(args)[0] if args else ''
			elif m == '%k':
				return self.file.path if hasattr(self, 'file') else ''
			elif m == '%c':
				return self.name
			else:
				return '%'

		for word in split_quoted_strings(self['Desktop Entry']['Exec']):
			# These expnd to multiple arguments and cannot be interpolated
			if word in ('%d', '%D', '%n', '%N', '%v', '%m'):
				continue # deprecated codes
			elif word == '%F':
				if args:
					cmd.extend([str(a) for a in args])
				seen_arg_code = True
				continue
			elif word == '%U':
				if args:
					cmd.extend([str(a) for a in uris(args)])
				seen_arg_code = True
				continue
			elif word == '%i':
				if 'Icon' in self['Desktop Entry'] \
				and self['Desktop Entry']['Icon']:
					cmd.extend(['--icon', self['Desktop Entry']['Icon']])
				continue
			elif word in ('%f', '%u') and not args:
				seen_arg_code = True
				continue
			else:
				# These can be interpolated inside arguments
				word = re.sub('%%|%[fukc]', sub_field_code, word)
				cmd.append(word)

		if not seen_arg_code and args:
			cmd.extend([str(a) for a in args])

		return tuple(cmd)

	def _cmd(self, args):
		# Hook into Application.spawn and Application.run
		cmd = self.parse_exec(args)
		if self.needsterminal:
			cmd = _get_terminal_command(cmd)
		return cmd

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


class OpenWithMenu(Gtk.Menu):
	'''Sub-class of C{Gtk.Menu} implementing an "Open With..." menu with
	applications to open a specific file. Also has an item
	"Customize...", which opens a L{CustomizeOpenWithDialog}
	and allows the user to add custom commands.
	'''

	CUSTOMIZE = _('Customize...')
		# T: label to customize 'open with' menu

	def __init__(self, widget, file, mimetype=None):
		'''Constructor

		@param widget: parent widget, needed to pop dialogs correctly
		@param file: a L{File} object or URL
		@param mimetype: the mime-type of the application, if already
		known. Providing this arguments prevents redundant lookups of
		the type (which is slow).
		'''
		GObject.GObject.__init__(self)
		self._window = widget.get_toplevel()
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
			item = Gtk.MenuItem.new_with_mnemonic(_('No Applications Found'))
				# T: message when no applications in "Open With" menu
			item.set_sensitive(False)
			self.append(item)

		self.append(Gtk.SeparatorMenuItem())

		item = Gtk.MenuItem.new_with_mnemonic(self.CUSTOMIZE)
		item.connect('activate', self.on_activate_customize, mimetype)
		self.append(item)

	def on_activate(self, menuitem):
		entry = menuitem.entry
		entry.spawn((self.file,))

	def on_activate_customize(self, o, mimetype):
		CustomizeOpenWithDialog(self._window, mimetype=mimetype).run()


class DesktopEntryMenuItem(Gtk.MenuItem):
	'''Single menu item for the L{OpenWithMenu}. Displays the application
	name and the icon.
	'''

	def __init__(self, entry):
		'''Constructor

		@param entry: the L{DesktopEntryFile}
		'''
		GObject.GObject.__init__(self)
		self.set_label(_('Open with "%s"') % entry.name)
			# T: menu item to open a file with an application, %s is the app name
		self.entry = entry


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

	def __init__(self, parent, mimetype):
		'''Constructor
		@param parent: the parent window or C{None}
		@param mimetype: mime-type for which we want to create a new
		application
		'''
		Dialog.__init__(self, parent, _('Configure Applications'),  # T: Dialog title
			buttons=Gtk.ButtonsType.CLOSE, help='Help:Default Applications')
		self.mimetype = mimetype
		self.add_text(_mimetype_dialog_text(mimetype))

		# Combo to set default
		self.default_combo = ApplicationComboBox()
		self.default_combo.connect('changed', self.on_default_changed)
		hbox = Gtk.HBox(spacing=12)
		self.vbox.add(hbox)
		hbox.pack_start(Gtk.Label(_('Default') + ':'), False, True, 0) # T: label for default application
		hbox.pack_start(self.default_combo, True, True, 0)

		# Button to add new
		button = Gtk.Button.new_with_mnemonic(_('Add Application'))
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



class ApplicationComboBox(Gtk.ComboBox):

	NAME_COL = 0
	APP_COL = 1
	ICON_COL = 2

	def __init__(self):
		GObject.GObject.__init__(self)
		self.set_model(
			Gtk.ListStore(str, object, GdkPixbuf.Pixbuf) # NAME_COL, APP_COL, ICON_COL
		)

		cell = Gtk.CellRendererPixbuf()
		self.pack_start(cell, False)
		cell.set_property('xpad', 5)
		self.add_attribute(cell, 'pixbuf', self.ICON_COL)

		cell = Gtk.CellRendererText()
		self.pack_start(cell, True)
		cell.set_property('xalign', 0.0)
		cell.set_property('xpad', 5)
		self.add_attribute(cell, 'text', self.NAME_COL)

	def clear(self):
		self.get_model().clear()

	def append(self, application):
		model = self.get_model()
		if hasattr(application, 'get_pixbuf'):
			pixbuf = application.get_pixbuf(Gtk.IconSize.MENU)
		else:
			pixbuf = self.render_icon(Gtk.STOCK_EXECUTE, Gtk.IconSize.MENU)

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

	def __init__(self, parent, mimetype):
		'''Constructor
		@param parent: the parent window or C{None}
		@param mimetype: mime-type for which we want to create a new
		application
		'''
		Dialog.__init__(self, parent, _('Add Application')) # T: Dialog title
		self.mimetype = mimetype
		self.add_text(_mimetype_dialog_text(mimetype))
		self.add_form((
			('name', 'string', _('Name')), # T: Field in 'custom command' dialog
			('exec', 'string', _('Command')), # T: Field in 'custom command' dialog
			('default', 'bool', _('Make default application')), # T: Field in 'custom command' dialog
		))
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
