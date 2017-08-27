# -*- coding: utf-8 -*-

# Copyright 2010 Fabian Moser
# Copyright 2011-2017 Jaap Karssenberg


import gobject
import gtk
import pango

import logging

from functools import partial

from zim.plugins import PluginClass, extends, WindowExtension
#~ PageTreeIter
from zim.gui.pageindex import PageTreeStore, PageTreeStoreBase, PageTreeView, \
    NAME_COL, PATH_COL, EMPTY_COL, STYLE_COL, FGCOLOR_COL, WEIGHT_COL, N_CHILD_COL, TIP_COL
from zim.notebook import Path
from zim.notebook.index import IndexNotFoundError
from zim.notebook.index.pages import PageIndexRecord
from zim.notebook.index.tags import IS_PAGE, IS_TAG, \
    TagsView, TaggedPagesTreeModelMixin, TagsTreeModelMixin, IndexTag
from zim.gui.widgets import LEFT_PANE, PANE_POSITIONS, populate_popup_add_separator, ScrolledWindow, encode_markup_text
from zim.gui.clipboard import pack_urilist, INTERNAL_PAGELIST_TARGET_NAME
from zim.signals import ConnectorMixin


logger = logging.getLogger('zim.plugins.tags')


class TagsPlugin(PluginClass):

    plugin_info = {
        'name': _('Tags'),  # T: plugin name
        'description': _('''\
This plugin provides a page index filtered by means of selecting tags in a cloud.
'''),  # T: plugin description
        'author': 'Fabian Moser & Jaap Karssenberg',
        'help': 'Plugins:Tags',
    }

    plugin_preferences = (
        # key, type, label, default
        ('pane', 'choice', _('Position in the window'), LEFT_PANE, PANE_POSITIONS),
        # T: option for plugin preferences
    )


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

    def __init__(self, plugin, window):
        WindowExtension.__init__(self, plugin, window)

        self.widget = TagsPluginWidget(self.window.ui.notebook.index, self.uistate, self.window.ui)  # XXX

        self.on_preferences_changed(plugin.preferences)
        self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

        self.uistate.setdefault('vpane_pos', 150)
        self.widget.set_position(self.uistate['vpane_pos'])

        def update_uistate(*a):
            self.uistate['vpane_pos'] = self.widget.get_position()
        self.widget.connect('notify::position', update_uistate)

    def on_preferences_changed(self, preferences):
        if self.widget is None:
            return

        try:
            self.window.remove(self.widget)
        except ValueError:
            pass
        self.window.add_tab(_('Tags'), self.widget, preferences['pane'])
        self.widget.show_all()

    def teardown(self):
        self.window.remove(self.widget)
        self.widget.disconnect_all()
        self.widget = None


