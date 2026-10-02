
# Copyright 2008-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import re
import sys
import enum

from .page import Path

from zim.newfs import File, Folder, _EOL, SEP, FileNotFoundError, FileExistsError
from zim.formats import get_format, list_formats, NATIVE_FORMAT

import zim.parse.encode # we use "error=urlencode" which is registerd in this module


class FileType(enum.Enum):
	PAGE_SOURCE = 1
	ATTACHMENT = 2

FILE_TYPE_PAGE_SOURCE = FileType.PAGE_SOURCE
FILE_TYPE_ATTACHMENT = FileType.ATTACHMENT

_fs_encoding = sys.getfilesystemencoding()


def encode_filename(pagename):
	'''Encode a pagename to a filename

	Since the filesystem may use another encoding than UTF-8 it may
	not be able to use all valid page names directly as file names.
	Therefore characters that are not allowed for the filesystem are
	replaced with url encoding. The result is still unicode, which can
	be used to construct a L{File} object. (The File object
	implementation takes care of actually encoding the string when
	needed.)

	Namespaces are mapped to directories by replacing ":" with "/".

	@param pagename: the pagename as string or unicode object
	@returns: the filename as unicode object but with characters
	incompatble with the filesystem encoding replaced
	'''
	assert not '%' in pagename # just to be sure
	pagename = pagename.encode(_fs_encoding, 'urlencode')
	pagename = pagename.decode(_fs_encoding)
	return pagename.replace(':', '/').replace(' ', '_')


_url_decode_re = re.compile('%([a-fA-F0-9]{2})')

def _url_decode(match):
	return chr(int(match.group(1), 16))


def decode_filename(filename):
	'''Decodes a filename to a pagename

	Reverse operation of L{encode_filename()}.

	@param filename: the filename as string or unicode object
	@returns: the pagename as unicode object
	'''
	filename = _url_decode_re.sub(_url_decode, filename)
	return filename.replace('\\', ':').replace('/', ':').replace('_', ' ')


class NotebookLayout(object):
	'''Object supporting the notebook with file-system layout logic

	The Layout is responsible for mapping between pages and files.
	It serves both the notebook directly and indirectly via the index.
	It does not maintain state, but just does the mapping on demand.
	State is done via the index.
	'''
	pass


