
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
L{notebook.zim.index} for more details.

The C{NotebookInfoList} is defined to help access known notebooks and
a C{NotebookInfo} object can be used to access the notebook properties
without instantiating a full L{Notebook} object. Use the convience
methods L{get_notebook_list()} and L{resolve_notebook()} to obtain these
objects.

@note: To open a notebook based on e.g. a commandline option it is
almost always better to use L{build_notebook()} rather than istantiating
the notebook directly.

@note: for more information about threading and concurency,
see L{notebook.zim.operations}

'''

import logging

logger = logging.getLogger('notebook.zim')


from zim.newfs import FileNotFoundError, localFileOrFolder, LocalFolder, FilePath
from zim.parsing import url_decode


from .info import NotebookInfo, NotebookInfoList, \
	resolve_notebook, get_notebook_list, get_notebook_info, interwiki_link

from .operations import NotebookOperation, SimpleAsyncOperation, \
	NotebookOperationOngoing, NotebookState

from .notebook import Notebook, NotebookExtension, TrashNotSupportedError, \
	PageNotFoundError, PageNotAllowedError, PageNotAvailableError, \
	PageExistsError

from .page import Path, Page, PageReadOnlyError, \
	HRef, HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE

from .layout import encode_filename, decode_filename

from .index import IndexNotFoundError, \
	LINK_DIR_BACKWARD, LINK_DIR_BOTH, LINK_DIR_FORWARD

from .content_updater import update_parsetree_and_copy_images, \
	set_parsetree_attributes_to_resolve_links, replace_parsetree_links_and_copy_images


def build_notebook(location):
	'''Create a L{Notebook} object for a file location
	Tries to automount file locations first if needed
	@param location: a L{FilePath} or a L{NotebookInfo}
	@returns: a L{Notebook} object and an (absolute) L{HRef} object or C{None}
	@raises FileNotFoundError: if file location does not exist and could not be mounted
	'''
	uri = location.uri
	href = None

	# Decipher zim+file:// uris
	if uri.startswith('zim+file://'):
		uri = uri[4:]
		if '?' in uri:
			uri, localpart = uri.split('?', 1)
			localpart = url_decode(localpart)
			href = HRef.new_from_wiki_link(localpart)

	if '#' in uri:
		uri, anchor = uri.split('#', 1)
		href = HRef.new_from_wiki_link('#' + anchor)

	# Automount if needed
	filepath = FilePath(uri)
	try:
		fileorfolder = localFileOrFolder(filepath)
	except FileNotFoundError:
		mount_notebook(filepath)
		fileorfolder = localFileOrFolder(uri) # Can raise FileNotFoundError
	else:
		# The folder of a mount point can exist, so check for specific content
		if isinstance(fileorfolder, LocalFolder) \
			and not fileorfolder.file('notebook.zim').exists():
				mount_notebook(filepath)
				fileorfolder = localFileOrFolder(uri) # Can raise FileNotFoundError

	if isinstance(fileorfolder, LocalFolder):
		folder, file = fileorfolder, None
	elif fileorfolder.basename == 'notebook.zim':
		folder, file = fileorfolder.parent(), None
	else:
		folder, file = fileorfolder.parent(), fileorfolder

	if not folder.file('notebook.zim').exists():
		for parent in folder.parents():
			if parent.file('notebook.zim').exists():
				folder = parent
				break

	# Resolve the page for a file
	if file:
		path = file.relpath(folder)
		if '.' in path:
			path, _ = path.rsplit('.', 1) # remove extension
		path = path.replace('\\', ':').replace('/', ':')
		if href and not href.names:
			# Anchor was given, add page name
			href.names = Path.makeValidPageName(path)
		else:
			href = HRef.new_from_wiki_link(path)
	elif href and not href.names:
		# Anchor without page name - ignore silent
		href = None

	# And finally create the notebook
	notebook = Notebook.new_from_dir(folder)
	return notebook, href


def mount_notebook(filepath):
	from zim.config import ConfigManager, String

	configdict = ConfigManager.get_config_dict('automount.conf')

	groups = sorted([k for k in list(configdict.keys()) if k.startswith('Path')])
	for group in groups:
		path = group[4:].strip() # len('Path') = 4
		folder = LocalFolder(path)
		if is_relevant_mount_point(folder, filepath):
			configdict[group].define(mount=String(None))
			handler = ApplicationMountPointHandler(folder, **configdict[group])
			if handler(filepath):
				break


def is_relevant_mount_point(root, path):
	# path can be notebook folder, or file path below notebook folder
	# root can be parent folder of notebook folder or notebook folder itself
	# mount point itself can exist, and can even contain files (e.g. README with mount instructions)
	# so only check existance of specific path and notebook.zim file
	if root.file('notebook.zim').exists():
		return False
	elif path.path == root.path:
		return True
	elif path.ischild(root):
		# Check none of the intermediate folders exist
		for parent in LocalFolder(path).parents():
			if parent.path == root.path:
				break
			elif parent.exists():
				return False
	else:
		return False


class ApplicationMountPointHandler(object):
	# TODO add password prompt logic, provide to cmd as argument, stdin

	def __init__(self, dir, mount, **a):
		self.dir = dir
		self.mount = mount

	def __call__(self, path):
		from zim.applications import Application
		logger.info('Mount: %s', self.dir)
		try:
			Application(self.mount).run()
		except:
			logger.exception('Failed to run: %s', self.mount)

		try:
			path = localFileOrFolder(path)
		except FileNotFoundError:
			return False
		else:
			return path.exists()


def init_notebook(dir, name=None):
	'''Initialize a new notebook in a directory'''
	from .notebook import NotebookConfig
	dir.touch()
	config = NotebookConfig(dir.file('notebook.zim'))
	config['Notebook']['name'] = name or dir.basename
	config.write()
