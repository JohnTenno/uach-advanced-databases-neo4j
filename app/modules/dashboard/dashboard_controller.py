from flask import Blueprint, g, render_template, request

from app.modules.articles.articles_service import ArticlesService
from app.modules.auth.jwt_guard import jwt_required
from app.modules.dashboard.dashboard_service import DashboardService
from app.modules.categories.categories_service import CategoriesService
from app.modules.tags.tags_service import TagsService
from app.modules.users.users_service import UsersService

dashboard = Blueprint("dashboard", __name__)
service = DashboardService()
articles = ArticlesService()
users = UsersService()
categories, tags = CategoriesService(), TagsService()
PAGE_SIZE = 10


@dashboard.get("/")
@jwt_required
def index():
    """Home: everyone's published articles, newest first. Optional filters: ?tag=, ?category= and ?q=
    (the top bar search, which also lists matching people)."""
    tag, category = request.args.get("tag", "")[:80], request.args.get("category", "")[:80]
    q = request.args.get("q", "").strip()[:80]
    sort = "popular" if request.args.get("sort") == "popular" else "recent"
    total = articles.count_published(tag, category, q)
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    return render_template("dashboard/index.html", section="home", page=page, pages=pages, total=total,
                           tag=tag, category=category, q=q, sort=sort, people=users.find_all(q, 6) if q else [],
                           feed=articles.find_published(g.user, PAGE_SIZE, (page - 1) * PAGE_SIZE, tag, category, q,
                                                     popular=sort == "popular"),
                           published=articles.count_by_author(g.user.id),
                           drafts=articles.count_by_author(g.user.id, "DRAFT"),
                           stats=users.profile_stats(g.user.id), totals=service.totals(),
                           categories=categories.find_used(), tags=tags.find_used(15))
