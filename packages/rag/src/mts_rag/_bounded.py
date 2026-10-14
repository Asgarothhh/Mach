"""Single-worker executors that degrade immediately when busy."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


class BoundedExecutor:
    """ThreadPoolExecutor with max_workers=1 and in-flight tracking via done-callbacks.

    If a job is already in flight, ``try_submit`` returns None instead of queueing.
    Cancelling the awaiting coroutine does not release the slot; the thread future's
    done-callback does.
    """

    def __init__(self, *, max_workers: int = 1, thread_name_prefix: str = "mts-rag") -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=thread_name_prefix
        )
        self._lock = threading.Lock()
        self._in_flight = 0
        self._capacity = max_workers

    def try_submit(self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T] | None:
        with self._lock:
            if self._in_flight >= self._capacity:
                return None
            self._in_flight += 1
        submitted = False
        try:
            future = self._pool.submit(fn, *args, **kwargs)
            submitted = True
        finally:
            if not submitted:
                with self._lock:
                    self._in_flight -= 1
        future.add_done_callback(self._release)
        return future

    def _release(self, _future: Future[Any]) -> None:
        with self._lock:
            self._in_flight -= 1

    def shutdown(self, *, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=False)