class TagsPluginWidget(ConnectorMixin, gtk.VPaned):
    '''Widget combining a tag cloud and a tag based page treeview'''

    def __init__(self, index, uistate, ui):  # XXX
        gtk.VPaned.__init__(self)
        self.index = index
        self.uistate = uistate

        self.uistate.setdefault('treeview', 'tags', set(['tagged', 'tags']))
        self.uistate.setdefault('tagcloud_sorting', 'score', set(['alpha', 'score']))
        self.uistate.setdefault('show_full_page_name', True)

        self.tagcloud = TagCloudWidget(self.index, sorting=self.uistate['tagcloud_sorting'])
        self.pack1(ScrolledWindow(self.tagcloud), shrink=False)

        self.treeview = TagsPageTreeView(ui)  # XXX
        self.pack2(ScrolledWindow(self.treeview), shrink=False)

        self.treeview.connect('populate-popup', self.on_populate_popup)
        self.tagcloud.connect('selection-changed', self.on_cloud_selection_changed)
        self.tagcloud.connect('sorting-changed', self.on_cloud_sortin_changed)

        self.connectto_all(ui, (  # XXX
            'open-page',
            ('start-index-update', lambda o: self.disconnect_model()),
            ('end-index-update', lambda o: self.reconnect_model()),
        ))

        self.reload_model()

    def on_open_page(self, ui, page, path):
        expand = True
        treepath = self.treeview.set_current_page(path, vivificate=True)
        expand = ui.notebook.namespace_properties[path.name].get('auto_expand_in_index', True)
        if treepath and expand:
            # change selection only if necessary
            selected_path = self.treeview.get_selected_path()
            if path == selected_path:
                logger.debug('Already selected: "%s"', path)
            else:
                self.treeview.select_treepath(treepath)

    def toggle_treeview(self):
        '''Toggle the treeview type in the widget'''
        if self.uistate['treeview'] == 'tagged':
            self.uistate['treeview'] = 'tags'
        else:
            self.uistate['treeview'] = 'tagged'

        model = self.treeview.get_model()
        if not isinstance(model, TaggedPageTreeStore):
            self.reload_model()

    def toggle_show_full_page_name(self):
        self.uistate['show_full_page_name'] = not self.uistate['show_full_page_name']
        self.reload_model()

    def on_populate_popup(self, treeview, menu):
        # If not a not a page (but e.g. a tag), remove page action
        if not treeview.get_selected_path():
            for item in menu.get_children():
                menu.remove(item)

        # Add a popup menu item to switch the treeview mode
        populate_popup_add_separator(menu, prepend=True)

        item = gtk.CheckMenuItem(_('Show full page name'))  # T: menu option
        item.set_active(self.uistate['show_full_page_name'])
        item.connect_object('toggled', self.__class__.toggle_show_full_page_name, self)
        menu.prepend(item)

        item = gtk.CheckMenuItem(_('Sort pages by tags'))  # T: menu option
        item.set_active(self.uistate['treeview'] == 'tags')
        item.connect_object('toggled', self.__class__.toggle_treeview, self)
        model = self.treeview.get_model()
        if isinstance(model, TaggedPageTreeStore):
            item.set_sensitive(False)  # with tag selection toggle does nothing
        menu.prepend(item)

        menu.show_all()

    def on_cloud_selection_changed(self, cloud):
        self.reload_model()
        # FIXME - allow updating selection, requires signals for all added / removed pages

    def on_cloud_sortin_changed(self, cloud, sorting):
        self.uistate['tagcloud_sorting'] = sorting

    def disconnect_model(self):
        '''Stop the model from listening to the index. Used to
        unhook the model before reloading the index. Typically
        should be followed by reload_model().
        '''
        self.treeview.disconnect_index()
        self.tagcloud.disconnect_index()

    def reconnect_model(self):
        self.tagcloud.connect_index(self.index)
        self.reload_model()

    def reload_model(self):
        '''Re-initialize the treeview model. This is called when
        reloading the index to get rid of out-of-sync model errors
        without need to close the app first.
        '''
        assert self.uistate['treeview'] in ('tagged', 'tags')
        tags = [t.name for t in self.tagcloud.get_tag_filter()]

        if tags:
            model = TaggedPageTreeStore(self.index, tags, self.uistate['show_full_page_name'])
        elif self.uistate['treeview'] == 'tags':
            model = TagsPageTreeStore(self.index, (), self.uistate['show_full_page_name'])
        else:
            model = PageTreeStore(self.index)

        self.treeview.set_model(model)


class DuplicatePageTreeStore(PageTreeStoreBase):
    '''Sub-class of PageTreeStore that allows for the same page appearing
    multiple times in the tree.
    '''

    def set_current_page(self, path):
        '''Since there may be duplicates of each page, highlight all of them'''
        oldpath = self.current_page
        self.current_page = path

        for mypath in (oldpath, path):
            if mypath:
                for treepath in self.find_all(mypath):
                    if treepath:
                        treeiter = self.get_iter(treepath)
                        self.emit('row-changed', treepath, treeiter)

    def get_indexpath(self, treeiter):
        '''Get an L{PageIndexRecord} for a C{gtk.TreeIter}

        @param treeiter: a C{gtk.TreeIter}
        @returns: an L{PageIndexRecord} object
        '''
        mytreeiter = self.get_user_data(treeiter)
        if mytreeiter.hint == IS_PAGE:
            return PageIndexRecord(mytreeiter.row)
        elif mytreeiter.hint == IS_TAG:
            return IndexTag(mytreeiter.row['name'], mytreeiter.row['id'])
        else:
            raise ValueError


