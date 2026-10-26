import typing
from collections.abc import Iterable
from enum import Enum
from typing import Tuple, Any, NamedTuple

from gi.repository import Gtk, GObject, Pango, Gdk  # type: ignore
from zim.signals import SignalHandler

from zim import signals
from zim.formats import heading_to_anchor
from zim.gui.widgets import (
    WindowSidePaneWidget,
    InputEntry,
    StatusPage,
    SingleClickTreeView,
    to_utf8_normalized_casefolded,
)
from zim.notebook import (
    Path,
    IndexNotFoundError,
    HRef,
    HREF_REL_FLOATING,
    LINK_DIR_BACKWARD,
)
from zim.notebook.index import IndexLink
from zim.plugins.collections import Autogen
from zim.plugins.collections.common import Collection, R, Notifier, CollectionNote
from zim.plugins.collections.db import ColDB
from zim.plugins.collections.dlgs import RmCollConfirmDlg, AddCollDlg, EditCollDlg
from zim.plugins.collections.misc import Misc, PageStructureT
from zim.plugins.collections.styling import StylingDlg

if typing.TYPE_CHECKING:

    def _(_: str) -> str:
        pass


class IndexRecDir(Enum):
    FORW = 0
    BACK = 1


class IndexEntry(NamedTuple):
    title: str
    href: str
    dir: IndexRecDir
    is_col: bool
    is_archived: bool
    tags: Iterable[str]


class CollectionFilterEntry(InputEntry):
    def __init__(self, check_func, handler):
        super().__init__(
            placeholder_text=R.FIND_COLLECTION_PLACEHOLDER,
            check_func=check_func,
        )
        self.handler = handler
        # name, namespace(see Misc.get_href_ns), href
        self.model = Gtk.ListStore(str, str, str)
        self.set_icon_to_clear()

        completion = Gtk.EntryCompletion()
        self.set_completion(completion)
        completion.set_model(self.model)
        completion.set_text_column(0)
        completion.set_minimum_key_length(0)
        completion.set_match_func(self.match_collection)

        ns_renderer = Gtk.CellRendererText()
        ns_renderer.set_property("style", Pango.Style.ITALIC)
        ns_renderer.set_property("foreground", "gray")
        completion.pack_start(ns_renderer, True)
        completion.add_attribute(ns_renderer, "text", 1)
        completion.connect("match-selected", self.on_selected)

        # layout = completion.get_area()
        # layout.set_orientation(Gtk.Orientation.VERTICAL)

    def populate(self, collections: Iterable[Collection]):
        self.model.clear()
        for col in collections:
            self.model.append((col.title, Misc.get_href_ns(col.href), col.href))

    def on_selected(self, completion, model, iter):
        href = completion.get_model().get_value(iter, 2)
        self.handler(href)

    @staticmethod
    def match_collection(completion, key, iter):
        if key is None:
            return False
        model = completion.get_model()
        title = to_utf8_normalized_casefolded(model.get_value(iter, 0))
        href = to_utf8_normalized_casefolded(model.get_value(iter, 2))
        return key in title or key in href


