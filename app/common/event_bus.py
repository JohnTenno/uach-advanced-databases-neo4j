from __future__ import annotations

import json
import queue
import threading
from typing import Iterator, Set


class EventBus:
    """In-memory pub/sub that feeds the Server-Sent Events stream.

    shortcut: lives in one process, so it needs a single gunicorn worker (threads are fine);
    use Redis pub/sub if the app ever runs several workers.
    """

    def __init__(self, keepalive: float = 25):
        self._lock = threading.Lock()
        self._subscribers: Set[queue.Queue] = set()
        self.keepalive = keepalive

    def publish(self, kind: str, **data) -> None:
        message = f"event: {kind}\ndata: {json.dumps(data)}\n\n"
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(message)
            except queue.Full:
                pass  # a stalled client misses events; its next reload catches up

    def stream(self) -> Iterator[str]:
        subscriber: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(subscriber)
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    yield subscriber.get(timeout=self.keepalive)
                except queue.Empty:
                    yield ": ping\n\n"  # keeps proxies from closing an idle connection
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)


events = EventBus()