class TagsPageTreeStore(TagsTreeModelMixin, DuplicatePageTreeStore):
    '''Subclass of the PageTreeStore that shows tags as the top level
    for sub-sets of the page tree.
    '''

    def __init__(self, index, tags=None, show_full_page_name=True):
        TagsTreeModelMixin.__init__(self, index, tags)
        PageTreeStoreBase.__init__(self)
        self.show_full_page_name = show_full_page_name

    def on_get_value(self, iter, column):
        '''Returns the data for a specific column'''
        if iter.hint == IS_TAG:
            if column == NAME_COL:
                return iter.row['name']
            elif column == TIP_COL:
                return encode_markup_text(iter.row['name'])
            elif column == PATH_COL:
                return IndexTag(*iter.row)
            elif column == EMPTY_COL:
                return False
            elif column == STYLE_COL:
                return pango.STYLE_NORMAL
            elif column == FGCOLOR_COL:
                return self.NORMAL_COLOR
            elif column == WEIGHT_COL:
                return pango.WEIGHT_NORMAL
            elif column == N_CHILD_COL:
                return iter.n_children
        else:
            if self.show_full_page_name \
                    and column == NAME_COL and len(iter.treepath) == 2:
                # Show top level pages with full contex
                # top level tree is tags, so top level pages len(path) is 2
                return iter.row['name']
            else:
                return PageTreeStoreBase.on_get_value(self, iter, column)


class TaggedPageTreeStore(TaggedPagesTreeModelMixin, DuplicatePageTreeStore):
    '''A TreeModel that lists all Zim pages in a flat list.
    Pages with associated sub-pages still show them as sub-nodes.
    Intended to be filtered by tags.
    '''

    def __init__(self, index, tags, show_full_page_name=True):
        TaggedPagesTreeModelMixin.__init__(self, index, tags)
        PageTreeStoreBase.__init__(self)
        self.show_full_page_name = show_full_page_name

    def on_get_value(self, iter, column):
        '''Returns the data for a specific column'''
        if self.show_full_page_name \
                and column == NAME_COL and len(iter.treepath) == 1:
            # Show top level pages with full contex
            return iter.row['name']
        else:
            return PageTreeStoreBase.on_get_value(self, iter, column)


class TagsPageTreeView(PageTreeView):

    def do_drag_data_get(self, dragcontext, selectiondata, info, time):
        assert selectiondata.target == INTERNAL_PAGELIST_TARGET_NAME
        model, iter = self.get_selection().get_selected()
        path = model.get_indexpath(iter)
        if isinstance(path, IndexTag):
            link = '@' + path.name
        else:
            link = path.name
        logger.debug('Drag data requested, we have internal tag/path "%s"', link)
        data = pack_urilist((link,))
        selectiondata.set(INTERNAL_PAGELIST_TARGET_NAME, 8, data)

    def set_current_page(self, path, vivificate=False):
        '''Set the current page in the treeview

        @param path: a notebook L{Path} object for the page
        @keyword vivificate: when C{True} the path is created
        temporarily when it did not yet exist

        @returns: a gtk TreePath (tuple of intergers) or C{None}
        '''
        #~ print '!! SELECT', path
        model = self.get_model()
        if model is None:
            return None  # index not yet initialized ...

        try:
            treepath = model.find(path)
            model.set_current_page(path)  # highlight in model
        except IndexNotFoundError:
            pass
        else:
            return treepath

# Need to register classes defining gobject signals
gobject.type_register(TagsPageTreeView)


class TagCloudItem(gtk.ToggleButton):
    '''Button item used on the tag cloud widget'''

    def __init__(self, indextag):
        gtk.ToggleButton.__init__(self, indextag.name, use_underline=False)
        self.set_relief(gtk.RELIEF_NONE)
        self.indextag = indextag

        def update_label(self):
            # Make button text bold when active
            label = self.get_child()
            if self.get_active():
                label.set_markup('<b>' + label.get_text() + '</b>')
            else:
                label.set_text(label.get_text())
                # get_text() gives string without markup

        self.connect_after('toggled', update_label)


