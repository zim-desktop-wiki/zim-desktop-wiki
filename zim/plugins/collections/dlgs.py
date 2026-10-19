from __future__ import annotations

import typing

from gi.repository import Gtk, Gdk, GObject, GLib  # type: ignore

from zim.gui.widgets import Dialog, PageEntry, InputEntry
from zim.notebook import HRef, Path
from zim.plugins.collections import Misc
from zim.plugins.collections.common import R, Query, Collection


class RmCollConfirmDlg(Dialog):
    def __init__(self, parent, title: str) -> None:
        Dialog.__init__(self, parent, R.RMCOLDLG_TITLE)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        self.vbox.add(grid)

        img_warn = Gtk.Image.new_from_icon_name(
            "dialog-warning-symbolic", Gtk.IconSize.DIALOG
        )
        grid.attach(img_warn, 0, 0, 1, 2)

        lbl_title = Gtk.Label(
            "<b>{title}</b>".format(title=R.RMCOLDLG_SUBTITLE), halign=Gtk.Align.START
        )
        lbl_title.set_use_markup(True)
        lbl_title.get_style_context().add_class(Gtk.STYLE_CLASS_TITLE)
        grid.attach(lbl_title, 1, 0, 1, 1)

        lbl_message = Gtk.Label(
            R.RMCOLDLG_MSG.format(title=title), halign=Gtk.Align.START
        )
        grid.attach(lbl_message, 1, 1, 1, 1)

    def do_response_ok(self):
        self.result = True
        return True


class QueryDlgMixin:
    query_enabled_cb: typing.Any

    def _setup_query_tab(self):
        grid = Gtk.Grid()

        # Query
        query_label = Gtk.Label(label=R.AG_QUERY, halign=Gtk.Align.START)
        grid.attach(query_label, 0, 0, 1, 1)

        self.query_entry = Gtk.Entry()
        self.query_entry.set_hexpand(True)
        self.query_entry.set_placeholder_text(R.SYNTAX_HELP)
        grid.attach(self.query_entry, 1, 0, 1, 1)

        # Root page
        root_page_label = Gtk.Label(label=R.ROOT_PAGE, halign=Gtk.Align.START)
        self.root_page_entry = Gtk.Entry()
        self.root_page_entry.set_placeholder_text(R.ROOT_PLACEHOLDER)
        self.root_page_entry.set_hexpand(True)
        grid.attach(root_page_label, 0, 1, 1, 1)
        grid.attach(self.root_page_entry, 1, 1, 1, 1)

        self.current_page_cb = Gtk.CheckButton(
            label=R.ROOT_CURRENT, halign=Gtk.Align.START
        )
        grid.attach(self.current_page_cb, 1, 2, 1, 1)

        # Bullets
        bullets_label = Gtk.Label(label=R.BULLETS, halign=Gtk.Align.START)
        grid.attach(bullets_label, 0, 3, 1, 1)

        self.bullets_combo = Gtk.ComboBoxText()
        self.bullets_combo.set_hexpand(True)
        self.bullets_combo.append_text(R.UNORDERED_LIST)
        self.bullets_combo.append_text(R.TASK_LIST)

        self.bullets_combo.props.active = 0
        grid.attach(self.bullets_combo, 1, 3, 1, 1)

        # Sort
        sort_lbl = Gtk.Label(label="Sort by:", halign=Gtk.Align.START)
        grid.attach(sort_lbl, 0, 4, 1, 1)
        self.sort_by_combo = Gtk.ComboBoxText()
        self.sort_by_combo.append_text(R.SCORE)
        self.sort_by_combo.append_text(R.ALPHABETICALLY)
        self.sort_by_combo.set_hexpand(True)
        grid.attach(self.sort_by_combo, 1, 4, 1, 1)

        # Mark entries
        mark_label = Gtk.Label(label=R.HIGHLIGHT, halign=Gtk.Align.START)
        self.mark_entry = Gtk.Entry()
        self.mark_entry.set_placeholder_text(R.MARK)
        self.mark_entry.set_hexpand(True)
        grid.attach(mark_label, 0, 5, 1, 1)
        grid.attach(self.mark_entry, 1, 5, 1, 1)

        # Checkboxes
        self.headers_cb = Gtk.CheckButton(
            label=R.INDIVIDUAL_HEADERS, halign=Gtk.Align.START
        )
        grid.attach(self.headers_cb, 0, 6, 2, 1)

        self.strike_cb = Gtk.CheckButton(
            label=R.STRIKE,
            halign=Gtk.Align.START,
        )
        grid.attach(self.strike_cb, 0, 7, 2, 1)

        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_column_spacing(6)
        grid.set_row_spacing(12)
        grid.set_margin_top(12)
        # grid.set_margin_bottom(50)

        return grid

    def set_query(self, query: Query | None):
        if query is None:
            self.query_enabled_cb.props.active = False
            return

        self.query_entry.props.text = query.get_core_part()
        self.root_page_entry.props.text = (
            query.section if query.section is not None else ""
        )
        self.bullets_combo.props.active = {"ul": 0, "cbl": 1}[query.list]
        self.mark_entry.props.text = (
            query.mark_tag if query.mark_tag is not None else ""
        )
        self.query_enabled_cb.props.active = True

    def get_query(self, current_page: str) -> Query | None:
        if not self.query_enabled_cb.props.active:
            return None

        query = Query.from_str(self.query_entry.props.text, current_page)
        if not query:
            return None
        section = self.root_page_entry.props.text
        if self.current_page_cb.props.active:
            section = "this"
        query.section = section.strip() if section is not None else None

        query.list = ["ul", "cbl"][self.bullets_combo.props.active]
        query.mark_tag = (
            self.mark_entry.props.text.strip()
            if self.mark_entry.props.text is not None
            else None
        )

        return query


