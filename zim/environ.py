
'''This module contains a wrapper for C{os.environ} that deals with
proper encoding / decoding of values

When this module is loaded it will try to set proper values
for C{HOME} and C{USER} if they are not set and C{APPDATA} on windows.
'''

import os
import logging
import collections

logger = logging.getLogger('zim')


from zim.fs import ENCODING, isdir


class Environ(collections.MutableMapping):

	def __getitem__(self, k):
		# Do NOT use zim.fs.decode here, we want real decoding on windows,
		# not just convert to unicode
		v = os.environ[k]
		if isinstance(v, str):
			return v.decode(ENCODING)
		else:
			return v

	def __setitem__(self, k, v):
		if isinstance(v, unicode):
			v = v.encode(ENCODING)
		os.environ[k] = v

	def __delitem__(self, k):
		del os.environ[k]

	def __iter__(self):
		return iter(os.environ)

	def __len__(self):
		return len(os.environ)

	def get(self, k, default=None):
		'''Get a parameter from the environment. Like C{os.environ.get()}
		but does decoding for non-ascii characters.
		@param k: the parameter to get
		@param default: the default if C{param} does not exist
		@returns: a unicode string or C{default}
		'''
		try:
			v = self[k]
		except KeyError:
			return default
		else:
			if not v or v.isspace(): # existing but empty is edge case in environ
				return default
			else:
				return v

	def get_list(self, k, default=None, sep=None):
		'''Get a parameter from the environment and convert to a list.
		@param k: the parameter to get
		@param default: the default if C{param} does not exist
		@param sep: optional seperator, defaults to C{os.pathsep} if not given
		@returns: a list or the default
		'''
		v = self.get(k, default)
		if v is None:
			return []
		elif isinstance(v, basestring):
			if sep is None:
				sep = os.pathsep
			return v.split(sep)
		else:
			assert isinstance(v, (list, tuple))
			return v


environ = Environ() # Singleton


## Check environment

if os.name == 'nt':
	# Windows specific environment variables
	# os.environ does not support setdefault() ...
	if not 'USER' in environ or not environ['USER']:
		environ['USER'] = environ['USERNAME']

	if not 'HOME' in environ or not environ['HOME']:
		if 'USERPROFILE' in environ:
			environ['HOME'] = environ['USERPROFILE']
		elif 'HOMEDRIVE' in environ and 'HOMEPATH' in environ:
			environ['HOME'] = \
				environ['HOMEDRIVE'] + environ['HOMEPATH']

	if not 'APPDATA' in environ or not environ['APPDATA']:
		environ['APPDATA'] = environ['HOME'] + '\\Application Data'

assert isdir(environ['HOME']), \
	'ERROR: environment variable $HOME not set correctly value is "%s"'
	# using our own environ here to ensure encoding

if not 'USER' in environ or not environ['USER']:
	# E.g. Maemo doesn't define $USER
	environ['USER'] = os.path.basename(environ['HOME'])
	logger.info('Environment variable $USER was not set, set to "%s"', environ['USER'])




