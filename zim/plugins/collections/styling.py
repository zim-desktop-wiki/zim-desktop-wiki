from __future__ import annotations

from typing import Iterable

from gi.repository import Gtk, Gdk  # type: ignore

from zim.gui.widgets import Dialog
from zim.notebook import Notebook, HRef, Path, IndexNotFoundError
from zim.plugins.collections import Misc
from zim.plugins.collections.common import Collection, R


class StylingData:
    def __init__(self):
        self.order_dict: dict[str, int] = {}
        self.clr_dict: dict[str, Gdk.RGBA] = {}

    def to_model(self):
        model = Gtk.ListStore(Gdk.RGBA, str)  # color, tag

        if not self.order_dict:
            self._default_populate(model)
            return model

        tags = sorted(self.order_dict.keys(), key=lambda t: self.order_dict[t])
        for t in tags:
            model.append([self.clr_dict[t], t])

        return model

    @staticmethod
    def from_model(model) -> StylingData:
        self = StylingData()
        for rank, row in enumerate(model):
            clr, tag = row
            self.order_dict[tag] = rank
            self.clr_dict[tag] = clr
        return self

    @staticmethod
    def _default_populate(model):
        colors = [
            (0.8, 0.1, 0.1),  # Red
            (0.8, 0.1, 0.1),  # Red
            (0.8, 0.8, 0.1),  # Yellow
            (0.1, 0.8, 0.1),  # Green
            (0.1, 0.1, 0.8),  # Blue
        ]
        strings = [
            R.TagDefPin,
            R.TagDefWork,
            R.TagDefImportant,
            R.TagDefIdea,
            R.TagDefProject,
        ]

        for color, string in zip(colors, strings):
            rgba = Gdk.RGBA(color[0], color[1], color[2], 1.0)
            model.append([rgba, string])

    def get_style_for_tags(self, tags: Iterable[str]) -> Gdk.RGBA | None:
        """
        Select the tag with the highest priority (lowest order value).
        Tags not present in order_dict are treated as lowest priority.
        """
        size = len(self.order_dict)
        if not tags or size == 0:
            return None

        tag = min(
            tags,
            key=lambda tag: (self.order_dict[tag] if tag in self.order_dict else size),
        )
        return self.clr_dict[tag] if tag in self.clr_dict else None

    def get_collection_style(self, c: Collection, nb: Notebook) -> Gdk.RGBA | None:
        href = HRef.new_from_wiki_link(c.href)
        if not href.anchor:
            try:
                tags = list(tag.name for tag in nb.tags.list_tags(Path(href.names)))
                return self.get_style_for_tags(tags)
            except IndexNotFoundError:
                return None

        page = nb.get_page(Path(href.names))
        structure = Misc.parse_page_structure(page, nb)
        if c.href not in structure:
            return None

        return self.get_style_for_tags(structure[c.href][2])


class AddTagDlg(Dialog):
    def __init__(self, parent):
        Dialog.__init__(self, parent, R.ADD_TAG_DLG, button=R.ADD)

        layout = Gtk.HBox(spacing=12)
        self.color_but = Gtk.ColorButton()
        layout.pack_start(self.color_but, False, False, 0)
        self.tags_entry = Gtk.Entry()
        self.tags_entry.set_placeholder_text(R.ADD_TAG_PLACEHOLDER)
        layout.pack_start(self.tags_entry, True, True, 0)
        self.vbox.add(layout)
        self.vbox.props.spacing = 24

    def do_response_ok(self) -> bool:
        tags_text = self.tags_entry.get_text()
        color = self.color_but.get_rgba()
        tags = [tag.strip() for tag in tags_text.split(",") if len(tag.strip()) > 0]
        if not tags:
            self.result = None
            return False
        self.result = (tags, color)
        return True


class StylingDlg(Dialog):
    def __init__(self, parent, data: StylingData):
        Dialog.__init__(
            self, parent, R.TAG_STYLING_TITLE, help="Plugins:Collections#styling"
        )

        self.model = data.to_model()

        self.treeview = Gtk.TreeView(model=self.model)
        self.treeview.props.reorderable = True

        color_renderer = Gtk.CellRendererText()
        color_renderer.props.text = R.SLAB_PIN
        column = Gtk.TreeViewColumn(" ", color_renderer, foreground_rgba=0)
        column.set_clickable(True)
        column.set_resizable(True)
        self.treeview.append_column(column)

        text_renderer = Gtk.CellRendererText()
        text_renderer.props.editable = True
        text_renderer.connect("edited", self.on_tag_edited)
        text_column = Gtk.TreeViewColumn(R.TAG, text_renderer, text=1)
        self.treeview.append_column(text_column)

        self.treeview.connect("row-activated", self.on_select_color_clicked)

        bt_add = Gtk.ToolButton()
        bt_add.set_icon_name("list-add-symbolic")
        bt_add.set_tooltip_text(R.ADD_TAG)
        bt_add.connect("clicked", self.on_add_tag_clicked)

        bt_rm = Gtk.ToolButton()
        bt_rm.set_icon_name("list-remove-symbolic")
        bt_rm.set_tooltip_text(R.REMOVE_TAG)
        bt_rm.connect("clicked", self.on_rm_tag_clicked)

        toolbar = Gtk.Toolbar()
        toolbar.set_icon_size(Gtk.IconSize.SMALL_TOOLBAR)

        toolbar.add(bt_add)
        toolbar.add(bt_rm)

        self.vbox.pack_start(toolbar, False, False, 0)
        self.vbox.pack_start(self.treeview, True, True, 0)

    def on_tag_edited(self, obj, path, new_text):
        it = self.model.get_iter(path)
        self.model[it][1] = new_text

    def on_select_color_clicked(self, treeview, path, column):
        iter_ = self.model.get_iter(path)

        # Open color chooser dialog
        color = self.model.get_value(iter_, 0)
        color_chooser = Gtk.ColorChooserDialog(R.ASSIGN_COLOR_FOR_TAG, self)
        color_chooser.set_rgba(color)

        response = color_chooser.run()
        if response == Gtk.ResponseType.OK:
            new_color = color_chooser.get_rgba()
            self.model.set_value(iter_, 0, new_color)
        color_chooser.destroy()

    def on_add_tag_clicked(self, widget):
        dlg = AddTagDlg(self)
        response = dlg.run()
        if response is None:
            return
        tags, color = response

        for tag in tags:
            self.model.append([color, tag])

    def on_rm_tag_clicked(self, widget):
        selection = self.treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            model.remove(tree_iter)

    def do_response_ok(self) -> bool:
        self.result = StylingData.from_model(self.model)
        return True
