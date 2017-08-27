# -*- coding: utf-8 -*-

# Copyright 2008-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Test cases for the zim.notebook module.'''

from __future__ import with_statement

import tests

import os
import time

from zim.fs import File, Dir
from zim.newfs.mock import os_native_path
from zim.config import ConfigManager, XDG_CONFIG_HOME, VirtualConfigBackend
from zim.formats import ParseTree
from zim.formats.wiki import Parser as WikiParser

from zim.notebook import *
from zim.notebook.notebook import NotebookConfig, IndexNotUptodateError, PageExistsError
from zim.notebook.index import Index
from zim.notebook.layout import FilesLayout

import zim.newfs
import zim.newfs.mock


class TestNotebookInfo(tests.TestCase):

    def runTest(self):
        for location, uri in (
                (File('file:///foo/bar'), 'file:///foo/bar'),
                ('file:///foo/bar', 'file:///foo/bar'),
                ('zim+file:///foo?bar', 'zim+file:///foo?bar'),
            # specifically ensure the "?" does not get url encoded
        ):
            if os.name == 'nt':
                if isinstance(location, basestring):
                    location = location.replace('///', '///C:/')
                uri = uri.replace('///', '///C:/')
            info = NotebookInfo(location)
            self.assertEqual(info.uri, uri)


@tests.slowTest
class TestNotebookInfoList(tests.TestCase):

    def setUp(self):
        config = ConfigManager()
        list = config.get_config_file('notebooks.list')
        file = list.file
        if file.exists():
            file.remove()

    def runTest(self):
        root = Dir(self.create_tmp_dir(u'some_utf8_here_\u0421\u0430\u0439'))

        # Start empty - see this is no issue
        list = get_notebook_list()
        self.assertTrue(isinstance(list, NotebookInfoList))
        self.assertTrue(len(list) == 0)

        info = list.get_by_name('foo')
        self.assertIsNone(info)

        # Now create it
        dir = root.subdir('/notebook')
        init_notebook(dir, name='foo')

        # And put it in the list and resolve it by name
        list = get_notebook_list()
        list.append(NotebookInfo(dir.uri, name='foo'))
        list.write()

        self.assertTrue(len(list) == 1)
        self.assertTrue(isinstance(list[0], NotebookInfo))

        info = list.get_by_name('foo')
        self.assertEqual(info.uri, dir.uri)
        self.assertEqual(info.name, 'foo')

        newlist = get_notebook_list()  # just to be sure re-laoding works..
        self.assertTrue(len(list) == 1)
        info = newlist.get_by_name('foo')
        self.assertEqual(info.uri, dir.uri)
        self.assertEqual(info.name, 'foo')

        # Add a second entry
        if os.name == 'nt':
            uri1 = 'file:///C:/foo/bar'
        else:
            uri1 = 'file:///foo/bar'

        list = get_notebook_list()
        self.assertTrue(len(list) == 1)
        list.append(NotebookInfo(uri1, interwiki='foobar'))
        # on purpose do not set name, should default to basename
        list.write()

        self.assertTrue(len(list) == 2)
        self.assertEqual(list[:], [NotebookInfo(dir.uri), NotebookInfo(uri1)])

        # And check all works OK
        info = list.get_by_name('foo')
        self.assertEqual(info.uri, dir.uri)
        nb, path = build_notebook(info)
        self.assertIsInstance(nb, Notebook)
        self.assertIsNone(path)

        for name in ('bar', 'Bar'):
            info = list.get_by_name(name)
            self.assertEqual(info.uri, uri1)
            self.assertRaises(FileNotFoundError, build_notebook, info)
            # path should not exist

        # Test default
        list.set_default(uri1)
        list.write()
        list = get_notebook_list()
        self.assertIsNotNone(list.default)
        self.assertEqual(list.default.uri, uri1)

        # Check interwiki parsing - included here since it interacts with the notebook list
        self.assertEqual(interwiki_link('wp?Foo'), 'http://en.wikipedia.org/wiki/Foo')
        self.assertEqual(interwiki_link('foo?Foo'), 'zim+' + dir.uri + '?Foo')
        self.assertEqual(interwiki_link('foobar?Foo'), 'zim+' + uri1 + '?Foo')  # interwiki key
        self.assertEqual(interwiki_link('FooBar?Foo'), 'zim+' + uri1 + '?Foo')  # interwiki key
        self.assertEqual(interwiki_link('bar?Foo'), 'zim+' + uri1 + '?Foo')  # name
        self.assertEqual(interwiki_link('Bar?Foo'), 'zim+' + uri1 + '?Foo')  # name

        # Check backward compatibility
        file = File('tests/data/notebook-list-old-format.list')
        list = NotebookInfoList(file)
        self.assertEqual(list[:], [
            NotebookInfo(Dir(path).uri) for path in
                        ('~/Notes', '/home/user/code/zim.debug', '/home/user/Foo Bar')
        ])
        self.assertEqual(list.default,
                         NotebookInfo(Dir('/home/user/code/zim.debug').uri))


