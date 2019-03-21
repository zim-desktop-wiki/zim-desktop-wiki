
# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import os
import re
import logging

logger = logging.getLogger('zim.notebook')


import zim.fs

from zim.fs import File, Dir, SEP
from zim.config import ConfigManager, INIConfigFile, XDGConfigFileIter, String
from zim.parsing import is_url_re, is_win32_path_re, url_encode

from .notebook import NotebookConfig, _resolve_relative_config


def get_notebook_list():
	'''Returns a list of known notebooks as a L{NotebookInfoList}

	This will load the list from the default X{notebooks.list} file
	'''
	file = ConfigManager.get_config_file('notebooks.list')
	return NotebookInfoList(file)


def resolve_notebook(string, pwd=None):
	'''Takes either a notebook name or a file or dir path. For a name
	it resolves the path by looking for a notebook of that name in the
	notebook list.
	Note that the L{NotebookInfo} for an file path is not using any
	actual info from the notebook, it just passes on the uri. Use
	L{build_notebook()} to split the URI in a notebook location and
	an optional page path.
	@returns: a L{NotebookInfo} or C{None}
	'''
	assert isinstance(string, str)
	from zim.fs import isabs

	if '/' in string or SEP in string:
		# FIXME do we need a isfilepath() function in fs.py ?
		if is_url_re.match(string):
			uri = string
		elif pwd and not isabs(string):
			uri = pwd + SEP + string
		else:
			uri = string
		return NotebookInfo(uri)
	else:
		nblist = get_notebook_list()
		return nblist.get_by_name(string)


def _get_path_object(path):
	if isinstance(path, str):
		file = File(path)
		if file.exists(): # exists and is a file
			path = file
		else:
			path = Dir(path)
	else:
		assert isinstance(path, (File, Dir))
	return path


def get_notebook_info(path):
	'''Look up the notebook info for either a uri,
	or a File or a Dir object.
	@param path: path as string, L{File} or L{Dir} object
	@returns: L{NotebookInfo} object, or C{None} if no notebook config
	was found
	'''
	path = _get_path_object(path)
	info = NotebookInfo(path.uri)
	if info.update():
		return info
	else:
		return None


def interwiki_link(link):
	'''Convert an interwiki link into an url'''
	assert isinstance(link, str) and '?' in link
	key, page = link.split('?', 1)
	lkey = key.lower()

	# First check known notebooks
	list = get_notebook_list()
	info = list.get_interwiki(key)
	if info:
		url = 'zim+' + info.uri + '?{NAME}'

	# Then search all "urls.list" in config and data dirs
	else:
		url = None
		files = XDGConfigFileIter('urls.list') # FIXME, shouldn't this be passed in ?
		for file in files:
			for line in file.readlines():
				if line.startswith('#') or line.isspace():
					continue
				try:
					mykey, myurl = line.split(None, 1)
				except ValueError:
					continue
				if mykey.lower() == lkey:
					url = myurl.strip()
					break

			if url is not None:
				break

	# Format URL
	if url:
		if not ('{NAME}' in url or '{URL}' in url):
			url += '{URL}'

		url = url.replace('{NAME}', page)
		url = url.replace('{URL}', url_encode(page))
		return url
	else:
		return None


