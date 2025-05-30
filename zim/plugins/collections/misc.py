import typing
from zim.formats import HEADING, heading_to_anchor, TAG, LINK, TokenListElement
from zim.gui.pageview import TextBuffer
from zim.gui.widgets import to_utf8_normalized_casefolded
from zim.notebook import HRef, HREF_REL_FLOATING, Page, Path
from zim.parse import tokenlist
from zim.parse.links import link_type
from zim.parse.tokenlist import tokens_to_text, collect_until_end_token
from zim.plugins.collections.common import CollectionNote

# {hdr_id: (hdr_id, hdr_title, {tags}, {urls})}
PageStructureT: typing.TypeAlias = dict[str, typing.Tuple[str, str, set[str], set[str]]]


class Misc:
    @staticmethod
    def canonical_href(link: str, nb, page: Path) -> str:
        href = HRef.new_from_wiki_link(link)
        href.names = nb.pages.resolve_link(page, href).name
        href.rel = HREF_REL_FLOATING
        return href.to_wiki_link()

    @staticmethod
    def get_next_heading(start_it):
        _is_heading_tag = lambda tag: hasattr(tag, "zim_tag") and tag.zim_tag == "h"
        it = start_it.copy()
        it.set_line_offset(0)

        ok = True
        while ok and not any(filter(_is_heading_tag, it.get_tags())):
            ok = it.forward_line()

        return it

    @staticmethod
    def get_buffer(page, notebook):
        buffer = page.get_textbuffer()
        if buffer is None:
            tree = page.get_parsetree()
            buffer = TextBuffer(notebook, page, parsetree=tree)
        return buffer

    @staticmethod
    def rename_heading(page, anchor, new_title):
        tree = page.get_parsetree()
        new_title = new_title.strip() + "\n"
        for e in tree._etree.iter(HEADING):
            if heading_to_anchor(e.text) == anchor:
                e.text = new_title
        page.set_parsetree(tree)

    @staticmethod
    def get_heading_link(page, h):
        anchor = heading_to_anchor(h)
        return HRef(HREF_REL_FLOATING, page.name, anchor).to_wiki_link()

    @staticmethod
    def parse_page_structure(page: Page, nb) -> PageStructureT:
        assert page.hascontent
        tree = page.get_parsetree()
        tokens = tree.iter_tokens()
        structure: PageStructureT = {}
        hdr = page.name
        for t in tokens:
            if t[0] == HEADING:
                h = tokens_to_text(collect_until_end_token(tokens, HEADING)).strip()
                hdr = (
                    Misc.get_heading_link(page, h) if t[1]["level"] != 1 else page.name
                )
                structure[hdr] = (hdr, h, set(), set())

            elif t[0] == TAG:
                tag = t[1]["name"]
                if hdr:
                    structure[hdr][2].add(tag)

            elif t[0] == LINK:
                structure[hdr][3].add(Misc.canonical_href(t[1]["href"], nb, page))

        return structure

    @staticmethod
    def get_heading_info(it) -> tuple[str | None, str | None, int]:
        is_heading_tag = lambda tag: hasattr(tag, "zim_tag") and tag.zim_tag == "h"
        it2 = it.copy()
        it2.set_line_offset(0)
        tag = next(filter(is_heading_tag, it2.get_tags()), None)
        if tag is None:
            return None, None, 0

        it2_end = it2.copy()
        it2_end.forward_to_line_end()
        text = it2.get_text(it2_end).strip()
        anchor = heading_to_anchor(text) if len(text) > 0 else None
        level = tag.zim_attrib["level"]

        return anchor, text, level

    @staticmethod
    def parse_section_links(section_href: str, nb) -> typing.Iterable[CollectionNote]:
        entries_seen = set()

        def not_seen_before(href: str):
            if href in entries_seen:
                return False
            entries_seen.add(href)
            return True

        href = HRef.new_from_wiki_link(section_href)
        page = nb.get_page(Path(href.names))
        buffer = Misc.get_buffer(page, nb)
        section_start_it = (
            buffer.find_anchor(href.anchor)
            if href.anchor is not None
            else buffer.get_start_iter()
        )
        if section_start_it is None:
            return []
        section_start_it.forward_line()
        section_end_it = Misc.get_next_heading(section_start_it)
        section_tree = buffer.get_parsetree(bounds=(section_start_it, section_end_it))

        return [
            CollectionNote(
                title="".join(link_el.itertext()),
                href=href_canonical,
            )
            for link_el in section_tree._etree.iter(LINK)
            if link_type(href_ := link_el.attrib.get("href")) == "page"
            and not_seen_before(href_canonical := Misc.canonical_href(href_, nb, page))
        ]

    @staticmethod
    def get_href_ns(href: str) -> str:
        href_ = HRef.new_from_wiki_link(href)
        if href_.anchor:
            return href_.names
        return Path(href_.names).namespace