@tests.slowTest
class TestResolveNotebook(tests.TestCase):

    def setUp(self):
        config = ConfigManager()
        list = config.get_config_file('notebooks.list')
        file = list.file
        if file.exists():
            file.remove()

    def runTest(self):
        # First test some paths
        for input, uri in (
                ('file:///foo/bar', 'file:///foo/bar'),
                ('~/bar', Dir('~/bar').uri),
        ):
            if os.name == 'nt':
                input = input.replace('///', '///C:/')
                if not '///C:/' in uri:
                    uri = uri.replace('///', '///C:/')
            info = resolve_notebook(input)
            self.assertEqual(info.uri, uri)

        # Then test with (empty) notebook list
        info = resolve_notebook('foobar')
        self.assertIsNone(info)

        # add an entry and show we get it
        dir = Dir(self.create_tmp_dir()).subdir('foo')
        init_notebook(dir, name='foo')

        list = get_notebook_list()
        list.append(NotebookInfo(dir.uri, name='foo'))
        list.write()

        info = resolve_notebook('foo')
        self.assertIsNotNone(info)
        self.assertEqual(info.uri, dir.uri)


@tests.slowTest
class TestBuildNotebook(tests.TestCase):
    # Test including automount and uniqueness !

    def setUp(self):
        self.tmpdir = Dir(self.get_tmp_name())
        self.notebookdir = self.tmpdir.subdir('notebook')

        script = self.tmpdir.file('mount.py')
        script.write('''\
import os
import sys
notebook = sys.argv[1]
os.mkdir(notebook)
os.mkdir(notebook + '/foo')
for path in (
	notebook + "/notebook.zim",
	notebook + "/foo/bar.txt"
):
	fh = open(path, 'w')
	fh.write("")
	fh.close()
''')

        automount = XDG_CONFIG_HOME.file('zim/automount.conf')
        assert not automount.exists(), "Exists: %s" % automount
        automount.write('''\
[Path %s]
mount=%s %s
''' % (self.notebookdir.path, script.path, self.notebookdir.path))

    #~ def tearDown(self):
        #~ automount = XDG_CONFIG_HOME.file('zim/automount.conf')
        #~ automount.remove()

    def runTest(self):
        def mockconstructor(dir):
            return dir

        nbid = None
        for uri, path in (
                (self.notebookdir.uri, None),
                (self.notebookdir.uri, None),  # repeat to check uniqueness
                (self.notebookdir.file('notebook.zim').uri, None),
                (self.notebookdir.file('foo/bar.txt').uri, Path('foo:bar')),
                #~ ('zim+' + tmpdir.uri + '?aaa:bbb:ccc', Path('aaa:bbb:ccc')),
        ):
            #~ print ">>", uri
            info = NotebookInfo(uri)
            nb, p = build_notebook(info)
            self.assertEqual(nb.dir, self.notebookdir)
            self.assertEqual(p, path)
            if nbid is None:
                nbid = id(nb)
            else:
                self.assertEqual(id(nb), nbid, 'Check uniqueness')

        info = NotebookInfo(self.notebookdir.file('nonexistingfile.txt'))
        self.assertRaises(FileNotFoundError, build_notebook, info)


