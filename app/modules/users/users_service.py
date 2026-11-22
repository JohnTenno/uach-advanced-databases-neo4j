from __future__ import annotations

from typing import List, Optional

from app.common.errors import AppError, NotFoundError
from app.database import read, read_one, write
from app.modules.auth.password_hasher import PasswordHasher, ScryptPasswordHasher
from app.modules.users.schemas.user_schema import SaveUserSchema, User

FIELDS = "u.user_id AS user_id, u.name AS name, u.email AS email, u.role AS role, u.created_at AS created_at, u.avatar AS avatar, u.cover AS cover"


class UsersService:
    def __init__(self, passwords: PasswordHasher = None):
        self.passwords = passwords or ScryptPasswordHasher()

    # Name or email contains the search text, ignoring case; an empty search matches everyone.
    MATCH_SEARCH = """MATCH (u:User) WHERE u.deleted_at IS NULL
            AND (toLower(u.name) CONTAINS $q OR toLower(u.email) CONTAINS $q)"""

    def count(self, q: str = "") -> int:
        return read_one(f"{self.MATCH_SEARCH} RETURN count(u) AS total", q=q.lower())["total"]

    def find_all(self, q: str = "", limit: int = 20, offset: int = 0) -> List[User]:
        rows = read(f"""
            {self.MATCH_SEARCH}
            RETURN {FIELDS},
                   COUNT {{ (u)-[:WROTE]->(a:Article) WHERE a.deleted_at IS NULL }} AS article_count,
                   COUNT {{ (u)-[:POSTED]->(c:Comment)-[:ON]->(a:Article)
                            WHERE c.deleted_at IS NULL AND a.deleted_at IS NULL }} AS comment_count,
                   COUNT {{ (u)-[:POSTED]->(c:Comment)-[:ON]->(a:Article)<-[:WROTE]-(o:User)
                            WHERE o <> u AND c.deleted_at IS NULL AND a.deleted_at IS NULL }}
                       AS foreign_comment_count
            ORDER BY u.name SKIP $offset LIMIT $limit""", q=q.lower(), limit=limit, offset=offset)
        return [User(**row) for row in rows]

    def find_one(self, user_id: int) -> User:
        row = read_one(f"MATCH (u:User {{user_id: $id}}) WHERE u.deleted_at IS NULL RETURN {FIELDS}", id=user_id)
        if not row:
            raise NotFoundError("El usuario no existe.")
        return User(**row)

    def profile_stats(self, user_id: int) -> dict:
        return read_one("""
            MATCH (u:User {user_id: $id}) WHERE u.deleted_at IS NULL
            RETURN COUNT { (u)-[:POSTED]->(c:Comment)-[:ON]->(a:Article)
                           WHERE c.deleted_at IS NULL AND a.deleted_at IS NULL } AS comments,
                   COUNT { (f:User)-[:LIKED]->(a:Article)<-[:WROTE]-(u)
                           WHERE f.deleted_at IS NULL AND a.deleted_at IS NULL AND a.status = 'PUBLISHED' } AS likes""",
                        id=user_id)

    def set_photos(self, user_id: int, avatar: Optional[str], cover: Optional[str],
                   remove_avatar: bool, remove_cover: bool) -> dict:
        """Point the user at new photo files (or none); returns the files that were replaced."""
        return write("""
            MATCH (u:User {user_id: $id}) WHERE u.deleted_at IS NULL
            WITH u, u.avatar AS old_avatar, u.cover AS old_cover
            SET u.avatar = CASE WHEN $avatar IS NOT NULL THEN $avatar WHEN $remove_avatar THEN null ELSE u.avatar END,
                u.cover = CASE WHEN $cover IS NOT NULL THEN $cover WHEN $remove_cover THEN null ELSE u.cover END
            RETURN CASE WHEN u.avatar IS NULL OR u.avatar <> old_avatar THEN old_avatar END AS avatar,
                   CASE WHEN u.cover IS NULL OR u.cover <> old_cover THEN old_cover END AS cover""",
                     not_found="El usuario no existe.", id=user_id, avatar=avatar, cover=cover,
                     remove_avatar=remove_avatar, remove_cover=remove_cover)[0]

    def community(self, user_id: int, limit: int = 5) -> List[dict]:
        """Who comments the most on this user's articles: (other)-[:POSTED]->()-[:ON]->()<-[:WROTE]-(user)."""
        return read("""
            MATCH (o:User)-[:POSTED]->(c:Comment)-[:ON]->(a:Article)<-[:WROTE]-(u:User {user_id: $id})
            WHERE o <> u AND o.deleted_at IS NULL AND c.deleted_at IS NULL AND a.deleted_at IS NULL
            RETURN o.user_id AS user_id, o.name AS name, o.avatar AS avatar, count(c) AS comments
            ORDER BY comments DESC, name LIMIT $limit""", id=user_id, limit=limit)

    def topics(self, user_id: int) -> List[dict]:
        return read("""
            MATCH (u:User {user_id: $id})-[:WROTE]->(a:Article {status: 'PUBLISHED'})-[:IN_CATEGORY]->(c:Category)
            WHERE a.deleted_at IS NULL AND c.deleted_at IS NULL
            RETURN c.name AS name, count(a) AS total ORDER BY total DESC, name""", id=user_id)

    def find_by_email_with_hash(self, email: str) -> Optional[dict]:
        """Only auth needs the hash, so it has its own query."""
        return read_one(f"MATCH (u:User {{email: $email}}) WHERE u.deleted_at IS NULL RETURN {FIELDS}, u.password_hash AS password_hash, "
                        "coalesce(u.token_version, 0) AS token_version",
                        email=email)

    def create(self, name: str, email: str, password: str, role: str) -> int:
        # A Counter node hands out numeric ids so routes read /users/3.
        rows = write("""
            MERGE (c:Counter {name: 'User'}) ON CREATE SET c.value = 0
            SET c.value = c.value + 1
            CREATE (u:User {user_id: c.value, name: $name, email: $email, role: $role,
                            password_hash: $hash, created_at: localdatetime({timezone: $tz})})
            RETURN u.user_id AS id""",
                     name=name, email=email, role=role, hash=self.passwords.hash(password))
        return rows[0]["id"]

    def create_from(self, dto: SaveUserSchema) -> int:
        return self.create(dto.name, dto.email, dto.password, dto.role)

    def set_role(self, user_id: int, role: str, acting_id: int) -> None:
        """The only thing an admin changes on someone else's account; their data is theirs."""
        if user_id == acting_id:
            raise AppError("No puedes cambiar tu propio rol.")
        if role not in ("ADMIN", "AUTHOR"):
            raise AppError("El rol debe ser ADMIN o AUTHOR.")
        write("MATCH (u:User {user_id: $id}) WHERE u.deleted_at IS NULL SET u.role = $role RETURN u.user_id",
              not_found="El usuario no existe.", id=user_id, role=role)

    def update_account(self, user_id: int, name: str, email: str, new_password: Optional[str],
                       current_password: str) -> int:
        """The user edits their own name, email and password. Changing the email or the password
        needs the current password. Returns the new token_version (bumped on a password change)."""
        row = read_one("MATCH (u:User {user_id: $id}) WHERE u.deleted_at IS NULL "
                       "RETURN u.email AS email, u.password_hash AS hash", id=user_id)
        if not row:
            raise NotFoundError("El usuario no existe.")
        if (email != row["email"] or new_password) and not (
                current_password and self.passwords.verify(current_password, row["hash"])):
            raise AppError("Para cambiar el correo o la contraseña escribe tu contraseña actual.")
        return write("""
            MATCH (u:User {user_id: $id}) WHERE u.deleted_at IS NULL
            SET u.name = $name, u.email = $email,
                u.password_hash = coalesce($hash, u.password_hash),
                u.token_version = coalesce(u.token_version, 0) + CASE WHEN $hash IS NULL THEN 0 ELSE 1 END
            RETURN u.token_version AS version""", not_found="El usuario no existe.", id=user_id, name=name,
                     email=email, hash=self.passwords.hash(new_password) if new_password else None)[0]["version"] or 0

    def remove(self, user_id: int, acting_id: int) -> None:
        """Logical delete, in cascade: the user, their articles and the comments on those
        articles get deleted_at. Comments they left on other people's articles stay visible,
        shown as "cuenta eliminada". Nothing is physically removed, images included.

        The email is unique, so it moves to deleted_email to free it for a new account.
        Bumping token_version logs the user out everywhere at once.
        """
        if user_id == acting_id:
            raise AppError("No puedes eliminar tu propia cuenta.")
        write("""
            MATCH (u:User {user_id: $id}) WHERE u.deleted_at IS NULL
            WITH u, localdatetime({timezone: $tz}) AS now
            SET u.deleted_at = now, u.deleted_email = u.email,
                u.token_version = coalesce(u.token_version, 0) + 1
            REMOVE u.email
            WITH u, now
            CALL (u, now) {
                MATCH (u)-[:WROTE]->(a:Article) WHERE a.deleted_at IS NULL
                SET a.deleted_at = now
                WITH a, now
                OPTIONAL MATCH (a)<-[:ON]-(c:Comment) WHERE c.deleted_at IS NULL
                SET c.deleted_at = now
            }
            RETURN 1 AS done""", not_found="El usuario no existe.", id=user_id)
