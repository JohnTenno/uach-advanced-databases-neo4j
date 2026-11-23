"""Server-side pagination: the controller counts, this class works out the page, and the
query reads only that page with SKIP/LIMIT. Templates just draw what it computed."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from flask import request


@dataclass(frozen=True)
class Pagination:
    number: int
    size: int
    total: int

    @classmethod
    def from_request(cls, total: int, size: int) -> "Pagination":
        """?page= from the URL, kept between 1 and the last page (a bad value never errors)."""
        pages = max(1, -(-total // size))
        return cls(min(max(request.args.get("page", 1, type=int), 1), pages), size, total)

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.size))

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size

    @property
    def first_item(self) -> int:
        return self.offset + 1 if self.total else 0

    @property
    def last_item(self) -> int:
        return min(self.offset + self.size, self.total)

    @property
    def window(self) -> List[Optional[int]]:
        """Page numbers to show: first, last and two around the current one; None marks a gap.
        Example on page 6 of 12: [1, None, 4, 5, 6, 7, 8, None, 12]."""
        keep = {1, self.pages, *range(self.number - 2, self.number + 3)}
        shown, last = [], 0
        for n in sorted(p for p in keep if 1 <= p <= self.pages):
            if n - last > 1:
                shown.append(None)
            shown.append(n)
            last = n
        return shown