class TestNotebook(tests.TestCase):

    def setUp(self):
        path = self.get_tmp_name()
        self.notebook = tests.new_notebook(fakedir=path)

    def testAPI(self):
        '''Test various notebook methods'''
        self.assertTrue(
            isinstance(self.notebook.get_home_page(), Page))

        page1 = self.notebook.get_page(Path('Tree:foo'))
        page2 = self.notebook.get_page(Path('Tree:foo'))
        self.assertTrue(page1.valid)
        self.assertTrue(id(page2) == id(page1))  # check usage of weakref
        self.notebook.flush_page_cache(Path('Tree:foo'))
        page3 = self.notebook.get_page(Path('Tree:foo'))
        self.assertTrue(id(page3) != id(page1))
        self.assertFalse(page1.valid)

        page = self.notebook.get_page(Path('Test:foo'))
        text = page.dump('plain')
        newtext = ['Some new content\n']
        assert newtext != text
        self.assertEqual(page.dump('plain'), text)
        #~ page.parse('plain', newtext)
        #~ self.assertEqual(page.dump('plain'), newtext)
        #~ self.assertTrue(page.modified)
        #~ re = self.notebook.revert_page(page)
        #~ self.assertFalse(re) # no return value
        #~ self.assertEqual(page.dump('plain'), text) # object reverted
        #~ self.assertFalse(page.modified)
        self.notebook.flush_page_cache(page)
        page = self.notebook.get_page(page)  # new object
        self.assertEqual(page.dump('plain'), text)
        page.parse('plain', newtext)
        self.assertEqual(page.dump('plain'), newtext)
        self.notebook.store_page(page)
        self.notebook.flush_page_cache(page)
        page = self.notebook.get_page(page)  # new object
        self.assertEqual(page.dump('plain'), newtext)

        # ensure storing empty tree works
        emptytree = ParseTree()
        self.assertFalse(emptytree.hascontent)
        page.set_parsetree(emptytree)
        self.notebook.store_page(page)

    def testManipulate(self):
        '''Test renaming, moving and deleting pages in the notebook'''

        # check test setup OK
        for path in (Path('Test:BAR'), Path('NewPage')):
            page = self.notebook.get_page(path)
            self.assertFalse(page.haschildren)
            self.assertFalse(page.hascontent)
            self.assertFalse(page.exists())

        for path in (Path('Test:foo'), Path('TaskList')):
            page = self.notebook.get_page(path)
            self.assertTrue(page.haschildren or page.hascontent)
            self.assertTrue(page.exists())

        # check errors
        self.assertRaises(PageExistsError,
                          self.notebook.move_page, Path('Test:foo'), Path('TaskList'))

        self.notebook.index.flush()
        self.assertFalse(self.notebook.index.is_uptodate)
        self.assertRaises(IndexNotUptodateError,
                          self.notebook.move_page, Path('Test:foo'), Path('Test:BAR'))
        self.notebook.index.check_and_update()

        # Test actual moving
        for oldpath, newpath in (
                (Path('Test:foo'), Path('Test:BAR')),
                (Path('TaskList'), Path('NewPage:Foo:Bar:Baz')),
        ):
            page = self.notebook.get_page(oldpath)
            text = page.dump('wiki')
            self.assertTrue(page.haschildren)
            self.notebook.move_page(oldpath, newpath)

            # newpath should exist and look like the old one
            page = self.notebook.get_page(newpath)
            self.assertTrue(page.haschildren)
            text = [l.replace('[[foo:bar]]', '[[+bar]]') for l in text]  # fix one updated link
            self.assertEqual(page.dump('wiki'), text)

            # oldpath should be deleted
            page = self.notebook.get_page(oldpath)
            self.assertFalse(page.hascontent, msg="%s still has content" % page)
            #self.assertFalse(page.haschildren, msg="%s still has children" % page)
            # Can still have remaining placeholders

        # Test moving a page below it's own namespace
        oldpath = Path('Test:Bar')
        newpath = Path('Test:Bar:newsubpage')

        page = self.notebook.get_page(oldpath)
        page.parse('wiki', 'Test 123')
        self.notebook.store_page(page)

        self.notebook.move_page(oldpath, newpath)
        page = self.notebook.get_page(newpath)
        self.assertEqual(page.dump('wiki'), ['Test 123\n'])

        page = self.notebook.get_page(oldpath)
        self.assertTrue(page.haschildren)
        self.assertFalse(page.hascontent)

        # Check delete and cleanup
        path = Path('AnotherNewPage:Foo:bar')
        page = self.notebook.get_page(path)
        page.parse('plain', 'foo bar\n')
        self.notebook.store_page(page)

        page = self.notebook.get_page(Path('SomePageWithLinks'))
        page.parse('wiki',
                   '[[:AnotherNewPage:Foo:bar]]\n'
                   '**bold** [[:AnotherNewPage]]\n')
        self.notebook.store_page(page)

        page = self.notebook.get_page(Path('AnotherNewPage'))
        self.assertTrue(page.haschildren)
        self.assertFalse(page.hascontent)
        nlinks = self.notebook.links.n_list_links_section(page, LINK_DIR_BACKWARD)
        self.assertEqual(nlinks, 2)

        self.notebook.delete_page(Path('AnotherNewPage:Foo:bar'))
        page = self.notebook.get_page(path)
        self.assertFalse(page.haschildren)
        self.assertFalse(page.hascontent)
        self.assertRaises(IndexNotFoundError,
                          self.notebook.links.n_list_links_section, page, LINK_DIR_BACKWARD)
        self.assertRaises(IndexNotFoundError,
                          self.notebook.links.list_links_section, page, LINK_DIR_BACKWARD)
        # if links are removed and placeholder is cleaned up the
        # page doesn't exist anymore in the index so we get this error

        page = self.notebook.get_page(Path('SomePageWithLinks'))
        content = page.dump('wiki')
        self.assertEqual(''.join(content),
                         ':AnotherNewPage:Foo:bar\n'
                         '**bold** [[:AnotherNewPage]]\n')

        self.notebook.delete_page(Path('AnotherNewPage:Foo:bar'))  # now should fail silently

        page = self.notebook.get_page(Path('AnotherNewPage'))
        self.assertFalse(page.haschildren)
        self.assertFalse(page.hascontent)
        nlinks = self.notebook.links.n_list_links_section(page, LINK_DIR_BACKWARD)
        self.assertEqual(nlinks, 1)
        self.notebook.delete_page(page)
        self.assertRaises(IndexNotFoundError,
                          self.notebook.links.n_list_links_section, page, LINK_DIR_BACKWARD)
        self.assertRaises(IndexNotFoundError,
                          self.notebook.links.list_links_section, page, LINK_DIR_BACKWARD)
        # if links are removed and placeholder is cleaned up the
        # page doesn't exist anymore in the index so we get this error

        page = self.notebook.get_page(Path('SomePageWithLinks'))
        content = page.dump('wiki')
        self.assertEqual(''.join(content),
                         ':AnotherNewPage:Foo:bar\n'
                         '**bold** :AnotherNewPage\n')

        #~ print '\n==== DB ===='
        #~ self.notebook.index.update()
        #~ cursor = self.notebook.index.db.cursor()
        #~ cursor.execute('select * from pages')
        #~ for row in cursor:
        #~ print row
        #~ cursor.execute('select * from links')
        #~ for row in cursor:
        #~ print row

        # Try rename
        page = self.notebook.get_page(Path('Test:wiki'))
        self.assertTrue(page.hascontent)
        copy = page
        # we now have a copy of the page object - this is an important
        # part of the test - see if caching of page objects doesn't bite

        with tests.LoggingFilter('zim.notebook', message='Number of links'):
            self.notebook.rename_page(Path('Test:wiki'), 'foo')
        page = self.notebook.get_page(Path('Test:wiki'))
        self.assertFalse(page.hascontent)
        page = self.notebook.get_page(Path('Test:foo'))
        # If we get an error here because notebook resolves Test:Foo
        # probably the index did not clean up placeholders correctly
        self.assertTrue(page.hascontent)

        self.assertFalse(copy.valid)

        self.notebook.rename_page(Path('Test:foo'), 'Foo')
        page = self.notebook.get_page(Path('Test:foo'))
        self.assertFalse(page.hascontent)
        page = self.notebook.get_page(Path('Test:Foo'))
        self.assertTrue(page.hascontent)

    def testUpdateLinks(self):
        '''Test logic for updating links on move'''

        # update the page that was moved itself
        # moving from Dus:Baz to foo:bar:Baz or renaming to Dus:Bar
        # while updating links in Dus:Ja
        text = u'''\
http://foo.org # urls are untouched
[[:Hmmm:OK]] # link way outside move
[[Baz:Ja]] # relative link that does not need change on move, but does on rename
[[Ja]] # relative link that needs updating on move, but not on rename
[[Ja|Grrr]] # relative link that needs updating on move, but not on rename - with name
[[:foo:bar:Dus]] # Link that could be made relative, but isn't
'''
        wanted1 = u'''\
http://foo.org # urls are untouched
[[:Hmmm:OK]] # link way outside move
[[Baz:Ja]] # relative link that does not need change on move, but does on rename
[[Dus:Ja]] # relative link that needs updating on move, but not on rename
[[Dus:Ja|Grrr]] # relative link that needs updating on move, but not on rename - with name
[[:foo:bar:Dus]] # Link that could be made relative, but isn't
'''
        wanted2 = u'''\
http://foo.org # urls are untouched
[[:Hmmm:OK]] # link way outside move
[[+Ja]] # relative link that does not need change on move, but does on rename
[[Ja]] # relative link that needs updating on move, but not on rename
[[Ja|Grrr]] # relative link that needs updating on move, but not on rename - with name
[[:foo:bar:Dus]] # Link that could be made relative, but isn't
'''

        linkingtext = u'''\
http://foo.org # urls are untouched
[[:Hmmm:OK]] # link way outside move
[[Baz:Ja]] # relative link that needs updating
[[Baz:Ja|Grr]] # relative link that needs updating - with name
[[Dus:Foo]] # relative link that does not need updating
[[:Dus:Baz]] # absolute link that needs updating
[[:Dus:Baz:Hmm]] # absolute link that needs updating
[[:Dus:Baz:Hmm:Ja]] # absolute link that needs updating
'''
        linkingwanted1 = u'''\
http://foo.org # urls are untouched
[[:Hmmm:OK]] # link way outside move
[[foo:bar:Baz:Ja]] # relative link that needs updating
[[foo:bar:Baz:Ja|Grr]] # relative link that needs updating - with name
[[Dus:Foo]] # relative link that does not need updating
[[:foo:bar:Baz]] # absolute link that needs updating
[[:foo:bar:Baz:Hmm]] # absolute link that needs updating
[[:foo:bar:Baz:Hmm:Ja]] # absolute link that needs updating
'''
        linkingwanted2 = u'''\
http://foo.org # urls are untouched
[[:Hmmm:OK]] # link way outside move
[[Bar:Ja]] # relative link that needs updating
[[Bar:Ja|Grr]] # relative link that needs updating - with name
[[Dus:Foo]] # relative link that does not need updating
[[:Dus:Bar]] # absolute link that needs updating
[[:Dus:Bar:Hmm]] # absolute link that needs updating
[[:Dus:Bar:Hmm:Ja]] # absolute link that needs updating
'''

        # move Dus:Baz -> foo:bar:Baz
        oldpage = self.notebook.get_page(Path('Dus:Baz'))
        oldpage.parse('wiki', text)
        self.notebook.store_page(oldpage)

        linking = self.notebook.get_page(Path('Dus:Ja'))
        linking.parse('wiki', linkingtext)
        self.notebook.store_page(linking)

        self.notebook.move_page(Path('Dus:Baz'), Path('foo:bar:Baz'))

        newpage = self.notebook.get_page(Path('foo:bar:Baz'))
        self.assertEqual(u''.join(newpage.dump('wiki')), wanted1)

        linking = self.notebook.get_page(Path('Dus:Ja'))
        self.assertEqual(u''.join(linking.dump('wiki')), linkingwanted1)

        # rename Dus:Baz -> Dus:Bar
        oldpage = self.notebook.get_page(Path('Dus:Baz'))
        oldpage.parse('wiki', text)
        self.notebook.store_page(oldpage)

        linking = self.notebook.get_page(Path('Dus:Ja'))
        linking.parse('wiki', linkingtext)
        self.notebook.store_page(linking)

        self.notebook.rename_page(Path('Dus:Baz'), 'Bar', update_heading=False)

        newpage = self.notebook.get_page(Path('Dus:Bar'))
        self.assertEqual(u''.join(newpage.dump('wiki')), wanted2)

        linking = self.notebook.get_page(Path('Dus:Ja'))
        self.assertEqual(u''.join(linking.dump('wiki')), linkingwanted2)

        # now test move on full notebook with more pages
        def links(source, target):
            #~ print '===='
            for link in self.notebook.links.list_links(source, LINK_DIR_FORWARD):
                #~ print 'FOUND LINK', link
                if link.target == target:
                    return True
            else:
                return False

        path = Path('Linking:Dus:Ja')
        newpath = Path('Linking:Hmm:Ok')

        self.assertTrue(links(path, Path('Linking:Dus')))
        self.assertTrue(links(path, Path('Linking:Foo:Bar')))
        self.assertTrue(links(Path('Linking:Foo:Bar'), path))
        self.assertFalse(links(Path('Linking:Foo:Bar'), newpath))

        self.notebook.move_page(path, newpath, update_links=True)

        self.assertTrue(links(newpath, Path('Linking:Dus')))
        self.assertTrue(links(newpath, Path('Linking:Foo:Bar')))
        self.assertTrue(links(Path('Linking:Foo:Bar'), newpath))

        # Yet another test based on bug #lp:617933 - no changes and all cross refs preserved
        parent = self.notebook.get_page(Path('TheParent'))
        child1 = self.notebook.get_page(Path('TheParent:FirstChild'))
        child2 = self.notebook.get_page(Path('TheParent:SecondChild'))

        parent.parse('wiki', 'Loves [[+FirstChild]] and [[+SecondChild]]\n')
        child1.parse('wiki', 'Hates the [[SecondChild]]\n')
        child2.parse('wiki', 'Loves the [[FirstChild]]\n')

        self.notebook.store_page(parent)
        self.notebook.store_page(child1)
        self.notebook.store_page(child2)

        self.notebook.rename_page(Path('TheParent'), 'NewName', update_heading=False)

        parent = self.notebook.get_page(Path('NewName'))
        child1 = self.notebook.get_page(Path('NewName:FirstChild'))
        child2 = self.notebook.get_page(Path('NewName:SecondChild'))

        self.assertEqual(u''.join(parent.dump('wiki')), 'Loves [[+FirstChild]] and [[+SecondChild]]\n')
        self.assertEqual(u''.join(child1.dump('wiki')), 'Hates the [[SecondChild]]\n')
        self.assertEqual(u''.join(child2.dump('wiki')), 'Loves the [[FirstChild]]\n')

    def testResolveFile(self):
        '''Test notebook.resolve_file()'''
        path = Path('Foo:Bar')
        dir = self.notebook.dir
        self.notebook.config['Notebook']['document_root'] = './notebook_document_root'
        self.notebook.do_properties_changed()  # parse config
        doc_root = self.notebook.document_root
        self.assertEqual(doc_root, dir.subdir('notebook_document_root'))
        for link, wanted, cleaned in (
                ('~/test.txt', File('~/test.txt'), '~/test.txt'),
                (r'~\test.txt', File('~/test.txt'), '~/test.txt'),
                ('file:///test.txt', File('file:///test.txt'), None),
                ('file:/test.txt', File('file:///test.txt'), None),
                ('file://localhost/test.txt', File('file:///test.txt'), None),
                ('/test.txt', doc_root.file('test.txt'), '/test.txt'),
                ('../../notebook_document_root/test.txt', doc_root.file('test.txt'), '/test.txt'),
                ('./test.txt', dir.file('Foo/Bar/test.txt'), './test.txt'),
                (r'.\test.txt', dir.file('Foo/Bar/test.txt'), './test.txt'),
                ('../test.txt', dir.file('Foo/test.txt'), '../test.txt'),
                (r'..\test.txt', dir.file('Foo/test.txt'), '../test.txt'),
                ('../Bar/Baz/test.txt', dir.file('Foo/Bar/Baz/test.txt'), './Baz/test.txt'),
                (r'C:\foo\bar', File('file:///C:/foo/bar'), None),
                (r'Z:\foo\bar', File('file:///Z:/foo/bar'), None),
        ):
            #~ print link, '>>', self.notebook.resolve_file(link, path)
            if cleaned is not None and not cleaned.startswith('/'):
                cleaned = os_native_path(cleaned)
            self.assertEqual(
                self.notebook.resolve_file(link, path), wanted)
            self.assertEqual(
                self.notebook.relative_filepath(wanted, path), cleaned)

        # check relative path without Path
        self.assertEqual(
            self.notebook.relative_filepath(doc_root.file('foo.txt')), '/foo.txt')
        self.assertEqual(
            self.notebook.relative_filepath(dir.file('foo.txt')), os_native_path('./foo.txt'))


