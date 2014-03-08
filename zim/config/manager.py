# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

from weakref import WeakValueDictionary


from . import basedirs
from .dicts import INIConfigFile

from zim.fs import FileNotFoundError

from zim.signals import ConnectorMixin, SignalEmitter, SignalHandler


class ConfigManager(object):
	'''This class defines an object that manages a set of config files.

	The config manager abstracts the lookup of files using the XDG
	search paths and ensures that there is only a single instance used
	for each config file.

	The config manager can switch the config file based on the config
	X{profile} that is used. The profile is determined by the notebook
	properties. However this object relies on it's creator to setup
	the hooks to get the property from the notebook. Changes to the
	profile are communicated to all users of the config by means of the
	"changed" signals on L{ConfigFile} and L{ConfigDict} objects.
	'''

	def __init__(self, dir=None, dirs=None, profile=None):
		'''Constructor
		@param dir: the folder for reading and writing config files,
		e.g. a C{Dir} or a C{VirtualConfigBackend} objects.
		If no dir is given, the XDG basedirs are used and C{dirs} is
		ignored.
		@param dirs: list or generator of C{Dir} objects used as
		search path when a config file does not exist on C{dir}
		@param profile: initial profile name
		'''
		self.profile = profile
		self._config_files = WeakValueDictionary()
		self._config_dicts = WeakValueDictionary()

		if dir is None:
			assert dirs is None, "Do not provide 'dirs' without 'dir'"
		self._dir = dir
		self._dirs = dirs

	def set_profile(self, profile):
		'''Set the profile to use for the configuration
		@param profile: the profile name or C{None}
		'''
		assert profile is None or isinstance(profile, basestring)
		if profile != self.profile:
			self.profile = profile
			for path, conffile in self._config_files.items():
				if path.startswith('<profile>/'):
					file, defaults = self._get_file(path)
					conffile.set_files(file, defaults)

			# Updates will cascade through the dicts by the
			# "changed" signals on various objects

	def _get_file(self, filename):
		basepath = filename.replace('<profile>/', '')
		if self.profile:
			path = filename.replace('<profile>/', 'profiles/%s/' % self.profile)
		else:
			path = basepath

		if self._dir:
			file = self._dir.file(path)
			if self._dirs:
				defaults = DefaultFileIter(self._dirs, path)
			else:
				defaults = DefaultFileIter([], path)

			if self.profile and filename.startswith('<profile>/'):
				mypath = filename.replace('<profile>/', '')
				defaults.extra.insert(0, self._dir.file(mypath))
		else:
			file = basedirs.XDG_CONFIG_HOME.file('zim/' + path)
			defaults = XDGConfigFileIter(basepath)

		## Backward compatibility for profiles
		if self.profile \
		and filename in (
			'<profile>/preferences.conf',
			'<profile>/style.conf'
		):
			backwardfile = self._get_backward_file(filename)
			defaults.extra.insert(0, backwardfile)

		return file, defaults

	def _get_backward_file(self, filename):
		if filename == '<profile>/preferences.conf':
			path = 'profiles/%s.conf' % self.profile
		elif filename == '<profile>/style.conf':
			path = 'styles/%s.conf' % self.profile
		else:
			raise AssertionError

		if self._dir:
			return self._dir.file(path)
		else:
			return basedirs.XDG_CONFIG_HOME.file('zim/' + path)

	def get_config_file(self, filename):
		'''Returns a C{ConfigFile} object for C{filename}'''
		if filename not in self._config_files:
			file, defaults = self._get_file(filename)
			config_file = ConfigFile(file, defaults)
			self._config_files[filename] = config_file

		return self._config_files[filename]

	def get_config_dict(self, filename):
		'''Returns a C{SectionedConfigDict} object for C{filename}'''
		if filename not in self._config_dicts:
			file = self.get_config_file(filename)
			config_dict = ConfigManagerINIConfigFile(file)
			self._config_dicts[filename] = config_dict

		return self._config_dicts[filename]

	#def get_all_config_files(filename)  - iterate multiple values ?
	#def get_config_section(filename, section): - return section


def VirtualConfigManager(**data):
	return ConfigManager(VirtualConfigBackend(**data))


class DefaultFileIter(object):
	'''Generator for iterating default files
	Will yield first the files in C{extra} followed by files that
	are based on C{path} and C{dirs}. Yields only existing files.
	'''

	def __init__(self, dirs, path, extra=None):
		self.path = path
		self.dirs = dirs
		self.extra = extra or []

	def __iter__(self):
		for file in self.extra:
			if file.exists():
				yield file

		for dir in self.dirs:
			file = dir.file(self.path)
			if file.exists():
				yield file


class XDGConfigDirsIter(object):
	'''Generator for iterating XDG config dirs
	Yields the "zim" subdir of each XDG config file.
	'''

	def __iter__(self):
		from . import data_dirs # XXX
		yield basedirs.XDG_CONFIG_HOME.subdir(('zim'))
		for dir in basedirs.XDG_CONFIG_DIRS:
			yield dir.subdir(('zim'))
		for dir in data_dirs():
			yield dir


