# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement


import sqlite3
import logging

logger = logging.getLogger('zim.notebook.index')

try:
    import gobject
except ImportError:
    gobject = None


from zim.newfs import LocalFile, File, Folder, FileNotFoundError
from zim.signals import SignalEmitter

from zim.notebook.operations import NotebookOperation, NotebookOperationOngoing, ongoing_operation

from .files import *
from .base import *
from .pages import *
from .links import *
from .tags import *


DB_VERSION = '0.7'


class Index(SignalEmitter):
    '''The Index keeps a cache of all pages in a notebook store, all
    links between pages and all tags. This data is used to speed up
    many operatons in the user interface, like showing the notebook
    index in the side pane, showing "what links here" and faster search
    for page attributes.

    The C{Index} object is an opaque object that only exposes an API
    to trigger index updates and notifications when changes are found.
    It does not expose the data it keeps directly. To query the index,
    you need to construct an "index view" first, see e.g. the
    L{PagesIndexView}, L{LinksIndexView} and L{TagsIndexView} classes.
    For convenience the L{Notebook} class also exposes these three
    views with the respective attributes C{pages}, C{links} and C{tags}.

    @signal: C{new-update-iter (update_iter)}: signal used for plugins wanting
    to extend the indexer
    @signal: C{changed ()}: emitted after changes have been committed
    '''

    __signals__ = {
            'new-update-iter': (None, None, (object,)),
            'changed': (None, None, ()),
    }

    def __init__(self, dbpath, layout):
        '''Constructor
        @param dbpath: a file path for the sqlite db, or C{":memory:"}
        @param layout: a L{NotebookLayout} instance to index
        '''
        self.dbpath = dbpath
        self.layout = layout
        self._db = self._new_connection()
        self._db_check()
        if not hasattr(self, 'update_iter'):
            self._update_iter_init()
        # else _update_iter_init already called view _db_check --> _db_init

        self._checker = FilesIndexChecker(self._db, self.layout.root)
        self.background_check = BackgroundCheck(self._checker, None)

    def _update_iter_init(self):
        self.update_iter = IndexUpdateIter(self._db, self.layout)
        self.update_iter.connect('commit', self.on_commit)
        self.emit('new-update-iter', self.update_iter)

    def on_commit(self, iter):
        self.emit('changed')

    def _new_connection(self):
        db = sqlite3.Connection(self.dbpath)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=OFF;')
        # Don't wait for disk writes, we can recover from crashes
        # anyway. Allows us to use commit more frequently.
        return db

    def _db_check(self):
        try:
            if self.get_property('db_version') == DB_VERSION:
                pass
            else:
                logger.debug('Index db_version out of date')
                self._db_init()
        except sqlite3.OperationalError:
            # db is there but table does not exist
            logger.debug('Operational error, init tabels')
            self._db_init()
        except sqlite3.DatabaseError:
            assert not self.dbpath == ':memory:'
            logger.warning('Overwriting possibly corrupt database: %s', self.dbpath)
            self.db.close()
            file = LocalFile(self.dbpath)
            try:
                file.remove()
            except:
                logger.exception('Could not delete: %s', file)
                # TODO: how to recover form this ? - seems fatal
            finally:
                self._db = self._new_connection()
                self._db_init()

        # TODO checks on locale, others?

    def _db_init(self):
        tables = [r[0] for r in self._db.execute(
                'SELECT name FROM sqlite_master '
                'WHERE type="table" and name NOT LIKE "sqlite%"'
        )]
        for table in tables:
            self._db.execute('DROP TABLE %s' % table)

        logger.debug('(Re-)Initializing database for index')
        self._db.executescript('''
			CREATE TABLE zim_index (
				key TEXT,
				value TEXT,
				CONSTRAINT uc_MetaOnce UNIQUE (key)
			);
			INSERT INTO zim_index VALUES ('db_version', %r)
		''' % DB_VERSION)

        self._update_iter_init()  # Force re-init of all tables
        self._db.commit()

    def get_property(self, key):
        c = self._db.execute('SELECT value FROM zim_index WHERE key=?', (key,))
        row = c.fetchone()
        return row[0] if row else None

    def set_property(self, key, value):
        if value is None:
            self._db.execute('DELETE FROM zim_index WHERE key=?', (key,))
        else:
            self._db.execute('INSERT OR REPLACE INTO zim_index VALUES (?, ?)', (key, value))

    @property
    def is_uptodate(self):
        row = self._db.execute(
                'SELECT * FROM files WHERE index_status=?',
                (STATUS_NEED_UPDATE,)
        ).fetchone()
        return row is None

    def check_and_update(self):
        '''Update all data in the index'''
        self.update_iter.check_and_update()

    def check_and_update_iter(self):
        return self.update_iter.check_and_update_iter()

    def check_async(self, notebook, paths, recursive=False):
        assert gobject, 'async operation requires gobject mainloop'
        for path in paths:
            file, folder = self.layout.map_page(path)
            self._checker.queue_check(file, recursive=recursive)
            self._checker.queue_check(folder, recursive=recursive)

        self.background_check.callback = lambda *a: on_out_of_date_found(notebook, self.background_check)
        # XXX: should go via constructor, but there notebook is not known
        self.background_check.start()

    def flush(self):
        '''Delete all data in the index'''
        logger.info('Flushing index')
        self._db_init()

    def flag_reindex(self):
        '''This methods flags all pages with content to be re-indexed.
        Main reason to use this would be when loading a new plugin that
        wants to index all pages.
        Differs from L{flush()} because it does not drop all data
        '''
        from .files import STATUS_NEED_UPDATE
        self._db.execute(
                'UPDATE files SET index_status = ?'
                'WHERE id IN (SELECT source_file FROM pages)',
                (STATUS_NEED_UPDATE,)
        )

    def start_background_check(self, notebook):
        self.check_async(notebook, [Path(':')], recursive=True)

    def stop_background_check(self):
        self.background_check.stop()

    def update_file(self, file):
        path = file.relpath(self.layout.root)
        filesindexer = self.update_iter.files
        row = self._db.execute('SELECT id FROM files WHERE path=?', (path,)).fetchone()
        if row is None and not file.exists():
            pass
        else:
            filesindexer.emit('start-update')

            if row:
                node_id = row[0]
                if isinstance(file, File):
                    if file.exists():
                        filesindexer.update_file(node_id, file)
                    else:
                        filesindexer.delete_file(node_id)
                elif isinstance(file, Folder):
                    if file.exists():
                        filesindexer.update_folder(node_id, file)
                    else:
                        filesindexer.delete_folder(node_id)
                else:
                    raise TypeError
            else:  # file.exists():
                if isinstance(file, File):
                    filesindexer.interactive_add_file(file)
                elif isinstance(file, Folder):
                    filesindexer.interactive_add_folder(file)
                else:
                    raise TypeError

            filesindexer.emit('finish-update')
            self._db.commit()
            self.on_commit(None)

    def file_moved(self, oldfile, newfile):
        # TODO: make this more efficient, specific for moved folders
        #       by supporting moved pages in indexers
        self.update_file(oldfile)
        self.update_file(newfile)

    def touch_current_page_placeholder(self, path):
        '''Create a placeholder for C{path} if the page does not
        exist. Cleans up old placeholders.
        '''
        # This method uses a hack by linking the page from the ROOT_ID
        # page if it does not exist.

        # cleanup
        self._db.execute(
                'DELETE FROM links WHERE source=?',
                (ROOT_ID,)
        )
        self.update_iter.links.cleanup_placeholders(None)

        # touch if needed
        row = self._db.execute(
                'SELECT * FROM pages WHERE name = ?', (path.name,)
        ).fetchone()

        if row is None:
            pid = self.update_iter.pages.insert_link_placeholder(path)
            self._db.execute(  # Need link to prevent cleanup
                    'INSERT INTO links(source, target, rel, names) '
                    'VALUES (?, ?, ?, ?)',
                    (ROOT_ID, pid, HREF_REL_ABSOLUTE, path.name)
            )

        self._db.commit()
        self.emit('changed')