#	def testResolveLink(self):
#		'''Test page.resolve_link()'''
#		page = self.notebook.get_page(':Test:foo')
#		for link, wanted in (
        #~ (':foo:bar', ('page', ':foo:bar')),
#			('foo:bar', ('page', ':Test:foo:bar')),
#			('Test', ('page', ':Test')),
#			('Test:non-existent', ('page', ':Test:non-existent')),
#			('user@domain.com', ('mailto', 'mailto:user@domain.com')),
#			('mailto:user@domain.com', ('mailto', 'mailto:user@domain.com')),
#			('http://zim-wiki.org', ('http', 'http://zim-wiki.org')),
#			('foo://zim-wiki.org', ('foo', 'foo://zim-wiki.org')),
        #~ ('file://'),
        #~ ('/foo/bar', ('file', '/foo/bar')),
        #~ ('man?test', ('man', 'test')),
#		): self.assertEqual(self.notebook.resolve_link(link, page), wanted)

    #~ def testResolveName(self):
        #~ '''Test store.resolve_name().'''
        #~ print '\n'+'='*10+'\nSTORE: %s' % self.store
#~
        #~ # First make sure basic list function is working
        #~ def list_pages(name):
        #~ for page in self.store.get_pages(name):
        #~ yield page.basename
        #~ self.assertTrue('Test' in list_pages(''))
        #~ self.assertTrue('foo' in list_pages(':Test'))
        #~ self.assertTrue('bar' in list_pages(':Test:foo'))
        #~ self.assertFalse('Dus' in list_pages(':Test:foo'))