class NotebookInfo(object):
	'''This class keeps the info for a notebook

	@ivar uri: The location of the notebook
	@ivar user_path: The location of the notebook relative to the
	home folder (starts with '~/') or C{None}
	@ivar name: The notebook name (or the basename of the uri)
	@ivar icon: The file uri for the notebook icon
	@ivar icon_path: The location of the icon as configured (either
	relative to the notebook location, relative to home folder or
	absolute path)
	@ivar mtime: The mtime of the config file this info was read from (if any)
	@ivar active: The attribute is used to signal whether the notebook
	is already open or not, used in the daemon context, C{None} if this
	is not used, C{True} or C{False} otherwise
	@ivar interwiki: The interwiki keyword (if any)
	'''

	def __init__(self, uri, name=None, icon=None, mtime=None, interwiki=None, **a):
		'''Constructor

		Known values for C{name}, C{icon} etc. can be specified.
		Alternatively L{update()} can be called to read there from the
		notebook configuration (if any). If C{mtime} is given the
		object acts as a cache and L{update()} will only read the config
		if it is newer than C{mtime}

		@param uri: location uri or file path for the notebook (esp. C{user_path})
		@param name: notebook name
		@param icon: the notebook icon path
		@param mtime: the mtime when config was last read
		@param interwiki: the interwiki keyword for this notebook
		@param a: any additional arguments will be discarded
		'''
		# **a is added to be future proof of unknown values in the cache
		if isinstance(uri, str) \
		and is_url_re.match(uri) and not uri.startswith('file://'):
			self.uri = uri
			self.user_path = None
			self.name = name
		else:
			f = File(uri)
			self.uri = f.uri
			self.user_path = f.user_path # set to None when uri is not a file uri
			self.name = name or f.basename
		self.icon_path = icon
		self.icon = File(icon).uri
		self.mtime = mtime
		self.interwiki = interwiki
		self.active = None

	def __eq__(self, other):
		# objects describe the same notebook when the uri is the same
		if isinstance(other, str):
			return self.uri == other
		elif hasattr(other, 'uri'):
			return self.uri == other.uri
		else:
			return False

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.uri)

	def update(self):
		'''Check if info is still up to date and update this object

		This method will check the X{notebook.zim} file for notebook
		folders and read it if it changed. It uses the C{mtime}
		attribute to keep track of changes.

		@returns: C{True} when data was updated, C{False} otherwise
		'''
		# TODO support for paths that turn out to be files
		dir = Dir(self.uri)
		file = dir.file('notebook.zim')
		if file.exists() and file.mtime() != self.mtime:
			config = NotebookConfig(file)
			section = config['Notebook']

			self.name = section['name']
			self.interwiki = section['interwiki']
			self.icon_path = section['icon']
			icon, document_root = _resolve_relative_config(dir, section)
			if icon:
				self.icon = icon.uri
			else:
				self.icon = None

			self.mtime = file.mtime()
			return True
		else:
			return False


class VirtualFile(object):
	### TODO - proper class for this in zim.fs
	###        unify with code in config manager

	def __init__(self, lines):
		self.lines = lines

	def readlines(self):
		return self.lines

	def connect(self, handler, *a):
		pass

	def disconnect(self, handler):
		pass


