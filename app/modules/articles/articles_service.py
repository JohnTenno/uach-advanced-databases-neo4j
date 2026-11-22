from __future__ import annotations

from typing import List, Optional

from app.common.errors import AppError, ForbiddenError, NotFoundError
from app.common.image_storage import ImageStorage
from app.database import Transaction, read, read_one, transaction, write
from app.modules.articles.schemas.article_schema import Article, SaveArticleSchema
from app.modules.auth.auth_user import AuthUser
from app.modules.categories.categories_service import CategoriesService
from app.modules.tags.tags_service import TagsService

# Every read passes $me so the card knows whether the viewer already liked it.
# Logical delete: anything with deleted_at is skipped by every read.
FIELDS = """a.article_id AS article_id, a.title AS title, a.body_text AS body_text,
       a.post_date AS post_date, a.status AS status, u.user_id AS author_id,
       u.name AS author_name, u.avatar AS author_avatar,
       COUNT { (a)<-[:ON]-(c:Comment) WHERE c.deleted_at IS NULL } AS comment_count,
       [(a)-[:TAGGED]->(t) WHERE t.deleted_at IS NULL | t.name] AS tags,
       [(a)-[:IN_CATEGORY]->(c) WHERE c.deleted_at IS NULL | c.name] AS categories,
       a.image AS image, COUNT { (f:User)-[:LIKED]->(a) WHERE f.deleted_at IS NULL } AS like_count,
       EXISTS { (:User {user_id: $me})-[:LIKED]->(a) } AS liked"""


