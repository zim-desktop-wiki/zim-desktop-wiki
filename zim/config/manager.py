# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from weakref import WeakValueDictionary


from . import basedirs
from .dicts import INIConfigFile

from zim.fs import FileNotFoundError



class ConfigManager(object):
	'''Object to manager a set of config files, and allowing to
	switch configuration profiles.
	'''

	def __init__(self, dir=None, dirs=None):
		'''Constructor
		@param dir: the folder for reading and writing config files,
		e.g. a C{Dir} or a C{VirtualConfigBackend} objects.
		If no dir is given, the XDG basedirs are used and C{dirs} is
		ignored.
		@param dirs: list or generator of C{Dir} objects used as
		search path when a config file does not exist on C{dir}
		'''
		self.profile = None
		self._config_files = WeakValueDictionary()
		self._config_dicts = WeakValueDictionary()

		if dir is None:
			assert dirs is None, "Do not provide 'dirs' without 'dir'"
		self._dir = dir
		self._dirs = dirs

	def set_profile(profile):
		'''Set the profile to use for the configuration
		@param profile: the profile name or C{None}
		'''
		assert profile is None or isinstance(profile, basestring)
		self.profile = profile
		# TODO switch

	def _expand_path(self, filename):
		if self.profile:
			path = filename.replace('<profile>/', 'profiles/%s/' % self.profile)
		else:
			path = filename.replace('<profile>/', '')

		return path

	def _get_file(self, path):
		if self._dir:
			file = self._dir.file(path)
			if self._dirs:
				defaults = DefaultFileIter(self._dirs, path)
			else:
				defaults = None
		else:
			file = basedirs.XDG_CONFIG_HOME.file(path)
			defaults = XDGDefaultFileIter(path)

		## TODO: special case backward compat preferences & styles -- insert in defaults
		return file, defaults

	def get_config_file(self, filename):
		'''Returns a C{ConfigFile} object for C{filename}'''
		path = self._expand_path(filename)
		if path in self._config_files:
			return self._config_files[path]
		else:
			file, defaults = self._get_file(path)
			config_file = ConfigFile(file, defaults)
			self._config_files[path] = config_file
			return config_file

	def get_config_dict(self, filename):
		'''Returns a C{SectionedConfigDict} object for C{filename}'''
		path = self._expand_path(filename)
		if path in self._config_dicts:
			return self._config_dicts[path]
		else:
			file = self.get_config_file(path)
			config_dict = INIConfigFile(file)
			config_dict.connect_after('changed', self.on_dict_changed)
				# autosave on changing the dict, connect after
				# regular handlers to avoid getting stuck with a set
			self._config_dicts[path] = config_dict
			return config_dict

	def on_dict_changed(self, dict):
		dict.write()

	#def get_all_config_files(filename)  - iterate multiple values ?
	#def get_config_section(filename, section): - return section


def VirtualConfigManager(**data):
	return ConfigManager(VirtualConfigBackend(**data))


class DefaultFileIter(object):

	def __init__(self, dirs, path):
		self.path = path
		self.dirs = dirs

	def __iter__(self):
		for dir in self.dirs:
			file = dir.file(self.path)
			if file.exists():
				yield file


class XDGDefaultFileIter(DefaultFileIter):

	def __init__(self, path):
		self.path = path

	@property
	def dirs(self):
		from . import data_dirs # XXX
		yield basedirs.XDG_CONFIG_HOME.subdir(('zim'))
		for dir in basedirs.XDG_CONFIG_DIRS:
			yield dir.subdir(('zim'))
		for dir in data_dirs():
			yield dir



class ConfigFile(object):
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
	'''

	def __init__(self, file, defaults=None):
		self.file = file
		self.defaults = defaults or []

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.file.path)

	def __eq__(self, other):
		return isinstance(other, ConfigFile) \
			and other.file == self.file

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

	# Not implemented: read_async and readlines_async

	def write(self, text):
		'''Write base file, see L{File.write()}'''
		self.file.write(text)

	def writelines(self, lines):
		'''Write base file, see L{File.writelines()}'''
		self.file.writelines(lines)

	def write_async(self, text, callback=None, data=None):
		'''Write base file async, see L{File.write_async()}'''
		return self.file.write_async(text, callback=callback, data=data)

	def writelines_async(self, lines, callback=None, data=None):
		'''Write base file async, see L{File.writelines_async()}'''
		return self.file.writelines_async(lines, callback=callback, data=data)

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

	def write_async(self, text, callback=None, data=None):
		self.write(text)

	def writelines_async(self, lines, callback=None, data=None):
		self.writelines(lines)

	def remove(self):
		del self._data[self._key]