#~
        #~ # Now test the resolving algorithm - only testing low level
        #~ # function in store, so path "anchor" does not work, search
        #~ # is strictly right to left through the namespace, if any
        #~ for link, namespace, name in (
        #~ ('BAR','Test:foo','Test:foo:bar'),
        #~ ('test',None,'Test'),
        #~ ('test','Test:foo:bar','Test'),
        #~ ('FOO:Dus','Test:foo:bar','Test:foo:Dus'),
        #~ # FIXME more ambigous test data
        #~ ):
        #~ print '-'*10+'\nLINK %s (%s)' % (link, namespace)
        #~ r = self.store.resolve_name(link, namespace=namespace)
        #~ print 'RESULT %s' % r
        #~ self.assertEqual(r, name)


class TestPath(tests.TestCase):
    '''Test path object'''

    def generator(self, name):
        return Path(name)

    def runTest(self):
        '''Test Path object'''

        for name in ('test', 'test this', 'test (this)', 'test:this (2)'):
            Path.assertValidPageName(name)

        for name in (':test', '+test', 'foo:_bar', 'foo::bar', 'foo#bar'):
            self.assertRaises(AssertionError, Path.assertValidPageName, name)

        #~ for input, name in ():
            #~ self.assertEqual(Path.makeValidPageName(input), name)

        for name, namespace, basename in [
                ('Test:foo', 'Test', 'foo'),
                ('Test', '', 'Test'),
        ]:
            # test name
            Path.assertValidPageName(name)
            self.assertEqual(Path.makeValidPageName(name), name)

            # get object
            path = self.generator(name)

            # test basic properties
            self.assertEqual(path.name, name)
            self.assertEqual(path.basename, basename)
            self.assertEqual(path.namespace, namespace)
            self.assertTrue(path.name in path.__repr__())

    # TODO test operators on paths > < + - >= <= == !=


