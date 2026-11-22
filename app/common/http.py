from flask import request


def wants_json() -> bool:
    """API routes, or a page's fetch() call that asked for JSON instead of a new page."""
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"
