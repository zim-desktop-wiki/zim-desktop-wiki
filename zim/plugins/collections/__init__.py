import typing
from typing import Protocol

from gi.repository import Gtk, Gdk, GLib, Pango, GObject  # type: ignore
from zim.gui.notebookview import NotebookViewExtension
from zim.gui.widgets import LEFT_PANE, PANE_POSITIONS
from zim.notebook import (
    HRef,
    HREF_REL_FLOATING,
)
from zim.plugins import PluginClass
from zim.plugins.collections.misc import Misc
from zim.plugins.collections.autogen import Autogen
from zim.plugins.collections.common import Collection, R, Toast
from zim.plugins.collections.dlgs import RmCollConfirmDlg, AddCollDlg
from zim.plugins.collections.floatpagebar import FloatPageBar
from zim.plugins.collections.sidepane import SidePane

if typing.TYPE_CHECKING:

    def _(_: str) -> str:
        pass


class ColPlugin(PluginClass):
    plugin_info = {
        "name": _("Collections"),
        "description": _("Manages note collections"),
        "author": "pgess",
    }

    plugin_preferences = (  # type: ignore
        # key, type, label, default
        ("pane", "choice", R.PREF_POSITION, LEFT_PANE, PANE_POSITIONS),
        ("hub_tags", "string", R.PREF_HUB_TAGS, "moc"),
        ("archive_tags", "string", R.PREF_ARCHIVE_TAGS, "archive"),
        ("archive_color", "color", R.PREF_ARCHIVE_COLOR, "#A1A9B1"),
    )


class ColNotebookViewExtension(NotebookViewExtension):
    STYLE = b"""
    #toast{
        background-color: #926d2b;
        border-radius: 12px;
        color: black;
        padding: 12px 12px; 
        margin: 4px;
    }
    #collection-tag{
        border-radius: 12px;
        color: black;
        padding: 4px 8px; 
        margin: 0px;
    }
    
    .hover>#hub-tag{
        background-color: #c9963c;
    }
    #hub-tag{
        background-color: #926d2b;
        color: black;
        padding: 4px 8px; 
        margin: 0px;
    }
    """

    def __init__(self, plugin, pageview) -> None:
        NotebookViewExtension.__init__(self, plugin, pageview)

        style = Gtk.CssProvider()
        style.load_from_data(self.STYLE)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.sidepane = SidePane(pageview, plugin, notifier=self)
        # bug changing model inside handler - use deferred handling
        self.add_sidepane_widget(self.sidepane, "pane")
        self.connectto(self.pageview, "page-changed")

        self.bar = FloatPageBar(pageview)
        pageview.overlay.add_overlay(self.bar)
        self.on_page_changed(pageview, pageview.page)
        self.connectto(
            self.bar,
            "goto-collection",
            handler=lambda sender, href: self.sidepane.goto_collection(href),
        )

        self.connectto(
            pageview.textview, "populate-popup", handler=self.on_textview_populate_popup
        )
        self.pageview = pageview

        self.toast = Toast()
        pageview.overlay.add_overlay(self.toast)
        self.connectto(plugin.preferences, "changed", self.on_pref_changed)
        self.bar.show_all()

    def teardown(self):
        self.bar.destroy()
        self.disconnect_all()

    def on_pref_changed(self, sender):
        self.sidepane.on_archive_roots_changed()
        self.sidepane.on_collections_changed()
        pass

    def on_add_collection_clicked(self, sender, href) -> None:
        dlg = AddCollDlg(self.pageview)
        dlg.href_entry.set_text(href)
        collection = dlg.run()
        if collection is None:
            return
        self.sidepane.add_collection(collection)
        self.sidepane.focus()
        self.notify(R.COLLECTION_ADDED.format(col=collection.title))

    def on_rm_collection(self, sender, c: Collection):
        ok = RmCollConfirmDlg(self, c.title).run()
        if not ok:
            return

        self.sidepane.db.rm_collection(c.id)
        self.notify(R.COLLECTION_REMOVED.format(col=c.title))

    def on_textview_populate_popup(self, sender, menu):
        textview = self.pageview.textview
        pos = max(len(menu) - 4, 0)
        iter = textview._get_popup_menu_mark()
        if iter is None:
            return
        anchor, title, level = Misc.get_heading_info(iter)
        if anchor is None:
            return
        href = (
            self.pageview.page.name
            if level == 1
            else HRef(HREF_REL_FLOATING, self.pageview.page.name, anchor).to_wiki_link()
        )

        if self.sidepane.db.is_existing_coll_href(href):
            c = next(
                filter(lambda c: c.href == href, self.sidepane.db.all_collections()),
                None,
            )
            assert c is not None
            item = Gtk.MenuItem.new_with_label(R.REMOVE_COL.format(title=c.title))
            item.connect("activate", self.on_rm_collection, c)
        else:
            item = Gtk.MenuItem.new_with_label(R.MAKE_HUB.format(title=title))
            item.connect("activate", self.on_add_collection_clicked, href)

        item.show_all()
        menu.insert(item, pos)

    def on_page_changed(self, pageview, page) -> None:
        colls = self.sidepane.get_collections_for_page(page.name)
        hubs = self.sidepane.db.get_hubs_for_page(page.name)
        self.bar.setup(colls, hubs, self.sidepane.styling)

        for hub in hubs:
            if not hub.query:
                continue
            gen = Autogen(hub, pageview)
            gen.run()

    def notify(self, msg):
        self.toast.fire(msg)
