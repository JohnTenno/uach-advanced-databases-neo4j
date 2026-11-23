# Blog on Neo4j

Final project for Advanced Databases. A Python (Flask) app that administers a blog stored in Neo4j, with full JWT authentication and role based permissions.

Team: Leonardo Franco Bulkley, Ivan Eduardo Urrutia Rodriguez and Jonathan Gandara Salazar.

## Graph model

| Node | Properties |
|---|---|
| `:User` | `user_id`, `name`, `email`, `role` (`ADMIN` / `AUTHOR`), `password_hash`, `created_at`, `avatar`, `cover` (photo file names), `token_version` |
| `:Article` | `article_id`, `title`, `body_text`, `status`, `post_date`, `image` (cover file name) |
| `:Comment` | `comment_id`, `name`, `url`, `body_text`, `created_at` |
| `:Tag`, `:Category` | `tag_id` / `category_id`, `name`, `url` |

```
(:User)-[:WROTE]->(:Article)            users 1-N articles
(:User)-[:POSTED]->(:Comment)           users 1-N comments
(:Comment)-[:ON]->(:Article)            articles 1-N comments
(:Article)-[:TAGGED]->(:Tag)            articles N-N tags
(:Article)-[:IN_CATEGORY]->(:Category)  articles N-N categories
(:User)-[:LIKED]->(:Article)            extra: likes on published articles
```

Neo4j has no auto increment, so a `:Counter` node per label hands out numeric ids.

Creating or editing an article runs in one explicit transaction (`app/database.py::transaction`):
the article node is written, then its tags and categories are linked, and only if every step
succeeds is it committed. Any failure rolls the whole thing back.

Deletes are logical: the node gets `deleted_at` and keeps its relationships, and every
query filters `deleted_at IS NULL`. Deleting an article marks its comments; deleting a user
marks their articles and the comments on them, logs them out (token_version) and moves the
email to `deleted_email` so it can be reused. Tags and categories move `name`/`url` to
`deleted_name`/`deleted_url` for the same reason. See query 11 in `03_consultas.cypher`.

Images (article covers, profile photos and profile covers) are stored locally in `uploads/`,
outside `static/`, with no external service or keys, so the project works right after cloning.
Every frame is decoded to check the file is really JPG, PNG, WebP or GIF (animated too), up to
5 MB. They are served through routes that apply the same visibility rules as the data: a draft's
cover is only visible to its author.

## Features

- **Feed** (`/`): everyone's published articles, newest first, 10 per page.
- **Profile** (`/profile/<id>`), laid out like a social network: cover, photo, counts (posts,
  comments, likes received) and tabs: Posts, Photos (grid of covers) and Drafts (only on your own).
  "Edit profile" changes your name, email, password (needs the current one) and photos.
- **Articles**: one form creates and edits; tags and categories are picked in the same form and
  saved in the same transaction. Drafts are private, even from admins. Publishing is one way: a
  published article can be edited or deleted, never sent back to draft (it would hide other people's
  likes and comments).
- **Comments** open with the newest 10; "Ver comentarios anteriores" loads older batches of 10 from
  the server (cursor = the oldest comment on screen, so nothing repeats when new ones arrive).
- **Comments and likes** without reloading the page (optimistic UI: if the request fails the view
  goes back and a toast explains why). Likes are idempotent and serialized per user, so concurrent
  clicks can never create two `LIKED` relationships.
- **Real time** (`/events`, Server-Sent Events): other people's likes, comments and new posts show up
  without reloading. Events carry ids and counts only, never content.
  `app/common/event_bus.py` is in memory, so it needs a single worker process (threads are fine).
- **Loading states** on every form that saves, publishes or deletes; deletes ask for confirmation
  in a dialog that says exactly what is removed.
- **Moderation**: an admin can delete anyone's articles and comments but not edit them, and can
  only change another user's role (their data is theirs).

## Authentication

Same design as our NestJS projects:

- Passwords stored as `scrypt$<salt>$<key>` (`app/modules/auth/password_hasher.py`).
- Login signs an HS256 JWT with `sub`, name, email and role, valid for `JWT_EXPIRES_HOURS`.
- Unknown email and wrong password return the same message.
- The guard reads `Authorization: Bearer <token>` (API) or the HttpOnly `access_token` cookie (pages), and re-checks the user in the graph on every request, so deleting a user or changing a role takes effect at once.
- `@jwt_required` and `@roles("ADMIN")` protect routes; login and register allow 5 attempts per minute.
- Only the author edits an article or comment. Admins can delete anyone's content, change roles, and manage users, tags and categories.
- Every POST form carries a CSRF token and the Origin is checked.
- Logout or a password change bumps `token_version`, which revokes every token issued before.

API: `POST /api/auth/login` `{email, password}` → `{accessToken, user}`, `GET /api/auth/me`.

## Structure

Organized like a NestJS project: each feature is a module with its controller, service and schemas. All Cypher lives in the services.

```
main.py                    starts the app on port 5050 (5000 is taken by macOS AirPlay)
app/__init__.py            creates the app, registers modules and error handling
app/database.py            Neo4j driver: read(), read_one(), write()
app/common/                errors, forms, CSRF, throttle, image storage, event bus, TaxonomyService
app/modules/auth/          auth_controller, auth_service, jwt_guard, password_hasher, schemas/
app/modules/users/         users_controller (admin), profile_controller, users_service, schemas/
app/modules/events/        events_controller: the Server-Sent Events stream
app/modules/articles/      articles_controller, articles_service, schemas/
app/modules/comments/      comments_controller, comments_service, schemas/
app/modules/tags/          TagsService(TaxonomyService)
app/modules/categories/    CategoriesService(TaxonomyService)
app/modules/dashboard/     home feed and graph totals
app/static/js/app.js       optimistic actions, loading states, real time
uploads/                   uploaded images (git ignored)
cypher/                    01_schema.cypher, 02_datos.cypher, 03_consultas.cypher (15 queries)
scripts/setup_db.py        loads the .cypher files
tests/                     unit tests and integration tests against Neo4j
docs/                      report, assignment and screenshots
```

## Running it

Requires Neo4j 5.23+ (tested with 2026.10) and Python 3.10+ (tested with 3.12).

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env              # Neo4j password and a JWT_SECRET of 32+ chars

.venv/bin/python -m scripts.setup_db   # WIPES the database, then loads schema and demo data
.venv/bin/python main.py               # http://127.0.0.1:5050
```

Demo users (password `Blog2026!`): `ana.torres@correo.com` (ADMIN), `luis.moreno@correo.com`, `sofia.ramirez@correo.com`.

### Deployment (for the presentation)

It runs on a home server behind Tailscale Funnel: gunicorn with **one** worker and threads (the
event bus lives in memory), `TRUST_PROXY=1` so the CSRF Origin check and secure cookies see HTTPS.

```bash
.venv/bin/gunicorn -w 1 -k gthread --threads 128 -b 127.0.0.1:8795 "app:create_app()"
```

Tests: `.venv/bin/python -m unittest discover tests` (integration tests are skipped when Neo4j is down; they change data, so run `setup_db` again afterwards).
