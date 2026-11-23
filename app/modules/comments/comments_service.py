from __future__ import annotations

from typing import List, Optional

from app.common.errors import ForbiddenError, NotFoundError
from app.database import read, read_one, write
from app.modules.articles.articles_service import ArticlesService
from app.modules.auth.auth_user import AuthUser
from app.modules.comments.schemas.comment_schema import Comment, SaveCommentSchema

# Deleted comments and articles are skipped. A comment whose author was deleted stays,
# shown as "cuenta eliminada" (user_id comes back null).
MATCH = """MATCH (c:Comment)-[:ON]->(a:Article) WHERE c.deleted_at IS NULL AND a.deleted_at IS NULL
        OPTIONAL MATCH (u:User)-[:POSTED]->(c) WHERE u.deleted_at IS NULL"""
FIELDS = """c.comment_id AS comment_id, a.article_id AS article_id, a.title AS article_title,
       u.user_id AS user_id, c.name AS name, c.url AS url, c.body_text AS body_text,
       c.created_at AS created_at, u.avatar AS avatar"""


class CommentsService:
    # Comments are ordered by (created_at, comment_id); a cursor is the comment to read before or after.
    WINDOW = """WHERE a.article_id = $id
              AND ($before IS NULL OR c.created_at < $before_at OR (c.created_at = $before_at AND c.comment_id < $before))
              AND ($after IS NULL OR c.created_at > $after_at OR (c.created_at = $after_at AND c.comment_id > $after))"""

    def find_by_article(self, article_id: int, limit: Optional[int] = None,
                        before: Optional[int] = None, after: Optional[int] = None) -> List[Comment]:
        """Oldest first, like a conversation. With limit, only the newest `limit` of them (before the
        `before` comment when given): "ver comentarios anteriores" walks back one batch at a time.
        With after, only the ones newer than that comment (what arrived live)."""
        rows = read(f"""{MATCH} WITH c, a, u {self.WINDOW}
            RETURN {FIELDS} ORDER BY c.created_at DESC, c.comment_id DESC {"LIMIT $limit" if limit else ""}""",
                    id=article_id, limit=limit, **self._cursors(before, after))
        return [Comment(**row) for row in reversed(rows)]

    def count_by_article(self, article_id: int, before: Optional[int] = None) -> int:
        return read_one(f"{MATCH} WITH c, a {self.WINDOW} RETURN count(c) AS total",
                        id=article_id, **self._cursors(before, None))["total"]

    @staticmethod
    def _cursors(before: Optional[int], after: Optional[int]) -> dict:
        at = lambda comment_id: comment_id and (read_one(
            "MATCH (c:Comment {comment_id: $id}) RETURN c.created_at AS at", id=comment_id) or {}).get("at")
        return {"before": before, "before_at": at(before), "after": after, "after_at": at(after)}

    def find_one(self, comment_id: int) -> Comment:
        row = read_one(f"{MATCH} WITH c, a, u WHERE c.comment_id = $id RETURN {FIELDS}", id=comment_id)
        if not row:
            raise NotFoundError("El comentario no existe.")
        return Comment(**row)

    def find_editable(self, comment_id: int, user: AuthUser, deleting: bool = False) -> Comment:
        comment = self.find_one(comment_id)
        # The article must be visible too: a comment never opens a door to someone else's draft.
        ArticlesService().find_one(comment.article_id, user)
        if deleting and not user.can_delete(comment.user_id):
            raise ForbiddenError("Solo quien escribió el comentario o un administrador pueden eliminarlo.")
        if not deleting and not user.can_edit(comment.user_id):
            raise ForbiddenError("Solo quien escribió el comentario puede editarlo.")
        return comment

    def create(self, article_id: int, dto: SaveCommentSchema, author: AuthUser) -> int:
        rows = write("""
            MATCH (a:Article {article_id: $article, status: 'PUBLISHED'}), (u:User {user_id: $author})
            WHERE a.deleted_at IS NULL
            MERGE (k:Counter {name: 'Comment'}) ON CREATE SET k.value = 0
            SET k.value = k.value + 1
            CREATE (u)-[:POSTED]->(c:Comment {comment_id: k.value, name: $name, url: $url,
                                             body_text: $body, created_at: localdatetime({timezone: $tz})})-[:ON]->(a)
            RETURN c.comment_id AS id""", not_found="El artículo no existe o todavía no se publica.", article=article_id,
                     author=author.id, name=dto.name, url=dto.url, body=dto.body_text)
        return rows[0]["id"]

    def update(self, comment_id: int, dto: SaveCommentSchema, user: AuthUser) -> int:
        comment = self.find_editable(comment_id, user)
        write("""
            MATCH (c:Comment {comment_id: $id})
            SET c.name = $name, c.url = $url, c.body_text = $body
            RETURN c.comment_id""", not_found="El comentario no existe.",
              id=comment_id, name=dto.name, url=dto.url, body=dto.body_text)
        return comment.article_id

    def remove(self, comment_id: int, user: AuthUser) -> int:
        comment = self.find_editable(comment_id, user, deleting=True)
        # Logical delete: the comment stays in the graph with deleted_at.
        write("MATCH (c:Comment {comment_id: $id}) WHERE c.deleted_at IS NULL "
              "SET c.deleted_at = localdatetime({timezone: $tz}) RETURN 1 AS done",
              not_found="El comentario no existe.", id=comment_id)
        return comment.article_id