class IndexUpdateIter(SignalEmitter):

    __signals__ = {
            'commit': (None, None, ()),
    }

    def __init__(self, db, layout):
        self.db = db
        self.layout = layout
        self.files = FilesIndexer(db, layout.root)
        self.pages = PagesIndexer(db, layout, self.files)
        self.links = LinksIndexer(db, self.pages, self.files)
        self.tags = TagsIndexer(db, self.pages, self.files)

    def __call__(self):
        return self

    def __iter__(self):
        for i in self.files.update_iter():
            yield
        self.emit('commit')

    def update(self):
        '''Convenience method to do a full update at once'''
        for i in self.files.update_iter():
            pass
        self.emit('commit')

    def check_and_update(self, file=None):
        '''Convenience method to do a full update and check at once'''
        for i in self.check_and_update_iter(file):
            pass

    def check_and_update_iter(self, file=None):
        checker = FilesIndexChecker(self.db, self.layout.root)
        checker.queue_check(file=file)
        for out_of_date in checker.check_iter():
            yield
            if out_of_date:
                for i in self.files.update_iter():
                    yield
        self.emit('commit')


class BackgroundCheck(object):

    def __init__(self, checker, callback):
        self.checker = checker
        self.callback = callback
        self.running = False

    def start(self):
        if not self.running:
            my_iter = iter(self.on_idle_iter())
            gobject.idle_add(lambda: next(my_iter, False), priority=gobject.PRIORITY_LOW)
            self.running = True

    def stop(self):
        self.running = False

    def on_idle_iter(self):
        if self.running:
            check_iter = self.checker.check_iter()
            logger.debug('BackgroundCheck started')
            while self.running:
                try:
                    needsupdate = check_iter.next()
                    if needsupdate:
                        self.callback()
                        logger.debug('BackgroundCheck found out-of-date')
                        break
                    else:
                        yield True  # Continue loop
                except StopIteration:
                    logger.debug('BackgroundCheck finished')
                    break
            else:
                logger.debug('BackgroundCheck stopped')
            self.running = False


def on_out_of_date_found(notebook, background_check):
    op = IndexUpdateOperation(notebook)
    op.connect('finished', lambda *a: background_check.start())  # continue checking
    # TODO ensure robust in case operation gives error
    try:
        op.run_on_idle()
    except NotebookOperationOngoing:
        other_op = ongoing_operation(notebook)
        other_op.connect('finished', lambda *a: background_check.start())  # continue checking
        # TODO ensure robust in case operation gives error


class IndexUpdateOperation(NotebookOperation):

    def __init__(self, notebook):
        NotebookOperation.__init__(
                self,
                notebook,
                _('Updating index'),  # T: Title of progressbar dialog
                self._get_iter(notebook)
        )

    def _get_iter(self, notebook):
        return iter(notebook.index.update_iter)


class IndexCheckAndUpdateOperation(IndexUpdateOperation):

    def _get_iter(self, notebook):
        return notebook.index.check_and_update_iter()
