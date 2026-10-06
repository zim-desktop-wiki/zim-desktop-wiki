from __future__ import annotations

import re
import typing
from typing import NamedTuple

from gi.repository import Gtk, Gdk, GLib, GObject  # type: ignore


class R:
    DBG_REFRESH_COLLECTIONS = "ReIndex collections"
    REMOVE_TAG = "Remove Tags"
    ADD_TAG = "Add Tags"
    RMCOLDLG_MSG = "Are you sure you want to delete {title}?\nNote: This action does not actually delete the pages in the collection."
    RMCOLDLG_SUBTITLE = "Confirm Deletion"
    COLLECTION_REMOVED = "{col} Removed"
    COLLECTION_ADDED = "{col} Added"
    PREF_ARCHIVE_COLOR = "Archive color"
    PREF_POSITION = "Position in the window"
    PREF_HUB_TAGS = "Hub Tags"
    PREF_ARCHIVE_TAGS = "Archive Tags"

    NOCOLS = "No collections yet.\nLet's make a first one"
    EMPTYCOL = "Collection looks empty.\n Add the first page"
    SELECTCOL = "No collection is selected.\nSelect any collection"

    QUERY = "Autogeneration"
    GENERAL = "General"
    ENABLE_AUTOGEN = "Enable Autogeneration"
    FIND_COLLECTION_PLACEHOLDER = "Find Collection..."
    ADD = "Add"
    ADD_TAG_DLG = "Add Tag(s)"
    ADDCOLLDLG_TITLE = "New Collection"

    TAG_STYLING_TITLE = "Styling"
    ADD_TAG_PLACEHOLDER = "E.g.: relax, exciting, food, tomorrow"
    TagDefProject = "project"
    TagDefIdea = "idea"
    TagDefImportant = "important"
    TagDefWork = "work"
    TagDefPin = "pin"

    ASSIGN_COLOR_FOR_TAG = "Assign color for tag"
    TAG = "Tag"
    SLAB_PIN = "🖈"
    SLAB_UP = "⮝"
    SLAB_DOWN = "⮟"
    TITLE = "Configure Tags"
    CHOOSE_COLOR = "Choose color:"
    ENTER_TEXT = "Enter text:"
    ADD_STRING = "Add Tag"

    NEW_NAME = "New name:"

    UPDATE = "Update"
    EDIT_COLLECTION = "Edit Collection"
    EDIT_COLLECTION_2 = "Edit {col}"
    REMOVE_COLLECTION = "Remove Collection"
    ADD_A_NEW_COLLECTION = "Add New Collection"
    GO_TO_HUB = "Go to Hub"

    # Autogen
    STRIKE = "Strike Through Existing Items that aren't in Search Results"
    INDIVIDUAL_HEADERS = "Include individual headers"
    MARK = "Marks entries with a specified tag"
    HIGHLIGHT = "Highlight:"
    ALPHABETICALLY = "Alphabetically"
    SCORE = "Score"
    TASK_LIST = "Task list"
    UNORDERED_LIST = "Unordered list"
    BULLETS = "Bullets:"
    ROOT_CURRENT = "Current Page as Root"
    ROOT_PLACEHOLDER = "Limit Results to Specified Page and its Subpages"
    ROOT_PAGE = "Root page:"
    SYNTAX_HELP = (
        "See Help for Syntax. e.g.: +tag:project -tag:archive links:Onboarding"
    )
    AG_QUERY = "Query:"
    AG_UPDATE = "_Update"
    AG_TITLE = "Masterlist"

    RMCOLDLG_TITLE = "Collections"
    SELECT_PAGE = "Select Page or Heading to Serve as Hub for Collection:"

    MAKE_HUB = "Make Hub for {title}"
    REMOVE_COL = "Remove Collection {title}"


class CollectionNote(NamedTuple):
    title: str
    href: str

    def __eq__(self, other):
        if not isinstance(other, CollectionNote):
            return NotImplemented
        return self.href == other.href

    def __hash__(self):
        return hash(self.href)


class Collection(NamedTuple):
    id: int
    title: str
    href: str
    query: str | None


THIS = "this"
QUERY_RE = re.compile(
    r"""
    \s*(\+tag:|\-tag:|\?tag:|links:|linksto:|linksfrom:|section:|mark:)?\s*
    (
     '[^']*' |  # single quoted word
     "[^"]*" |  # double quoted word
	 \S+        # word without spaces
	)\s*
""",
    re.X | re.IGNORECASE,
)