class ArticlesService:
    def __init__(self):
        self.tags, self.categories = TagsService(), CategoriesService()
        self.images = ImageStorage()

    # ---- reads -------------------------------------------------------------

    # Feed filters: a tag, a category or text in the title/body (all optional, empty = no filter).
    FEED = """MATCH (u:User)-[:WROTE]->(a:Article {status: 'PUBLISHED'})
            WHERE a.deleted_at IS NULL AND u.deleted_at IS NULL
              AND ($tag = '' OR EXISTS { (a)-[:TAGGED]->(t:Tag {name: $tag}) WHERE t.deleted_at IS NULL })
              AND ($category = '' OR EXISTS { (a)-[:IN_CATEGORY]->(c:Category {name: $category}) WHERE c.deleted_at IS NULL })
              AND ($q = '' OR toLower(a.title) CONTAINS $q OR toLower(a.body_text) CONTAINS $q)"""

    def find_published(self, user: AuthUser, limit: int = 20, offset: int = 0,
                       tag: str = "", category: str = "", q: str = "", popular: bool = False) -> List[Article]:
        """Newest first, or with popular=True the most liked first (ties: newest)."""
        order = "like_count DESC, a.post_date DESC" if popular else "a.post_date DESC, a.article_id DESC"
        rows = read(f"""{self.FEED}
            RETURN {FIELDS} ORDER BY {order}
            SKIP $offset LIMIT $limit""", me=user.id, limit=limit, offset=offset,
                    tag=tag, category=category, q=q.lower())
        return self.spread_authors([Article(**row) for row in rows])

    @staticmethod
    def spread_authors(articles: List[Article]) -> List[Article]:
        """Never two posts in a row by the same author: when the next one would repeat, the
        first upcoming post by someone else moves up. Otherwise the order is kept."""
        pending, result = list(articles), []
        while pending:
            last = result[-1].author_id if result else None
            pick = next((a for a in pending if a.author_id != last), pending[0])
            pending.remove(pick)
            result.append(pick)
        return result

    def count_published(self, tag: str = "", category: str = "", q: str = "") -> int:
        return read_one(f"{self.FEED} RETURN count(a) AS total", tag=tag, category=category, q=q.lower())["total"]

    def find_related(self, article: Article, user: AuthUser, limit: int = 4) -> List[dict]:
        """Articles that share the most tags with this one: two hops in the graph."""
        return read("""
            MATCH (a:Article {article_id: $id})-[:TAGGED]->(t:Tag)<-[:TAGGED]-(o:Article {status: 'PUBLISHED'})<-[:WROTE]-(u:User)
            WHERE o <> a AND o.deleted_at IS NULL AND t.deleted_at IS NULL AND u.deleted_at IS NULL
            WITH o, u, count(DISTINCT t) AS shared
            RETURN o.article_id AS article_id, o.title AS title, u.name AS author_name, o.image AS image, shared
            ORDER BY shared DESC, o.post_date DESC LIMIT $limit""",
                    id=article.article_id, limit=limit)

    def find_popular_by_author(self, author_id: int, exclude: int = 0, limit: int = 3) -> List[dict]:
        return read("""
            MATCH (u:User {user_id: $author})-[:WROTE]->(a:Article {status: 'PUBLISHED'})
            WHERE a.deleted_at IS NULL AND a.article_id <> $exclude
            RETURN a.article_id AS article_id, a.title AS title, a.image AS image,
                   COUNT { (f:User)-[:LIKED]->(a) WHERE f.deleted_at IS NULL } AS like_count
            ORDER BY like_count DESC, a.post_date DESC LIMIT $limit""", author=author_id, exclude=exclude, limit=limit)

    def find_by_author(self, author_id: int, viewer: AuthUser, status: str = "PUBLISHED",
                       limit: int = 10, offset: int = 0, with_image: bool = False) -> List[Article]:
        """An author's articles for their profile. Drafts belong only to their author, admins included."""
        if status != "PUBLISHED" and author_id != viewer.id:
            return []
        rows = read(f"""
            MATCH (u:User {{user_id: $author}})-[:WROTE]->(a:Article {{status: $status}})
            WHERE a.deleted_at IS NULL AND u.deleted_at IS NULL AND ($with_image = false OR a.image IS NOT NULL)
            RETURN {FIELDS} ORDER BY a.post_date DESC, a.article_id DESC
            SKIP $offset LIMIT $limit""", author=author_id, status=status, with_image=with_image,
                    me=viewer.id, limit=limit, offset=offset)
        return [Article(**row) for row in rows]

    def count_by_author(self, author_id: int, status: str = "PUBLISHED", with_image: bool = False) -> int:
        return read_one("""RETURN COUNT { (:User {user_id: $author})-[:WROTE]->(a:Article {status: $status})
                                          WHERE a.deleted_at IS NULL AND ($with_image = false OR a.image IS NOT NULL) } AS total""",
                        author=author_id, status=status, with_image=with_image)["total"]

    def find_one(self, article_id: int, user: AuthUser) -> Article:
        row = read_one(f"MATCH (u:User)-[:WROTE]->(a:Article {{article_id: $id}}) "
                       f"WHERE a.deleted_at IS NULL RETURN {FIELDS}",
                       id=article_id, me=user.id)
        # A draft is private: to anyone but its author it does not exist.
        if not row or (row["status"] != "PUBLISHED" and row["author_id"] != user.id):
            raise NotFoundError("El artículo no existe.")
        return Article(**row)

    def find_editable(self, article_id: int, user: AuthUser, deleting: bool = False) -> Article:
        article = self.find_one(article_id, user)
        if deleting and not user.can_delete(article.author_id):
            raise ForbiddenError("Solo el autor o un administrador pueden eliminar este artículo.")
        if not deleting and not user.can_edit(article.author_id):
            raise ForbiddenError("Solo el autor puede editar este artículo.")
        return article

    # ---- writes ------------------------------------------------------------

    def create(self, dto: SaveArticleSchema, author: AuthUser) -> int:
        """One transaction: create the article, then link its tags and categories.

        The author is always the logged-in user, taken from the JWT. If linking fails
        the article is rolled back, and the image already written to disk is removed.
        """
        image = self.images.save(dto.image)

        def work(tx: Transaction) -> int:
            article_id = tx.run("""
                MATCH (u:User {user_id: $author})
                MERGE (c:Counter {name: 'Article'}) ON CREATE SET c.value = 0
                SET c.value = c.value + 1
                CREATE (u)-[:WROTE]->(a:Article {article_id: c.value, title: $title, body_text: $body,
                                                status: $status, image: $image, post_date: localdatetime({timezone: $tz})})
                RETURN a.article_id AS id""", not_found="El autor no existe.",
                                author=author.id, title=dto.title, body=dto.body_text,
                                status=dto.status or "DRAFT", image=image)[0]["id"]
            self._link(tx, article_id, dto)
            return article_id

        return self._with_image_cleanup(work, image)

    def update(self, article_id: int, dto: SaveArticleSchema, user: AuthUser) -> None:
        """A null status keeps the current one; publishing stamps the date.

        A new image replaces the old one; the old file is deleted only after the commit.
        """
        current = self.find_editable(article_id, user)
        new_image = self.images.save(dto.image)

        def work(tx: Transaction) -> None:
            tx.run("""
                MATCH (a:Article {article_id: $id})
                WITH a, coalesce($status, a.status) AS status
                SET a.title = $title, a.body_text = $body,
                    a.image = CASE WHEN $image IS NOT NULL THEN $image
                                   WHEN $remove_image THEN null ELSE a.image END,
                    a.post_date = CASE WHEN status = 'PUBLISHED' AND a.status <> 'PUBLISHED'
                                       THEN localdatetime({timezone: $tz}) ELSE a.post_date END,
                    a.status = status
                RETURN a.article_id""", not_found="El artículo no existe.", id=article_id,
                   title=dto.title, body=dto.body_text, status=dto.status,
                   image=new_image, remove_image=dto.remove_image)
            self._link(tx, article_id, dto)

        self._with_image_cleanup(work, new_image)
        if new_image or dto.remove_image:
            self.images.delete(current.image)

    def set_status(self, article_id: int, status: str, user: AuthUser) -> None:
        """Only the status (and the date when publishing); links stay as they are."""
        self.find_editable(article_id, user)
        write("""
            MATCH (a:Article {article_id: $id})
            SET a.post_date = CASE WHEN $status = 'PUBLISHED' AND a.status <> 'PUBLISHED'
                                   THEN localdatetime({timezone: $tz}) ELSE a.post_date END,
                a.status = $status
            RETURN a.article_id""", not_found="El artículo no existe.", id=article_id, status=status)

    def set_like(self, article_id: int, user: AuthUser, want: bool) -> bool:
        """Leave the article liked (want=True) or not liked by the user. Idempotent.

        Locking the user node first (a dummy SET takes Neo4j's write lock) makes concurrent
        requests from the same user run one after another, so MERGE can never create two
        LIKED relationships for the same pair. Only published articles can be liked.
        """
        article = self.find_one(article_id, user)
        if want and article.status != "PUBLISHED":
            raise AppError("Solo se puede dar like a artículos publicados.")

        def work(tx: Transaction) -> bool:
            tx.run("MATCH (u:User {user_id: $me}) SET u.like_lock = true REMOVE u.like_lock", me=user.id)
            if want:
                tx.run("""
                    MATCH (u:User {user_id: $me}), (a:Article {article_id: $id})
                    MERGE (u)-[l:LIKED]->(a) ON CREATE SET l.at = localdatetime({timezone: $tz})""", me=user.id, id=article_id)
            else:
                tx.run("MATCH (:User {user_id: $me})-[l:LIKED]->(:Article {article_id: $id}) DELETE l",
                       me=user.id, id=article_id)
            return want
        return transaction(work)

    def remove(self, article_id: int, user: AuthUser) -> None:
        """Logical delete: the article and its comments get the same deleted_at.

        Nodes, relationships, likes and the cover image are kept, so nothing is lost.
        """
        self.find_editable(article_id, user, deleting=True)
        write("""
            MATCH (a:Article {article_id: $id}) WHERE a.deleted_at IS NULL
            WITH a, localdatetime({timezone: $tz}) AS now
            SET a.deleted_at = now
            WITH a, now
            OPTIONAL MATCH (a)<-[:ON]-(c:Comment) WHERE c.deleted_at IS NULL
            SET c.deleted_at = now
            RETURN count(*) AS done""", not_found="El artículo no existe.", id=article_id)

    # ---- helpers -----------------------------------------------------------

    def _link(self, tx: Transaction, article_id: int, dto: SaveArticleSchema) -> None:
        self.tags.replace_links(tx, article_id, list(dto.tag_ids))
        self.categories.replace_links(tx, article_id, list(dto.category_ids))

    def _with_image_cleanup(self, work, image: Optional[str]):
        """Run the transaction; if it rolls back, the just-saved file goes too."""
        try:
            return transaction(work)
        except Exception:
            self.images.delete(image)
            raise
