"""Qdrant hybrid KnowledgeRetriever (SSOT §6.7, §6.9, §14.2)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import re
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from mts_contracts.knowledge import (
    ACTIVE_INDEX_REVISION,
    CandidateDiagnostics,
    ChunkMetadata,
    DegradationReason,
    EvidenceStatus,
    FilterExclusionReason,
    Identifier,
    IndexRevisionNotFound,
    RetrievalConfig,
    RetrievalDeadlineExceeded,
    RetrievalFilters,
    RetrievalMode,
    RetrievalResult,
    RetrievalUnavailable,
    RetrievedChunk,
    StaleReason,
    TenantId,
    TenantIsolationError,
)
from pydantic import TypeAdapter, ValidationError

from mts_rag._bounded import BoundedExecutor
from mts_rag._request import _parse_request, _snippet, _utc_now
from mts_rag.cache import (
    MemoryResultCache,
    ResultCache,
    cache_key,
    dump_result,
    load_result,
)
from mts_rag.embeddings import DenseEmbedder
from mts_rag.evidence import compute_evidence_status, detect_conflicts
from mts_rag.filters import ResolvedFilter, resolve_filters, scope_exclusion, temporal_exclusion
from mts_rag.fusion import FusedItem, reciprocal_rank_fusion
from mts_rag.lexical import index_terms, query_terms, term_coverage
from mts_rag.qdrant_http import (
    GatewayNotFound,
    GatewayUnavailable,
    GatewayVersionUnsupported,
    QdrantGateway,
)
from mts_rag.query import query_variants
from mts_rag.rerank import Reranker
from mts_rag.sparse import (
    SPARSE_VECTOR_NAME,
    Bm25HashSparseEncoder,
    chunk_terms,
    chunk_token_list,
    document_text,
)

logger = logging.getLogger("mts_rag.qdrant")

PAYLOAD_SCHEMA = 1
_REVISION_NOT_FOUND = "index revision not found"
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_STATUSES_WITH_CHUNKS = frozenset({EvidenceStatus.SUFFICIENT, EvidenceStatus.EVIDENCE_CONFLICT})
_KEYWORD_INDEXES = (
    "tenant_id",
    "language",
    "audience",
    "effective_status",
    "service",
    "topic",
    "source_type",
    "document_id",
)
_INT_INDEXES = ("valid_from_us", "valid_to_us")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MTS_RAG_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://mts.by/rag/chunk-id")
_TENANT_ID_ADAPTER: TypeAdapter[str] = TypeAdapter(TenantId)
_IDENTIFIER_ADAPTER: TypeAdapter[str] = TypeAdapter(Identifier)


class IndexPublishError(Exception):
    """Publish smoke checks failed; the active alias is left unchanged."""


@dataclass(frozen=True, slots=True)
class QdrantRetrieverSettings:
    config: RetrievalConfig = field(default_factory=RetrievalConfig)
    collection_prefix: str = "kb"
    min_term_coverage: float = 0.5
    min_dense_score: float = 0.55
    min_rerank_score: float = 0.5
    embed_timeout_ms: int = 180
    rerank_timeout_ms: int = 80
    rerank_min_remaining_ms: int = 30
    alias_cache_ttl_s: float = 2.0
    health_timeout_s: float = 1.0
    cache_ttl_s: float = 30.0
    keep_revisions: int = 2
    exclusion_scroll_limit: int = 2000

    def __post_init__(self) -> None:
        for name, value, low, high in (
            ("min_term_coverage", self.min_term_coverage, 0.0, 1.0),
            ("min_dense_score", self.min_dense_score, 0.0, 1.0),
            ("min_rerank_score", self.min_rerank_score, 0.0, 1.0),
            ("alias_cache_ttl_s", self.alias_cache_ttl_s, 0.0, 60.0),
            ("health_timeout_s", self.health_timeout_s, 0.1, 30.0),
            ("cache_ttl_s", self.cache_ttl_s, 0.0, 3600.0),
        ):
            if not (math.isfinite(value) and low <= value <= high):
                raise ValueError(f"{name} must be within [{low}, {high}]")
        for name, value in (
            ("embed_timeout_ms", self.embed_timeout_ms),
            ("rerank_timeout_ms", self.rerank_timeout_ms),
            ("rerank_min_remaining_ms", self.rerank_min_remaining_ms),
            ("keep_revisions", self.keep_revisions),
            ("exclusion_scroll_limit", self.exclusion_scroll_limit),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1")
        if not self.collection_prefix or any(ch in self.collection_prefix for ch in ":/"):
            raise ValueError("collection_prefix is invalid")


@dataclass
class _MergedHit:
    chunk: ChunkMetadata
    dense_rank: int | None = None
    dense_score: float | None = None
    sparse_rank: int | None = None
    sparse_score: float | None = None


@dataclass(frozen=True)
class _RankedList:
    pairs: tuple[tuple[ChunkMetadata, float], ...]
    ran: bool
    reason: DegradationReason | None = None


class QdrantHybridRetriever:
    """Dense + sparse retrieval in Qdrant with client-side RRF and optional rerank."""

    def __init__(
        self,
        gateway: QdrantGateway,
        *,
        embedder: DenseEmbedder | None = None,
        reranker: Reranker | None = None,
        settings: QdrantRetrieverSettings | None = None,
        cache: ResultCache | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._gateway = gateway
        self._embedder = embedder
        self._reranker = reranker
        self._settings = settings if settings is not None else QdrantRetrieverSettings()
        self._cache = cache if cache is not None else MemoryResultCache()
        self._clock = clock
        self._now = now
        self._sparse = Bm25HashSparseEncoder()
        self._embed_pool = BoundedExecutor(max_workers=1, thread_name_prefix="mts-rag-embed")
        self._rerank_pool = BoundedExecutor(max_workers=1, thread_name_prefix="mts-rag-rerank")
        self._alias_cache: dict[str, tuple[float, str]] = {}
        self._collection_cache: dict[str, dict[str, Any]] = {}
        self._version_ok: bool | None = None

    @property
    def settings(self) -> QdrantRetrieverSettings:
        return self._settings

    def set_embedder(self, embedder: DenseEmbedder | None) -> None:
        self._embedder = embedder

    async def publish(
        self,
        tenant_id: str,
        index_revision: str,
        chunks: Iterable[ChunkMetadata],
        *,
        activate: bool = True,
    ) -> None:
        await self._ensure_version()
        snapshot = self._validate_publish(tenant_id, index_revision, chunks)
        collection = self._collection_name(tenant_id, index_revision)
        token_docs = [chunk_token_list(chunk) for chunk in snapshot]
        stats = self._sparse.fit(token_docs)
        sparse_vectors = [self._sparse.encode_document(tokens, stats) for tokens in token_docs]
        dense_vectors = await self._embed_documents(snapshot)
        exists = await self._collection_exists(collection)
        if not exists:
            await self._create_collection(collection, dense_vectors is not None)
        elif dense_vectors is not None:
            info = await self._collection_info(collection)
            embedder = self._embedder
            if embedder is None or not _collection_has_dense(
                info, embedder.vector_name, embedder.dim
            ):
                raise IndexPublishError("index schema mismatch")
        points: list[dict[str, Any]] = []
        for index, chunk in enumerate(snapshot):
            vector: dict[str, Any] = {
                SPARSE_VECTOR_NAME: {
                    "indices": sparse_vectors[index].indices,
                    "values": sparse_vectors[index].values,
                }
            }
            if dense_vectors is not None and self._embedder is not None:
                vector[self._embedder.vector_name] = dense_vectors[index]
            payload = chunk.model_dump(mode="json")
            payload["valid_from_us"] = _datetime_to_us(chunk.valid_from)
            payload["valid_to_us"] = _datetime_to_us(chunk.valid_to)
            payload["payload_schema"] = PAYLOAD_SCHEMA
            points.append(
                {
                    "id": str(uuid.uuid5(MTS_RAG_NS, f"{tenant_id}|{chunk.chunk_id}")),
                    "vector": vector,
                    "payload": payload,
                }
            )
        upsert_failed = False
        try:
            await self._gateway.upsert_points(collection, points)
        except GatewayUnavailable:
            upsert_failed = True
        if upsert_failed:
            raise IndexPublishError("index publish failed")
        smoke_failed = False
        try:
            await self._smoke(collection, tenant_id, snapshot)
        except IndexPublishError:
            smoke_failed = True
        if smoke_failed:
            await self._delete_if_unaliased(collection)
            raise IndexPublishError("index publish smoke failed")
        self._collection_cache.pop(collection, None)
        if activate:
            await self.activate(tenant_id, index_revision)
        logger.info(
            "index_published",
            extra={
                "tenant_id": tenant_id,
                "index_revision": index_revision,
                "points": len(snapshot),
            },
        )

    async def activate(self, tenant_id: str, index_revision: str) -> None:
        await self._ensure_version()
        collection = self._collection_name(tenant_id, index_revision)
        missing = False
        try:
            info = await self._gateway.get_collection(collection)
        except GatewayNotFound:
            missing = True
            info = None
        except GatewayUnavailable:
            raise RetrievalUnavailable("retrieval unavailable") from None
        if missing or info is None:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        alias = self._alias_name(tenant_id)
        aliases: list[dict[str, str]] = []
        alias_failed = False
        try:
            aliases = await self._gateway.get_aliases()
        except GatewayUnavailable:
            alias_failed = True
        if alias_failed:
            raise RetrievalUnavailable("retrieval unavailable")
        current = next(
            (item["collection_name"] for item in aliases if item["alias_name"] == alias),
            None,
        )
        if current != collection:
            actions: list[dict[str, Any]] = []
            if current is not None:
                actions.append({"delete_alias": {"alias_name": alias}})
            actions.append({"create_alias": {"collection_name": collection, "alias_name": alias}})
            switch_failed = False
            try:
                await self._gateway.post_aliases(actions)
            except GatewayUnavailable:
                switch_failed = True
            if switch_failed:
                raise RetrievalUnavailable("retrieval unavailable")
        self._alias_cache[tenant_id] = (self._clock(), collection)
        keep = {collection}
        if current is not None and self._settings.keep_revisions >= 2:
            keep.add(current)
        await self._gc_old_revisions(tenant_id, keep=keep)
        logger.info(
            "index_activated",
            extra={"tenant_id": tenant_id, "index_revision": index_revision},
        )

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        language: str,
        audience: str,
        filters: RetrievalFilters,
        index_revision: str,
        deadline_ms: int,
    ) -> RetrievalResult:
        started = self._clock()
        settings = self._settings
        config = settings.config
        request = _parse_request(
            {
                "query": query,
                "tenant_id": tenant_id,
                "language": language,
                "audience": audience,
                "filters": filters,
                "index_revision": index_revision,
                "deadline_ms": deadline_ms,
            },
            max_query_chars=config.max_query_chars,
        )
        deadline = request.deadline_ms
        children: list[asyncio.Task[Any]] = []
        try:
            self._elapsed_ms(started, deadline)
            await asyncio.sleep(0)
            await self._ensure_version()
            collection, resolved_revision = await self._resolve_revision(
                request.tenant_id, request.index_revision
            )
            info = await self._collection_info(collection)
            self._elapsed_ms(started, deadline)
            await asyncio.sleep(0)
            resolved = resolve_filters(
                request.filters,
                tenant_id=request.tenant_id,
                language=request.language,
                audience=request.audience,
                now=self._now(),
            )
            variants = query_variants(request.query, max_query_variants=config.max_query_variants)
            if settings.cache_ttl_s > 0:
                key = cache_key(
                    tenant_id=request.tenant_id,
                    index_revision=resolved_revision,
                    language=request.language,
                    audience=str(request.audience),
                    query=request.query,
                    applied=resolved.applied,
                )
                cached_payload = await self._cache.get(key)
                if cached_payload is not None:
                    duration_ms = self._elapsed_ms(started, deadline)
                    return load_result(cached_payload, variants=variants, duration_ms=duration_ms)
            query_filter = build_search_filter(resolved, request.tenant_id, outdated=False)
            outdated_filter = build_search_filter(resolved, request.tenant_id, outdated=True)
            remaining_s = self._remaining_s(started, deadline)
            sparse_task = asyncio.create_task(
                self._sparse_branch(
                    collection,
                    variants,
                    query_filter,
                    outdated_filter,
                    config.sparse_top_k,
                    remaining_s,
                    request.tenant_id,
                    resolved,
                )
            )
            children.append(sparse_task)
            dense_task = asyncio.create_task(
                self._dense_branch(
                    collection,
                    info,
                    variants,
                    query_filter,
                    config.dense_top_k,
                    remaining_s,
                    request.tenant_id,
                    resolved,
                    started,
                    deadline,
                )
            )
            children.append(dense_task)
            sparse_lists, sparse_ran, sparse_reason, outdated_hits = await sparse_task
            dense_lists, dense_ran, dense_reason = await dense_task
            self._elapsed_ms(started, deadline)
            await asyncio.sleep(0)
            if not sparse_ran and not dense_ran:
                raise RetrievalUnavailable("retrieval unavailable")
            degraded: list[DegradationReason] = []
            if sparse_reason is not None:
                degraded.append(sparse_reason)
            if dense_reason is not None:
                degraded.append(dense_reason)
            if dense_ran and sparse_ran:
                mode = RetrievalMode.HYBRID
            elif sparse_ran:
                mode = RetrievalMode.SPARSE_ONLY
            else:
                mode = RetrievalMode.DENSE_ONLY
            merged = _merge_hits(sparse_lists, dense_lists)
            rankings = [[chunk.chunk_id for chunk, _score in lst] for lst in sparse_lists]
            rankings.extend([chunk.chunk_id for chunk, _score in lst] for lst in dense_lists)
            fused_items = reciprocal_rank_fusion(rankings, k=config.rrf_k, top_k=config.rrf_top_k)
            fused = {item.id: item for item in fused_items}
            rerank_scores, reranked_order, rerank_degraded = await self._maybe_rerank(
                request.query,
                fused_items,
                merged,
                started,
                deadline,
            )
            if rerank_degraded is not None:
                degraded.append(rerank_degraded)
            ordered_ids = (
                reranked_order if reranked_order is not None else [item.id for item in fused_items]
            )
            content_terms = query_terms(request.query)
            relevant: list[tuple[float, ChunkMetadata]] = []
            for chunk_id in ordered_ids:
                hit = merged.get(chunk_id)
                if hit is None:
                    continue
                if not _is_candidate(hit, settings.min_dense_score):
                    continue
                rerank_score = rerank_scores.get(chunk_id)
                if not _is_relevant(hit, content_terms, rerank_score, settings):
                    continue
                fused_item = fused.get(chunk_id)
                if fused_item is None:
                    continue
                score = rerank_score if rerank_score is not None else fused_item.score
                relevant.append((score, hit.chunk))
            outdated_matches = sum(
                1
                for chunk, _score in outdated_hits
                if term_coverage(content_terms, chunk_terms(chunk)) >= settings.min_term_coverage
            )
            excluded_counts = await self._excluded_counts(
                collection, request.tenant_id, resolved, started, deadline
            )
            conflicts = detect_conflicts(chunk for _, chunk in relevant)
            selected = relevant[: config.context_top_k]
            reference_time = resolved.reference_time
            stale_after = config.stale_after
            stale_ids = (
                {
                    chunk.chunk_id
                    for _, chunk in selected
                    if reference_time - chunk.crawled_at > stale_after
                }
                if stale_after is not None
                else set()
            )
            evidence_status = compute_evidence_status(
                has_candidates=any(
                    _is_candidate(hit, settings.min_dense_score) for hit in merged.values()
                ),
                relevant_count=len(relevant),
                outdated_matches=outdated_matches,
                has_conflicts=bool(conflicts),
                all_selected_stale=bool(selected) and len(stale_ids) == len(selected),
            )
            returned = selected if evidence_status in _STATUSES_WITH_CHUNKS else []
            if any(chunk.tenant_id != request.tenant_id for _, chunk in returned):
                raise TenantIsolationError(
                    "retrieved chunk does not belong to the requesting tenant"
                )
            returned_ids = {chunk.chunk_id for _, chunk in returned}
            diagnostics = _build_diagnostics(
                merged, fused, rerank_scores, returned_ids, settings.min_dense_score
            )
            retrieved = tuple(
                RetrievedChunk(
                    rank=rank,
                    score=score,
                    snippet=_snippet(chunk.text, config.snippet_max_chars),
                    metadata=chunk,
                    is_stale=chunk.chunk_id in stale_ids,
                    stale_reasons=(
                        (StaleReason.CRAWL_AGE_EXCEEDED,) if chunk.chunk_id in stale_ids else ()
                    ),
                )
                for rank, (score, chunk) in enumerate(returned, start=1)
            )
            duration_ms = self._elapsed_ms(started, deadline)
            top_score = _top_score(
                ordered_ids, merged, fused, rerank_scores, settings.min_dense_score
            )
            logger.info(
                "retrieve_complete",
                extra={
                    "tenant_id": request.tenant_id,
                    "index_revision": resolved_revision,
                    "retrieval_mode": mode.value,
                    "degraded": tuple(
                        reason.value for reason in sorted(set(degraded), key=lambda r: r.value)
                    ),
                    "candidates": len(diagnostics),
                    "chunks": len(retrieved),
                    "duration_ms": duration_ms,
                    "error_class": "",
                },
            )
            result: RetrievalResult | None = None
            with contextlib.suppress(ValidationError):
                result = RetrievalResult(
                    tenant_id=request.tenant_id,
                    index_revision=resolved_revision,
                    retrieval_mode=mode,
                    config_version=config.version,
                    query_variants=variants,
                    applied_filters=resolved.applied,
                    candidates=diagnostics,
                    chunks=retrieved,
                    evidence_status=evidence_status,
                    top_score=top_score,
                    conflicts=conflicts
                    if evidence_status is EvidenceStatus.EVIDENCE_CONFLICT
                    else (),
                    outdated_matches=outdated_matches,
                    excluded_counts=excluded_counts,
                    degraded=tuple(sorted(set(degraded), key=lambda reason: reason.value)),
                    duration_ms=duration_ms,
                )
            if result is None:
                if any(chunk.metadata.tenant_id != request.tenant_id for chunk in retrieved):
                    raise TenantIsolationError(
                        "retrieved chunk does not belong to the requesting tenant"
                    )
                raise RetrievalUnavailable("retrieval result failed validation")
            if settings.cache_ttl_s > 0 and not result.degraded:
                await self._cache.set(
                    cache_key(
                        tenant_id=request.tenant_id,
                        index_revision=resolved_revision,
                        language=request.language,
                        audience=str(request.audience),
                        query=request.query,
                        applied=resolved.applied,
                    ),
                    dump_result(result),
                    settings.cache_ttl_s,
                )
            return result
        finally:
            for task in children:
                if not task.done():
                    task.cancel()
            if children:
                await asyncio.gather(*children, return_exceptions=True)

    async def health(self, tenant_id: str) -> dict[str, str]:
        qdrant = "unavailable"
        alias = "missing"
        points = "0"
        version_failed = False
        unsupported = False
        try:
            await self._gateway.get_version()
        except GatewayVersionUnsupported:
            unsupported = True
        except GatewayUnavailable:
            version_failed = True
        if unsupported:
            return {"qdrant": "version_unsupported", "alias": alias, "points": points}
        if version_failed:
            return {"qdrant": qdrant, "alias": alias, "points": points}
        qdrant = "ok"
        resolve_failed = False
        collection = ""
        try:
            collection, _revision = await self._resolve_revision(tenant_id, ACTIVE_INDEX_REVISION)
        except (IndexRevisionNotFound, GatewayNotFound, GatewayUnavailable):
            resolve_failed = True
        if resolve_failed or not collection:
            return {"qdrant": qdrant, "alias": alias, "points": points}
        alias = "ok"
        count_failed = False
        count = 0
        try:
            count = await self._gateway.count(collection, {"exact": True})
        except (GatewayNotFound, GatewayUnavailable):
            count_failed = True
        if count_failed:
            return {"qdrant": qdrant, "alias": alias, "points": points}
        return {"qdrant": qdrant, "alias": alias, "points": str(count)}

    async def aclose(self) -> None:
        self._embed_pool.shutdown(wait=False)
        self._rerank_pool.shutdown(wait=False)
        cache_close = getattr(self._cache, "aclose", None)
        if cache_close is not None:
            await cache_close()
        closer = getattr(self._gateway, "aclose", None)
        if closer is not None:
            await closer()

    async def _gc_old_revisions(self, tenant_id: str, *, keep: set[str]) -> None:
        prefix = f"{self._settings.collection_prefix}__{tenant_id}__"
        names: list[str] = []
        list_failed = False
        try:
            names = await self._gateway.list_collections()
        except GatewayUnavailable:
            list_failed = True
        if list_failed:
            return
        extras = [name for name in names if name.startswith(prefix) and name not in keep]
        for name in extras:
            await self._delete_if_unaliased(name)
            self._collection_cache.pop(name, None)

    async def _excluded_counts(
        self,
        collection: str,
        tenant_id: str,
        resolved: ResolvedFilter,
        started: float,
        deadline_ms: int,
    ) -> tuple[tuple[FilterExclusionReason, int], ...]:
        remaining = deadline_ms - (self._clock() - started) * 1000.0
        if remaining < 20:
            return ()
        failed = False
        points: list[dict[str, Any]] = []
        try:
            async with asyncio.timeout(min(remaining / 1000.0, 0.08)):
                points = await self._gateway.scroll(
                    collection,
                    {
                        "limit": self._settings.exclusion_scroll_limit,
                        "with_payload": True,
                        "with_vector": False,
                        "filter": {"must": [{"key": "tenant_id", "match": {"value": tenant_id}}]},
                    },
                )
        except (TimeoutError, GatewayUnavailable, GatewayNotFound):
            failed = True
        except asyncio.CancelledError:
            raise
        if failed:
            return ()
        counts: Counter[FilterExclusionReason] = Counter()
        isolation = False
        for point in points:
            payload = point.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("tenant_id") != tenant_id:
                isolation = True
                break
            chunk_failed = False
            chunk: ChunkMetadata | None = None
            try:
                fields = {key: payload[key] for key in ChunkMetadata.model_fields}
                chunk = ChunkMetadata.model_validate(fields)
            except (KeyError, ValidationError, TypeError, ValueError):
                chunk_failed = True
            if chunk_failed or chunk is None:
                continue
            reason = scope_exclusion(chunk, resolved) or temporal_exclusion(chunk, resolved)
            if reason is not None:
                counts[reason] += 1
        if isolation:
            raise TenantIsolationError("retrieved chunk does not belong to the requesting tenant")
        return tuple(
            (reason, count)
            for reason, count in sorted(counts.items(), key=lambda item: item[0].value)
            if count >= 1
        )

    def _validate_publish(
        self, tenant_id: str, index_revision: str, chunks: Iterable[ChunkMetadata]
    ) -> tuple[ChunkMetadata, ...]:
        tenant_invalid = False
        try:
            _TENANT_ID_ADAPTER.validate_python(tenant_id, strict=True)
        except ValidationError:
            tenant_invalid = True
        if tenant_invalid:
            raise ValueError("invalid tenant_id")
        revision_invalid = False
        try:
            _IDENTIFIER_ADAPTER.validate_python(index_revision, strict=True)
        except ValidationError:
            revision_invalid = True
        if (
            revision_invalid
            or index_revision == ACTIVE_INDEX_REVISION
            or ":" in index_revision
            or _REVISION_RE.match(index_revision) is None
        ):
            if index_revision == ACTIVE_INDEX_REVISION:
                raise ValueError(f"index revision name {ACTIVE_INDEX_REVISION!r} is reserved")
            raise ValueError("invalid index revision")
        snapshot = tuple(chunks)
        if any(chunk.tenant_id != tenant_id for chunk in snapshot):
            raise TenantIsolationError("chunk tenant does not match the target tenant")
        chunk_ids = [chunk.chunk_id for chunk in snapshot]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("duplicate chunk_id in index revision")
        return snapshot

    def _collection_name(self, tenant_id: str, index_revision: str) -> str:
        return f"{self._settings.collection_prefix}__{tenant_id}__{index_revision}"

    def _alias_name(self, tenant_id: str) -> str:
        return f"{self._settings.collection_prefix}__{tenant_id}__{ACTIVE_INDEX_REVISION}"

    async def _ensure_version(self) -> None:
        if self._version_ok is True:
            return
        unsupported = False
        failed = False
        try:
            await self._gateway.get_version()
        except GatewayVersionUnsupported:
            unsupported = True
        except GatewayUnavailable:
            failed = True
        if unsupported or failed:
            self._version_ok = False
            raise RetrievalUnavailable("retrieval unavailable")
        self._version_ok = True

    async def _resolve_revision(self, tenant_id: str, index_revision: str) -> tuple[str, str]:
        if index_revision != ACTIVE_INDEX_REVISION:
            return self._collection_name(tenant_id, index_revision), index_revision
        expected_prefix = f"{self._settings.collection_prefix}__{tenant_id}__"
        cached = self._alias_cache.get(tenant_id)
        collection: str | None = None
        if cached is not None and (self._clock() - cached[0]) < self._settings.alias_cache_ttl_s:
            collection = cached[1]
        else:
            failed = False
            aliases: list[dict[str, str]] = []
            try:
                aliases = await self._gateway.get_aliases()
            except GatewayUnavailable:
                failed = True
            if failed:
                raise RetrievalUnavailable("retrieval unavailable")
            alias = self._alias_name(tenant_id)
            collection = next(
                (item["collection_name"] for item in aliases if item["alias_name"] == alias),
                None,
            )
            if collection is not None:
                self._alias_cache[tenant_id] = (self._clock(), collection)
        if collection is None:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        if not collection.startswith(expected_prefix):
            logger.info("tenant_alias_mismatch", extra={"tenant_id": tenant_id})
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        resolved = collection[len(expected_prefix) :]
        if not resolved:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        return collection, resolved

    async def _collection_info(self, name: str) -> dict[str, Any]:
        cached = self._collection_cache.get(name)
        if cached is not None:
            return cached
        missing = False
        failed = False
        info: dict[str, Any] | None = None
        try:
            info = await self._gateway.get_collection(name)
        except GatewayNotFound:
            missing = True
        except GatewayUnavailable:
            failed = True
        if missing:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        if failed or info is None:
            raise RetrievalUnavailable("retrieval unavailable")
        self._collection_cache[name] = info
        return info

    async def _collection_exists(self, name: str) -> bool:
        missing = False
        failed = False
        try:
            await self._gateway.get_collection(name)
        except GatewayNotFound:
            missing = True
        except GatewayUnavailable:
            failed = True
        if failed:
            raise IndexPublishError("index publish failed")
        return not missing

    async def _create_collection(self, name: str, with_dense: bool) -> None:
        vectors: dict[str, Any] = {}
        if with_dense and self._embedder is not None:
            vectors[self._embedder.vector_name] = {
                "size": self._embedder.dim,
                "distance": "Cosine",
            }
        body = {"vectors": vectors, "sparse_vectors": {SPARSE_VECTOR_NAME: {}}}
        failed = False
        try:
            await self._gateway.put_collection(name, body)
            for field_name in _KEYWORD_INDEXES:
                await self._gateway.put_index(
                    name, {"field_name": field_name, "field_schema": "keyword"}
                )
            for field_name in _INT_INDEXES:
                await self._gateway.put_index(
                    name, {"field_name": field_name, "field_schema": "integer"}
                )
        except GatewayUnavailable:
            failed = True
        if failed:
            raise IndexPublishError("index publish failed")

    async def _embed_documents(self, chunks: Sequence[ChunkMetadata]) -> list[list[float]] | None:
        if self._embedder is None or not chunks:
            return None
        texts = [document_text(chunk) for chunk in chunks]
        failed = False
        vectors: list[list[float]] | None = None
        try:
            vectors = await asyncio.to_thread(self._embedder.embed, texts, kind="document")
        except asyncio.CancelledError:
            raise
        except Exception:
            failed = True
        if failed or vectors is None:
            raise IndexPublishError("document embed failed")
        return vectors

    async def _smoke(
        self, collection: str, tenant_id: str, chunks: Sequence[ChunkMetadata]
    ) -> None:
        failed = False
        count = -1
        points: list[dict[str, Any]] = []
        try:
            await self._gateway.get_collection(collection)
            count = await self._gateway.count(
                collection,
                {
                    "exact": True,
                    "filter": {"must": [{"key": "tenant_id", "match": {"value": tenant_id}}]},
                },
            )
            points = await self._gateway.scroll(
                collection, {"limit": max(len(chunks), 1), "with_payload": True}
            )
        except (GatewayUnavailable, GatewayNotFound):
            failed = True
        if failed or count != len(chunks):
            raise IndexPublishError("index publish smoke failed")
        invalid = False
        isolation = False
        try:
            for point in points:
                payload = point.get("payload")
                if not isinstance(payload, dict):
                    invalid = True
                    break
                if payload.get("tenant_id") != tenant_id:
                    isolation = True
                    break
                fields = {key: payload[key] for key in ChunkMetadata.model_fields}
                ChunkMetadata.model_validate(fields)
        except (KeyError, ValidationError):
            invalid = True
        if isolation:
            raise TenantIsolationError("retrieved chunk does not belong to the requesting tenant")
        if invalid:
            raise IndexPublishError("index publish smoke failed")
        if not chunks:
            return
        query_vec = self._sparse.encode_query(chunk_token_list(chunks[0]))
        if not query_vec.indices:
            return
        search_failed = False
        hits: list[dict[str, Any]] = []
        try:
            batch = await self._gateway.search_batch(
                collection,
                [
                    {
                        "vector": {
                            "name": SPARSE_VECTOR_NAME,
                            "vector": {
                                "indices": query_vec.indices,
                                "values": query_vec.values,
                            },
                        },
                        "limit": min(len(chunks), 10),
                        "with_payload": True,
                    }
                ],
            )
            hits = batch[0] if batch else []
        except (GatewayUnavailable, GatewayNotFound):
            search_failed = True
        if search_failed:
            raise IndexPublishError("index publish smoke failed")
        found_ids = {
            (hit.get("payload") or {}).get("chunk_id")
            for hit in hits
            if isinstance(hit.get("payload"), dict)
        }
        if chunks[0].chunk_id not in found_ids:
            raise IndexPublishError("index publish smoke failed")

    async def _delete_if_unaliased(self, collection: str) -> None:
        aliased = False
        failed = False
        try:
            aliases = await self._gateway.get_aliases()
            aliased = any(item["collection_name"] == collection for item in aliases)
        except GatewayUnavailable:
            failed = True
        if failed or aliased:
            return
        with contextlib.suppress(GatewayUnavailable, GatewayNotFound):
            await self._gateway.delete_collection(collection)

    async def _sparse_branch(
        self,
        collection: str,
        variants: tuple[str, ...],
        query_filter: dict[str, Any],
        outdated_filter: dict[str, Any],
        top_k: int,
        timeout_s: float,
        tenant_id: str,
        resolved: ResolvedFilter,
    ) -> tuple[
        list[list[tuple[ChunkMetadata, float]]],
        bool,
        DegradationReason | None,
        list[tuple[ChunkMetadata, float]],
    ]:
        searches: list[dict[str, Any]] = []
        for variant in variants:
            vector = self._sparse.encode_query(index_terms(variant))
            if not vector.indices:
                continue
            searches.append(
                {
                    "vector": {
                        "name": SPARSE_VECTOR_NAME,
                        "vector": {"indices": vector.indices, "values": vector.values},
                    },
                    "filter": query_filter,
                    "limit": top_k,
                    "with_payload": True,
                    "with_vector": False,
                }
            )
        outdated_vector = self._sparse.encode_query(index_terms(variants[0]))
        outdated_index: int | None = None
        if outdated_vector.indices:
            outdated_index = len(searches)
            searches.append(
                {
                    "vector": {
                        "name": SPARSE_VECTOR_NAME,
                        "vector": {
                            "indices": outdated_vector.indices,
                            "values": outdated_vector.values,
                        },
                    },
                    "filter": outdated_filter,
                    "limit": top_k,
                    "with_payload": True,
                    "with_vector": False,
                }
            )
        if not searches:
            empty: list[list[tuple[ChunkMetadata, float]]] = [[] for _ in variants]
            return empty, True, None, []
        missing = False
        failed = False
        raw: list[list[dict[str, Any]]] = []
        try:
            async with asyncio.timeout(timeout_s):
                raw = await self._gateway.search_batch(collection, searches)
        except TimeoutError:
            failed = True
        except GatewayNotFound:
            missing = True
        except GatewayUnavailable:
            failed = True
        if missing:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        if failed:
            return [[] for _ in variants], False, DegradationReason.SPARSE_UNAVAILABLE, []
        parsed_lists: list[list[tuple[ChunkMetadata, float]]] = []
        cursor = 0
        for variant in variants:
            if not self._sparse.encode_query(index_terms(variant)).indices:
                parsed_lists.append([])
                continue
            parsed_lists.append(
                self._parse_hits(raw[cursor] if cursor < len(raw) else [], tenant_id, resolved)
            )
            cursor += 1
        outdated_hits: list[tuple[ChunkMetadata, float]] = []
        if outdated_index is not None and outdated_index < len(raw):
            outdated_hits = self._parse_hits(
                raw[outdated_index], tenant_id, resolved, recheck=False
            )
        return parsed_lists, True, None, outdated_hits

    async def _dense_branch(
        self,
        collection: str,
        info: dict[str, Any],
        variants: tuple[str, ...],
        query_filter: dict[str, Any],
        top_k: int,
        timeout_s: float,
        tenant_id: str,
        resolved: ResolvedFilter,
        started: float,
        deadline_ms: int,
    ) -> tuple[list[list[tuple[ChunkMetadata, float]]], bool, DegradationReason | None]:
        embedder = self._embedder
        if embedder is None:
            return [], False, DegradationReason.EMBEDDER_UNAVAILABLE
        if not _collection_has_dense(info, embedder.vector_name, embedder.dim):
            return [], False, DegradationReason.DENSE_UNAVAILABLE
        remaining_ms = deadline_ms - (self._clock() - started) * 1000.0
        embed_timeout = min(self._settings.embed_timeout_ms, max(remaining_ms, 0.0)) / 1000.0
        future = self._embed_pool.try_submit(embedder.embed, list(variants), kind="query")
        if future is None:
            return [], False, DegradationReason.EMBEDDER_UNAVAILABLE
        failed = False
        timed_out = False
        vectors: list[list[float]] | None = None
        try:
            async with asyncio.timeout(embed_timeout):
                vectors = await asyncio.wrap_future(future)
        except TimeoutError:
            timed_out = True
        except asyncio.CancelledError:
            raise
        except Exception:
            failed = True
        if timed_out or failed or vectors is None:
            return [], False, DegradationReason.EMBEDDER_UNAVAILABLE
        searches = [
            {
                "vector": {"name": embedder.vector_name, "vector": vector},
                "filter": query_filter,
                "limit": top_k,
                "with_payload": True,
                "with_vector": False,
            }
            for vector in vectors
        ]
        search_timeout = self._remaining_s(started, deadline_ms)
        missing = False
        search_failed = False
        raw: list[list[dict[str, Any]]] = []
        try:
            async with asyncio.timeout(search_timeout):
                raw = await self._gateway.search_batch(collection, searches)
        except TimeoutError:
            search_failed = True
        except GatewayNotFound:
            missing = True
        except GatewayUnavailable:
            search_failed = True
        if missing:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        if search_failed:
            return [], False, DegradationReason.DENSE_UNAVAILABLE
        return (
            [self._parse_hits(hits, tenant_id, resolved) for hits in raw],
            True,
            None,
        )

    async def _maybe_rerank(
        self,
        query: str,
        fused_items: list[FusedItem],
        merged: dict[str, _MergedHit],
        started: float,
        deadline_ms: int,
    ) -> tuple[dict[str, float], list[str] | None, DegradationReason | None]:
        settings = self._settings
        config = settings.config
        remaining_ms = deadline_ms - (self._clock() - started) * 1000.0
        fused_ids = [item.id for item in fused_items]
        if self._reranker is None:
            return {}, None, None
        if not fused_ids:
            return {}, None, None
        if remaining_ms < settings.rerank_min_remaining_ms:
            return {}, None, DegradationReason.RERANKER_UNAVAILABLE
        to_rerank = fused_ids[: config.rerank_top_k]
        documents = [
            document_text(merged[chunk_id].chunk) for chunk_id in to_rerank if chunk_id in merged
        ]
        ids = [chunk_id for chunk_id in to_rerank if chunk_id in merged]
        if not ids:
            return {}, None, None
        timeout_s = min(settings.rerank_timeout_ms, max(remaining_ms, 0.0)) / 1000.0
        future = self._rerank_pool.try_submit(self._reranker.score, query, documents)
        if future is None:
            return {}, None, DegradationReason.RERANKER_UNAVAILABLE
        failed = False
        timed_out = False
        scores: list[float] | None = None
        try:
            async with asyncio.timeout(timeout_s):
                scores = await asyncio.wrap_future(future)
        except TimeoutError:
            timed_out = True
        except asyncio.CancelledError:
            raise
        except Exception:
            failed = True
        if timed_out or failed or scores is None or len(scores) != len(ids):
            return {}, None, DegradationReason.RERANKER_UNAVAILABLE
        scored = list(zip(ids, scores, strict=True))
        scored.sort(key=lambda item: (-item[1], item[0]))
        rerank_map = {chunk_id: score for chunk_id, score in scored}
        ordered = [chunk_id for chunk_id, _score in scored]
        ordered.extend(chunk_id for chunk_id in fused_ids[config.rerank_top_k :])
        return rerank_map, ordered, None

    def _parse_hits(
        self,
        hits: list[dict[str, Any]],
        tenant_id: str,
        resolved: ResolvedFilter,
        *,
        recheck: bool = True,
    ) -> list[tuple[ChunkMetadata, float]]:
        isolation = False
        invalid = False
        parsed: list[tuple[ChunkMetadata, float]] = []
        try:
            for hit in hits:
                payload = hit.get("payload")
                if not isinstance(payload, dict):
                    invalid = True
                    break
                if payload.get("tenant_id") != tenant_id:
                    isolation = True
                    break
                fields = {key: payload[key] for key in ChunkMetadata.model_fields}
                chunk = ChunkMetadata.model_validate(fields)
                if recheck and (
                    scope_exclusion(chunk, resolved) or temporal_exclusion(chunk, resolved)
                ):
                    continue
                parsed.append((chunk, float(hit.get("score") or 0.0)))
        except (KeyError, ValidationError, TypeError, ValueError):
            invalid = True
        if isolation:
            raise TenantIsolationError("retrieved chunk does not belong to the requesting tenant")
        if invalid:
            raise RetrievalUnavailable("index payload invalid")
        return parsed

    def _elapsed_ms(self, started: float, deadline_ms: int) -> int:
        elapsed_ms = (self._clock() - started) * 1000.0
        if elapsed_ms >= deadline_ms:
            raise RetrievalDeadlineExceeded("retrieval deadline exceeded")
        return int(elapsed_ms)

    def _remaining_s(self, started: float, deadline_ms: int) -> float:
        remaining_ms = deadline_ms - (self._clock() - started) * 1000.0
        if remaining_ms <= 0:
            raise RetrievalDeadlineExceeded("retrieval deadline exceeded")
        return remaining_ms / 1000.0


def build_search_filter(
    resolved: ResolvedFilter, tenant_id: str, *, outdated: bool
) -> dict[str, Any]:
    applied = resolved.applied
    t_us = _datetime_to_us(applied.reference_time) or 0
    must: list[dict[str, Any]] = [
        {"key": "tenant_id", "match": {"value": tenant_id}},
        {"key": "language", "match": {"value": applied.language}},
        {"key": "audience", "match": {"value": applied.audience.value}},
    ]
    if resolved.services is not None:
        must.append({"key": "service", "match": {"any": sorted(resolved.services)}})
    if resolved.topics is not None:
        must.append({"key": "topic", "match": {"any": sorted(resolved.topics)}})
    if resolved.source_types is not None:
        must.append(
            {
                "key": "source_type",
                "match": {"any": sorted(item.value for item in resolved.source_types)},
            }
        )
    if resolved.document_ids is not None:
        must.append({"key": "document_id", "match": {"any": sorted(resolved.document_ids)}})
    allowed = [status.value for status in resolved.effective_statuses]
    if outdated:
        must.append(
            {
                "should": [
                    {"must_not": [{"key": "effective_status", "match": {"any": allowed}}]},
                    {"key": "valid_to_us", "range": {"lte": t_us}},
                ]
            }
        )
    else:
        must.append({"key": "effective_status", "match": {"any": allowed}})
        must.append(
            {
                "should": [
                    {"is_null": {"key": "valid_from_us"}},
                    {"key": "valid_from_us", "range": {"lte": t_us}},
                ]
            }
        )
        must.append(
            {
                "should": [
                    {"is_null": {"key": "valid_to_us"}},
                    {"key": "valid_to_us", "range": {"gt": t_us}},
                ]
            }
        )
    return {"must": must}


def _datetime_to_us(value: datetime | None) -> int | None:
    if value is None:
        return None
    utc = value.astimezone(UTC)
    delta = utc - _EPOCH
    return delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds


def _collection_has_dense(info: dict[str, Any], name: str, dim: int) -> bool:
    params = info.get("config", {}).get("params", info)
    vectors = params.get("vectors") if isinstance(params, dict) else None
    if not isinstance(vectors, dict) or name not in vectors:
        return False
    spec = vectors[name]
    if not isinstance(spec, dict):
        return False
    return int(spec.get("size") or 0) == dim


def _merge_hits(
    sparse_lists: Sequence[Sequence[tuple[ChunkMetadata, float]]],
    dense_lists: Sequence[Sequence[tuple[ChunkMetadata, float]]],
) -> dict[str, _MergedHit]:
    merged: dict[str, _MergedHit] = {}

    def take(lists: Sequence[Sequence[tuple[ChunkMetadata, float]]], *, dense: bool) -> None:
        for ranking in lists:
            for rank, (chunk, score) in enumerate(ranking, start=1):
                item = merged.get(chunk.chunk_id)
                if item is None:
                    item = _MergedHit(chunk=chunk)
                    merged[chunk.chunk_id] = item
                if dense:
                    item.dense_rank, item.dense_score = _best_rank(
                        item.dense_rank, item.dense_score, rank, score
                    )
                else:
                    item.sparse_rank, item.sparse_score = _best_rank(
                        item.sparse_rank, item.sparse_score, rank, score
                    )

    take(sparse_lists, dense=False)
    take(dense_lists, dense=True)
    return merged


def _best_rank(
    old_rank: int | None, old_score: float | None, rank: int, score: float
) -> tuple[int, float]:
    if old_rank is None or rank < old_rank:
        return rank, score
    if rank == old_rank and (old_score is None or score > old_score):
        return rank, score
    return old_rank, old_score if old_score is not None else score


def _is_candidate(hit: _MergedHit, min_dense_score: float) -> bool:
    if hit.sparse_score is not None and hit.sparse_score > 0.0:
        return True
    return hit.dense_score is not None and hit.dense_score >= min_dense_score


def _is_relevant(
    hit: _MergedHit,
    query_terms: frozenset[str],
    rerank_score: float | None,
    settings: QdrantRetrieverSettings,
) -> bool:
    if rerank_score is not None:
        return rerank_score >= settings.min_rerank_score
    coverage = term_coverage(query_terms, chunk_terms(hit.chunk))
    dense = hit.dense_score if hit.dense_score is not None else float("-inf")
    return coverage >= settings.min_term_coverage or dense >= settings.min_dense_score


def _build_diagnostics(
    merged: dict[str, _MergedHit],
    fused: dict[str, FusedItem],
    rerank_scores: dict[str, float],
    returned_ids: set[str],
    min_dense_score: float,
) -> tuple[CandidateDiagnostics, ...]:
    items = [hit for hit in merged.values() if _is_candidate(hit, min_dense_score)]
    items.sort(
        key=lambda hit: (
            fused[hit.chunk.chunk_id].rank if hit.chunk.chunk_id in fused else 10**9,
            hit.chunk.chunk_id,
        )
    )
    rerank_ranks = {
        chunk_id: rank
        for rank, chunk_id in enumerate(
            sorted(rerank_scores, key=lambda cid: (-rerank_scores[cid], cid)), start=1
        )
    }
    diagnostics: list[CandidateDiagnostics] = []
    for hit in items:
        chunk = hit.chunk
        fused_item = fused.get(chunk.chunk_id)
        rerank_score = rerank_scores.get(chunk.chunk_id)
        diagnostics.append(
            CandidateDiagnostics(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                revision_id=chunk.revision_id,
                dense_rank=hit.dense_rank,
                dense_score=hit.dense_score,
                sparse_rank=hit.sparse_rank,
                sparse_score=hit.sparse_score,
                rrf_rank=fused_item.rank if fused_item is not None else None,
                rrf_score=fused_item.score if fused_item is not None else None,
                rerank_rank=rerank_ranks.get(chunk.chunk_id) if rerank_score is not None else None,
                rerank_score=rerank_score,
                selected=chunk.chunk_id in returned_ids,
            )
        )
    return tuple(diagnostics)


def _top_score(
    ordered_ids: Sequence[str],
    merged: dict[str, _MergedHit],
    fused: dict[str, FusedItem],
    rerank_scores: dict[str, float],
    min_dense_score: float,
) -> float | None:
    for chunk_id in ordered_ids:
        hit = merged.get(chunk_id)
        if hit is None or not _is_candidate(hit, min_dense_score):
            continue
        if chunk_id in rerank_scores:
            return rerank_scores[chunk_id]
        fused_item = fused.get(chunk_id)
        if fused_item is not None:
            return fused_item.score
    for hit in merged.values():
        if _is_candidate(hit, min_dense_score):
            fused_item = fused.get(hit.chunk.chunk_id)
            if fused_item is not None:
                return fused_item.score
            if hit.dense_score is not None:
                return hit.dense_score
            if hit.sparse_score is not None:
                return hit.sparse_score
    return None
