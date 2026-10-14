"""Retrieve result cache (SSOT §6.7.8). Keys hash the query; values omit query text."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from typing import Any, Protocol

from mts_contracts.knowledge import AppliedFilters, RetrievalResult


def cache_key(
    *,
    tenant_id: str,
    index_revision: str,
    language: str,
    audience: str,
    query: str,
    applied: AppliedFilters,
) -> str:
    payload = "|".join(
        (
            tenant_id,
            index_revision,
            language,
            audience,
            applied.model_dump_json(),
            query,
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"mts-rag:v1:{digest}"


def dump_result(result: RetrievalResult) -> dict[str, Any]:
    data = result.model_dump(mode="json")
    data["query_variants"] = ["cached"]
    return data


def load_result(
    data: Mapping[str, Any], *, variants: tuple[str, ...], duration_ms: int
) -> RetrievalResult:
    payload = dict(data)
    payload["query_variants"] = list(variants)
    payload["duration_ms"] = duration_ms
    return RetrievalResult.model_validate(payload)


class ResultCache(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set(self, key: str, value: Mapping[str, Any], ttl_s: float) -> None: ...


class MemoryResultCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        return dict(payload)

    async def set(self, key: str, value: Mapping[str, Any], ttl_s: float) -> None:
        if ttl_s <= 0:
            return
        self._items[key] = (time.monotonic() + ttl_s, dict(value))


class RedisResultCache:
    """Lazy redis.asyncio client. Missing redis package degrades to no-op."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Any = None
        self._failed = False

    async def _connect(self) -> Any | None:
        if self._failed:
            return None
        if self._client is not None:
            return self._client
        failed = False
        client: Any = None
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(self._url, decode_responses=True)
        except Exception:
            failed = True
        if failed:
            self._failed = True
            return None
        self._client = client
        return self._client

    async def get(self, key: str) -> dict[str, Any] | None:
        client = await self._connect()
        if client is None:
            return None
        raw: Any = None
        failed = False
        try:
            raw = await client.get(key)
        except Exception:
            failed = True
        if failed:
            self._failed = True
            return None
        if not raw:
            return None
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None

    async def set(self, key: str, value: Mapping[str, Any], ttl_s: float) -> None:
        if ttl_s <= 0:
            return
        client = await self._connect()
        if client is None:
            return
        failed = False
        try:
            await client.set(key, json.dumps(value), ex=max(1, int(ttl_s)))
        except Exception:
            failed = True
        if failed:
            self._failed = True

    async def aclose(self) -> None:
        client = self._client
        if client is None:
            return
        with_close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if with_close is not None:
            await with_close()
        self._client = None
