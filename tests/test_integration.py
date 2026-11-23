"""End-to-end flows against a running Neo4j loaded with cypher/02_datos.cypher.
Skipped when the database is not reachable. Reload the data after running."""
import io
import re
import unittest
from pathlib import Path

from app import create_app
from app.common import throttle
from app.common.image_storage import ImageStorage
from app.database import driver, read_one

try:
    driver.verify_connectivity()
    DB_UP = True
except Exception:
    DB_UP = False

PASSWORD = "Blog2026!"


def real_png() -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (32, 18), (242, 214, 0)).save(buffer, "PNG")
    return buffer.getvalue()



def status_of(client, url: str) -> int:
    """Status of a file response, closing it so the served file handle is released."""
    with client.get(url) as response:
        return response.status_code


def tearDownModule():
    from app.database import driver
    driver.close()

class CsrfClient:
    """Test client that sends the CSRF token and confirms deletes, like the real page does."""

    def __init__(self):
        self.client = create_app().test_client()

    def token(self):
        self.client.get("/auth/login")
        with self.client.session_transaction() as session:
            return session.get("csrf_token")

    def get(self, *args, **kwargs):
        return self.client.get(*args, **kwargs)

    def post(self, path, data=None, **kwargs):
        if "json" in kwargs:
            return self.client.post(path, **kwargs)
        data = dict(data or {}, csrf_token=self.token(), confirm="1")
        return self.client.post(path, data=data, **kwargs)


