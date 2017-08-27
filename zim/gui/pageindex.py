# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the page index widget which is normally shown
in the side pane of the main window. L{PageIndex} is the main widget
which contains a L{PageTreeView} which is the actual list view widget.
The L{PageTreeStore} is our custom data model which connects to the
L{index<Index>} to get the page list data and maps it to the TreeView API.
'''

import gobject
import gtk
import pango
import logging

from functools import partial

from zim.notebook import Path
from zim.notebook.index.pages import PagesTreeModelMixin, PageIndexRecord, IndexNotFoundError

from zim.gui.widgets import ui_environment, BrowserTreeView, \
    populate_popup_add_separator, encode_markup_text, \
    ErrorDialog
from zim.gui.clipboard import \
    Clipboard, \
    INTERNAL_PAGELIST_TARGET_NAME, INTERNAL_PAGELIST_TARGET, \
    pack_urilist, unpack_urilist

from zim.actions import PRIMARY_MODIFIER_MASK


logger = logging.getLogger('zim.gui.pageindex')


NAME_COL = 0  #: Column with short page name (page.basename)
PATH_COL = 1  #: Column with the zim PageIndexRecord itself
EMPTY_COL = 2  # : Column to flag if the page is empty or not
STYLE_COL = 3  # : Column to specify style (based on empty or not)
FGCOLOR_COL = 4  # : Column to specify color (based on empty or not)
WEIGHT_COL = 5  # : Column to specify the font weight (open page in bold)
N_CHILD_COL = 6  # : Column with the number of child pages
TIP_COL = 7  # : Column with the name to be used in the tooltip

# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVAL_C = gtk.gdk.unicode_to_keyval(ord('c'))
KEYVAL_L = gtk.gdk.unicode_to_keyval(ord('l'))


#~ import gc
#~ gc.set_debug(gc.DEBUG_LEAK)
#~ gc.set_debug(gc.DEBUG_STATS)

# TODO split in a base class to be used by e.g. Tags as well and
# a subclass combining the base with the mixin

class PageTreeStoreBase(gtk.GenericTreeModel, gtk.TreeDragSource, gtk.TreeDragDest):
    '''Custom gtk TreeModel that is integrated closely with the L{Index}
    object of the notebook. This model is mostly an API layer translating
    between the C{gtk.TreeView} and the zim L{Index} interfaces. It
    fetches data on the fly when requested and only keeps a very
    limited cache in memory. This allows scaling to very large notebooks.

    This custom model is based on C{gtk.GenericTreeModel} which takes
    care of the C library wrapper. See the documentation there to
    get the fine details of the API.

    Be aware that in this interface there are two classes both
    referred to as "paths". The first is the gtk TreePath (which is in
    fact just a tuple of integers, without a propr class) and the second
    is L{zim.notebook.Path}. When a gtk TreePath is intended the argument is
    explicitly called "treepath", while arguments called "path" refer to a
    zim Path.

    For all the methods with a name starting with C{on_} the "iter"
    argument is a L{MyTreeIter}. The GenericTreeModel in turn
    wraps these in C{gtk.TreeIter} object. So e.g. the implementation
    of C{get_iter()} calls C{on_get_iter()} and wraps the
    L{MyTreeIter} object into a C{gtk.TreeIter}.
    '''

    # We inherit from gtk.TreeDragSource and gtk.TreeDragDest even though
    # we do not actually implement them. Somehow this is needed to get
    # the TreeView to understand we support drag-and-drop even though
    # actual work is implemented in the treeview itself.

    # FIXME: Figure out how to bind cellrenderer style to the
    # EMPTY_COL so we do not need the separate style and fgcolor cols.
    # This will also allow making style for empty pages configurable.

    # This model does it own memory management for outstanding treeiter
    # objects. The reason is that we otherwise leak references and consume
    # a lot of memory. The downside is that we now need to track the
    # MyTreeIter objects ourselves to ensure they are not collected by
    # the garbage collector while still being used. This is handled by the
    # cache dict in PagesTreeModelMixin. We need to flush this cache regularly
    # to prevent collecting the whole index in memory.
    # Ideally we want to flush after every operation using treeiters.
    # We achieve this by scheduling the flushing on the main loop idle
    # event. This has the result that iters are valid within the same
    # operation but can not be carried between events. (Of course you
    # should not do that in the first place and use a TreeRowReference
    # instead.)

    COLUMN_TYPES = (
        gobject.TYPE_STRING,  # NAME_COL
        gobject.TYPE_PYOBJECT,  # PATH_COL
        bool,  # EMPTY_COL
        pango.Style,  # STYLE_COL
        gobject.TYPE_STRING,  # FGCOLOR_COL
        int,  # WEIGHT_COL
        gobject.TYPE_STRING,  # N_CHILD_COL
        gobject.TYPE_STRING,  # TIP_COL
    )

    NORMAL_COLOR = None
    EMPTY_COLOR = 'grey'  # FIXME set based on style.text[gtk.STATE_INSENSITIVE]

    def __init__(self):
        gtk.GenericTreeModel.__init__(self)
        self.current_page = None
        self.set_property('leak-references', False)
        # We do our own memory management, thank you very much
        self._flush_scheduled = False

    def flush_cache(self):
        # Drop references and free memory
        #~ print '!! Freeing %i refs' % len(self._cache)
        #~ print '=' * 60
        self.invalidate_iters()
        self.cache.clear()
        self._flush_scheduled = False
        return False  # In case we are called from idle signal

    def _emit_page_changes(self, path):
        try:
            treepath = self.find(path)
        except IndexNotFoundError:
            return None
        else:
            treeiter = self.get_iter(treepath)
            self.emit('row-changed', treepath, treeiter)
            return treepath

    def set_current_page(self, path):
        '''Set the current open page to highlight it in the index.
        @param path: the L{Path} that is currently open, or C{None} to unset
        '''
        oldpath = self.current_page
        self.current_page = path
        if oldpath:
            self._emit_page_changes(oldpath)

        if path:
            return self._emit_page_changes(path)
        else:
            return None

    def get_indexpath(self, treeiter):
        '''Get an L{PageIndexRecord} for a C{gtk.TreeIter}

        @param treeiter: a C{gtk.TreeIter}
        @returns: an L{PageIndexRecord} object
        '''
        myiter = self.get_user_data(treeiter)
        return PageIndexRecord(myiter.row)

    def on_get_flags(self):
        return 0  # no flags

    def on_get_n_columns(self):
        return len(self.COLUMN_TYPES)

    def on_get_column_type(self, i):
        #~ print '>> on_get_column_type', index
        return self.COLUMN_TYPES[i]

    def on_get_value(self, iter, column):
        #~ print '>> on_get_value', iter, column
        if column == NAME_COL:
            return iter.row['name'].split(':')[-1]
        elif column == TIP_COL:
            basename = iter.row['name'].split(':')[-1]
            return encode_markup_text(basename)
        elif column == PATH_COL:
            return PageIndexRecord(iter.row)
        elif column == EMPTY_COL:
            return iter.row['is_link_placeholder']
        elif column == STYLE_COL:
            if iter.row['is_link_placeholder']:
                return pango.STYLE_ITALIC
            else:
                return pango.STYLE_NORMAL
        elif column == FGCOLOR_COL:
            if iter.row['is_link_placeholder']:
                return self.EMPTY_COLOR
            else:
                return self.NORMAL_COLOR
        elif column == WEIGHT_COL:
            if self.current_page and iter.row['name'] == self.current_page.name:
                return pango.WEIGHT_BOLD
            else:
                return pango.WEIGHT_NORMAL
        elif column == N_CHILD_COL:
            return iter.n_children or ''
            # don't display "0" to keep look bit clean

    def on_get_iter(self, treepath):
        '''Returns an MyTreeIter for a gtk TreePath or None'''
        #~ print '>> on_get_iter', treepath

        # Schedule a flush with some timeout to try to take advantage
        # of known cache for repeated requests. Cache can grow very fast
        # on scroll, so don't make the time constant to large.
        if not self._flush_scheduled:
            def idle_add():
                gobject.idle_add(self.flush_cache)
                return False  # delete timeout

            gobject.timeout_add(500, idle_add)
            self._flush_scheduled = True

        return self.get_mytreeiter(treepath)

    def on_get_path(self, iter):
        '''Returns a gtk TreePath for an indexpath'''
        #~ print '>> on_get_path', iter
        return iter.treepath

    def on_iter_next(self, iter):
        '''Returns the PageIndexRecord for the next row on the same level or None'''
        # Only within one namespace, so not the same as index.get_next()
        #~ print '>> on_iter_next', iter
        treepath = list(iter.treepath)
        treepath[-1] += 1
        treepath = tuple(treepath)
        return self.on_get_iter(treepath)

    def on_iter_children(self, iter):
        '''Returns an PageIndexRecord for the first child below path or None.
        If path is None returns the PageIndexRecord for first top level item.
        '''
        #~ print '>> on_iter_children', iter
        if iter is None:
            treepath = (0,)
        else:
            treepath = iter.treepath + (0,)
        return self.on_get_iter(treepath)

    def on_iter_has_child(self, iter):
        '''Returns True if PageIndexRecord for iter has children'''
        return iter.n_children > 0

    def on_iter_n_children(self, iter):
        '''Returns the number of children in a namespace. When iter
        is None the number of pages in the root namespace is given.
        '''
        #~ print '>> on_iter_n_children', iter
        if iter is None:
            return self.n_children_top()
        else:
            return iter.n_children

    def on_iter_nth_child(self, iter, n):
        '''Returns the nth child or None. If iter is C{None} the
        nth item in the root namespace is returned.
        '''
        #~ print '>> on_iter_nth_child', iter, n
        if iter is None:
            treepath = (n,)
        else:
            treepath = iter.treepath + (n,)
        return self.on_get_iter(treepath)

    def on_iter_parent(self, iter):
        '''Returns an indexpath for parent node or None'''
        #~ print '>> on_iter_parent', iter
        treepath = iter.treepath[:-1]
        if len(treepath) > 0:
            return self.on_get_iter(treepath)
        else:
            return None

    # Compatibility for older version of GenericTreeModel
    if not hasattr(gtk.GenericTreeModel, 'create_tree_iter'):
        logger.warn('Using work around for older version of GenericTreeModel - may hurt performance')

        def create_tree_iter(self, indexpath):
            # Use GenericTreeModel API to wrap the iter
            return self.get_iter(iter.treepath)

    if not hasattr(gtk.GenericTreeModel, 'get_user_data'):
        def get_user_data(self, treeiter):
            # Use GenericTreeModel API to unwrap the iter
            treepath = self.get_path(treeiter)
            return self.cache[treepath]

# Need to register classes defining gobject signals or overloading methods
gobject.type_register(PageTreeStoreBase)


class PageTreeStore(PagesTreeModelMixin, PageTreeStoreBase):

    def __init__(self, index):
        PagesTreeModelMixin.__init__(self, index)
        PageTreeStoreBase.__init__(self)


class PageTreeView(BrowserTreeView):
    '''TreeView widget to show a list of pages.

    This view is intended to show a L{PageTreeStore} model, but it
    can also handle filtered models and subclasses that have the
    same columns. (The "tags" plugin uses this same view with
    alternative models.)

    @signal: C{page-activated (path)}: emitted when a page is clicked
    @signal: C{populate-popup (menu)}: hook to populate the context menu
    @signal: C{copy ()}: copy the current selection to the clipboard
    @signal: C{insert-link (path)}: called when the user pressed <Ctrl>L on page
    '''

    # define signals we want to use - (closure type, return type and arg types)
    __gsignals__ = {
        'page-activated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
        'insert-link': (gobject.SIGNAL_RUN_LAST, None, (object,)),
        'copy': (gobject.SIGNAL_RUN_LAST, None, ()),
    }

    def __init__(self, ui, model=None):
        '''Constructor

        @param ui: the L{GtkInterface} object
        @param model: a L{PageTreeStore} object
        '''
        BrowserTreeView.__init__(self)
        self.set_name('zim-pageindex')
        self.ui = ui

        column = gtk.TreeViewColumn('_pages_')
        self.append_column(column)

        cr1 = gtk.CellRendererText()
        cr1.set_property('ellipsize', pango.ELLIPSIZE_END)
        column.pack_start(cr1, True)
        column.set_attributes(cr1, text=NAME_COL,
                              style=STYLE_COL, foreground=FGCOLOR_COL, weight=WEIGHT_COL)

        cr2 = self.get_cell_renderer_number_of_items()
        column.pack_start(cr2, False)
        column.set_attributes(cr2, text=N_CHILD_COL, weight=WEIGHT_COL)

        if gtk.gtk_version >= (2, 12) \
                and gtk.pygtk_version >= (2, 12):
            self.set_tooltip_column(TIP_COL)

        self.set_headers_visible(False)

        self.set_enable_search(True)
        self.set_search_column(0)

        self.enable_model_drag_source(
            gtk.gdk.BUTTON1_MASK, (INTERNAL_PAGELIST_TARGET,),
            gtk.gdk.ACTION_LINK | gtk.gdk.ACTION_MOVE)
        self.enable_model_drag_dest(
            (INTERNAL_PAGELIST_TARGET,),
            gtk.gdk.ACTION_MOVE)

        if model:
            self.set_model(model)

    def disconnect_index(self):
        '''Stop the widget from listening to the index. Used e.g. to
        unhook the model before reloading the index, thus avoiding
        many signals to be processed by both the model and the view.
        Doing this requires constructing and setting a new model with
        L{set_model()} to get the view in sync with the index again.
        '''
        model = self.get_model()
        if isinstance(model, gtk.TreeModelFilter):
            model = model.get_model()  # get childmodel
        model.teardown()

    def set_model(self, model):
        '''Set a new model for the view.

        @param model: a new TreeModel object
        '''
        BrowserTreeView.set_model(self, model)
        model.connect('row-inserted', self.on_row_inserted)

    def on_row_inserted(self, model, treepath, iter):
        path = model.get_indexpath(iter)
        if path and path == self.ui.page:
            self.select_treepath(treepath)

    def do_row_activated(self, treepath, column):
        model = self.get_model()
        iter = model.get_iter(treepath)
        path = model.get_indexpath(iter)
        if path:
            self.emit('page-activated', path)

    def do_page_activated(self, path):
        self.ui.open_page(path)

    def do_key_press_event(self, event):
        # Keybindings for the treeview:
        #  Ctrl-C copy link to selected page
        #  Ctrl-L insert link to selected page in pageview
        # Keybindings for collapsing and expanding items are
        # implemented in the BrowserTreeView parent class
        # And MainWindow hooks Esc to close side pane
        handled = False
        #~ print 'KEY %s (%i)' % (gtk.gdk.keyval_name(event.keyval), event.keyval)

        if event.state & PRIMARY_MODIFIER_MASK:
            if event.keyval == KEYVAL_C:
                self.emit('copy')
                handled = True
            elif event.keyval == KEYVAL_L:
                path = self.get_selected_path()
                #~ print '!! insert-link', path
                self.emit('insert-link', path)
                handled = True

        return handled \
            or BrowserTreeView.do_key_press_event(self, event)

    def do_initialize_popup(self, menu):
        # TODO get path first and determine what menu options are valid
        path = self.get_selected_path() or Path(':')
        self.ui.populate_popup('page_popup', menu, path)

        populate_popup_add_separator(menu)
        item = gtk.ImageMenuItem('gtk-copy')
        item.connect('activate', lambda o: self.do_copy())
        menu.append(item)
        menu.show_all()

        self.populate_popup_expand_collapse(menu)

    def do_copy(self):
        #~ print '!! copy location'
        page = self.get_selected_path()
        if page:
            Clipboard.set_pagelink(self.ui.notebook, page)

    def do_drag_data_get(self, dragcontext, selectiondata, info, time):
        assert selectiondata.target == INTERNAL_PAGELIST_TARGET_NAME
        model, iter = self.get_selection().get_selected()
        path = model.get_indexpath(iter)
        logger.debug('Drag data requested, we have internal path "%s"', path.name)
        data = pack_urilist((path.name,))
        selectiondata.set(INTERNAL_PAGELIST_TARGET_NAME, 8, data)

    def do_drag_data_received(self, dragcontext, x, y, selectiondata, info, time):
        assert selectiondata.target == INTERNAL_PAGELIST_TARGET_NAME
        names = unpack_urilist(selectiondata.data)
        assert len(names) == 1
        source = Path(names[0])

        dest_row = self.get_dest_row_at_pos(x, y)
        if dest_row:
            treepath, position = dest_row
        else:
            dragcontext.finish(False, False, time)  # NOK
            return
        model = self.get_model()
        iter = model.get_iter(treepath)
        path = model.get_indexpath(iter)

        if position == gtk.TREE_VIEW_DROP_BEFORE:
            logger.debug('Dropped %s before %s', source, path)
            dest = path.parent + source.basename
        elif position == gtk.TREE_VIEW_DROP_AFTER:
            logger.debug('Dropped %s after %s', source, path)
            dest = path.parent + source.basename
        else:
            # gtk.TREE_VIEW_DROP_INTO_OR_BEFORE
            # or gtk.TREE_VIEW_DROP_INTO_OR_AFTER
            logger.debug('Dropped %s into %s', source, path)
            dest = path + source.basename

        if path == source or dest == source:
            # TODO - how to get the row image float back like when drop is not allowed ?
            if path == source:
                logger.debug('Dropped page onto itself')
            else:
                logger.debug('Paths have same namespace, no reordering')
            dragcontext.finish(False, False, time)  # NOK
            return

        try:
            notebook = self.ui.notebook  # XXX
            notebook.move_page(source, dest, update_links=True)
        except:
            logger.exception('Failed to move page %s -> %s', source, dest)
            dragcontext.finish(False, False, time)  # NOK
        else:
            dragcontext.finish(True, False, time)  # OK

    def set_current_page(self, path, vivificate=False):
        '''Select a page in the treeview

        @param path: a notebook L{Path} object for the page
        @param vivificate: when C{True} the path is created
        temporarily when it did not yet exist

        @returns: a gtk TreePath (tuple of intergers) or C{None}
        '''
        #~ print '!! SELECT', path
        model = self.get_model()
        if model is None:
            return None  # index not yet initialized ...

        treepath = model.set_current_page(path)  # highlight in model
        return treepath  # can be None

    def select_treepath(self, treepath):
        '''Select a gtk TreePath in the view

        @param treepath: a gtk TreePath (tuple of integers)
        '''
        self.expand_to_path(treepath)
        self.get_selection().select_path(treepath)
        self.set_cursor(treepath)
        #~ self.scroll_to_cell(treepath, use_align=True, row_align=0.9)
        # BUG: align 0.9 doesn't behave as one would expect..
        self.scroll_to_cell(treepath)

    def get_selected_path(self):
        '''Get the selected notebook path

        @returns: a L{PageIndexRecord} or C{None} if there was no selection
        '''
        model, iter = self.get_selection().get_selected()
        if model is None or iter is None:
            return None
        else:
            return model.get_indexpath(iter)

# Need to register classes defining gobject signals
gobject.type_register(PageTreeView)


class PageIndex(gtk.ScrolledWindow):
    '''This is the main widget to display a page index.
    It contains a L{PageTreeView} within a scrolled window.

    @ivar treeview: the L{PageTreeView}
    '''

    def __init__(self, ui):
        '''Constructor

        @param ui: the main L{GtkInterface} object
        '''
        gtk.ScrolledWindow.__init__(self)
        self.ui = ui

        self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.set_shadow_type(gtk.SHADOW_IN)

        self.treeview = PageTreeView(ui)
        self.add(self.treeview)

        # Set model and connect to index
        assert self.ui.notebook, 'BUG: need notebook at initialization'
        index = self.ui.notebook.index

        model = PageTreeStore(index)
        self.treeview.set_model(model)

        # Connect to ui signals
        ui.connect('open-page', self.on_open_page)
        ui.connect('start-index-update', lambda o: self.disconnect_model())
        ui.connect('end-index-update', lambda o: self.reload_model())

        # Select current page, if any
        if self.ui.page:
            self.on_open_page(self.ui, self.ui, page, self.ui, page)

    def on_open_page(self, ui, page, path):
        treepath = self.treeview.set_current_page(Path(path.name), vivificate=True)
        # Force reloading Path - stale PageIndexRecord will not be checked later
        expand = ui.notebook.namespace_properties[path.name].get('auto_expand_in_index', True)
        if treepath and expand:
            self.treeview.select_treepath(treepath)

    def is_focus(self):
        return self.treeview.is_focus()

    def grab_focus(self):
        return self.treeview.grab_focus()

    def get_selected_path(self):
        '''Get the selected notebook path

        @returns: a L{PageIndexRecord} or C{None} if there was no selection
        '''
        return self.treeview.get_selected_path()

    def disconnect_model(self):
        '''Stop the widget from listening to the index. Used e.g. to
        unhook the model before reloading the index, thus avoiding
        many signals to be processed by both the model and the view.
        Typically should be followed by L{reload_model()} to get the
        view in sync with the index again.
        '''
        self.treeview.disconnect_index()

    def reload_model(self):
        '''Re-initialize the treeview model. This is called when
        reloading the index to get rid of out-of-sync model errors
        without need to close the app first.
        '''
        model = PageTreeStore(self.ui.notebook.index)
        self.treeview.set_model(model)
        if self.ui.page:
            self.on_open_page(self.ui, self.ui.page, self.ui.page)
