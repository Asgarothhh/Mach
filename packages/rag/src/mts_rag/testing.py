"""Test doubles for Qdrant hybrid retrieval. Not used in production."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from mts_rag.lexical import lexical_score, tokenize
from mts_rag.qdrant_http import GatewayNotFound, GatewayUnavailable, GatewayVersionUnsupported

_DEFAULT_VERSION = "1.7.4"


class HashingFakeEmbedder:
    """Signed feature hashing over tokenize(), L2-normalized."""

    vector_name: str = "dense_fake_hash64_v1"
    dim: int = 64
    model_revision: str = "fake-hash64"

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
        self.vector_name = f"dense_fake_hash{dim}_v1" if dim != 64 else "dense_fake_hash64_v1"

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        del kind
        return [_hash_vector(text, self.dim) for text in texts]


class FailingEmbedder:
    vector_name: str = "dense_fake_hash64_v1"
    dim: int = 64
    model_revision: str = "failing"

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        del texts, kind
        raise RuntimeError("embedder unavailable")


class SlowEmbedder:
    vector_name: str = "dense_fake_hash64_v1"
    dim: int = 64
    model_revision: str = "slow"

    def __init__(self, delay_s: float = 1.0, dim: int = 64) -> None:
        self.delay_s = delay_s
        self.dim = dim
        self.vector_name = f"dense_fake_hash{dim}_v1" if dim != 64 else "dense_fake_hash64_v1"

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        time.sleep(self.delay_s)
        return [_hash_vector(text, self.dim) for text in texts]


class FakeReranker:
    model_revision: str = "fake-overlap"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        query_terms = frozenset(tokenize(query))
        return [lexical_score(query_terms, frozenset(tokenize(doc))) for doc in documents]


class FailingReranker:
    model_revision: str = "failing"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        del query, documents
        raise RuntimeError("reranker unavailable")


class SlowReranker:
    model_revision: str = "slow"

    def __init__(self, delay_s: float = 1.0) -> None:
        self.delay_s = delay_s

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        time.sleep(self.delay_s)
        query_terms = frozenset(tokenize(query))
        return [lexical_score(query_terms, frozenset(tokenize(doc))) for doc in documents]


def matches_filter(payload: Mapping[str, Any], clause: Mapping[str, Any]) -> bool:
    """Evaluate the Qdrant filter DSL subset used by QdrantHybridRetriever."""
    if "must" in clause or "should" in clause or "must_not" in clause:
        must = clause.get("must")
        if isinstance(must, list) and not all(
            matches_filter(payload, item) for item in must if isinstance(item, Mapping)
        ):
            return False
        should = clause.get("should")
        if (
            isinstance(should, list)
            and should
            and not any(
                matches_filter(payload, item) for item in should if isinstance(item, Mapping)
            )
        ):
            return False
        must_not = clause.get("must_not")
        return not (
            isinstance(must_not, list)
            and any(matches_filter(payload, item) for item in must_not if isinstance(item, Mapping))
        )
    if "nested" in clause:
        spec = clause["nested"]
        if not isinstance(spec, Mapping):
            return False
        key = spec.get("key")
        nested_filter = spec.get("filter")
        if not isinstance(key, str) or not isinstance(nested_filter, Mapping):
            return False
        nested_payload = payload.get(key)
        if isinstance(nested_payload, Mapping):
            return matches_filter(nested_payload, nested_filter)
        if isinstance(nested_payload, list):
            return any(
                isinstance(item, Mapping) and matches_filter(item, nested_filter)
                for item in nested_payload
            )
        return False
    if "is_null" in clause:
        spec = clause["is_null"]
        key = spec["key"] if isinstance(spec, Mapping) else None
        if not isinstance(key, str):
            return False
        return payload.get(key) is None
    key = clause.get("key")
    if not isinstance(key, str):
        return False
    if "match" in clause:
        match = clause["match"]
        if not isinstance(match, Mapping):
            return False
        value = payload.get(key)
        if "value" in match:
            return bool(value == match["value"])
        if "any" in match:
            options = match["any"]
            return isinstance(options, list) and value in options
        return False
    if "range" in clause:
        value = payload.get(key)
        if value is None or not isinstance(value, int | float):
            return False
        bounds = clause["range"]
        if not isinstance(bounds, Mapping):
            return False
        if "gt" in bounds and not value > bounds["gt"]:
            return False
        if "gte" in bounds and not value >= bounds["gte"]:
            return False
        if "lt" in bounds and not value < bounds["lt"]:
            return False
        if "lte" in bounds:
            return bool(value <= bounds["lte"])
        return True
    return False


class InMemoryQdrantGateway:
    """In-process QdrantGateway: collections, aliases, cosine/dot search, filter DSL."""

    def __init__(self, *, version: str = _DEFAULT_VERSION) -> None:
        self.version = version
        self.down = False
        self.drop_points = False
        self.foreign_payload = False
        self._fail_remaining = 0
        self._collections: dict[str, _Collection] = {}
        self._aliases: dict[str, str] = {}
        self.captured_searches: list[dict[str, Any]] = []

    def fail_next(self, count: int = 1) -> None:
        self._fail_remaining = count

    async def get_version(self) -> str:
        self._before()
        if not _version_ok(self.version):
            raise GatewayVersionUnsupported()
        return self.version

    async def get_collection(self, name: str) -> dict[str, Any]:
        self._before()
        collection = self._collections.get(name)
        if collection is None:
            raise GatewayNotFound()
        return {"config": {"params": collection.config}}

    async def put_collection(self, name: str, body: dict[str, Any]) -> None:
        self._before()
        existing = self._collections.get(name)
        points = existing.points if existing is not None else {}
        self._collections[name] = _Collection(config=dict(body), points=points)

    async def delete_collection(self, name: str) -> None:
        self._before()
        self._collections.pop(name, None)
        stale = [alias for alias, target in self._aliases.items() if target == name]
        for alias in stale:
            del self._aliases[alias]

    async def put_index(self, collection: str, body: dict[str, Any]) -> None:
        self._before()
        if collection not in self._collections:
            raise GatewayNotFound()
        del body

    async def upsert_points(self, collection: str, points: list[dict[str, Any]]) -> None:
        self._before()
        stored = self._collections.get(collection)
        if stored is None:
            raise GatewayNotFound()
        if self.drop_points:
            return
        for point in points:
            point_id = str(point["id"])
            stored.points[point_id] = {
                "id": point_id,
                "vector": dict(point.get("vector") or {}),
                "payload": dict(point.get("payload") or {}),
            }

    async def search_batch(
        self, collection: str, searches: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        self._before()
        stored = self._collections.get(collection)
        if stored is None:
            raise GatewayNotFound()
        out: list[list[dict[str, Any]]] = []
        for search in searches:
            self.captured_searches.append(search)
            out.append(self._search_one(stored, search))
        return out

    async def count(self, collection: str, body: dict[str, Any]) -> int:
        self._before()
        stored = self._collections.get(collection)
        if stored is None:
            raise GatewayNotFound()
        clause = body.get("filter") if isinstance(body.get("filter"), Mapping) else None
        total = 0
        for point in stored.points.values():
            payload = point["payload"]
            if clause is None or matches_filter(payload, clause):
                total += 1
        return total

    async def scroll(self, collection: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        self._before()
        stored = self._collections.get(collection)
        if stored is None:
            raise GatewayNotFound()
        limit = int(body.get("limit") or 100)
        return [
            {"id": point["id"], "payload": dict(point["payload"])}
            for point in list(stored.points.values())[:limit]
        ]

    async def list_collections(self) -> list[str]:
        self._before()
        return sorted(self._collections)

    async def get_aliases(self) -> list[dict[str, str]]:
        self._before()
        return [
            {"alias_name": alias, "collection_name": target}
            for alias, target in sorted(self._aliases.items())
        ]

    async def post_aliases(self, actions: list[dict[str, Any]]) -> None:
        self._before()
        pending = dict(self._aliases)
        for action in actions:
            if "delete_alias" in action:
                alias = str(action["delete_alias"]["alias_name"])
                pending.pop(alias, None)
            elif "create_alias" in action:
                spec = action["create_alias"]
                pending[str(spec["alias_name"])] = str(spec["collection_name"])
        self._aliases = pending

    async def aclose(self) -> None:
        return None

    def _before(self) -> None:
        if self.down:
            raise GatewayUnavailable()
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise GatewayUnavailable()

    def _search_one(self, stored: _Collection, search: Mapping[str, Any]) -> list[dict[str, Any]]:
        vector_spec = search.get("vector")
        if not isinstance(vector_spec, Mapping):
            return []
        name = str(vector_spec.get("name") or "")
        raw = vector_spec.get("vector")
        limit = int(search.get("limit") or 10)
        clause = search.get("filter") if isinstance(search.get("filter"), Mapping) else None
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for point in stored.points.values():
            payload = dict(point["payload"])
            if clause is not None and not matches_filter(payload, clause):
                continue
            stored_vector = point["vector"].get(name)
            score = _score_vector(raw, stored_vector)
            if self.foreign_payload:
                payload["tenant_id"] = "foreign-tenant"
            scored.append((score, str(point["id"]), payload))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            {"id": point_id, "score": score, "payload": payload}
            for score, point_id, payload in scored[:limit]
        ]


class _Collection:
    def __init__(self, *, config: dict[str, Any], points: dict[str, dict[str, Any]]) -> None:
        self.config = config
        self.points = points


def _hash_vector(text: str, dim: int) -> list[float]:
    import hashlib

    vec = [0.0] * dim
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[index] += sign
    norm = math.sqrt(sum(value * value for value in vec))
    if norm > 0.0:
        vec = [value / norm for value in vec]
    return vec


def _score_vector(query: Any, stored: Any) -> float:
    if stored is None:
        return 0.0
    if isinstance(query, Mapping) and "indices" in query:
        q_map = {
            int(idx): float(val)
            for idx, val in zip(query.get("indices") or [], query.get("values") or [], strict=False)
        }
        if isinstance(stored, Mapping):
            s_indices = stored.get("indices") or []
            s_values = stored.get("values") or []
            s_map = {int(idx): float(val) for idx, val in zip(s_indices, s_values, strict=False)}
        else:
            return 0.0
        return math.fsum(q_map[idx] * s_map[idx] for idx in q_map if idx in s_map)
    if not isinstance(query, list) or not isinstance(stored, list):
        return 0.0
    if not query or not stored or len(query) != len(stored):
        return 0.0
    dot = math.fsum(float(a) * float(b) for a, b in zip(query, stored, strict=True))
    qn = math.sqrt(math.fsum(float(a) * float(a) for a in query))
    sn = math.sqrt(math.fsum(float(b) * float(b) for b in stored))
    if qn == 0.0 or sn == 0.0:
        return 0.0
    return dot / (qn * sn)


def _version_ok(version: str) -> bool:
    from mts_rag.qdrant_http import version_supported

    return version_supported(version)