class NotebookInfoList(list):
	'''This class keeps a list of L{NotebookInfo} objects

	It maps to a X{notebooks.list} config file that keeps a list of
	notebook locations and cached attributes from the various
	X{notebook.zim} config files

	@ivar default: L{NotebookInfo} object for the default
	'''

	def __init__(self, file):
		'''Constructor
		@param file: a L{File} or L{ConfigFile} object for X{notebooks.list}
		'''
		self.file = file
		self.default = None # default notebook
		self.read()
		try:
			self.update()
		except:
			logger.exception('Exception while loading notebook list:')

	def read(self):
		'''Read the config and cache and populate the list'''
		lines = self.file.readlines()
		if len(lines) > 0:
			if lines[0].startswith('[NotebookList]'):
				self.parse(lines)
			else:
				self.parse_old_format(lines)

	def parse(self, text):
		'''Parses the config and cache and populates the list

		Format is::

		  [NotebookList]
		  Default=uri1
		  1=uri1
		  2=uri2

		  [Notebook 1]
		  name=Foo
		  uri=uri1

		Then followed by more "[Notebook]" sections that are cache data

		@param text: a string or a list of lines
		'''
		# Format <= 0.60 was:
		#
		#  [NotebookList]
		#  Default=uri1
		#  uri1
		#  uri2
		#
		#  [Notebook]
		#  name=Foo
		#  uri=uri1


		if isinstance(text, str):
			text = text.splitlines(True)

		assert text[0].strip() == '[NotebookList]'

		# Backward compatibility, make valid INI file:
		# - make redundant [Notebook] sections numbered
		# - prefix lines without a key with a number
		n = 0
		l = 0
		for i, line in enumerate(text):
			if line.strip() == '[Notebook]':
				n += 1
				text[i] = '[Notebook %i]\n' % n
			elif line and not line.isspace()  \
			and not line.lstrip().startswith('[') \
			and not line.lstrip().startswith('#') \
			and not '=' in line:
				l += 1
				text[i] = ('%i=' % l) + line
		###

		config = INIConfigFile(VirtualFile(text))

		mylist = config['NotebookList']
		mylist.define(Default=String(None))
		mylist.define((k, String(None)) for k in list(mylist._input.keys())) # XXX

		for key, uri in list(config['NotebookList'].items()):
			if key == 'Default':
				continue

			section = config['Notebook %s' % key]
			section.define(
				uri=String(None),
				name=String(None),
				icon=String(None),
				mtime=String(None),
				interwiki=String(None)
			)
			if section['uri'] == uri:
				info = NotebookInfo(**section)
			else:
				info = NotebookInfo(uri)
			self.append(info)

		if 'Default' in config['NotebookList'] \
		and config['NotebookList']['Default']:
			self.set_default(config['NotebookList']['Default'])

	def parse_old_format(self, text):
		'''Parses the config and cache and populates the list

		Method for backward compatibility with list format with no
		section headers and a whitespace separator between notebook
		name and uri.

		@param text: a string or a list of lines
		'''
		# Old format is name, value pair, separated by whitespace
		# with all other whitespace escaped by a \
		# Default was _default_ which could refer a notebook name.
		if isinstance(text, str):
			text = text.splitlines(True)

		fields_re = re.compile(r'(?:\\.|\S)+') # match escaped char or non-whitespace
		escaped_re = re.compile(r'\\(.)') # match single escaped char

		default = None
		defaulturi = None
		uris = []
		for line in text:
			if not line or line.isspace() or line.startswith('#'):
				continue

			cols = fields_re.findall(line.strip())
			if len(cols) == 2:
				name = escaped_re.sub(r'\1', cols[0])
				path = escaped_re.sub(r'\1', cols[1])
				if name == '_default_':
					default = path
				else:
					uri = File(path).uri
					uris.append(uri)
					if name == default:
						defaulturi = uri

		if default and not defaulturi:
			defaulturi = File(default).uri

		# Populate ourselves
		for uri in uris:
			info = NotebookInfo(uri)
			self.append(info)

		if defaulturi:
			self.set_default(defaulturi)

	def write(self):
		'''Write the config and cache'''
		if self.default:
			default = self.default.user_path or self.default.uri
		else:
			default = None

		lines = [
			'[NotebookList]\n',
			'Default=%s\n' % (default or '')
		]
		for i, info in enumerate(self):
			n = i + 1
			uri = info.user_path or info.uri
			lines.append('%i=%s\n' % (n, uri))

		for i, info in enumerate(self):
			n = i + 1
			uri = info.user_path or info.uri
			lines.extend([
				'\n',
				'[Notebook %i]\n' % n,
				'uri=%s\n' % uri,
				'name=%s\n' % info.name,
				'interwiki=%s\n' % info.interwiki,
				'icon=%s\n' % info.icon_path,
			])

		self.file.writelines(lines)

	def update(self):
		'''Update L{NotebookInfo} objects and write cache'''
		changed = False
		for info in self:
			changed = info.update() or changed
		if changed:
			self.write()

	def set_default(self, uri):
		'''Set the default notebook
		@param uri: the file uri or file path for the default notebook
		'''
		uri = File(uri).uri # e.g. "~/foo" to file:// uri
		for info in self:
			if info.uri == uri:
				self.default = info
				return
		else:
			info = NotebookInfo(uri)
			self.insert(0, info)
			self.default = info

	def get_by_name(self, name):
		'''Get the L{NotebookInfo} object for a notebook by name

		Names are checked case sensitive first, then case-insensitive

		@param name: notebook name as string
		@returns: a L{NotebookInfo} object or C{None}
		'''
		for info in self:
			if info.name == name:
				return info

		lname = name.lower()
		for info in self:
			if info.name.lower() == lname:
				return info

		return None

	def get_interwiki(self, key):
		'''Get the L{NotebookInfo} object for a notebook by interwiki key

		First checks the interwiki key for all notebooks (case insensitive)
		than falls back to L{get_by_name()}.

		@param key: notebook name or interwiki key as string
		@returns: a L{NotebookInfo} object or C{None}
		'''
		lkey = key.lower()
		for info in self:
			if info.interwiki and info.interwiki.lower() == lkey:
				return info
		else:
			return self.get_by_name(key)
