"""Shared CRUD for the two catalogs an article links to N-to-N.

Tags and categories have the same shape (name, url) and differ only in the
label and relationship, so each module subclasses this and sets three names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from app.common.errors import AppError, NotFoundError
from app.common.forms import text
from app.database import Transaction, read, read_one, write


# Same rule as the HTML pattern in catalog/form.html: plain ASCII slug.
URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class TaxonomyItem:
    id: int
    name: str
    url: str
    article_count: int = 0


@dataclass(frozen=True)
class SaveTaxonomySchema:
    name: str
    url: str

    @classmethod
    def from_form(cls) -> "SaveTaxonomySchema":
        url = text("url", True, "URL", 80)
        if not URL_PATTERN.fullmatch(url):
            raise AppError("La URL solo puede llevar letras, números, - y _.")
        return cls(name=text("name", True, "nombre", 60), url=url.lower())


class TaxonomyService:
    label = ""          # node label, e.g. Tag
    key = ""            # id property, e.g. tag_id
    relationship = ""   # Article -> node relationship, e.g. TAGGED
    noun = ""           # Spanish name for messages

    @property
    def fields(self) -> str:
        return f"t.{self.key} AS id, t.name AS name, t.url AS url"

    def count(self) -> int:
        return read_one(f"MATCH (t:{self.label}) WHERE t.deleted_at IS NULL RETURN count(t) AS total")["total"]

    def find_all(self, limit: Optional[int] = None, offset: int = 0) -> List[TaxonomyItem]:
        """All of them (the article form needs every option), or one page with limit/offset."""
        rows = read(f"""
            MATCH (t:{self.label}) WHERE t.deleted_at IS NULL
            RETURN {self.fields},
                   COUNT {{ (a:Article)-[:{self.relationship}]->(t) WHERE a.deleted_at IS NULL }} AS article_count
            ORDER BY t.name SKIP $offset {"LIMIT $limit" if limit else ""}""", offset=offset, limit=limit)
        return [TaxonomyItem(**row) for row in rows]

    def find_used(self, limit: int = 50) -> List[TaxonomyItem]:
        """Only the ones with published articles, most used first: the feed filters."""
        rows = read(f"""
            MATCH (t:{self.label}) WHERE t.deleted_at IS NULL
            WITH t, COUNT {{ (a:Article {{status: 'PUBLISHED'}})-[:{self.relationship}]->(t) WHERE a.deleted_at IS NULL }} AS article_count
            WHERE article_count > 0
            RETURN {self.fields}, article_count ORDER BY article_count DESC, t.name LIMIT $limit""", limit=limit)
        return [TaxonomyItem(**row) for row in rows]

    def find_one(self, item_id: int) -> TaxonomyItem:
        row = read_one(f"MATCH (t:{self.label} {{{self.key}: $id}}) WHERE t.deleted_at IS NULL "
                       f"RETURN {self.fields}", id=item_id)
        if not row:
            raise NotFoundError(f"La {self.noun} no existe.")
        return TaxonomyItem(**row)

    def for_article(self, article_id: int, linked: bool) -> List[TaxonomyItem]:
        """What the article already has (linked) or could still get (not linked)."""
        negate = "" if linked else "NOT "
        rows = read(f"""
            MATCH (a:Article {{article_id: $id}}), (t:{self.label})
            WHERE t.deleted_at IS NULL AND {negate}(a)-[:{self.relationship}]->(t)
            RETURN {self.fields} ORDER BY t.name""", id=article_id)
        return [TaxonomyItem(**row) for row in rows]

    def create(self, dto: SaveTaxonomySchema) -> int:
        rows = write(f"""
            MERGE (c:Counter {{name: '{self.label}'}}) ON CREATE SET c.value = 0
            SET c.value = c.value + 1
            CREATE (t:{self.label} {{{self.key}: c.value, name: $name, url: $url}})
            RETURN t.{self.key} AS id""", name=dto.name, url=dto.url)
        return rows[0]["id"]

    def update(self, item_id: int, dto: SaveTaxonomySchema) -> None:
        write(f"""
            MATCH (t:{self.label} {{{self.key}: $id}}) WHERE t.deleted_at IS NULL
            SET t.name = $name, t.url = $url
            RETURN t.{self.key}""", not_found=f"La {self.noun} no existe.",
              id=item_id, name=dto.name, url=dto.url)

    def remove(self, item_id: int) -> None:
        """Logical delete: the node and its links stay in the graph, marked with deleted_at.

        name and url are unique, so they move to deleted_name / deleted_url to free them
        for a new tag or category.
        """
        write(f"""
            MATCH (t:{self.label} {{{self.key}: $id}}) WHERE t.deleted_at IS NULL
            SET t.deleted_at = localdatetime({{timezone: $tz}}), t.deleted_name = t.name, t.deleted_url = t.url
            REMOVE t.name, t.url
            RETURN 1 AS done""", not_found=f"La {self.noun} no existe.", id=item_id)

    def replace_links(self, tx: Transaction, article_id: int, item_ids: List[int]) -> None:
        """Inside the caller's transaction: leave the article linked to exactly item_ids.

        Raising here makes the caller's transaction roll back, article included.
        """
        # Links to deleted items are kept: they belong to the logical-delete history.
        tx.run(f"MATCH (:Article {{article_id: $id}})-[r:{self.relationship}]->(t) "
               "WHERE t.deleted_at IS NULL DELETE r", id=article_id)
        rows = tx.run(f"""
            MATCH (a:Article {{article_id: $id}})
            UNWIND $ids AS item_id
            MATCH (t:{self.label} {{{self.key}: item_id}}) WHERE t.deleted_at IS NULL
            MERGE (a)-[:{self.relationship}]->(t)
            RETURN count(t) AS linked""", id=article_id, ids=item_ids)
        if (rows[0]["linked"] if rows else 0) != len(item_ids):
            raise AppError(f"Una {self.noun} que marcaste ya no existe. No se guardó nada.")