class TestHRefFromWikiLink(tests.TestCase):

    def runtTest(self):
        for link, rel, names, properlink in (
                ('Foo:::Bar', HREF_REL_FLOATING, 'Foo:Bar', 'Foo:Bar'),
                (':Foo:', HREF_REL_ABSOLUTE, 'Foo', ':Foo'),
                (':<Foo>:', HREF_REL_ABSOLUTE, 'Foo', ':Foo'),
                ('+Foo:Bar', HREF_REL_RELATIVE, 'Foo:Bar', '+Foo:Bar'),
                ('Child2:AAA', HREF_REL_FLOATING, 'Child2:AAA', 'Child2:AAA'),
        ):
            href = HRef.new_from_wiki_link(link)
            self.assertEqual(href.rel, rel)
            self.assertEqual(href.names, names)
            self.assertEqual(href.to_wiki_link(), properlink)


class TestPage(TestPath):
    '''Test page object'''

    def generator(self, name):
        from zim.newfs.mock import MockFile, MockFolder
        file = MockFile('/mock/test/page.txt')
        folder = MockFile('/mock/test/page/')
        return Page(Path(name), False, file, folder)

    def testMain(self):
        '''Test Page object'''
        TestPath.runTest(self)

        tree = ParseTree().fromstring('''\
<zim-tree>
<link href='foo:bar'>foo:bar</link>
<link href='bar'>bar</link>
<tag name='baz'>@baz</tag>
</zim-tree>
'''		)
        page = self.generator('Foo')
        page.set_parsetree(tree)

        links = list(page.get_links())
        self.assertEqual(links, [
            ('page', 'foo:bar', {}),
            ('page', 'bar', {}),
        ])

        tags = list(page.get_tags())
        self.assertEqual(tags, [
            ('baz', {'name': 'baz'}),
        ])

        self.assertEqual(page.get_parsetree().tostring(), tree.tostring())
        # ensure we didn't change the tree

        # TODO test get / set parse tree with and without source

        tree = ParseTree().fromstring('<zim-tree></zim-tree>')
        self.assertFalse(tree.hascontent)
        page.set_parsetree(tree)
        self.assertFalse(page.hascontent)

    def testShouldAutochangeHeading(self):
        from zim.newfs.mock import MockFile, MockFolder
        file = MockFile('/mock/test/page.txt')
        folder = MockFile('/mock/test/page/')
        page = Page(Path('Foo'), False, file, folder)

        tree = ParseTree().fromstring('<zim-tree></zim-tree>')
        tree.set_heading("Foo")
        page.set_parsetree(tree)
        self.assertTrue(page.heading_matches_pagename())
        tree.set_heading("Bar")
        page.set_parsetree(tree)
        self.assertFalse(page.heading_matches_pagename())

    def testPageSource(self):
        from zim.newfs.mock import MockFile, MockFolder

        file = MockFile('/mock/test/page.txt')
        folder = MockFile('/mock/test/page/')
        page = Page(Path('Foo'), False, file, folder)

        self.assertFalse(page.readonly)
        self.assertFalse(page.hascontent)
        self.assertIsNone(page.ctime)
        self.assertIsNone(page.mtime)
        self.assertIsNone(page.get_parsetree())

        page1 = Page(Path('Foo'), False, file, folder)
        self.assertTrue(page.isequal(page1))

        tree = ParseTree().fromstring('''\
<zim-tree>
<link href='foo:bar'>foo:bar</link>
<link href='bar'>bar</link>
<tag name='baz'>@baz</tag>
</zim-tree>
'''		)
        page.set_parsetree(tree)
        page._store()

        self.assertTrue(file.exists())
        self.assertTrue(page.hascontent)
        self.assertIsInstance(page.ctime, float)
        self.assertIsInstance(page.mtime, float)

        lines = file.readlines()
        self.assertEqual(lines[0], 'Content-Type: text/x-zim-wiki\n')
        self.assertEqual(lines[1][:11], 'Wiki-Format')
        self.assertEqual(lines[2][:13], 'Creation-Date')

        self.assertEqual(page.get_parsetree(), tree)

        self.assertTrue(page.isequal(page1))
        self.assertTrue(page1.hascontent)
        self.assertIsInstance(page1.ctime, float)
        self.assertIsInstance(page1.mtime, float)
        self.assertIsNotNone(page1.get_parsetree())

        file.write('foo 123')
        page.set_parsetree(tree)

        self.assertRaises(zim.newfs.FileChangedError, page._store)

        # Custom header should be preserved
        # Also when setting new ParseTree - e.g. after edting
        file.writelines(lines[0:3] + ['X-Custom-Header: MyTest'] + lines[3:])
        page = Page(Path('Foo'), False, file, folder)
        tree = page.get_parsetree()
        page.set_parsetree(tree)
        page._store()
        lines = file.readlines()
        self.assertEqual(lines[0], 'Content-Type: text/x-zim-wiki\n')
        self.assertEqual(lines[1][:11], 'Wiki-Format')
        self.assertEqual(lines[2][:13], 'Creation-Date')
        self.assertEqual(lines[3], 'X-Custom-Header: MyTest\n')

        newtree = ParseTree().fromstring('<zim-tree>Test 123</zim-tree>')
        page.set_parsetree(newtree)
        page._store()
        lines = file.readlines()
        self.assertEqual(lines[0], 'Content-Type: text/x-zim-wiki\n')
        self.assertEqual(lines[1][:11], 'Wiki-Format')
        self.assertEqual(lines[2][:13], 'Creation-Date')
        self.assertEqual(lines[3], 'X-Custom-Header: MyTest\n')
        ###