class TagCloudWidget(ConnectorMixin, gtk.TextView):
    '''Text-view based list of tags, where each tag is represented by a
    button inserted as a child in the textview.

    @signal: C{selection-changed ()}: emitted when tag selection changes
    @signal: C{sorting-changed ()}: emitted when tag sorting changes
    '''

    # define signals we want to use - (closure type, return type and arg types)
    __gsignals__ = {
        'selection-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
        'sorting-changed': (gobject.SIGNAL_RUN_LAST, None, (object,)),
    }

    def __init__(self, index, sorting='score'):
        gtk.TextView.__init__(self, None)  # Create TextBuffer implicitly
        self.set_name('zim-tags-tagcloud')
        self.index = None

        self.set_editable(False)
        self.set_cursor_visible(False)
        self.set_wrap_mode(gtk.WRAP_CHAR)

        self.set_sorting(sorting)
        self.connect_index(index)

    def set_sorting(self, sorting):
        self._alphabetically = (sorting == 'alpha')

    def connect_index(self, index):
        '''Connect to an Index object'''
        self.disconnect_index()  # just to be sure
        self.index = index
        self.connectto_all(self.index.update_iter.tags, (
            ('tag-row-inserted', self._update),
            ('tag-row-deleted', self._update),
        ))
        self._update()

    def disconnect_index(self):
        '''Stop the model from listening to the index. Used to unhook
        the model before reloading the index.
        '''
        if self.index is not None:
            self.disconnect_from(self.index.update_iter.tags)
        self._clear()

    def get_tag_filter(self):
        '''Returns a tuple with two lists of tags; the first gives all
        tags that are selected, the second gives all tags shown in the
        cloud. By definition the first list is a subset of the second.
        If no tags are selected returns None instead.
        '''
        return [
            b.indextag for b in self.get_children() if b.get_active()
        ]

    def _clear(self):
        '''Clears the cloud'''
        self.foreach(lambda b: self.remove(b))
        buffer = self.get_buffer()
        buffer.delete(*buffer.get_bounds())

    def _update(self, *a):
        '''Update the cloud to show only tags that share a set of pages
        with the selected tags.'''
        tagview = TagsView.new_from_index(self.index)
        selected = []
        for button in self.get_children():
            if button.get_active():
                try:
                    selected.append(tagview.lookup_by_tagname(button.indextag))
                except IndexNotFoundError:
                    pass
                # Need the lookup here in case the tag went missing in the
                # mean time e.g. due to editing of the page
        self._clear()

        if selected:
            tags = tagview.list_intersecting_tags(selected)
        else:
            tags = tagview.list_all_tags_by_n_pages()

        if self._alphabetically:
            tags = sorted(tags, key=lambda t: t.name)
        # else leave sorted by score

        buffer = self.get_buffer()
        for tag in tags:
            iter = buffer.get_end_iter()
            anchor = buffer.create_child_anchor(iter)
            button = TagCloudItem(tag)
            button.set_active(tag in selected)
            button.connect("toggled", lambda b: self._update())
            self.add_child_at_anchor(button, anchor)

        self.show_all()
        self.emit('selection-changed')

    def do_populate_popup(self, menu):
        populate_popup_add_separator(menu, prepend=True)

        item = gtk.CheckMenuItem(_('Sort alphabetically'))  # T: Context menu item for tag cloud
        item.set_active(self._alphabetically)
        item.connect('toggled', self._switch_sorting)
        item.show_all()
        menu.prepend(item)

    def _switch_sorting(self, widget, *a):
        self._alphabetically = widget.get_active()
        self._update()
        if self._alphabetically:
            self.emit('sorting-changed', 'alpha')
        else:
            self.emit('sorting-changed', 'score')

# Need to register classes defining gobject signals
gobject.type_register(TagCloudWidget)
