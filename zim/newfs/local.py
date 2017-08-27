# -*- coding: utf-8 -*-

# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Local file system object'''

from __future__ import with_statement

import sys
import os
import time
import shutil
import tempfile
import errno

import logging

logger = logging.getLogger('zim.newfs')


from . import FS_CASE_SENSITIVE, FS_ENCODING
from .base import *
from .base import _EOL, _SEP, _encode_path

from zim.environ import environ
from zim.parsing import url_encode, URL_ENCODE_READABLE


def _os_lrmdir(path):
    '''Wrapper for C{os.rmdir} that also knows how to unlink symlinks.
    Fails when the folder is not a link and is not empty.
    @param path: a file system path as string
    '''
    try:
        os.rmdir(path)
    except OSError:
        if os.path.islink(path) and os.path.isdir(path):
            os.unlink(path)
        else:
            raise


class LocalFSObjectBase(FSObjectBase):

    def __init__(self, path, watcher=None):
        FSObjectBase.__init__(self, path, watcher=watcher)
        self.encodedpath = _encode_path(self.path)

    def _stat(self):
        try:
            return os.stat(self.encodedpath)
        except OSError:
            raise FileNotFoundError(self)

    def _set_mtime(self, mtime):
        os.utime(self.encodedpath, (mtime, mtime))

    def parent(self):
        dirname = self.dirname
        if dirname is None:
            raise ValueError('Can not get parent of root')
        else:
            return LocalFolder(dirname, watcher=self.watcher)

    def ctime(self):
        return self._stat().st_ctime

    def mtime(self):
        return self._stat().st_mtime

    def iswritable(self):
        if self.exists():
            return os.access(self.encodedpath, os.W_OK)
        else:
            return self.parent().iswritable()  # recurs

    def isequal(self, other):
        # Do NOT assume paths are the same - could be hard link
        # or it could be a case-insensitive filesystem
        try:
            stat_result = os.stat(self.encodedpath)
            other_stat_result = os.stat(other.encodedpath)
        except OSError:
            return False
        else:
            return stat_result == other_stat_result

    def moveto(self, other):
        # Using shutil.move instead of os.rename because move can cross
        # file system boundaries, while rename can not
        if isinstance(self, File):
            if isinstance(other, Folder):
                other = other.file(self.basename)

            assert isinstance(other, File)
        else:
            assert isinstance(other, Folder)

        if not isinstance(other, LocalFSObjectBase):
            raise NotImplementedError('TODO: support cross object type move')

        assert not other.path == self.path  # case sensitive
        logger.info('Rename %s to %s', self.path, other.path)

        if not FS_CASE_SENSITIVE \
                and self.path.lower() == other.path.lower():
            # Rename to other case - need in between step
            other = self.__class__(other, watcher=self.watcher)
            tmp = self.parent().new_file(self.basename)
            shutil.move(self.encodedpath, tmp.encodedpath)
            shutil.move(tmp.encodedpath, other.encodedpath)
        elif os.path.exists(_encode_path(other.path)):
            raise FileExistsError(other)
        else:
            # normal case
            other = self.__class__(other, watcher=self.watcher)
            other.parent().touch()
            shutil.move(self.encodedpath, other.encodedpath)

        if self.watcher:
            self.watcher.emit('moved', self, other)

        self._cleanup()
        return other


