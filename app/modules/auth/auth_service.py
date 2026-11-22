from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.common.errors import UnauthorizedError
from app.database import config, read_one, write
from app.modules.auth.auth_user import AuthUser
from app.modules.auth.password_hasher import PasswordHasher, ScryptPasswordHasher
from app.modules.auth.schemas.login_schema import LoginSchema, RegisterSchema
from app.modules.users.users_service import UsersService

ALGORITHM = "HS256"
AUTH_FIELDS = ("u.user_id AS user_id, u.name AS name, u.email AS email, u.role AS role, "
               "u.avatar AS avatar, coalesce(u.token_version, 0) AS token_version")


class AuthService:
    def __init__(self, users: UsersService = None, passwords: PasswordHasher = None):
        self.passwords = passwords or ScryptPasswordHasher()
        self.users = users or UsersService(self.passwords)

    def login(self, dto: LoginSchema) -> dict:
        row = self.users.find_by_email_with_hash(dto.email)
        valid = self.passwords.verify(dto.password, row["password_hash"]) if row else False
        if not row or not valid:
            # Same message for unknown email and wrong password, so accounts cannot be probed.
            raise UnauthorizedError("Correo o contraseña incorrectos.")
        user = self._to_auth_user(row)
        return {"accessToken": self.sign(user), "user": user}

    def register(self, dto: RegisterSchema) -> dict:
        """Public sign up always creates an AUTHOR; only an admin can grant ADMIN."""
        user_id = self.users.create(dto.name, dto.email, dto.password, "AUTHOR")
        user = AuthUser(id=user_id, name=dto.name, email=dto.email, role="AUTHOR", token_version=0)
        return {"accessToken": self.sign(user), "user": user}

    def sign(self, user: AuthUser) -> str:
        now = datetime.now(timezone.utc)
        payload = {"sub": str(user.id), "name": user.name, "email": user.email, "role": user.role,
                   "ver": user.token_version, "iat": now, "exp": now + timedelta(hours=config.jwt_expires_hours)}
        return jwt.encode(payload, config.jwt_secret, algorithm=ALGORITHM)

    def verify_token(self, token: str) -> AuthUser:
        invalid = UnauthorizedError("La sesión expiró o no es válida.")
        try:
            payload = jwt.decode(token, config.jwt_secret, algorithms=[ALGORITHM],
                                 options={"require": ["sub", "exp", "iat", "ver"]})
            user_id = int(payload["sub"])
        except (jwt.PyJWTError, ValueError, TypeError):
            raise invalid from None
        # Re-checked against the graph: a deleted user, a changed role, a new password
        # or a logout (which bumps token_version) takes effect at once.
        row = read_one(f"MATCH (u:User {{user_id: $id}}) WHERE u.deleted_at IS NULL RETURN {AUTH_FIELDS}", id=user_id)
        if not row or row["token_version"] != payload["ver"]:
            raise invalid
        return self._to_auth_user(row)

    def logout(self, user: AuthUser) -> None:
        """Invalidate every token issued so far for this user."""
        write("MATCH (u:User {user_id: $id}) SET u.token_version = coalesce(u.token_version, 0) + 1",
              id=user.id)

    @staticmethod
    def _to_auth_user(row: dict) -> AuthUser:
        return AuthUser(id=row["user_id"], name=row["name"], email=row["email"], role=row["role"],
                        token_version=row.get("token_version") or 0, avatar=row.get("avatar"))