class AddCollDlg(Dialog, QueryDlgMixin):
    def __init__(self, pageview) -> None:
        self.pageview = pageview
        Dialog.__init__(
            self,
            pageview,
            R.ADDCOLLDLG_TITLE,
            button=R.ADD,
            use_default_button=True,
            help="Plugins:Collections#auto-generation",
        )
        tabs = Gtk.Notebook()
        self.vbox.pack_start(tabs, True, True, 0)

        tab1 = self._setup_general_tab()
        tab1_label = Gtk.Label(label=R.GENERAL)
        tab1_label.set_margin_start(12)
        tab1_label.set_margin_end(12)
        tabs.append_page(tab1, tab1_label)

        self.tab2 = self._setup_query_tab()
        tab2_label = Gtk.Label(label=R.QUERY)
        tab2_label.set_margin_start(12)
        tab2_label.set_margin_end(12)
        tabs.append_page(self.tab2, tab2_label)

        self.vbox.set_spacing(6)
        self.vbox.set_margin_start(12)
        self.vbox.set_margin_end(12)

        GLib.idle_add(lambda: self.tab2.hide())

    def _setup_general_tab(self):
        tab = Gtk.VBox(spacing=6)
        label = Gtk.Label(label=R.SELECT_PAGE, halign=Gtk.Align.START)
        tab.pack_start(label, False, False, 0)

        self.href_entry = PageEntry(self.pageview.notebook)
        self.href_entry.props.text = self.pageview.page.name
        tab.pack_start(self.href_entry, False, False, 0)

        self.query_enabled_cb = Gtk.CheckButton(label=R.ENABLE_AUTOGEN)
        tab.pack_start(self.query_enabled_cb, False, False, 0)
        self.query_enabled_cb.connect("toggled", self.on_enable_autogen)

        tab.set_margin_top(12)
        tab.set_margin_bottom(12)
        tab.set_margin_start(12)
        tab.set_margin_end(12)
        return tab

    def on_enable_autogen(self, sender):
        if sender.get_active():
            self.tab2.show()
        else:
            self.tab2.hide()

    def _get_heading(self, page, anchor) -> str:
        buffer = Misc.get_buffer(page, self.pageview.notebook)
        iter_from = buffer.find_anchor(anchor)
        iter_from.set_line_offset(0)
        iter_to = iter_from.copy()
        iter_to.forward_to_line_end()
        return iter_from.get_text(iter_to)

    def do_response_ok(self) -> bool:
        href = HRef.new_from_wiki_link(self.href_entry.props.text)
        page = self.pageview.notebook.get_page(Path(href.names))
        if not page.exists():
            self.result = None
            return False

        title = (
            page.get_title()
            if href.anchor is None
            else self._get_heading(page, href.anchor)
        )
        query = self.get_query(current_page=page.name)
        self.result = Collection(
            id=-1,
            title=title,
            href=href.to_wiki_link(),
            query=(str(query) if query is not None else None),
        )

        return True


class EditCollDlg(Dialog, QueryDlgMixin):
    def __init__(self, parent, col: Collection) -> None:
        Dialog.__init__(
            self,
            parent,
            R.EDIT_COLLECTION_2.format(col=col.title),
            button=R.UPDATE,
            use_default_button=True,
        )
        self.col = col
        tabs = Gtk.Notebook()
        self.vbox.pack_start(tabs, True, True, 0)

        tab1 = self._setup_general_tab()
        tab1_label = Gtk.Label(label=R.GENERAL)
        tab1_label.set_margin_start(12)
        tab1_label.set_margin_end(12)
        tabs.append_page(tab1, tab1_label)

        self.tab2 = self._setup_query_tab()
        self.set_query(Query.from_str(query=col.query, current_page=col.href))

        tab2_label = Gtk.Label(label=R.QUERY)
        tab2_label.set_margin_start(12)
        tab2_label.set_margin_end(12)
        tabs.append_page(self.tab2, tab2_label)

        self.vbox.set_spacing(6)
        self.vbox.set_margin_start(12)
        self.vbox.set_margin_end(12)

        self.show_all()
        GLib.idle_add(
            lambda: self.tab2.show() if self.col.query is not None else self.tab2.hide()
        )

    def _setup_general_tab(self) -> Gtk.VBox:
        tab = Gtk.VBox(spacing=6)

        label = Gtk.Label(label=R.NEW_NAME, halign=Gtk.Align.START)
        tab.pack_start(label, False, False, 0)

        self.entry = InputEntry(
            allow_empty=False,
            show_empty_invalid=True,
        )
        self.entry.set_text(self.col.title)
        tab.pack_start(self.entry, False, False, 0)

        self.query_enabled_cb = Gtk.CheckButton(label=R.ENABLE_AUTOGEN)
        tab.pack_start(self.query_enabled_cb, False, False, 0)
        self.query_enabled_cb.props.active = self.col.query is not None
        self.query_enabled_cb.connect("toggled", self.on_enable_autogen)

        tab.set_margin_top(12)
        tab.set_margin_bottom(12)
        tab.set_margin_start(12)
        tab.set_margin_end(12)

        return tab

    def on_enable_autogen(self, sender):
        if sender.get_active():
            self.tab2.show()
        else:
            self.tab2.hide()

    def do_response_ok(self) -> bool:
        title = self.entry.get_text().strip()
        if not title:
            self.result = None
            return False

        query = self.get_query(current_page=self.col.href)
        self.result = Collection(
            id=self.col.id,
            title=title,
            href=self.col.href,
            query=str(query) if query is not None else None,
        )
        return True
