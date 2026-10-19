import colorsys
from typing import Sequence

from gi.repository import Gtk, Gdk, GObject  # type: ignore

from zim.gui.widgets import widget_set_css
from zim.plugins.collections import Collection
from zim.plugins.collections.styling import StylingData
from zim.signals import ConnectorMixin


def highlight(gdk_rgba: Gdk.RGBA) -> Gdk.RGBA:
    factor = 1.2
    h, l, s = colorsys.rgb_to_hls(gdk_rgba.red, gdk_rgba.green, gdk_rgba.blue)
    l = min(l * factor, 1.0)
    return Gdk.RGBA(*colorsys.hls_to_rgb(h, l, s))


class FloatPageBar(Gtk.VBox, ConnectorMixin):
    MARGIN_V = 16
    MARGIN_H = 12

    __gsignals__ = {"goto-collection": (GObject.SIGNAL_RUN_FIRST, None, (str,))}

    def __init__(self, pageview) -> None:
        GObject.GObject.__init__(self)

        self.content = None
        self.pageview = pageview
        self._handler_dict: dict[object, Collection] = {}

        widget_set_css(
            self,
            "collections-page-bar",
            "",  # "background-color: blue; border: 1px solid @fg_color",
        )
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.END)
        self.set_margin_end(self.MARGIN_H)
        self.set_margin_bottom(self.MARGIN_V)

    def setup(
        self,
        colls: Sequence[Collection],
        hubs: Sequence[Collection],
        styling: StylingData,
    ) -> None:
        if self.content is not None:
            self.content.destroy()

        self._handler_dict = {}
        self.content = Gtk.FlowBox()
        assert self.content is not None
        self.pack_start(self.content, False, False, 0)

        nb = self.pageview.notebook
        colls_combined = set(colls) | set(hubs)
        for col in colls_combined:
            self._add_tag(
                col,
                css_class="collection-tag",
                icon="emblem-favorite",
                handler=self.goto_collection,
                style=styling.get_collection_style(col, nb),
            )

        self.content.set_valign(Gtk.Align.START)
        self.content.set_min_children_per_line(2)
        self.content.set_max_children_per_line(5)
        self.content.set_selection_mode(Gtk.SelectionMode.NONE)

        self.content.show_all()

    def _add_tag(
        self, col: Collection, css_class, icon, handler, style: Gdk.RGBA
    ) -> None:
        assert self.content is not None

        tag = Gtk.HBox(spacing=6)
        tag.set_name(css_class)
        img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
        tag.pack_start(img, False, False, 0)
        lbl = Gtk.Label(label=col.title)
        tag.pack_start(lbl, False, False, 0)

        event_box = Gtk.EventBox()
        event_box.connect("button-press-event", handler)

        def on_enter(sender, ev):
            sender.get_style_context().add_class("hover")

        def on_leave(sender, ev):
            sender.get_style_context().remove_class("hover"),

        event_box.connect("enter-notify-event", on_enter)
        event_box.connect("leave-notify-event", on_leave)
        event_box.add(tag)
        self._handler_dict[event_box] = col
        self.content.add(event_box)

        tag.get_style_context().add_provider(
            self.get_tag_css_style(style),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def get_tag_css_style(self, clr_rgba: Gdk.RGBA | None):
        if not clr_rgba:
            clr_rgba = Gdk.RGBA(0.5, 0.5, 0.5)

        clr = clr_rgba.to_string()
        clr_hi = highlight(clr_rgba).to_string()

        style = Gtk.CssProvider()
        style.load_from_data(
            f"""
        #collection-tag{{
            background-color: {clr};
        }}
        
        .hover>#collection-tag{{
            background-color: {clr_hi};
        }}
        """
        )
        return style

    def goto_hub(self, sender, ev):
        try:
            c = self._handler_dict[sender]
            self.pageview.activate_link(c.href)

        except KeyError:
            pass

    def goto_collection(self, sender, ev) -> None:
        try:
            col = self._handler_dict[sender]
            self.emit("goto-collection", col.href)
        except KeyError:
            pass