class SidePane(Gtk.VBox, WindowSidePaneWidget):
    """Side pane widget for managing and displaying collections."""

    title = _("Collections")
    __gsignals__ = {
        "goto-collection": (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    def __init__(self, pageview, plugin, notifier: Notifier) -> None:
        GObject.GObject.__init__(self)
        self.plugin = plugin
        self.pageview = pageview
        self.notifier = notifier
        self.index: dict[str, Tuple[Collection, Any]] = {}
        self.db = ColDB(pageview.notebook.index._db)
        self.db.connect("changed", self.on_collections_changed)
        self.archive_roots = self._find_archive_roots(
            plugin.preferences["archive_tags"]
        )
        self.props.spacing = 6
        self.set_margin_start(6)
        self.set_margin_end(6)

        # Toolbar
        toolbar = self._init_toolbar()
        self.pack_start(toolbar, False, False, 0)

        # Collection Search Entry
        self.coll_filter = CollectionFilterEntry(
            check_func=self.db.is_existing_coll_name,
            handler=self.goto_collection,
        )
        self.pack_start(self.coll_filter, False, False, 0)

        # Main view
        self.main_view = Gtk.Stack()
        self.pack_start(self.main_view, True, True, 0)

        placeholder_no_cols = StatusPage(icon_name=None, title=None, info_text=R.NOCOLS)
        placeholder_no_cols.show_all()
        self.main_view.add_named(placeholder_no_cols, "no-cols-placeholder")

        placeholder_empty_col = StatusPage(
            icon_name=None, title=None, info_text=R.EMPTYCOL
        )
        placeholder_empty_col.show_all()
        self.main_view.add_named(placeholder_empty_col, "empty-col-placeholder")

        placeholder_select_col = StatusPage(
            icon_name=None, title=None, info_text=R.SELECTCOL
        )
        placeholder_select_col.show_all()
        self.main_view.add_named(placeholder_select_col, "select-col-placeholder")

        # Current Collection Notes View
        self._current_coll: Collection | None = None
        self.collection_view = SingleClickTreeView()
        self.collection_view.props.headers_visible = False
        self.collection_view.show_all()
        self.main_view.add_named(self.collection_view, "collection-view")
        self.collection_view.connect("row-activated", self.goto_note)

        tag_color_rend = Gtk.CellRendererText()
        tag_color_rend.props.xalign = 0.5
        tag_color_rend.props.yalign = 0.5
        col_tag_color = Gtk.TreeViewColumn(
            " ", tag_color_rend, text=6, foreground_rgba=7
        )
        self.collection_view.append_column(col_tag_color)

        title_renderer = Gtk.CellRendererText()
        col_note = Gtk.TreeViewColumn(
            "note",
            title_renderer,
            weight=1,
            text=0,
            strikethrough=3,
            style=4,
            foreground_rgba=5,
        )
        self.collection_view.append_column(col_note)

        # Styling
        self.styling = self.db.load_styling()

        updated = self._find_tagged_hubs(plugin.preferences["hub_tags"])
        if not updated:
            self.on_collections_changed()

        nb = self.pageview.notebook
        self.connectto(
            nb.index.update_iter.pages, "page-changed", order=signals.SIGNAL_RUN_LAST
        )

    def _init_toolbar(self) -> Gtk.Toolbar:
        """Initialize and return the toolbar."""
        toolbar = Gtk.Toolbar()
        toolbar.set_icon_size(Gtk.IconSize.SMALL_TOOLBAR)

        self.bt_home = Gtk.ToolButton()
        self.bt_home.set_tooltip_text(R.GO_TO_HUB)
        self.bt_home.set_icon_name("go-home-symbolic")
        self.bt_home.connect("clicked", self.on_goto_hub_clicked)
        toolbar.add(self.bt_home)

        self.bt_add = Gtk.ToolButton()
        self.bt_add.set_tooltip_text(R.ADD_A_NEW_COLLECTION)
        self.bt_add.set_icon_name("list-add-symbolic")
        self.bt_add.connect("clicked", self.on_add_collection_clicked)
        toolbar.add(self.bt_add)

        self.bt_rm = Gtk.ToolButton()
        self.bt_rm.set_tooltip_text(R.REMOVE_COLLECTION)
        self.bt_rm.set_icon_name("list-remove-symbolic")
        self.bt_rm.connect("clicked", self.on_rm_collection_clicked)
        toolbar.add(self.bt_rm)

        self.bt_edit = Gtk.ToolButton()
        self.bt_edit.set_tooltip_text(R.EDIT_COLLECTION)
        self.bt_edit.set_icon_name("edit-symbolic")
        self.bt_edit.connect("clicked", self.on_edit_collection_clicked)
        toolbar.add(self.bt_edit)

        self.bt_styling = Gtk.ToolButton()
        self.bt_styling.set_icon_name("tag-symbolic")
        self.bt_styling.set_tooltip_text(R.TAG_STYLING_TITLE)
        self.bt_styling.connect("clicked", self.on_styling_clicked)
        toolbar.add(self.bt_styling)

        self.bt_refresh = Gtk.ToolButton()
        self.bt_refresh.set_icon_name("view-refresh-symbolic")
        self.bt_refresh.set_tooltip_text(R.DBG_REFRESH_COLLECTIONS)
        self.bt_refresh.connect("clicked", self.on_collections_changed)
        toolbar.add(self.bt_refresh)

        return toolbar

    def _update_toolbar(self):
        col_selected = self._current_coll is not None
        self.bt_home.set_sensitive(col_selected)
        self.bt_rm.set_sensitive(col_selected)
        self.bt_edit.set_sensitive(col_selected)

    def on_add_collection_clicked(self, sender) -> None:
        dlg = AddCollDlg(self.pageview)
        dlg.run()
        c = dlg.result
        if not c:
            return
        self.add_collection(c)
        self.notifier.notify(R.COLLECTION_ADDED.format(col=c.title))

    def on_rm_collection_clicked(self, sender) -> None:
        if self._current_coll is None:
            return
        title = self._current_coll.title
        ok = RmCollConfirmDlg(self, title).run()
        if not ok:
            return
        self.db.rm_collection(self._current_coll.id)
        self.notifier.notify(R.COLLECTION_REMOVED.format(col=title))

    def on_edit_collection_clicked(self, sender) -> None:
        if self._current_coll is None:
            return
        col_updated = EditCollDlg(self.pageview, self._current_coll).run()
        if col_updated is None:
            return
        new_path = col_updated.href
        if col_updated.title != self._current_coll.title:
            new_path = self.update_path_and_title(col_updated.title)

        # if the collection is visible, regenerate it
        if col_updated.query:
            col_page = HRef.new_from_wiki_link(col_updated.href).names
            if self.pageview.page.name == col_page:
                gen = Autogen(col_updated, self.pageview)
                gen.run()
        self.db.update_collection(col_updated, new_path)

    def update_path_and_title(self, new_title: str) -> str:
        assert self._current_coll is not None
        href = HRef.new_from_wiki_link(self._current_coll.href)
        if href.anchor is None:
            new_path_list = href.names.split(":")
            new_path_list[-1] = new_title
            new_path = ":".join(new_path_list)
            self.pageview.notebook.move_page(
                Path(href.names), Path(new_path), update_heading=True
            )
        else:
            page = self.pageview.notebook.get_page(Path(href.names))
            Misc.rename_heading(page, anchor=href.anchor, new_title=new_title)
            new_path = HRef(
                HREF_REL_FLOATING, href.names, heading_to_anchor(new_title)
            ).to_wiki_link()
        return new_path

    def goto_collection(self, href: str) -> None:
        """Switch to the given collection by href."""
        try:
            self._current_coll, model = self.index[href]
        except KeyError:
            coll = self.db.get_collection_by_href(href)
            self._index_collections([coll])
            self._current_coll, model = self.index[href]

        self.coll_filter.set_text(self._current_coll.title)
        self.coll_filter.update_input_valid()
        self.collection_view.set_model(model)
        widget = "collection-view" if len(model) > 0 else "empty-col-placeholder"
        self.main_view.set_visible_child_name(widget)
        self._update_toolbar()
        self.focus()

    def on_collections_changed(self, sender=None) -> None:
        """Refresh the collections index and UI."""
        self._index_collections()
        self.coll_filter.clear()
        self.coll_filter.populate(self.db.all_collections())
        self._current_coll = None
        self.collection_view.set_model(None)
        self._update_toolbar()
        placeholder = "select-col-placeholder" if self.index else "no-cols-placeholder"
        self.main_view.set_visible_child_name(placeholder)

    def on_goto_hub_clicked(self, sender):
        if self._current_coll is None:
            return
        self.pageview.activate_link(self._current_coll.href)

    def on_styling_clicked(self, sender):
        dlg = StylingDlg(self, self.styling)
        updated_styling = dlg.run()
        if updated_styling:
            self.styling = updated_styling
            self.db.save_styling(updated_styling)

    def focus(self):
        """Focus the pane in the UI."""
        position = self.plugin.preferences["pane"]
        self.pageview.get_toplevel().set_pane_state(
            pane=position,
            visible=True,
            activetab=self.__class__.__name__,
            grab_focus=True,
        )

    def _find_archive_roots(self, tags_str: str) -> frozenset[Path]:
        nb = self.pageview.notebook
        archive_tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
        archived_roots = set()
        for tag in archive_tags:
            try:
                archived_roots.update(nb.tags.list_pages(tag))
            except IndexNotFoundError:
                pass
        return frozenset(archived_roots)

    def _find_tagged_hubs(self, tags_str: str) -> bool:
        nb = self.pageview.notebook
        hub_tags = set(tag.strip() for tag in tags_str.split(",") if tag.strip())
        page_path_set = set()
        for tag in hub_tags:
            try:
                page_path_set |= set(nb.tags.list_pages(tag))
            except IndexNotFoundError:
                pass

        colls = []
        for page_path in page_path_set:
            page = nb.get_page(page_path)
            page_struct = Misc.parse_page_structure(page, nb)
            for href, title, tags, _ in page_struct.values():
                if tags & hub_tags and not self.db.is_existing_coll_href(href):
                    colls.append(Collection(id=-1, title=title, href=href, query=None))
        if colls:
            self.db.add_collections(colls)
        return bool(colls)

    def is_archived_page(self, page: Path) -> bool:
        return any(page == root or page.ischild(root) for root in self.archive_roots)

    def add_collection(self, col: Collection) -> None:
        self.db.add_collections([col])
        if col.href in self.index:
            self.goto_collection(col.href)

        # if the collection is visible, regenerate it
        if col.query:
            col_page = HRef.new_from_wiki_link(col.href).names
            if self.pageview.page.name == col_page:
                gen = Autogen(col, self.pageview)
                gen.run()

    def goto_note(self, sender, path, column) -> None:
        model = sender.get_model()
        note_it = model.get_iter(path)
        if note_it is not None:
            note = model[note_it]
            if self.db.is_existing_coll_href(note[1]):
                self.goto_collection(href=note[1])
                return
            self.pageview.activate_link(note[1])

    def set_orientation(self, orientation) -> None:
        pass

    def _index_one_collection(self, coll: Collection) -> list[IndexEntry]:
        """Build a comprehensive index of notes related to the given collection.

        Finds all notes connected to a collection in two directions:
        1. Forward links: Notes that are linked from the collection's hub page
        2. Backward links: Notes that link to the collection's hub page

        For each note, it determines whether it's a collection itself, is archived,
        and collects its tags.

        Args:
            coll: The Collection object to index

        Returns:
            A list of IndexEntry objects representing all notes related to this collection
        """
        nb = self.pageview.notebook
        entries_seen: set[str] = set()

        def not_seen_before(href: str):
            if href in entries_seen:
                return False
            entries_seen.add(href)
            return True

        # Add notes found in the hub note
        entries_forw = Misc.parse_section_links(coll.href, nb)
        entries_seen = {e.href for e in entries_forw}

        pages = set()
        for e in entries_forw:
            href = HRef.new_from_wiki_link(e.href)
            path = nb.pages.resolve_link(self.pageview.page, href)
            page = nb.get_page(path)
            if page.hascontent:
                pages.add(page)

        notes: PageStructureT = {}
        for p in pages:
            notes |= Misc.parse_page_structure(p, nb)

        index: list[IndexEntry] = [
            IndexEntry(
                e.title,
                e.href,
                IndexRecDir.FORW,
                self.db.is_existing_coll_href(e.href),
                self.is_archived_page(Path(e.href)),
                notes[e.href][2],
            )
            for e in entries_forw
            if e.href in notes
        ]

        # Add notes that link to the hub
        coll_path = Path(HRef.new_from_wiki_link(coll.href).names)
        entries_back = list(nb.links.list_links(coll_path, LINK_DIR_BACKWARD))
        entries_back.append(IndexLink(coll_path, Path("")))

        index += [
            IndexEntry(
                title,
                href,
                IndexRecDir.BACK,
                self.db.is_existing_coll_href(href),
                self.is_archived_page(Path(href)),
                tags,
            )
            for e in entries_back
            for href, title, tags, links in Misc.parse_page_structure(
                nb.get_page(e.source), nb
            ).values()
            if coll.href in links and not_seen_before(href)
        ]

        return index

    def _index_to_model_row(self):
        pass

    def _index_collections(self, collections=None) -> None:
        CLR_TEXT_NORM = self.pageview.get_style_context().get_color(
            Gtk.StateFlags.NORMAL
        )
        CLR_ARCHIVED = Gdk.RGBA()
        CLR_ARCHIVED.parse(self.plugin.preferences["archive_color"])

        collections = collections or self.db.all_collections()
        for coll in collections:
            # title, href, None, strikethru, text-style, text-color, tag-slab, tag-color
            model = Gtk.ListStore(
                str, str, str, bool, Pango.Style, Gdk.RGBA, str, Gdk.RGBA
            )
            self.index[coll.href] = (coll, model)
            index = self._index_one_collection(coll)

            # Priorities for collection entries:
            #   - Collections over non-collections,
            #   - Collections with BACK direction,
            #   - Entries with styled tags,
            #   - Non-archived entries over archived ones.
            index.sort(
                reverse=True,
                key=lambda rec: (2 if rec.is_col else 0)
                + (1 if rec.dir == IndexRecDir.BACK and rec.is_col else 0)
                + (1 if self.styling.get_style_for_tags(rec.tags) is not None else 0)
                - (2 if rec.is_archived else 0),
            )
            for entry in index:
                tag_color = (
                    self.styling.get_style_for_tags(entry.tags)
                    if not entry.is_col
                    else None
                )
                slab = (
                    (R.SLAB_PIN if tag_color else None)
                    if not entry.is_col
                    else (R.SLAB_UP if entry.dir == IndexRecDir.BACK else R.SLAB_DOWN)
                )
                model.append(
                    [
                        entry.title,
                        entry.href,
                        None,
                        entry.is_archived,
                        (
                            Pango.Style.NORMAL
                            if not entry.is_archived
                            else Pango.Style.ITALIC
                        ),
                        CLR_TEXT_NORM if not entry.is_archived else CLR_ARCHIVED,
                        slab,
                        tag_color,
                    ]
                )

    def get_collections_for_page(self, page_href: str) -> list[Collection]:
        """Get collections this page belongs to."""
        result = []
        for coll, model in self.index.values():
            for row in model:
                href = HRef.new_from_wiki_link(row[1]).names
                if href == page_href:
                    result.append(coll)
        return result

    def on_page_changed(self, sender, row, content):
        nb = self.pageview.notebook
        page = Path(row["name"])

        # Hub changed - invalidate all collections with hubs on  this page
        hubs = self.db.get_hubs_for_page(page.name)

        # non hub page changed - invalidate all collections it's part of
        hrefs = (
            Misc.canonical_href(href.to_wiki_link(), nb, page)
            for href in content.iter_href(include_anchors=True)
        )
        colls_internal = [
            self.db.get_collection_by_href(href)
            for href in hrefs
            if self.db.is_existing_coll_href(href)
        ]
        colls_external = self.get_collections_for_page(page.name)
        for c in hubs + colls_external + colls_internal:
            try:
                del self.index[c.href]
            except KeyError:
                pass

    def on_archive_roots_changed(self):
        self.archive_roots = self._find_archive_roots(
            self.plugin.preferences["archive_tags"]
        )
