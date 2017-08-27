# -*- coding: utf-8 -*-

# Copyright 2008-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import re
import codecs

from .page import Path

from zim.newfs import FS_ENCODING, File, Folder, _EOL, _SEP
from zim.formats import get_format

FILE_TYPE_PAGE_SOURCE = 1
FILE_TYPE_ATTACHMENT = 2


def _url_encode_on_error(error):
    string = error.object
    section = string[error.start:error.end].encode('utf-8')
    replace = u''
    for char in section:
        replace += u'%%%02X' % ord(char)
    return replace, error.end

codecs.register_error('urlencode', _url_encode_on_error)


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
    assert not '%' in pagename  # just to be sure
    if not FS_ENCODING in ('utf-8', 'mbcs'):
        # if not utf-8 we may not be able to encode all characters
        # enforce safe encoding, but do not actually encode here
        # ('mbcs' means we are running on windows and filesystem can
        # handle unicode natively )
        pagename = pagename.encode(FS_ENCODING, 'urlencode')
        pagename = pagename.decode(FS_ENCODING)
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
    if FS_ENCODING != 'utf-8':
        filename = filename.encode('utf-8')
        filename = _url_decode_re.sub(_url_decode, filename)
        filename = filename.decode('utf-8')
    return filename.replace('\\', ':').replace('/', ':').replace('_', ' ')


class NotebookLayout(object):
    pass


class FilesLayout(NotebookLayout):
    '''Layout is responsible for mapping between pages and files.
    This is the most basic version, where each page maps to the
    like-named file.
    '''

    default_extension = '.txt'
    default_format = get_format('wiki')

    def __init__(self, folder, endofline=_EOL):
        '''Constructor
        @param folder: a L{Folder} object
        @param endofline: either "dos" or "unix", default per OS
        '''
        assert isinstance(folder, Folder)
        self.root = folder
        self.endofline = _EOL

    def map_page(self, pagename):
        '''Map a pagename to a (default) file
        @param pagename: a L{Path}
        @returns: a 2-tuple of a L{File} for the source and a L{Folder}
        for the attachments. Neither of these needs to exist.
        '''
        path = encode_filename(pagename.name)
        file = self.root.file(path + self.default_extension)
        file.endofline = self.endofline  # TODO, make this auto-detect for existing files ?
        folder = self.root.folder(path) if path else self.root
        return file, folder

    def get_attachments_folder(self, pagename):
        file, folder = self.map_page(pagename)
        return FilesAttachmentFolder(folder, self.default_extension)

    def map_file(self, file):
        '''Map a filepath to a pagename
        @param file: a L{File} or L{FilePath} object
        @returns: a L{Path} and a file type (C{FILE_TYPE_PAGE_SOURCE},
        F{FILE_TYPE_ATTACHMENT})
        '''
        path = file.relpath(self.root)
        return self.map_filepath(path)

    def map_filepath(self, path):
        '''Like L{map_file} but takes a string with relative path'''
        if path.endswith(self.default_extension):
            path = path[:-len(self.default_extension)]
            type = FILE_TYPE_PAGE_SOURCE
        else:
            if _SEP in path:
                path, x = path.rsplit(_SEP, 1)
            else:
                path = ':'  # ROOT_PATH
            type = FILE_TYPE_ATTACHMENT
        if path == ':':
            return Path(':'), type
        else:
            name = decode_filename(path)
            Path.assertValidPageName(name)
            return Path(name), type

    def resolve_conflict(self, *filepaths):
        '''Decide which is the real page file when multiple files
        map to the same page.
        @param filepaths: 2 or more L{FilePath} objects
        @returns: L{FilePath} that should take precedent as te page
        source
        '''
        filespaths.sort(key=lambda p: (p.ctime(), p.basename))
        return filepaths[0]

    def get_format(self, file):
        if file.path.endswith(self.default_extension):
            return self.default_format
        else:
            raise AssertionError('Unknown file type for page: %s' % file)

    def index_list_children(self, pagename):
        # Convenience method - remove if no longer used by the index
        file, folder = self.map_page(pagename)
        if not folder.exists():
            return []

        names = set()
        for object in folder:
            if isinstance(object, File):
                if object.path.endswith(self.default_extension):
                    name = object.basename[:-len(self.default_extension)]
                else:
                    continue
            else:  # Folder
                name = object.basename

            pname = decode_filename(name)
            if encode_filename(pname) == name:  # will reject e.g. whitespace in file name
                names.add(pname)

        return [pagename + basename for basename in sorted(names)]


class FilesAttachmentFolder(object):

    def __init__(self, folder, default_extension):
        self._folder = folder
        self._default_extension = default_extension

    def __getattr__(self, name):
        return getattr(self._folder, name)

    def __iter__(self):
        for obj in self._folder:
            if isinstance(obj, File) \
            and not obj.basename.endswith(self._default_extension) \
            and not obj.basename.endswith('.zim'):
                yield obj

    def list_names(self):
        for obj in self.__iter__():
            yield obj.basename

    def list_files(self):
        return self.__iter__()

    def list_folders(self):
        return []
