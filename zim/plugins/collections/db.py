from __future__ import annotations

import collections
from typing import Sequence, Iterable, List
from zim.notebook import HRef
from zim.plugins.collections import Collection
from zim.plugins.collections.styling import StylingData
from gi.repository import Gtk, Gdk, GObject  # type: ignore


class ColDB(GObject.GObject):
    __gsignals__ = {"changed": (GObject.SIGNAL_RUN_FIRST, None, ())}
    _idx_collections: List[Collection]

    CREATE_TABLE_SQL = """CREATE TABLE IF NOT EXISTS "collections" (
	"id"	INTEGER NOT NULL UNIQUE,
	"title"	TEXT NOT NULL,
	"href"	TEXT NOT NULL,
	"query" TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
    CREATE TABLE IF NOT EXISTS "styling" (
        "id"	INTEGER NOT NULL UNIQUE,
        "tag"	TEXT NOT NULL UNIQUE,
        "color"	TEXT NOT NULL,
        PRIMARY KEY("id" AUTOINCREMENT)
    );
"""

    def __init__(self, db) -> None:
        GObject.GObject.__init__(self)
        self._idx_coll_names: frozenset[str] | None = None
        self._idx_coll_hrefs: frozenset[str] | None = None
        self._idx_coll_pages: dict[str, list[Collection]] | None = None
        self.db = db
        self.db.executescript(ColDB.CREATE_TABLE_SQL)
        self.invalidate()

    def all_collections(self) -> Iterable[Collection]:
        return self._idx_collections

    def get_collection_by_href(self, href) -> Collection:
        return next(filter(lambda c: c.href == href, self.all_collections()))

    def is_existing_coll_name(self, c: str) -> bool:
        return (
            len(c) == 0
            or self._idx_coll_names is not None
            and c in self._idx_coll_names
        )

    def is_existing_coll_href(self, href: str) -> bool:
        return (
            len(href) != 0
            and self._idx_coll_hrefs is not None
            and href in self._idx_coll_hrefs
        )

    def add_collections(self, cols: Sequence[Collection]) -> None:
        self.db.executemany(
            "INSERT  INTO collections(title, href, query) VALUES (:title, :href, :query)",
            (
                {"title": col.title, "href": col.href, "query": col.query}
                for col in cols
            ),
        )
        self.db.commit()
        self.invalidate()

    def rm_collection(self, col_id: int) -> None:
        self.db.execute("DELETE FROM collections WHERE id = :id", {"id": col_id})
        self.db.commit()
        self.invalidate()

    def update_collection(self, col: Collection, new_href: str) -> None:
        self.db.execute(
            "UPDATE collections SET title=:title, href=:href, query=:query WHERE id=:id",
            {"id": col.id, "title": col.title, "href": new_href, "query": col.query},
        )
        self.db.commit()
        self.invalidate()

    def invalidate(self):
        self._idx_collections = [
            Collection(*entry)
            for entry in self.db.execute(
                'SELECT id, title, href, query FROM "collections"'
            )
        ]

        assert self._idx_collections is not None
        self._idx_coll_names = frozenset(c.title for c in self._idx_collections)
        self._idx_coll_hrefs = frozenset(c.href for c in self._idx_collections)

        self._idx_coll_pages = collections.defaultdict(list)
        for c in self._idx_collections:
            page = HRef.new_from_wiki_link(c.href).names
            self._idx_coll_pages[page].append(c)

        self.emit("changed")

    def get_hubs_for_page(self, page: str) -> list[Collection]:
        """
        Get hubs located on this page
        """
        if self._idx_coll_pages is None or page not in self._idx_coll_pages:
            return []
        return self._idx_coll_pages[page]

    def save_styling(self, data: StylingData):
        tags = sorted(data.order_dict, key=lambda k: data.order_dict[k])
        db_data = (
            {"tag": tag, "color": data.clr_dict[tag].to_string()} for tag in tags
        )
        self.db.execute("DELETE FROM styling")
        self.db.executemany(
            "INSERT INTO styling(tag, color) VALUES(:tag, :color)", db_data
        )
        self.db.commit()

    def load_styling(self) -> StylingData:
        result = StylingData()
        # sorted(data.)
        db_data = list(self.db.execute("SELECT tag, color FROM styling ORDER BY id"))
        result.order_dict = {tag: id for id, (tag, _) in enumerate(db_data)}

        for tag, clr_str in db_data:
            color = Gdk.RGBA()
            color.parse(clr_str)
            result.clr_dict[tag] = color

        return result
