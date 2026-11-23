"""Checks that need no running Neo4j: hashing, tokens, validation and guards."""
import unittest

import jwt

from app import create_app
from app.common.errors import AppError
from app.database import config
from app.modules.auth.auth_service import ALGORITHM, AuthService
from app.modules.auth.auth_user import AuthUser
from app.modules.auth.password_hasher import ScryptPasswordHasher


class PasswordHasherTest(unittest.TestCase):
    def test_verifies_only_the_right_password(self):
        hasher = ScryptPasswordHasher()
        stored = hasher.hash("Blog2026!")
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertTrue(hasher.verify("Blog2026!", stored))
        self.assertFalse(hasher.verify("blog2026!", stored))
        self.assertFalse(hasher.verify("Blog2026!", "garbage"))


class TokenTest(unittest.TestCase):
    def test_token_carries_identity_and_expiry(self):
        token = AuthService().sign(AuthUser(id=7, name="Ana", email="a@b.com", role="ADMIN"))
        payload = jwt.decode(token, config.jwt_secret, algorithms=[ALGORITHM])
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["role"], "ADMIN")
        self.assertIn("exp", payload)

    def test_token_without_expiry_is_rejected(self):
        incomplete = jwt.encode({"sub": "1"}, config.jwt_secret, algorithm=ALGORITHM)
        with self.assertRaises(AppError):
            AuthService().verify_token(incomplete)

    def test_tampered_token_is_rejected(self):
        forged = jwt.encode({"sub": "1", "role": "ADMIN"}, "x" * 40, algorithm=ALGORITHM)
        with self.assertRaises(AppError):
            AuthService().verify_token(forged)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_pages_redirect_to_login_without_token(self):
        for path in ("/", "/articles/", "/users/", "/tags/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/auth/login", response.headers["Location"])

    def test_api_answers_401_without_token(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_forged_bearer_is_ignored(self):
        forged = jwt.encode({"sub": "1"}, "y" * 40, algorithm=ALGORITHM)
        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        self.assertEqual(response.status_code, 401)

    def test_login_page_renders(self):
        self.assertEqual(self.client.get("/auth/login").status_code, 200)

    def test_register_rejects_bad_email(self):
        self.client.get("/auth/register")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        response = self.client.post("/auth/register", data={
            "name": "X", "email": "no-es-correo", "password": "12345678", "password_confirm": "12345678",
            "csrf_token": token})
        self.assertEqual(response.status_code, 400)
        self.assertIn("formato v".encode(), response.data)


if __name__ == "__main__":
    unittest.main()


class SpreadAuthorsTest(unittest.TestCase):
    def test_no_two_in_a_row_by_the_same_author(self):
        from types import SimpleNamespace
        from app.modules.articles.articles_service import ArticlesService
        posts = [SimpleNamespace(article_id=i, author_id=a) for i, a in enumerate([1, 1, 1, 2, 3, 2, 2, 4])]
        authors = [p.author_id for p in ArticlesService.spread_authors(posts)]
        self.assertEqual(sorted(authors), sorted([1, 1, 1, 2, 3, 2, 2, 4]))
        self.assertFalse(any(x == y for x, y in zip(authors, authors[1:])), authors)
        self.assertEqual(ArticlesService.spread_authors([posts[0], posts[1]])[0].article_id, 0, "only one author: order kept")


class PaginationTest(unittest.TestCase):
    def test_counts_and_page_window(self):
        from app.common.pagination import Pagination
        p = Pagination(number=6, size=10, total=115)
        self.assertEqual((p.pages, p.offset, p.first_item, p.last_item), (12, 50, 51, 60))
        self.assertEqual(p.window, [1, None, 4, 5, 6, 7, 8, None, 12])
        self.assertEqual(Pagination(1, 10, 17).window, [1, 2])
        self.assertEqual(Pagination(2, 10, 17).last_item, 17)
        empty = Pagination(1, 10, 0)
        self.assertEqual((empty.pages, empty.first_item, empty.last_item), (1, 0, 0))