@unittest.skipUnless(DB_UP, "Neo4j is not running")
class BlogFlowTest(unittest.TestCase):
    def setUp(self):
        throttle._hits.clear()  # every test logs in several times

    def tearDown(self):
        # The app deletes logically; test data is removed for real so it does not pile up.
        from app.database import write
        write("""MATCH (a:Article) WHERE a.title STARTS WITH 'QA'
                 OPTIONAL MATCH (a)<-[:ON]-(c:Comment) DETACH DELETE c, a""")
        write("MATCH (c:Comment) WHERE c.body_text STARTS WITH 'QA' DETACH DELETE c")

    def client_for(self, email):
        client = CsrfClient()
        response = client.post("/auth/login", data={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 302, f"login failed for {email}")
        return client

    def test_wrong_password_gives_generic_message(self):
        client = CsrfClient()
        response = client.post("/auth/login", data={"email": "ana.torres@correo.com", "password": "mala"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Correo o contraseña incorrectos".encode(), response.data)

    def test_sixth_login_attempt_is_throttled(self):
        client = CsrfClient()
        codes = [client.post("/auth/login", data={"email": "x@y.com", "password": "mala"}).status_code
                 for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)

    def test_api_login_and_me(self):
        client = CsrfClient()
        token = client.post("/api/auth/login", json={"email": "luis.moreno@correo.com",
                                                    "password": PASSWORD}).get_json()["accessToken"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).get_json()
        self.assertEqual(me["role"], "AUTHOR")
        self.assertEqual(me["email"], "luis.moreno@correo.com")

    def test_author_full_article_cycle(self):
        luis = self.client_for("luis.moreno@correo.com")
        response = luis.post("/articles/", data={"title": "QA integracion", "body_text": "Hola",
                                                 "intent": "draft", "tag_ids": ["1"], "category_ids": ["2"]})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        luis.post(f"/articles/{article_id}/comments", data={"body_text": "QA comentario en borrador"})
        sofia = self.client_for("sofia.ramirez@correo.com")
        self.assertEqual(sofia.get(f"/articles/{article_id}").status_code, 404, "drafts must be private")
        ana = self.client_for("ana.torres@correo.com")
        self.assertEqual(ana.get(f"/articles/{article_id}").status_code, 404, "even admins cannot read drafts")
        self.assertNotIn(b"QA integracion", ana.get("/profile/2?tab=drafts").data)

        luis.post(f"/articles/{article_id}/publish")
        luis.post(f"/articles/{article_id}/comments", data={"body_text": "QA mi comentario"})
        page = luis.get(f"/articles/{article_id}").data.decode()
        self.assertIn("QA integracion", page)
        self.assertIn("#neo4j", page)
        self.assertIn("Avanzado", page)
        self.assertIn("QA mi comentario", page)
        self.assertNotIn("QA comentario en borrador", page)
        self.assertIn("Publicado", page)

        self.assertEqual(sofia.post(f"/articles/{article_id}/delete").status_code, 403)
        self.assertEqual(luis.get(f"/articles/{article_id}").status_code, 200, "another author deleted it")

        luis.post(f"/articles/{article_id}", data={"title": "QA editado", "body_text": "Hola", "intent": "save",
                                                   "tag_ids": ["2"]})
        page = luis.get(f"/articles/{article_id}").data.decode()
        self.assertIn("Publicado", page, "save keeps the status")
        self.assertIn("#cypher", page)
        self.assertNotIn("#neo4j", page, "unchecked tags are unlinked")
        self.assertNotIn("Avanzado", page)
        luis.post(f"/articles/{article_id}/delete")
        self.assertEqual(luis.get(f"/articles/{article_id}").status_code, 404)

    def test_only_admin_reaches_users(self):
        luis = self.client_for("luis.moreno@correo.com")
        for path in ("/users/", "/tags/", "/categories/"):
            self.assertEqual(luis.get(path).status_code, 403, path)
        self.assertNotIn(b"/tags/", luis.get("/").data, "authors should not see the tags link")
        self.assertEqual(self.client_for("ana.torres@correo.com").get("/users/").status_code, 200)

    def test_duplicate_tag_is_reported(self):
        ana = self.client_for("ana.torres@correo.com")
        response = ana.client.post("/tags/", data={"name": "neo4j", "url": "otra", "csrf_token": ana.token()},
                                   headers={"Referer": "http://localhost/tags/new"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Ya existe una etiqueta con ese nombre".encode(), response.data)
        self.assertIn(b'value="otra"', response.data, "the form keeps what was typed")

    def test_published_never_goes_back_to_draft(self):
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        response = luis.post("/articles/", data={"title": "QA publicado", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        sofia.post(f"/articles/{article_id}/comments", data={"body_text": "QA comentario"})
        self.assertNotIn(b"Pasar a borrador", luis.get(f"/articles/{article_id}").data)
        self.assertNotIn(b'value="draft"', luis.get(f"/articles/{article_id}/edit").data)
        edited = luis.post(f"/articles/{article_id}", data={"title": "QA publicado", "body_text": "x", "intent": "draft"})
        self.assertEqual(edited.status_code, 400)
        self.assertEqual(luis.post(f"/articles/{article_id}/draft").status_code, 404, "the route is gone")
        self.assertEqual(sofia.get(f"/articles/{article_id}").status_code, 200, "still public, with its comment")
        draft = luis.post("/articles/", data={"title": "QA borrador", "body_text": "x", "intent": "draft"})
        draft_id = int(re.search(r"/articles/(\d+)", draft.headers["Location"]).group(1))
        self.assertEqual(sofia.post(f"/articles/{draft_id}/comments", data={"body_text": "QA no"}).status_code, 404)
        luis.post(f"/articles/{draft_id}/delete")
        luis.post(f"/articles/{article_id}/delete")

    def test_bad_tag_rolls_back_the_whole_article(self):
        from app.database import read_one
        count = lambda: read_one("MATCH (a:Article) RETURN count(a) AS n")["n"]
        before = count()
        luis = self.client_for("luis.moreno@correo.com")
        response = luis.client.post("/articles/", data={
            "title": "QA rollback", "body_text": "x", "intent": "publish", "tag_ids": ["1", "999999"],
            "csrf_token": luis.token()}, headers={"Referer": "http://localhost/articles/new"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(count(), before, "the article must not exist without its tags")
        self.assertIn(b'value="QA rollback"', response.data, "the form keeps what was typed")

    def test_like_toggles_and_drafts_cannot_be_liked(self):
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        response = luis.post("/articles/", data={"title": "QA likes", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        sofia.post(f"/articles/{article_id}/like")
        self.assertIn(b'aria-pressed="true"', sofia.get(f"/articles/{article_id}").data)
        self.assertIn(b"Me gusta (1)", luis.get(f"/articles/{article_id}").data.replace(b"Quitar me gusta", b"Me gusta"))
        sofia.post(f"/articles/{article_id}/like", data={"want": "0"})
        self.assertIn(b'aria-pressed="false"', sofia.get(f"/articles/{article_id}").data)
        draft = luis.post("/articles/", data={"title": "QA likes borrador", "body_text": "x", "intent": "draft"})
        draft_id = int(re.search(r"/articles/(\d+)", draft.headers["Location"]).group(1))
        self.assertEqual(luis.post(f"/articles/{draft_id}/like").status_code, 400)
        luis.post(f"/articles/{draft_id}/delete")
        luis.post(f"/articles/{article_id}/delete")

    def test_cover_image_is_validated_stored_and_removed(self):
        uploads = Path(__file__).resolve().parent.parent / "uploads"
        png = real_png()
        luis = self.client_for("luis.moreno@correo.com")
        fake = luis.client.post("/articles/", data={
            "title": "QA fake", "body_text": "x", "intent": "draft", "csrf_token": luis.token(),
            "image": (io.BytesIO(b"<?php echo 1; ?>"), "foto.png")}, content_type="multipart/form-data")
        self.assertEqual(fake.status_code, 400, "content decides the type, not the extension")
        before = set(uploads.iterdir())
        response = luis.post("/articles/", data={"title": "QA imagen", "body_text": "x", "intent": "publish",
                                                 "image": (io.BytesIO(png), "foto.png")},
                             content_type="multipart/form-data")
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        added = set(uploads.iterdir()) - before
        self.assertEqual(len(added), 1)
        stored = added.pop()
        self.assertTrue(stored.name.endswith(".png"))
        self.assertEqual(status_of(luis, f"/articles/{article_id}/image"), 200)
        luis.post(f"/articles/{article_id}/delete")
        self.assertEqual(luis.get(f"/articles/{article_id}").status_code, 404)
        self.assertTrue(stored.exists(), "logical delete keeps the file")
        stored.unlink()

        before = set(uploads.iterdir())
        luis.post("/articles/", data={"title": "QA rollback img", "body_text": "x", "intent": "publish",
                                      "tag_ids": ["999999"], "image": (io.BytesIO(png), "foto.png")},
                  content_type="multipart/form-data")
        self.assertEqual(set(uploads.iterdir()), before, "a rolled back article leaves no file behind")

    def test_comments_load_in_batches_like_a_feed(self):
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        response = luis.post("/articles/", data={"title": "QA muchos comentarios", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        for n in range(1, 14):
            sofia.post(f"/articles/{article_id}/comments", data={"body_text": f"QA c{n:02d}"})
        ids = lambda html: [int(i) for i in re.findall(r'id="comentario-(\d+)"', html)]
        page = sofia.get(f"/articles/{article_id}").data.decode()
        shown = ids(page)
        self.assertEqual(len(shown), 10, "only the newest 10 at first")
        self.assertIn("QA c13", page)
        self.assertNotIn("QA c03", page)
        self.assertIn("Ver comentarios anteriores (<span data-older>3</span>)", page)
        older = sofia.get(f"/articles/{article_id}/comments?before={shown[0]}").get_json()
        self.assertEqual((len(ids(older["html"])), older["older"], older["count"]), (3, 0, 13))
        self.assertLess(older["html"].index("QA c01"), older["html"].index("QA c03"), "oldest first")
        self.assertEqual(ids(sofia.get(f"/articles/{article_id}/comments?after={shown[-1]}").get_json()["html"]), [])
        newer = sofia.get(f"/articles/{article_id}/comments?after={shown[-2]}").get_json()
        self.assertEqual(ids(newer["html"]), [shown[-1]])
        self.assertEqual(len(ids(sofia.get(f"/articles/{article_id}?comentarios=todos").data.decode())), 13, "no-JS fallback")
        self.assertEqual(sofia.get(f"/articles/{article_id}/comments").status_code, 400)
        draft = luis.post("/articles/", data={"title": "QA borrador lote", "body_text": "x", "intent": "draft"})
        draft_id = int(re.search(r"/articles/(\d+)", draft.headers["Location"]).group(1))
        self.assertEqual(sofia.get(f"/articles/{draft_id}/comments?after=0").status_code, 404, "drafts stay private")
        luis.post(f"/articles/{draft_id}/delete")
        luis.post(f"/articles/{article_id}/delete")

    def test_background_actions_answer_json(self):
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        json_headers = {"Accept": "application/json"}
        response = luis.post("/articles/", data={"title": "QA fetch", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        like = sofia.post(f"/articles/{article_id}/like", headers=json_headers)
        self.assertEqual(like.get_json(), {"liked": True, "like_count": 1})
        created = sofia.post(f"/articles/{article_id}/comments", data={"body_text": "QA vía fetch"}, headers=json_headers)
        self.assertEqual(created.status_code, 201)
        self.assertIn("QA vía fetch", created.get_json()["html"])
        comment_id = int(re.search(r'id="comentario-(\d+)"', created.get_json()["html"]).group(1))
        denied = luis.client.post(f"/comments/{comment_id}/delete", headers=json_headers,
                                  data={"csrf_token": luis.token(), "confirm": "1"})
        self.assertEqual(denied.status_code, 403, "errors keep their status as JSON")
        self.assertIn("message", denied.get_json())
        deleted = sofia.post(f"/comments/{comment_id}/delete", headers=json_headers)
        self.assertEqual(deleted.get_json(), {"count": 0})
        luis.post(f"/articles/{article_id}/delete")

    def test_delete_is_logical(self):
        from app.database import read_one
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        response = luis.post("/articles/", data={"title": "QA logico", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        sofia.post(f"/articles/{article_id}/comments", data={"body_text": "QA comentario logico"})
        luis.post(f"/articles/{article_id}/delete")
        self.assertEqual(luis.get(f"/articles/{article_id}").status_code, 404, "hidden from the app")
        self.assertNotIn(b"QA logico", luis.get("/profile/").data)
        row = read_one("""MATCH (a:Article {article_id: $id})<-[:ON]-(c:Comment)
                          RETURN a.deleted_at IS NOT NULL AS article_marked, c.deleted_at = a.deleted_at AS same_mark""",
                       id=article_id)
        self.assertEqual(row, {"article_marked": True, "same_mark": True}, "still in the graph, comments marked too")

    def test_deleted_user_is_logical_and_frees_the_email(self):
        from app.database import read_one, write
        ana = self.client_for("ana.torres@correo.com")
        ana.post("/users/", data={"name": "QA Borrable", "email": "qa.borrable@correo.com",
                                  "password": PASSWORD, "role": "AUTHOR"})
        user_id = read_one("MATCH (u:User {email: 'qa.borrable@correo.com'}) RETURN u.user_id AS id")["id"]
        qa = CsrfClient()
        token = qa.post("/api/auth/login", json={"email": "qa.borrable@correo.com",
                                                 "password": PASSWORD}).get_json()["accessToken"]
        ana.post(f"/users/{user_id}/delete")
        self.assertEqual(qa.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code, 401)
        self.assertEqual(qa.post("/api/auth/login", json={"email": "qa.borrable@correo.com",
                                                          "password": PASSWORD}).status_code, 401)
        row = read_one("MATCH (u:User {user_id: $id}) RETURN u.deleted_email AS kept, u.email AS email", id=user_id)
        self.assertEqual(row, {"kept": "qa.borrable@correo.com", "email": None})
        ana.post("/users/", data={"name": "QA Nuevo", "email": "qa.borrable@correo.com",
                                  "password": PASSWORD, "role": "AUTHOR"})
        self.assertIsNotNone(read_one("MATCH (u:User {email: 'qa.borrable@correo.com'}) RETURN u.user_id AS id"),
                             "the email can be used again")
        write("MATCH (u:User) WHERE u.name STARTS WITH 'QA' DETACH DELETE u")

    def test_concurrent_likes_never_stack(self):
        from concurrent.futures import ThreadPoolExecutor
        from app.database import read_one
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        response = luis.post("/articles/", data={"title": "QA concurrente", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        token = sofia.token()
        cookie = sofia.client.get_cookie("access_token").value
        app = create_app()

        def like(_):
            client = app.test_client()
            client.set_cookie("access_token", cookie)
            with client.session_transaction() as session:
                session["csrf_token"] = token
            return client.post(f"/articles/{article_id}/like", data={"want": "1", "csrf_token": token},
                               headers={"Accept": "application/json"}).status_code

        with ThreadPoolExecutor(max_workers=10) as pool:
            codes = list(pool.map(like, range(10)))
        self.assertTrue(all(code == 200 for code in codes), codes)
        total = read_one("MATCH (:User {user_id: 3})-[l:LIKED]->(:Article {article_id: $id}) RETURN count(l) AS n",
                         id=article_id)["n"]
        self.assertEqual(total, 1)

    def test_corrupt_image_and_private_draft_cover(self):
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        broken = luis.client.post("/articles/", data={
            "title": "QA corrupta", "body_text": "x", "intent": "publish", "csrf_token": luis.token(),
            "image": (io.BytesIO(real_png()[:40]), "rota.png")}, content_type="multipart/form-data")
        self.assertEqual(broken.status_code, 400, "a truncated file is not an image")
        response = luis.post("/articles/", data={"title": "QA portada privada", "body_text": "x", "intent": "draft",
                                                 "image": (io.BytesIO(real_png()), "p.png")},
                             content_type="multipart/form-data")
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        self.assertEqual(status_of(luis, f"/articles/{article_id}/image"), 200)
        self.assertEqual(sofia.get(f"/articles/{article_id}/image").status_code, 404, "a draft's cover is private")
        self.assertEqual(CsrfClient().get(f"/articles/{article_id}/image").status_code, 302, "needs a session")
        from app.database import read_one
        name = read_one("MATCH (a:Article {article_id: $id}) RETURN a.image AS f", id=article_id)["f"]
        (Path(__file__).resolve().parent.parent / "uploads" / name).unlink()

    def test_huge_ids_and_head_requests(self):
        luis = self.client_for("luis.moreno@correo.com")
        for path in ("/articles/9223372036854775808", "/comments/9223372036854775808/edit"):
            self.assertEqual(luis.get(path).status_code, 404, path)
        bad = luis.post("/articles/", data={"title": "QA id", "body_text": "x", "intent": "draft",
                                            "tag_ids": ["9" * 200]})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(CsrfClient().client.head("/auth/login").status_code, 200)
        self.assertIn("Esta página no existe".encode(), luis.get("/no-existe").data)

    def test_post_without_csrf_token_is_rejected(self):
        luis = self.client_for("luis.moreno@correo.com")
        response = luis.client.post("/articles/", data={"title": "QA x", "body_text": "y", "intent": "draft"})
        self.assertEqual(response.status_code, 400)

    def test_login_ignores_external_next(self):
        client = CsrfClient()
        response = client.post("/auth/login?next=https://example.invalid/x",
                               data={"email": "luis.moreno@correo.com", "password": PASSWORD})
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_revokes_the_token(self):
        client = CsrfClient()
        token = client.post("/api/auth/login", json={"email": "sofia.ramirez@correo.com",
                                                     "password": PASSWORD}).get_json()["accessToken"]
        bearer = {"Authorization": f"Bearer {token}"}
        self.assertEqual(client.get("/api/auth/me", headers=bearer).status_code, 200)
        client.client.set_cookie("access_token", token)
        client.post("/auth/logout")
        self.assertEqual(client.get("/api/auth/me", headers=bearer).status_code, 401)

    def test_api_rejects_non_object_json(self):
        for body in ([1], "QA", 7):
            response = CsrfClient().post("/api/auth/login", json=body)
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.is_json)

    def test_profile_shows_drafts_only_to_their_author(self):
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        luis.post("/articles/", data={"title": "QA perfil borrador", "body_text": "x", "intent": "draft"})
        self.assertIn(b"QA perfil borrador", luis.get("/profile/?tab=drafts").data)
        other = sofia.get("/profile/2?tab=drafts")
        self.assertEqual(other.status_code, 200)
        self.assertNotIn(b"QA perfil borrador", other.data, "someone else's drafts tab falls back to posts")
        self.assertNotIn(b"Borradores", other.data)
        self.assertEqual(sofia.get("/profile/999999").status_code, 404)


    def test_profile_photos_replace_and_remove(self):
        luis, sofia = self.client_for("luis.moreno@correo.com"), self.client_for("sofia.ramirez@correo.com")
        bad = luis.post("/profile/edit", data={"name": "Luis Moreno", "email": "luis.moreno@correo.com", "avatar": (io.BytesIO(b"nope"), "a.png")}, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)
        luis.post("/profile/edit", data={"name": "Luis Moreno", "email": "luis.moreno@correo.com", "avatar": (io.BytesIO(real_png()), "a.png"),
                                         "cover": (io.BytesIO(real_png()), "c.png")}, content_type="multipart/form-data")
        files = read_one("MATCH (u:User {user_id: 2}) RETURN u.avatar AS avatar, u.cover AS cover")
        try:
            self.assertTrue(files["avatar"] and files["cover"])
            self.assertEqual(status_of(sofia, "/profile/2/avatar"), 200, "any logged user sees it")
            self.assertIn(b"/profile/2/avatar", sofia.get("/profile/2").data)
            luis.post("/profile/edit", data={"name": "Luis Moreno", "email": "luis.moreno@correo.com", "avatar": (io.BytesIO(real_png()), "b.png")}, content_type="multipart/form-data")
            self.assertFalse(ImageStorage().path(files["avatar"]), "the replaced file is deleted")
        finally:
            luis.post("/profile/edit", data={"name": "Luis Moreno", "email": "luis.moreno@correo.com", "remove_avatar": "1", "remove_cover": "1"})
        self.assertEqual(read_one("MATCH (u:User {user_id: 2}) RETURN u.avatar AS a, u.cover AS c"), {"a": None, "c": None})
        self.assertEqual(sofia.get("/profile/2/cover").status_code, 404)
        self.assertFalse(ImageStorage().path(files["cover"]))


    def test_admin_only_changes_the_role(self):
        ana = self.client_for("ana.torres@correo.com")
        try:
            ana.post("/users/2", data={"role": "ADMIN", "name": "Hackeado", "email": "x@correo.com", "password": "otraClave123"})
            row = read_one("MATCH (u:User {user_id: 2}) RETURN u.name AS name, u.email AS email, u.role AS role")
            self.assertEqual(row, {"name": "Luis Moreno", "email": "luis.moreno@correo.com", "role": "ADMIN"})
            self.client_for("luis.moreno@correo.com")  # the old password still works
        finally:
            ana.post("/users/2", data={"role": "AUTHOR"})
        self.assertEqual(ana.get("/users/1/edit").status_code, 302, "your own row goes to your profile")

    def test_own_account_edit_needs_current_password(self):
        luis = self.client_for("luis.moreno@correo.com")
        base = {"name": "Luis Moreno", "email": "luis.moreno@correo.com"}
        bad = luis.post("/profile/edit", data={**base, "email": "luis.nuevo@correo.com"})
        self.assertEqual(bad.status_code, 400)
        try:
            ok = luis.post("/profile/edit", data={**base, "new_password": "NuevaClave2026!", "current_password": "Blog2026!"})
            self.assertEqual(ok.status_code, 302)
            self.assertEqual(luis.get("/profile/").status_code, 200, "the session survives the password change")
        finally:
            luis.post("/profile/edit", data={**base, "new_password": "Blog2026!", "current_password": "NuevaClave2026!"})
        self.client_for("luis.moreno@correo.com")


    def test_animated_gif_is_accepted(self):
        from PIL import Image
        frames = [Image.new("RGB", (16, 16), color) for color in ((255, 0, 0), (0, 0, 255))]
        buffer = io.BytesIO()
        frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:], duration=200, loop=0)
        from werkzeug.datastructures import FileStorage
        name = ImageStorage().save(FileStorage(io.BytesIO(buffer.getvalue()), "a.gif"))
        try:
            self.assertTrue(name.endswith(".gif"))
            with Image.open(ImageStorage().path(name)) as saved:
                self.assertEqual(saved.n_frames, 2, "stored as is, still animated")
        finally:
            ImageStorage().delete(name)


    def test_admin_deletes_but_cannot_edit_others_content(self):
        luis, ana = self.client_for("luis.moreno@correo.com"), self.client_for("ana.torres@correo.com")
        response = luis.post("/articles/", data={"title": "QA moderacion", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        luis.post(f"/articles/{article_id}/comments", data={"body_text": "QA comentario moderado"})
        comment_id = read_one("MATCH (c:Comment {body_text: 'QA comentario moderado'}) RETURN c.comment_id AS id")["id"]
        page = ana.get(f"/articles/{article_id}").data
        self.assertNotIn(f"/articles/{article_id}/edit".encode(), page)
        self.assertIn(f"/articles/{article_id}/delete".encode(), page)
        self.assertEqual(ana.get(f"/articles/{article_id}/edit").status_code, 403)
        self.assertEqual(ana.post(f"/articles/{article_id}", data={"title": "Hackeado", "body_text": "x"}).status_code, 403)
        self.assertEqual(ana.post(f"/articles/{article_id}/publish").status_code, 403)
        self.assertEqual(ana.get(f"/comments/{comment_id}/edit").status_code, 403)
        self.assertEqual(ana.post(f"/comments/{comment_id}/delete").status_code, 302)
        self.assertEqual(ana.post(f"/articles/{article_id}/delete").status_code, 302)
        self.assertEqual(luis.get(f"/articles/{article_id}").status_code, 404)


    def test_edit_without_intent_keeps_the_status(self):
        luis = self.client_for("luis.moreno@correo.com")
        response = luis.post("/articles/", data={"title": "QA sin intent", "body_text": "x", "intent": "publish"})
        article_id = int(re.search(r"/articles/(\d+)", response.headers["Location"]).group(1))
        luis.post(f"/articles/{article_id}", data={"title": "QA sin intent 2", "body_text": "y"})
        row = read_one("MATCH (a:Article {article_id: $id}) RETURN a.status AS status", id=article_id)
        self.assertEqual(row["status"], "PUBLISHED")
        created = luis.post("/articles/", data={"title": "QA sin intent nuevo", "body_text": "x"})
        new_id = int(re.search(r"/articles/(\d+)", created.headers["Location"]).group(1))
        self.assertEqual(read_one("MATCH (a:Article {article_id: $id}) RETURN a.status AS s", id=new_id)["s"], "DRAFT")


    def test_users_search_and_pagination(self):
        ana = self.client_for("ana.torres@correo.com")
        page = ana.get("/users/?q=MORENO").data
        self.assertIn(b"Luis Moreno", page)
        self.assertNotIn(b"Sofia Ramirez", page)
        self.assertIn(b"Sofia Ramirez", ana.get("/users/?q=sofia.ramirez@").data, "search by email too")
        self.assertIn(b"No hay usuarios", ana.get("/users/?q=nadie-se-llama-asi").data)
        self.assertEqual(ana.get("/users/?page=999").status_code, 200, "out of range clamps to the last page")


    def test_feed_filters_search_and_side_panels(self):
        luis = self.client_for("luis.moreno@correo.com")
        self.assertIn(b"Primeros pasos con Cypher", luis.get("/?tag=cypher").data)
        self.assertNotIn(b"Primeros pasos con Cypher", luis.get("/?tag=python").data)
        found = luis.get("/?q=SOFIA").data
        self.assertIn(b"Personas", found)
        self.assertIn(b"Sofia Ramirez", found)
        self.assertIn(b"Ning\xc3\xban art\xc3\xadculo coincide", luis.get("/?q=zzzz-nada").data)
        self.assertIn(b"Su comunidad", luis.get("/profile/1").data)
        self.assertIn(b"M\xc3\xa1s de", luis.get("/articles/1").data)


    def test_home_offers_filters_and_combines_them(self):
        luis = self.client_for("luis.moreno@correo.com")
        home = luis.get("/").data
        self.assertIn(b'aria-label="Filtrar por categor', home)
        self.assertIn(b"Etiquetas populares", home)
        both = luis.get("/?category=Avanzado&tag=cypher").data
        self.assertIn(b"Categor\xc3\xada: Avanzado", both)
        self.assertIn(b'href="/?category=Avanzado"', both, "removing the tag keeps the category")


    def test_feed_sorts_by_popularity(self):
        from app.modules.articles.articles_service import ArticlesService
        from app.modules.auth.auth_user import AuthUser
        me = AuthUser(id=2, name="Luis", email="luis.moreno@correo.com", role="AUTHOR")
        likes = [a.like_count for a in ArticlesService().find_published(me, 50, popular=True)]
        self.assertEqual(likes[0], max(likes), "most liked first (authors are spread, so the rest is near-sorted)")
        page = self.client_for("luis.moreno@correo.com").get("/?sort=popular&tag=cypher").data
        self.assertIn(b'href="/?tag=cypher"', page, "Recientes keeps the tag filter")


if __name__ == "__main__":
    unittest.main()
