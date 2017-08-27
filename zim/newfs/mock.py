# -*- coding: utf-8 -*-

# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Mock objects for file system classes

Since the file system is an external resource that assumes an
underlying reality, it is a hard thing to mock in test cases.
However it is also relatively slow, so having a good mock makes
good test cases much more usable.
Therefore we go to great lenght here to have a full set of mock
classes for all file system related objects.
'''

from __future__ import with_statement

import os
import time

from .base import *
from .base import _EOL, _SEP


__all__ = ('MockFolder', 'MockFile')


def clone_mock_object(source, target):
    '''Similar to C{copyto}, but used to copy to a mock object
    that belongs to another mock filesystem hierarchy.
    @param source: a L{MockFile} or L{MockFolder}
    @param target: another L{MockFile} or L{MockFolder}
    '''
    assert source.__class__ is target.__class__
    mynode = source._node()
    newnode = target._fs.touch(target.pathnames, mynode.deepcopy_data())
    newnode.ctime = mynode.ctime
    newnode.mtime = mynode.mtime


def os_native_path(unixpath):
    '''Adapts unix style paths for windows if needed
    Used for convenience to of writing cross-platform test cases
    Called automatically when constructing a L{MockFile} or L{MockFolder} object
    Does not modify URLs
    @param unixpath: the (mock) unix path as a string
    '''
    assert isinstance(unixpath, basestring)
    if os.name == 'nt' and not is_url_re.match(unixpath):
        if unixpath.startswith('/'):
            unixpath = 'M:' + unixpath  # arbitrary drive letter, should be OK for mock
        return unixpath.replace('/', '\\')
    else:
        return unixpath


class MockFSNode(object):

    __slots__ = ('ctime', 'mtime', 'size', 'data', 'isdir')

    def __init__(self, data):
        assert isinstance(data, (basestring, dict))
        self.ctime = None
        self.mtime = None
        self.size = None
        self.isdir = isinstance(data, dict)
        self.data = data
        self.on_changed()

    def deepcopy_data(self):
        if self.isdir:
            new = {}
            for name, node in self.data.items():
                new[name] = MockFSNode(node.deepcopy_data())  # recurs
                new[name].ctime = node.ctime
                new[name].mtime = node.mtime
            return new
        else:
            return self.data

    def on_changed(self):
        # Called after change of data attribute to update
        # mtime, ctime and size attributes
        old = self.mtime
        self.mtime = time.time()
        if old and "%.2f" % self.mtime == "%.2f" % old:
            self.mtime += 0.01  # Hack to make tests pass ..
        if self.ctime is None:
            self.ctime = self.mtime
        self.size = len(self.data) if self.data else 0


class MockFS(MockFSNode):
    # Special node object that has some filesystem-like functions

    def __init__(self):
        MockFSNode.__init__(self, {})

    def tree(self):
        def walk(prefix, node):
            for name in node.data:
                yield prefix + name
                if node.data[name].isdir:
                    for line in walk(prefix + name + '/', node.data[name]):
                        yield line

        return walk('', self)

    def stat(self, names):
        # Find node below or self if 'names' is empty
        node = self
        for i, name in enumerate(names):
            parent = node
            if not parent.isdir:
                raise AssertionError('Not a folder: %s' % _SEP.join(names[:i + 1]))
            else:
                try:
                    node = parent.data[name]
                except KeyError:
                    raise FileNotFoundError(_SEP.join(names))
        return node

    def touch(self, names, data):
        # Walk nodes below and create new where needed
        if not names:
            return self  # toplevel always exists

        node = self
        for i, name in enumerate(names[:-1]):
            parent = node
            if not name in parent.data:
                parent.data[name] = MockFSNode({})  # new folder
                parent.on_changed()
            node = parent.data[name]
            if not node.isdir:
                raise AssertionError('Not a folder: %s' % _SEP.join(names[:i + 1]))

        parent, basename = node, names[-1]
        if basename not in parent.data:
            parent.data[basename] = MockFSNode(data)
            parent.on_changed()

        return parent.data[basename]


class MockFSObjectBase(FSObjectBase):
    # Base class for MockFolder and MockFile. It uses an internal
    # structure of MockFSNode objects to represent a file tree. Between
    # external facing objects this internal structure is passed on.
    # The result is that there is persistency as long as any of the
    # file or folder objects created is alive. Also multiple objects
    # can refer to the same resource; same as with a real external
    # file system.

    def __init__(self, path, watcher=None, _fs=None):
        if isinstance(path, basestring):
            path = os_native_path(path)  # make test syntax easier
        FSObjectBase.__init__(self, path, watcher=watcher)
        if not _fs:
            _fs = MockFS()
        self._fs = _fs
        assert isinstance(self._fs, MockFS)

    def __eq__(self, other):
        return FilePath.__eq__(self, other) and other._fs is self._fs

    def _set_mtime(self, mtime):
        assert isinstance(mtime, (int, float))
        node = self._node()
        node.mtime = mtime

    def _node(self):
        raise NotImplemented

    def parent(self):
        dirname = self.dirname
        if dirname is None:
            raise ValueError('Can not get parent of root')
        else:
            return MockFolder(dirname, watcher=self.watcher, _fs=self._fs)

    def exists(self):
        try:
            self._node()
        except FileNotFoundError:
            return False
        else:
            return True

    def iswritable(self):
        return True

    def isequal(self, other):
        return isinstance(other, self.__class__) \
            and self._fs is other._fs \
            and self.path == other.path

    def ctime(self):
        return self._node().ctime

    def mtime(self):
        return self._node().mtime

    def moveto(self, other):
        if isinstance(self, File) and isinstance(other, Folder):
            other = other.file(self.basename)

        if not isinstance(other, MockFSObjectBase):
            raise NotImplementedError('TODO: support cross object type move')

        self._mock_copyto(other)
        self._remove(removechildren=True)
        if self.watcher:
            self.watcher.emit('moved', self, other)

        self._cleanup()
        return other

    def copyto(self, other):
        if isinstance(self, File) and isinstance(other, Folder):
            other = other.file(self.basename)

        if isinstance(other, MockFSObjectBase):
            self._mock_copyto(other)
        else:
            assert isinstance(other, (File, Folder))
            self._copyto(other)

        if self.watcher:
            self.watcher.emit('created', other)
        return other

    def _mock_copyto(self, other):
        assert other._fs is self._fs
        assert not other.path == self.path

        if isinstance(self, File):
            assert isinstance(other, File)
        else:
            assert isinstance(other, Folder)

        try:
            node = self._fs.stat(other.pathnames)
        except FileNotFoundError:
            mynode = self._node()
            newnode = self._fs.touch(other.pathnames, mynode.deepcopy_data())
            newnode.ctime = mynode.ctime
            newnode.mtime = mynode.mtime
        else:
            raise FileExistsError(other)

    def remove(self):
        if self.exists():
            self._remove()
            if self.watcher:
                self.watcher.emit('removed', self)

        self._cleanup()

    def _remove(self, removechildren=False):
        node = self._node()
        if node.isdir and node.data and not removechildren:
            raise FolderNotEmptyError(self)

        parentnode = self._fs.stat(self.pathnames[:-1])
        parentnode.data.pop(self.pathnames[-1])
        parentnode.on_changed()


class MockFolder(MockFSObjectBase, Folder):

    def _node(self):
        node = self._fs.stat(self.pathnames)
        if not node.isdir:
            raise AssertionError('Not a folder: %s' % self.path)
        return node

    def exists(self):
        try:
            return self._node().isdir
        except:
            return False

    def touch(self):
        if not self.exists():
            try:
                self.parent().touch()
            except ValueError:
                pass

            node = self._fs.touch(self.pathnames, {})
            if not node.isdir:
                raise AssertionError('Not a folder: %s' % self.path)

            if self.watcher:
                self.watcher.emit('created', self)

    def __iter__(self):
        children = self._node().data
        return self._object_iter(children, True, True)

    def list_files(self):
        children = self._node().data
        return self._object_iter(children, True, False)

    def list_folders(self):
        children = self._node().data
        return self._object_iter(children, False, True)

    def _object_iter(self, children, showfile, showdir):
        # inner iter to force FileNotFoundError on call instead of first iter call
        for name, node in sorted(children.items()):
            if node.isdir:
                if showdir:
                    yield self.folder(name)
            else:
                if showfile:
                    yield self.file(name)

    def list_names(self):
        children = self._node().data
        return sorted(children.keys())

    def file(self, path):
        return MockFile(self.get_childpath(path), watcher=self.watcher, _fs=self._fs)

    def folder(self, path):
        return MockFolder(self.get_childpath(path), watcher=self.watcher, _fs=self._fs)

    def child(self, path):
        # Will raise if path does not exist
        p = self.get_childpath(path)
        node = self._fs.stat(p.pathnames)
        if node.isdir:
            return self.folder(path)
        else:
            return self.file(path)


class MockFile(MockFSObjectBase, File):

    def __init__(self, path, endofline=_EOL, watcher=None, _fs=None):
        assert endofline in ('dos', 'unix')
        MockFSObjectBase.__init__(self, path, watcher=watcher, _fs=_fs)
        self._mimetype = None
        self.endofline = endofline  # attribute not used in this mock ..

    def _node(self):
        node = self._fs.stat(self.pathnames)
        if node.isdir:
            raise AssertionError('Not a file: %s' % self.path)
        return node

    def size(self):
        return self._node().size

    def read_binary(self):
        return self._node().data

    def read(self):
        return self._node().data

    def readlines(self):
        return self.read().splitlines(True)

    def write(self, text):
        assert isinstance(text, basestring)

        with self._write_decoration():
            try:
                node = self._node()
            except FileNotFoundError:
                self._fs.touch(self.pathnames, text)
            else:
                node.data = text
                node.on_changed()

    write_binary = write

    def writelines(self, lines):
        self.write(''.join(lines))