class XDGConfigFileIter(DefaultFileIter):
	'''Like C{DefaultFileIter}, but uses XDG config dirs'''

	def __init__(self, path, extra=None):
		self.path = path
		self.dirs = XDGConfigDirsIter()
		self.extra = extra or []


class ConfigManagerINIConfigFile(INIConfigFile):
	'''Like L{INIConfigFile} but with autosave when the dict changes'''

	def __init__(self, file):
		INIConfigFile.__init__(self, file, monitor=True)
		self.connect_after('changed', self.on_changed)
			# autosave on changing the dict, connect after
			# regular handlers to avoid getting stuck with a set

	@SignalHandler
	def on_changed(self, *a):
		with self.on_file_changed.blocked():
			self.write()

	@SignalHandler
	def on_file_changed(self, *a):
		with self.on_changed.blocked():
			INIConfigFile.on_file_changed(self, *a)


class ConfigFile(ConnectorMixin, SignalEmitter):
	'''Container object for a config file

	Maps to a "base" file in the home folder, used to write new values,
	and an optional default file, which is used for reading only.

	@ivar file: the underlying file object for the base config file
	in the home folder
	@ivar defaults: a generator that yields default files

	@note: this class implement similar API to the L{File} class but
	is explicitly not a sub-class of L{File} because config files should
	typically not be moved, renamed, etc. It just implements the reading
	and writing methods.

	@signal: C{changed ()}: emitted when the
	underlying file changed (based on C{gio} monitoring support)
	or for file monitors or on profile switched
	'''

	# TODO __signals__

	def __init__(self, file, defaults=None):
		self.file = None
		self.defaults = None
		with self.blocked_signals('changed'):
			self.set_files(file, defaults)

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.file.path)

	def __eq__(self, other):
		return isinstance(other, ConfigFile) \
			and other.file == self.file

	def set_files(self, file, defaults=None):
		if self.file:
			self.disconnect_from(self.file)
		self.file = file
		self.defaults = defaults or []
		#~ self.connectto(self.file, 'changed', self.on_file_changed)
		self.emit('changed')

	#~ def on_file_changed(self, file, *a):
		#~ print "CONF FILE changed:", file
		# TODO verify etag (we didn't write ourselves)
		#~ self.emit('changed')

	def check_has_changed_on_disk(self):
		return True # we do not emit the signal if it is not real...

	@property
	def basename(self):
		return self.file.basename

	def touch(self):
		'''Ensure the custom file in the home folder exists. Either by
		copying a default config file, or touching an empty file.
		Intended to be called before trying to edit the file with an
		external editor.
		'''
		if not self.file.exists():
			for default in self.defaults:
				default.copyto(self.file)
				break
			else:
				self.file.touch() # create empty file

	def read(self, fail=False):
		'''Read the base file or first default file
		@param fail: if C{True} a L{FileNotFoundError} error is raised
		when neither the base file or a default file are found. If
		C{False} it will return C{''} for a non-existing file.
		@returns: file content as a string
		'''
		try:
			return self.file.read()
		except FileNotFoundError:
			for default in self.defaults:
				return default.read()
			else:
				if fail:
					raise
				else:
					return ''

	def readlines(self, fail=False):
		'''Read the base file or first default file
		@param fail: if C{True} a L{FileNotFoundError} error is raised
		when neither the base file or a default file are found. If
		C{False} it will return C{[]} for a non-existing file.
		@returns: file content as a list of lines
		'''
		try:
			return self.file.readlines()
		except FileNotFoundError:
			for default in self.defaults:
				return default.readlines()
			else:
				if fail:
					raise
				else:
					return []

	def write(self, text):
		'''Write base file, see L{File.write()}'''
		self.file.write(text)

	def writelines(self, lines):
		'''Write base file, see L{File.writelines()}'''
		self.file.writelines(lines)

	def remove(self):
		'''Remove user file, leaves default files in place'''
		if self.file.exists():
			return self.file.remove()



class VirtualConfigBackend(object):
	'''Virtual dir, mainly used for testing'''

	def __init__(self, **data):
		self._data = data

	def file(self, path):
		return VirtualConfigBackendFile(self._data, path)



class VirtualConfigBackendFile(object):
	'''Virtual file, mainly used for testing'''

	def __init__(self, data, path):
		self._key = path
		self._data = data

	@property
	def path(self):
		return '<virtual>/' + self._key

	@property
	def basename(self):
		import os
		return os.path.basename(self.path)

	def connect(self, handler, *a):
		pass

	def disconnect(self, handler):
		pass

	def exists(self):
		return self._key in self._data \
			and self._data[self._key] is not None

	def touch(self):
		self._data.setdefault(self._key, '')

	def copyto(self, other):
		text = self.read()
		other.write(text)

	def read(self):
		try:
			text = self._data[self._key]
		except KeyError:
			raise FileNotFoundError(self)
		else:
			if text is None:
				raise FileNotFoundError(self)
			else:
				return text

	def readlines(self):
		text = self.read()
		return text.splitlines(True)

	def write(self, text):
		self._data[self._key] = text or ''

	def writelines(self, lines):
		self._data[self._key] = ''.join(lines) or ''

	def remove(self):
		del self._data[self._key]



