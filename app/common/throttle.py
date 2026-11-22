"""Fixed window rate limit, like @Throttle in Nest."""
from __future__ import annotations

import time
from collections import defaultdict
from functools import wraps

from flask import request

from app.common.errors import AppError


class TooManyRequestsError(AppError):
    status = 429

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


# shortcut: counters live in process memory, fine for one dev server; move to Redis if deployed with workers.
_hits = defaultdict(list)


def throttle(limit: int, seconds: int):
    def decorator(view):
        @wraps(view)
        def limited(*args, **kwargs):
            if request.method == "POST":
                key = (view.__name__, request.remote_addr)
                now = time.monotonic()
                _hits[key] = [t for t in _hits[key] if now - t < seconds]
                if len(_hits[key]) >= limit:
                    wait = int(seconds - (now - _hits[key][0])) + 1
                    raise TooManyRequestsError(f"Demasiados intentos. Espera {wait} segundos.", wait)
                _hits[key].append(now)
            return view(*args, **kwargs)
        return limited
    return decorator