def join(parts: typing.Iterable[str | None]) -> str:
    parts2 = [part.strip() for part in parts if part is not None]
    parts2 = [part for part in parts2 if part != ""]

    return " ".join(parts2)


class Query:
    def __init__(self):
        self.list = "ul"
        self.requiredTags = set()
        self.excludeTags = set()
        self.optTags = set()
        self.section: str | None = None
        self.linksFrom: str | None = None
        self.linksTo: str | None = None
        self.list = "ul"
        self.mark_tag: str | None = None

    @staticmethod
    def from_str(query: str | None, current_page: str) -> Query | None:
        if not query or not query.strip():
            return None

        self = Query()
        raw_query = QUERY_RE.findall(query)
        for entry in raw_query:
            cmd = entry[0][:-1] if len(entry[0]) > 0 else entry[1]
            cmd = cmd.lower()

            if cmd == "+tag":
                self.requiredTags.add(entry[1])
            elif cmd == "-tag":
                self.excludeTags.add(entry[1])
            elif cmd == "?tag":
                self.optTags.add(entry[1])
            elif cmd == "section":
                self.section = self._unescape_quoted_string(entry[1])
            elif cmd == "linksto":
                self.linksTo = self._unescape_quoted_string(entry[1])
            elif cmd == "links" or cmd == "linksfrom":
                self.linksFrom = self._unescape_quoted_string(entry[1])
            elif cmd in ["ul", "ol", "cbl"]:
                self.list = cmd
            elif cmd == "mark":
                self.mark_tag = entry[1]

        for attr in ["section", "linksFrom", "linksTo"]:
            if getattr(self, attr) == THIS:
                setattr(self, attr, current_page)
        if (
            not self.requiredTags
            and not self.optTags
            and not self.linksFrom
            and not self.linksTo
        ):
            return None

        return self

    def __repr__(self) -> str:
        core = self.get_core_part()
        section = (
            f'section:"{self.section}"'
            if self.section is not None and len(self.section) > 0
            else None
        )
        mark_tag = (
            f"mark:{self.mark_tag}"
            if self.mark_tag is not None and len(self.mark_tag) > 0
            else None
        )

        return join(
            [
                core,
                section,
                mark_tag,
                self.list,
            ]
        )

    def get_core_part(self) -> str:
        tags_required = " ".join([f"+tag:{tag}" for tag in self.requiredTags])
        tags_opt = " ".join([f"?tag:{tag}" for tag in self.optTags])
        tags_excl = " ".join([f"-tag:{tag}" for tag in self.excludeTags])

        links_from = (
            f'links:"{self.linksFrom.strip()}"' if self.linksFrom is not None else None
        )

        links_to = (
            f'linksto:"{self.linksTo.strip()}"' if self.linksTo is not None else None
        )

        return join(
            [
                tags_required,
                tags_opt,
                tags_excl,
                links_to,
                links_from,
            ]
        )

    def _unescape_quoted_string(self, string):
        """Removes quotes from a string and unescapes embedded quotes
        @returns: string
        """
        if not string:
            return string
        elif string[0] in ('"', "'") and string[-1] == string[0]:
            return string[1:-1]

        return string


class Toast(Gtk.Revealer):
    def __init__(self):
        Gtk.Revealer.__init__(self)

        self.set_reveal_child(False)
        self.set_transition_duration(300)
        self.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)

        layout = Gtk.HBox(spacing=6)
        layout.set_name("toast")
        img = Gtk.Image.new_from_icon_name("notification-symbolic", Gtk.IconSize.MENU)
        layout.pack_start(img, False, False, 0)
        self.lbl = Gtk.Label()
        layout.pack_start(self.lbl, False, False, 0)

        self.set_valign(Gtk.Align.END)
        self.set_halign(Gtk.Align.CENTER)
        layout.set_margin_bottom(20)
        self.add(layout)

    def fire(self, message):
        self.lbl.set_label(message)
        self.set_reveal_child(True)
        GLib.timeout_add(3000, self._stop)

    def _stop(self):
        self.set_reveal_child(False)
        return False  # Stop the timeout


class Notifier(typing.Protocol):
    """Protocol for objects that can display notifications to the user."""

    def notify(self, msg: str) -> None:
        """Display a notification message to the user.

        Args:
            msg: The message to display
        """
        ...
