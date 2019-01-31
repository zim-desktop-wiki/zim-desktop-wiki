
# Copyright 2013-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>



from weakref import WeakValueDictionary

import logging

logger = logging.getLogger('zim.config')


from . import basedirs
from .dicts import INIConfigFile

from zim.newfs import FileNotFoundError
from zim.fs import FileNotFoundError as oldFileNotFoundError

from zim.signals import ConnectorMixin, SignalEmitter, SignalHandler, SIGNAL_NORMAL


class ConfigManagerClass(object):
	'''This class defines an object that manages a set of config files.

	The config manager abstracts the lookup of files using the XDG
	search paths and ensures that there is only a single instance used
	for each config file.

	Typically config files are instantiated as a L{ConfigDict} file and changes
	are communicated to all users of the config by means of the "changed" signal.
	'''

	def __init__(self):
		self._set()

	def _set(self, dir=None, dirs=None):
		# this method is called to create virtual configmanagers
		self._config_files = WeakValueDictionary()
		self._config_dicts = WeakValueDictionary()
		self._dir = dir
		self._dirs = dirs

	def __call__(self):
		# Behave as singleton
		return self

	@property
	def preferences(self):
		return self.get_config_dict('preferences.conf')

	def _get_file(self, filename):
		if self._dir:
			file = self._dir.file(filename)
		else:
			file = basedirs.XDG_CONFIG_HOME.file('zim/' + filename)

		if self._dirs:
			defaults = DefaultFileIter(self._dirs, filename)
		else:
			defaults = XDGConfigFileIter(filename)

		return file, defaults

	def get_config_file(self, filename):
		'''Returns a C{ConfigFile} object for C{filename}'''
		if filename.startswith('<profile>/'):
			logger.warning('Use of "<profile>/" in config file is deprecated')
			filename = filename.replace('<profile>/', '')

		if filename not in self._config_files:
			file, defaults = self._get_file(filename)
			config_file = ConfigFile(file, defaults)
			self._config_files[filename] = config_file

		return self._config_files[filename]

	def get_config_dict(self, filename):
		'''Returns a C{SectionedConfigDict} object for C{filename}'''
		if filename.startswith('<profile>/'):
			logger.warning('Use of "<profile>/" in config file is deprecated')
			filename = filename.replace('<profile>/', '')

		if filename not in self._config_dicts:
			file = self.get_config_file(filename)
			config_dict = ConfigManagerINIConfigFile(file)
			self._config_dicts[filename] = config_dict

		return self._config_dicts[filename]

	#def get_all_config_files(filename)  - iterate multiple values ?
	#def get_config_section(filename, section): - return section


ConfigManager = ConfigManagerClass()  # define singleton


def makeConfigManagerVirtual():
	# Used in test suite to turn ConfigManager singleton in blank virtual state
	# _set() also resets internal state, but objects that already have a
	# reference to a config file or config dict will not see this
	from zim.newfs.mock import MockFolder
	folder = MockFolder('/<VirtualConfigManager>/')
	ConfigManager._set(folder)


def resetConfigManager():
	# Used in test suite to turn ConfigManager singleton in blank virtual state
	# _set() also resets internal state
	# Objects that were created with the virtual data don not get notified
	ConfigManager._set()


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
	underlying file changed (based on C{gio} monitoring support).
	'''

	__signals__ = {
		'changed': (SIGNAL_NORMAL, None, ())
	}

	def __init__(self, file, defaults=None):
		self.file = file
		self.defaults = defaults or []

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.file.path)

	def __eq__(self, other):
		return isinstance(other, ConfigFile) \
			and other.file == self.file

	def check_has_changed_on_disk(self):
		return True # we do not emit the signal if it is not real...

	@property
	def basename(self):
		return self.file.basename

	def exists(self):
		return self.file.exists() or \
			any(default.exists() for default in self.defaults)

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
		except (FileNotFoundError, oldFileNotFoundError):
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
		except (FileNotFoundError, oldFileNotFoundError):
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
		self.emit('changed')

	def writelines(self, lines):
		'''Write base file, see L{File.writelines()}'''
		self.file.writelines(lines)
		self.emit('changed')

	def remove(self):
		'''Remove user file, leaves default files in place'''
		if self.file.exists():
			return self.file.remove()
		self.emit('changed')
