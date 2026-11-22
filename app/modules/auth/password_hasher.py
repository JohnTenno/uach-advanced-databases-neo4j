"""Password hashing with scrypt from the standard library.

Same storage format as the Nest projects: ``scrypt$<salt hex>$<key hex>``,
and the same parameters as Node's crypto.scrypt defaults, so hashes are
interchangeable between both.
"""
import hashlib
import hmac
import os
from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, stored_hash: str) -> bool: ...


class ScryptPasswordHasher(PasswordHasher):
    PREFIX = "scrypt"
    SALT_BYTES = 16
    KEY_BYTES = 64

    def hash(self, password: str) -> str:
        salt = os.urandom(self.SALT_BYTES)
        key = self._derive(password, salt, self.KEY_BYTES)
        return "$".join([self.PREFIX, salt.hex(), key.hex()])

    def verify(self, password: str, stored_hash: str) -> bool:
        parts = (stored_hash or "").split("$")
        if len(parts) != 3 or parts[0] != self.PREFIX or not parts[1] or not parts[2]:
            return False
        expected = bytes.fromhex(parts[2])
        actual = self._derive(password, bytes.fromhex(parts[1]), len(expected))
        return hmac.compare_digest(expected, actual)

    @staticmethod
    def _derive(password: str, salt: bytes, length: int) -> bytes:
        return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=length)