class TestMovePageNewNotebook(tests.TestCase):

    def setUp(self):
        folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_MOCK)
        layout = FilesLayout(folder, endofline='unix')
        index = Index(':memory:', layout)

        ### XXX - Big HACK here - Get better classes for this - XXX ###
        dir = VirtualConfigBackend()
        file = dir.file('notebook.zim')
        file.dir = dir
        file.dir.basename = 'Unnamed Notebook'
        ###
        config = NotebookConfig(file)

        dir = None
        cache_dir = None
        self.notebook = Notebook(dir, cache_dir, config, folder, layout, index)
        index.check_and_update()

    def runTest(self):
        '''Try populating a notebook from scratch'''
        # Based on bug lp:511481 - should reproduce bug with updating links to child pages
        notebook = self.notebook

        for name, text in (
                ('page1', 'Foo bar\n'),
                ('page1:child', 'I have backlinks !\n'),
                ('page2', '[[page1:child]] !\n'),
                ('page3', 'Hmm\n'),
        ):
            path = Path(name)
            page = self.notebook.get_page(path)
            page.parse('wiki', text)
            notebook.store_page(page)

        for name, forw, backw in (
                ('page1', 0, 0),
                ('page1:child', 0, 1),
                ('page2', 1, 0),
                ('page3', 0, 0),
        ):
            path = Path(name)
            self.assertEqual(
                notebook.links.n_list_links(path, LINK_DIR_FORWARD), forw)
            self.assertEqual(
                notebook.links.n_list_links(path, LINK_DIR_BACKWARD), backw)

        self.assertRaises(IndexNotFoundError,
                          notebook.links.n_list_links, Path('page3:page1'), LINK_DIR_FORWARD
                          )

        notebook.move_page(Path('page1'), Path('page3:page1'))
        for name, forw, backw in (
                ('page2', 1, 0),
                ('page3', 0, 0),
                ('page3:page1', 0, 0),
                ('page3:page1:child', 0, 1),
        ):
            path = Path(name)
            self.assertEqual(
                notebook.links.n_list_links(path, LINK_DIR_FORWARD), forw)
            self.assertEqual(
                notebook.links.n_list_links(path, LINK_DIR_BACKWARD), backw)

        self.assertRaises(IndexNotFoundError,
                          notebook.links.n_list_links, Path('page1'), LINK_DIR_FORWARD
                          )

        text = ''.join(notebook.get_page(Path('page3:page1:child')).dump('wiki'))
        self.assertEqual(text, 'I have backlinks !\n')