class FilesLayout(NotebookLayout):
	'''Layout implementation which maps each page to a file of the same name

	For example::

		page -> page.txt
		page:subpage -> page/subpage.txt

	'''

	# NOTE: We assume source files always have a file extension

	def __init__(self, folder: Folder, default_format='zim-wiki', default_extension='.txt', endofline=_EOL):
		'''Constructor
		@param folder: a L{Folder} object
		@param endofline: either "dos" or "unix", default per OS
		'''
		assert isinstance(folder, Folder)
		assert endofline in ('dos', 'unix')
		self.root = folder
		self.endofline = endofline

		self.supported_formats = {n: get_format(n) for n, l in list_formats(NATIVE_FORMAT)}
		self.supported_extensions = {}
		for name, format in self.supported_formats.items():
			self.supported_extensions.update({e: format for e in format.info['extensions']})
		self.set_format(default_format, default_extension)
	
	def set_format(self, default_format: str, default_extension: str):
		if not default_format in self.supported_formats:
			raise ValueError('Format not supported for notebook layout: %s' % default_format)

		if not default_extension.startswith('.'):
			default_extension = '.' + default_extension

		self.default_extension = default_extension
		self.default_format = get_format(default_format)

	def is_source_file(self, file: File) -> bool:
		'''Check whether file is in source format
		Does not check for conflicting files, so does not guarantee this file is used
		in the notbook
		'''
		x, ext = file.basename.rsplit('.', 1) if '.' in file.basename else (None, None)

		if ext and ext in self.supported_extensions:
			pname = decode_filename(file.basename)
			if encode_filename(pname) != file.basename: # will reject e.g. whitespace in file name
				return False

			if self.supported_extensions[ext].info['mimetype'] == 'text/x-zim-wiki':
				try:
					line = file.readline(size=50) # max size to allow for some trailing whitespace and end-of-line
					return line.strip() == 'Content-Type: text/x-zim-wiki'
				except FileNotFoundError:
					return True # give file the benefit of the doubt, could be a deleted source file
			else:
				# Other source formats, like markdown, can still contain
				# frontmatter, but will accept based on file extension only
				return True
		else:
			return False

	def map_page(self, pagename: Path) -> tuple[File, Folder]:
		'''Map a pagename to a (default) source file and folder
		If the default source file does not exist, also checks for other supported formats
		@param pagename: a L{Path}
		@returns: a 2-tuple of a L{File} for the source and a L{Folder} for the attachments. Neither of these needs to exist.
		'''
		path = encode_filename(pagename.name)

		file = self.root.file(path + self.default_extension)
		if not file.exists():
			file = self._check_alternatives(file)

		file.endofline = self.endofline ## TODO, make this auto-detect for existing files ?
		folder = self.root.folder(path) if path else self.root
		return file, folder

	def map_page_with_fixed_format(self, pagename: Path, extension: str) -> tuple[File, Folder]:
		'''Like L{map_page} for enforces the file extension to be used
		Does not check for conflicts, so this method should only be used in cases where it is
		already known whether there are conflicting files.
		'''
		path = encode_filename(pagename.name)
		file = self.root.file(path + '.' + extension.strip('.'))
		file.endofline = self.endofline ## TODO, make this auto-detect for existing files ?
		folder = self.root.folder(path) if path else self.root
		return file, folder

	def get_attachments_folder(self, pagename: Path) -> 'FilesAttachmentFolder':
		file, folder = self.map_page(pagename)
		return FilesAttachmentFolder(folder, self.is_source_file)

	def map_file(self, file: File) -> tuple[Path, FileType]:
		'''Map a filepath to a pagename and a file type
		In determining the file type, alternative formats are supported, in case of conflicting
		names only one file is identified as the source
		@param file: a L{File} or L{FilePath} object
		@returns: a L{Path} and a file type (C{FILE_TYPE_PAGE_SOURCE}, C{FILE_TYPE_ATTACHMENT})
		'''
		type = FILE_TYPE_PAGE_SOURCE if self.is_source_file(file) else FILE_TYPE_ATTACHMENT

		if type == FILE_TYPE_PAGE_SOURCE and not (file.basename.endswith(self.default_extension) and file.exists()):
			# It looks like a page source, but not in the default format --> check for conflicts
			source = self._check_alternatives(file)
			if source != file:
				type = FILE_TYPE_ATTACHMENT

		path = file.relpath(self.root)
		if type == FILE_TYPE_PAGE_SOURCE:
			path, x = path.rsplit('.', 1)
		else: # FILE_TYPE_ATTACHMENT
			if SEP in path:
				path, x = path.rsplit(SEP, 1)
			else:
				path = ':' # ROOT_PATH

		if path == ':':
			return Path(':'), type
		else:
			name = decode_filename(path)
			Path.assertValidPageName(name)
			return Path(name), type

	def map_filepath(self, path):
		'''Like L{map_file} but takes a string with relative path'''
		return self.map_file(self.root.file(path))

	def _check_alternatives(self, file: File) -> File:
		# Check for alternative formats
		folder = file.parent()
		name, x = file.basename.rsplit('.', 1)
		candidates = []
		for f in [folder.file(name + '.' + ext) for ext in self.supported_extensions]:
			if f.exists():
				candidates.append(f)

		if candidates:
			return self.resolve_conflict(*candidates) if len(candidates) > 1 else candidates[0]
		else:
			return file

	def resolve_conflict(self, *files):
		'''Decide which is the real page file when multiple files map to the same page
		@param filepaths: 2 or more L{File} objects
		@returns: L{File} that should take precedent as te page source
		'''
		# First give prio to default extension, then go by creation date
		for f in files:
			if f.basename.endswith(self.default_extension):
				return f
		files = sorted(files, key=lambda p: (p.ctime(), p.basename))
		return files[0]

	def get_format(self, file):
		x, ext = file.basename.rsplit('.', 1) if '.' in file.basename else (None, None)
		if ext and ext in self.supported_extensions:
			return self.supported_extensions[ext]
		else:
			raise AssertionError('Unknown file type for page: %s' % file.basename)

	def move_page_resources(self, path: Path, newpath: Path) -> dict[File|Folder, File|Folder]:
		'''Move page source file(s) and attachements
		This is a low-level method that does not update the notebook index etc.
		It should only by used when several pre-conditions are checked - e.g. the new page
		should not already exist
		See C{Notebook.move_page()} for high level interface.
		@param path: current page path
		@param newpath: destination page path
		@returns: a dictionary of changes, mapping old file or folder to new file or folder
		'''
		# Implemented here as the logic here might depend on the file and folder layout
		# and it deals with e.g. making sure new file is detected as the right format

		file, folder = self.map_page(path)
		if not (file.exists() or folder.exists()):
			raise FileNotFoundError(file)

		newfile, newfolder = self.map_page_with_fixed_format(newpath, file.extension)
			# Preserving file extensions, because else things go wrong with
			# the format detection next time the page is loaded

		if file.path.lower() == newfile.path.lower() \
			and (newfile.isequal(file) or newfolder.isequal(folder)):
				pass # renaming on case-insensitive filesystem
		elif newfile.exists():
			raise FileExistsError(newfile)
		elif newfolder.exists():
			raise FileExistsError(newfolder)

		# First move the dir - if it fails due to some file being locked
		# the whole move is cancelled. Chance is bigger than the other
		# way around, e.g. attachment open in external program.

		changes = []

		if folder.exists():
			if newfolder.ischild(folder):
				# special case where we want to move a page down
				# into it's own namespace
				parent = folder.parent()
				tmp = parent.new_folder(folder.basename)
				folder.moveto(tmp)
				tmp.moveto(newfolder)
			else:
				folder.moveto(newfolder)

			changes.append((folder, newfolder))

			# check if we also moved the file inadvertently
			if file.ischild(folder):
				rel = file.relpath(folder)
				movedfile = newfolder.file(rel)
				if movedfile.exists() and movedfile.path != newfile.path:
						movedfile.moveto(newfile)
						changes.append((movedfile, newfile))
			elif file.exists():
				file.moveto(newfile)
				changes.append((file, newfile))

		elif file.exists():
			file.moveto(newfile)
			changes.append((file, newfile))

		return changes


class FilesAttachmentFolder(object):
	'''Filter around a L{Folder} object which filters out source files'''

	def __init__(self, folder, is_source_file_func):
		self._inner_fs_object = folder
		self._is_source_file_func = is_source_file_func

	def __str__(self):
		return str(self._inner_fs_object)

	def __getattr__(self, name):
		return getattr(self._inner_fs_object, name)

	def __iter__(self):
		for obj in self._inner_fs_object:
			if isinstance(obj, File) \
			and not self._is_source_file_func(obj) \
			and not obj.basename.endswith('.zim'):
				yield obj

	def list_names(self):
		for obj in self.__iter__():
			yield obj.basename

	def list_files(self):
		return self.__iter__()

	def list_folders(self):
		return []
