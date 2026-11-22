from dataclasses import dataclass
from typing import Optional

ROLES = ("ADMIN", "AUTHOR")


@dataclass(frozen=True)
class AuthUser:
    """Identity carried in the JWT and attached to each request as g.user."""

    id: int
    name: str
    email: str
    role: str
    token_version: int = 0  # bumped on logout / password change to revoke old tokens
    avatar: Optional[str] = None  # profile photo file, read from the graph on every request

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    def can_edit(self, owner_id) -> bool:
        """Only the author edits their own content, admins included."""
        return owner_id == self.id

    def can_delete(self, owner_id) -> bool:
        """Admins moderate: they can remove anyone's content, but not rewrite it."""
        return self.is_admin or owner_id == self.id