class LocalFolder(LocalFSObjectBase, Folder):

    def exists(self):
        return os.path.isdir(self.encodedpath)

    def touch(self, mode=None):
        if not self.exists():
            self.parent().touch(mode)
            try:
                if mode is not None:
                    os.mkdir(self.encodedpath, mode)
                else:
                    os.mkdir(self.encodedpath)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
            else:
                if self.watcher:
                    self.watcher.emit('created', self)

    def __iter__(self):
        names = self.list_names()
        return self._object_iter(names, True, True)

    def list_files(self):
        names = self.list_names()
        return self._object_iter(names, True, False)

    def list_folders(self):
        names = self.list_names()
        return self._object_iter(names, False, True)

    def _object_iter(self, names, showfile, showdir):
        # inner iter to force FileNotFoundError on call instead of first iter call
        for name in names:
            encpath = self.encodedpath + _SEP + _encode_path(name)
            if os.path.isdir(encpath):
                if showdir:
                    yield self.folder(name)
            else:
                if showfile:
                    yield self.file(name)

    def list_names(self):
        try:
            names = os.listdir(self.encodedpath)
        except OSError:
            raise FileNotFoundError(self)

        names = sorted([n for n in names
                        if n[0] not in ('.', '~') and n[-1] != '~'])
        # Ignore hidden files and tmp files

        if FS_ENCODING == 'mbcs':
            # We are running on windows and os.listdir will handle unicode natively
            assert isinstance(self.encodedpath, unicode)
            assert all(isinstance(n, unicode) for n in names)
            return names
        else:
            # If filesystem does not handle unicode natively and path for
            # os.listdir(path) is _not_ a unicode object, the result will
            # be a list of byte strings. We can decode them ourselves.
            assert not isinstance(self.encodedpath, unicode)
            encnames = []
            for n in names:
                try:
                    encnames.append(n.decode(FS_ENCODING))
                except UnicodeDecodeError:
                    logger.warn('Ignoring file: "%s" invalid file name', n)
            return encnames

    def file(self, path):
        return LocalFile(self.get_childpath(path), watcher=self.watcher)

    def folder(self, path):
        return LocalFolder(self.get_childpath(path), watcher=self.watcher)

    def child(self, path):
        p = self.get_childpath(path)
        encpath = _encode_path(p.path)
        if os.path.isdir(encpath):
            return self.folder(path)
        elif os.path.isfile(encpath):
            return self.file(path)
        else:
            raise FileNotFoundError(p)

    def copyto(self, other):
        assert isinstance(other, Folder)
        assert not other.path == self.path

        logger.info('Copy dir %s to %s', self.path, other.path)

        if isinstance(other, LocalFolder):
            if os.path.exists(other.encodedpath):
                raise FileExistsError(other)

            shutil.copytree(self.encodedpath, other.encodedpath, symlinks=True)
        else:
            self._copyto(other)

        if self.watcher:
            self.watcher.emit('created', other)

        return other

    def remove(self):
        if os.path.isdir(self.encodedpath):
            try:
                _os_lrmdir(self.encodedpath)
            except OSError:
                raise FolderNotEmptyError('Folder not empty: %s' % self.path)
            else:
                if self.watcher:
                    self.watcher.emit('removed', self)

        self._cleanup()


# Replace logic based on discussion here:
# http://stupidpythonideas.blogspot.nl/2014/07/getting-atomic-writes-right.html
#
# The point is to get a function to replace an old file with a new
# file as "atomic" as possible

if hasattr(os, 'replace'):
    _replace_file = os.replace
elif sys.platform == 'win32':
    # The win32api.MoveFileEx method somehow does not like our unicode,
    # the ctypes version does ??!
    import ctypes
    _MoveFileEx = ctypes.windll.kernel32.MoveFileExW
    _MoveFileEx.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    _MoveFileEx.restype = ctypes.c_bool

    def _replace_file(src, dst):
        try:
            if not _MoveFileEx(src, dst, 1):  # MOVEFILE_REPLACE_EXISTING
                raise OSError('Could not replace "%s" -> "%s"' % (src, dst))
        except:
            # Sometimes it fails - we play stupid and try again...
            time.sleep(0.5)
            if not _MoveFileEx(src, dst, 1):  # MOVEFILE_REPLACE_EXISTING
                raise OSError('Could not replace "%s" -> "%s"' % (src, dst))
else:
    _replace_file = os.rename


class AtomicWriteContext(object):
    # Functions for atomic write as a context manager
    # used by LocalFile.read and .readlines
    # Exposed as separate object to make it testable.
    # Should not be needed outside this module

    def __init__(self, file, mode='w'):
        self.path = file.encodedpath
        self.tmppath = self.path + '.zim-new~'
        self.mode = mode

    def __enter__(self):
        self.fh = open(self.tmppath, self.mode)
        return self.fh

    def __exit__(self, *exc_info):
        # flush to ensure write is done
        self.fh.flush()
        os.fsync(self.fh.fileno())
        self.fh.close()

        if not any(exc_info) and os.path.isfile(self.tmppath):
            # do the replace magic
            _replace_file(self.tmppath, self.path)
        else:
            # errors happened - try to clean up
            try:
                os.remove(self.tmppath)
            except:
                pass


