
# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This module contains the main Notebook class and related classes.

The C{Notebook} interface is the generic API for accessing and storing
pages and other data in the notebook. The interface uses L{Path} objects
to indicate a specific page. See L{Notebook.pages.lookup_from_user_input()}
to obtain a L{Path} from a page name as string. Pages in the notebook
are represented by the L{Page} object, which allows to access the page
contents.

The notebook keeps track of all pages using an C{Index} which is stored
in a C{sqlite} database. Methods that need a list of pages in the
notebook always use the index rather than a direct lookup. See
L{zim.notebook.index} for more details.

The C{NotebookInfoList} is defined to help access known notebooks and
a C{NotebookInfo} object can be used to access the notebook properties
without instantiating a full L{Notebook} object. Use the convience
methods L{get_notebook_list()} and L{resolve_notebook()} to obtain these
objects.

@note: To open a notebook based on e.g. a commandline option it is
almost always better to use L{build_notebook()} rather than istantiating
the notebook directly.

@note: for more information about threading and concurency,
see L{zim.notebook.operations}

'''

from zim.fs import FilePath, File, Dir, FileNotFoundError
from zim.parsing import url_decode


from .info import NotebookInfo, NotebookInfoList, \
	resolve_notebook, get_notebook_list, get_notebook_info, interwiki_link

from .operations import NotebookOperation, SimpleAsyncOperation, \
	NotebookOperationOngoing, NotebookState

from .notebook import Notebook, NotebookExtension, TrashNotSupportedError, \
	PageNotFoundError, PageNotAllowedError, PageExistsError, PageReadOnlyError

from .page import Path, Page, \
	HRef, HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE

from .layout import encode_filename, decode_filename

from .index import IndexNotFoundError, \
	LINK_DIR_BACKWARD, LINK_DIR_BOTH, LINK_DIR_FORWARD



def build_notebook(location):
	'''Create a L{Notebook} object for a file location
	Tries to automount file locations first if needed
	@param location: a L{FilePath} or a L{NotebookInfo}
	@returns: a L{Notebook} object and a L{Path} object or C{None}
	@raises FileNotFoundError: if file location does not exist and could not be mounted
	'''
	uri = location.uri
	page = None

	# Decipher zim+file:// uris
	if uri.startswith('zim+file://'):
		uri = uri[4:]
		if '?' in uri:
			uri, page = uri.split('?', 1)
			page = url_decode(page)
			page = Path(page)

	# Automount if needed
	filepath = FilePath(uri)
	if not filepath.exists():
		mount_notebook(filepath)
		if not filepath.exists():
			raise FileNotFoundError(filepath)

	# Figure out the notebook dir
	if filepath.isdir():
		dir = Dir(uri)
		file = None
	else:
		file = File(uri)
		dir = file.dir

	if file and file.basename == 'notebook.zim':
		file = None
	else:
		parents = list(dir)
		parents.reverse()
		for parent in parents:
			if parent.file('notebook.zim').exists():
				dir = parent
				break

	# Resolve the page for a file
	if file:
		path = file.relpath(dir)
		if '.' in path:
			path, _ = path.rsplit('.', 1) # remove extension
		path = path.replace('/', ':')
		page = Path(path)

	# And finally create the notebook
	notebook = Notebook.new_from_dir(dir)
	return notebook, page


def mount_notebook(filepath):
	from zim.config import ConfigManager, String

	configdict = ConfigManager.get_config_dict('automount.conf')

	groups = sorted([k for k in list(configdict.keys()) if k.startswith('Path')])
	for group in groups:
		path = group[4:].strip() # len('Path') = 4
		dir = Dir(path)
		if filepath.path == dir.path or filepath.ischild(dir):
			configdict[group].define(mount=String(None))
			handler = ApplicationMountPointHandler(dir, **configdict[group])
			if handler(filepath):
				break


class ApplicationMountPointHandler(object):
	# TODO add password prompt logic, provide to cmd as argument, stdin

	def __init__(self, dir, mount, **a):
		self.dir = dir
		self.mount = mount

	def __call__(self, path):
		if path.path == self.dir.path or path.ischild(self.dir) \
		and not self.dir.exists() \
		and self.mount:
			from zim.applications import Application
			Application(self.mount).run()
			return path.exists()
		else:
			return False


def init_notebook(dir, name=None):
	'''Initialize a new notebook in a directory'''
	assert isinstance(dir, Dir)
	from .notebook import NotebookConfig
	dir.touch()
	config = NotebookConfig(dir.file('notebook.zim'))
	config['Notebook']['name'] = name or dir.basename
	config.write()