@tests.slowTest
class TestPageChangeFile(tests.TestCase):
    # Test case to ensure page caching doesn't bite after page has
    # changed on disk. This is important for use cases where an
    # open/cached page gets modified by e.g. syncing Dropbox.
    # Reloading the pageshould show the changes.

    def runTest(self):
        dir = Dir(self.create_tmp_dir())
        notebook = Notebook.new_from_dir(dir)

        page = notebook.get_page(Path('SomePage'))
        file = zim.newfs.LocalFile(page.source_file.path)
        self.assertIsNot(file, page.source_file)

        def change_file(file, text):
            old = file.mtime()
            file.write(text)
            while file.mtime() == old:
                time.sleep(0.01)  # new mtime
                file.write(text)

        # First we don't keep ref, but change params quick enough
        # that caching will not have time to clean up

        page.parse('wiki', 'Test 123\n')
        notebook.store_page(page)

        # Page as we stored it
        page = notebook.get_page(Path('SomePage'))
        self.assertEqual(page.dump('wiki'), ['Test 123\n'])

        # Now we change the file and want to see the change
        change_file(file, 'Test 5 6 7 8\n')

        page = notebook.get_page(Path('SomePage'))
        self.assertEqual(page.dump('wiki'), ['Test 5 6 7 8\n'])

        # Repeat but keep refs explicitly

        page1 = notebook.get_page(Path('SomeOtherPage'))
        page1.parse('wiki', 'Test 123\n')
        notebook.store_page(page1)

        # Page as we stored it
        page2 = notebook.get_page(Path('SomeOtherPage'))
        self.assertIs(page2, page1)
        self.assertEqual(page2.dump('wiki'), ['Test 123\n'])

        # Now we change the file and want to see the change
        file = zim.newfs.LocalFile(page1.source_file.path)
        self.assertIsNot(file, page1.source_file)
        change_file(file, 'Test 5 6 7 8\n')

        page3 = notebook.get_page(Path('SomeOtherPage'))
        self.assertIs(page3, page1)
        self.assertTrue(page3.valid)
        self.assertEqual(page3.dump('wiki'), ['Test 5 6 7 8\n'])


try:
    import gio
except ImportError:
    gio = None


@tests.slowTest
@tests.skipUnless(gio, 'Trashing not supported, \'gio\' is missing')
class TestTrash(tests.TestCase):

    def runTest(self):
        notebook = tests.new_files_notebook(self.create_tmp_dir())
        page = notebook.get_page(Path('TrashMe'))
        self.assertTrue(page.exists())

        notebook.trash_page(Path('TrashMe'))

        page = notebook.get_page(Path('TrashMe'))
        self.assertFalse(page.exists())


class TestIndexBackgroundCheck(tests.TestCase):

    def runTest(self):
        notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
        notebook.index.flush()
        self.assertFalse(notebook.index.is_uptodate)

        notebook.index.start_background_check(notebook)
        while notebook.index.background_check.running:
            tests.gtk_process_events()
        self.assertTrue(notebook.index.is_uptodate)
        self.assertTrue(notebook.pages.n_all_pages() > 10)

        notebook.index.stop_background_check()


class TestBackgroundSave(tests.TestCase):

    def runTest(self):
        notebook = self.setUpNotebook()

        page = notebook.get_page(Path('Page1'))
        tree = WikiParser().parse('test 123\n')

        signals = tests.SignalLogger(notebook)

        op = notebook.store_page_async(page, tree)
        thread = op._thread
        while thread.is_alive():
            tests.gtk_process_events()

        tests.gtk_process_events()
        self.assertFalse(op.error_event.is_set())

        text = page.dump('wiki')
        self.assertEqual(text[-1], 'test 123\n')
        self.assertEqual(signals['stored-page'], [(page,)])  # post handler happened as well