class LocalFile(LocalFSObjectBase, File):

    def __init__(self, path, endofline=_EOL, watcher=None):
        LocalFSObjectBase.__init__(self, path, watcher=watcher)
        self._mimetype = None
        self.endofline = endofline

    def exists(self):
        return os.path.isfile(self.encodedpath)

    def size(self):
        return self._stat().st_size

    def read_binary(self):
        try:
            with open(self.encodedpath, 'rb') as fh:
                return fh.read()
        except IOError:
            if not self.exists():
                raise FileNotFoundError(self)
            else:
                raise

    def read(self):
        try:
            with open(self.encodedpath, 'rU') as fh:
                try:
                    text = fh.read().decode('UTF-8')
                except UnicodeDecodeError as err:
                    raise FileUnicodeError(self, err)
                else:
                    return text.lstrip(u'\ufeff').replace('\x00', '')
                    # Strip unicode byte order mark
                    # Internally we use Unix line ends - so strip out \r
                    # And remove any NULL byte since they screw up parsing
        except IOError:
            if not self.exists():
                raise FileNotFoundError(self)
            else:
                raise

    def readlines(self):
        try:
            with open(self.encodedpath, 'rU') as fh:
                return [
                    l.decode('UTF-8').lstrip(u'\ufeff').replace('\x00', '')
                    for l in fh]
                # Strip unicode byte order mark
                # Internally we use Unix line ends - so strip out \r
                # And remove any NULL byte since they screw up parsing
        except IOError:
            if not self.exists():
                raise FileNotFoundError(self)
            else:
                raise

    def write(self, text):
        text = text.encode('UTF-8')
        if self.endofline != _EOL:
            if self.endofline == 'dos':
                text = text.replace('\n', '\r\n')
            mode = 'wb'
        else:
            mode = 'w'  # trust newlines to be handled

        with self._write_decoration():
            with AtomicWriteContext(self, mode=mode) as fh:
                fh.write(text)

    def writelines(self, lines):
        lines = map(lambda l: l.encode('UTF-8'), lines)
        if self.endofline != _EOL:
            if self.endofline == 'dos':
                lines = map(lambda l: l.replace('\n', '\r\n'), lines)
            mode = 'wb'
        else:
            mode = 'w'  # trust newlines to be handled

        with self._write_decoration():
            with AtomicWriteContext(self, mode=mode) as fh:
                fh.writelines(lines)

    def write_binary(self, data):
        with self._write_decoration():
            with AtomicWriteContext(self, mode='wb') as fh:
                fh.write(data)

    def touch(self):
        # overloaded because atomic write can cause mtime < ctime
        if not self.exists():
            with self._write_decoration():
                with open(self.encodedpath, 'w') as fh:
                    fh.write('')

    def copyto(self, other):
        if isinstance(other, Folder):
            other = other.file(self.basename)

        assert isinstance(other, File)
        assert other.path != self.path

        logger.info('Copy %s to %s', self.path, other.path)

        if isinstance(other, LocalFile):
            if os.path.exists(other.encodedpath):
                raise FileExistsError(other)

            other.parent().touch()
            shutil.copy2(self.encodedpath, other.encodedpath)
        else:
            self._copyto(other)

        if self.watcher:
            self.watcher.emit('created', other)

        return other

    def remove(self):
        if os.path.isfile(self.encodedpath):
            os.remove(self.encodedpath)

        if self.watcher:
            self.watcher.emit('removed', self)

        self._cleanup()


def get_tmpdir():
    '''Get a folder in the system temp dir for usage by zim.
    This zim specific temp folder has permission set to be readable
    only by the current users, and is touched if it didn't exist yet.
    Used as base folder by L{TmpFile}.
    @returns: a L{LocalFolder} object for the zim specific tmp folder
    '''
    # We encode the user name using urlencoding to remove any non-ascii
    # characters. This is because sockets are not always unicode safe.

    root = tempfile.gettempdir()
    name = url_encode(environ['USER'], URL_ENCODE_READABLE)
    dir = LocalFolder(tempfile.gettempdir()).folder('zim-%s' % name)

    try:
        dir.touch(mode=0o700)  # Limit to single user
        os.chmod(dir.encodedpath, 0o700)  # Limit to single user when dir already existed
        # Raises OSError if not allowed to chmod
        os.listdir(dir.encodedpath)
        # Raises OSError if we do not have access anymore
    except OSError:
        raise AssertionError('Either you are not the owner of "%s" or the permissions are un-safe.\n'
                             'If you can not resolve this, try setting $TMP to a different location.' % dir.path)
    else:
        # All OK, so we must be owner of a safe folder now ...
        return dir


class TmpFile(LocalFile):
    '''Class for temporary files. These are stored in the temp directory
    and by default they are deleted again when the object is destructed.
    '''

    def __init__(self, basename, unique=True, persistent=False):
        '''Constructor
        @param basename: gives the name for this tmp file.
        @param unique: if C{True} the L{Dir.new_file()} method is used
        to make sure we have a new file.
        @param persistent: if C{False} the file will be removed when the
        object is destructed, if C{True} we leave it alone
        '''
        dir = get_tmpdir()
        if unique:
            LocalFile.__init__(self, dir.new_file(basename))
        else:
            LocalFile.__init__(self, dir.get_childpath(basename))

        self.persistent = persistent

    def __del__(self):
        if not self.persistent:
            self.remove()
