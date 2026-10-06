import collections
import typing
from tokenize import single_quoted

from gi.repository import Gtk  # type: ignore
from zim.formats import (
    ParseTree,
    FORMATTEDTEXT,
    END,
    BULLETLIST,
    NUMBEREDLIST,
    UNCHECKED_BOX,
    BULLET,
    LISTITEM,
    LINK,
    TEXT,
    MARK,
)

from zim.notebook import (
    HRef,
    IndexNotFoundError,
    LINK_DIR_BACKWARD,
    LINK_DIR_FORWARD,
    Path,
)

from zim.plugins.collections import Misc
from zim.plugins.collections.common import Query, Collection

# {hdr-href: (hdr-href, hdr-title, {tags}, {urls})}
HubT: typing.TypeAlias = dict[
    str, typing.Tuple[str, str, typing.AbstractSet[str], typing.AbstractSet[str]]
]


class Autogen:
    def __init__(self, coll: Collection, pageview):
        self.coll = coll
        self.query = Query.from_str(coll.query, pageview.page.name)
        self.hub: HubT = {}
        self.existing_entries: set[str] = set()
        self.notebook = pageview.notebook
        self.pageview = pageview

    def run(self) -> None:
        if self.query is None:
            return

        self.existing_entries = set(
            entry.href
            for entry in Misc.parse_section_links(self.coll.href, self.notebook)
        )
        self._search()
        output = self._render()
        if not output:
            return
        buffer = self.pageview.page.get_textbuffer()
        insertion_point = self._guess_insertion_point()
        buffer.insert_parsetree(insertion_point, output)

    def _search(self) -> None:
        assert self.query is not None
        pages_visited = set()

        if self.query.linksFrom is None:
            tags_all = self.query.requiredTags | self.query.optTags
            for tag in tags_all:
                try:
                    for page in self.notebook.tags.list_pages(tag):
                        page = self.notebook.get_page(page)
                        if page.name in pages_visited:
                            continue
                        self.hub.update(Misc.parse_page_structure(page, self.notebook))
                        pages_visited.add(page.name)
                except IndexNotFoundError:
                    pass

            if self.query.linksTo is not None:
                href_to = HRef.new_from_wiki_link(self.query.linksTo)
                path_to = self.notebook.pages.resolve_link(page, href_to)
                for page in self.notebook.links.list_links(path_to, LINK_DIR_BACKWARD):
                    page = self.notebook.get_page(page.source)
                    if page.name in pages_visited:
                        continue
                    self.hub.update(Misc.parse_page_structure(page, self.notebook))
                    pages_visited.add(page.name)

        else:  # self.query.linksFrom is not None
            href_from = HRef.new_from_wiki_link(self.query.linksFrom)
            hub_path = Path(self.coll.href)
            path_from = self.notebook.pages.resolve_link(hub_path, href_from)
            for link in self.notebook.links.list_links(path_from, LINK_DIR_FORWARD):
                page = self.notebook.get_page(link.target)
                if page.name in pages_visited:
                    continue
                pages_visited.add(page.name)
                self.hub.update(Misc.parse_page_structure(page, self.notebook))

        self.hub = {
            href: entry
            for href, entry in self.hub.items()
            if self.query.requiredTags.issubset(entry[2])
            and (len(self.query.optTags) == 0 or len(entry[2] & self.query.optTags) > 0)
            and (len(entry[2] & self.query.excludeTags) == 0)
            and href not in self.existing_entries
            and (self.query.section is None or href.startswith(self.query.section))
            and (self.query.linksTo is None or self.query.linksTo in entry[3])
        }

    def _render(self) -> ParseTree | None:
        assert self.query is not None

        tokens = []
        if len(self.hub) > 0:
            list_tag = BULLETLIST if self.query.list == "cbl" else self.query.list
            list_bullet = {
                BULLETLIST: BULLET,
                NUMBEREDLIST: None,
                "cbl": UNCHECKED_BOX,
            }[self.query.list]

            for item in self.hub.values():
                single_entry_tokens = [
                    (
                        LISTITEM,
                        {"bullet": list_bullet} if list_bullet is not None else {},
                    ),
                    (LINK, {"href": item[0]}),
                    (TEXT, item[1]),
                    (END, "link"),
                    (END, "li"),
                ]

                if self.query.mark_tag is not None and self.query.mark_tag in item[2]:
                    single_entry_tokens = (
                        [(MARK, {})] + single_entry_tokens + [(END, MARK)]
                    )
                tokens.extend(single_entry_tokens)

            tokens = (
                [(list_tag, {"indent": 0})] + tokens + [(END, list_tag), (TEXT, "\n")]
            )
            tokens = [(FORMATTEDTEXT, None)] + tokens + [(END, FORMATTEDTEXT)]
        return ParseTree.new_from_tokens(tokens) if tokens else None

    def _guess_insertion_point(self):
        """
        Finds an appropriate insertion point in the buffer.

        Inserts at the first blank line, before the next heading, or before any list items.
        Returns a text iterator positioned at the chosen insertion point.
        """

        _is_term_tag = lambda tag: hasattr(tag, "zim_tag") and (
            tag.zim_tag == "h" or tag.zim_tag == "li"
        )
        buffer = self.pageview.page.get_textbuffer()
        href = HRef.new_from_wiki_link(self.coll.href)
        section_start_it = (
            buffer.find_anchor(href.anchor)
            if href.anchor is not None
            else buffer.get_start_iter()
        )
        ok = True
        while ok:
            ok = section_start_it.forward_line()
            line_end_it = section_start_it.copy()
            line_end_it.forward_to_line_end()
            line = section_start_it.get_text(line_end_it)
            ok &= bool(line) and line[0] != "\n"

            ok &= not any(filter(_is_term_tag, section_start_it.get_tags()))
        return section_start_it
