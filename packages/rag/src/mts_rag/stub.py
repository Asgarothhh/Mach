"""In-memory lexical KnowledgeRetriever stub (MLB-S1-STUB, SSOT §14.2)."""

import asyncio
import contextlib
import math
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

from mts_contracts.knowledge import (
    ACTIVE_INDEX_REVISION,
    CandidateDiagnostics,
    ChunkMetadata,
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

from mts_rag._request import (
    MAX_DEADLINE_MS,
    _parse_request,
    _RetrievalRequest,
    _snippet,
    _utc_now,
)
from mts_rag.evidence import compute_evidence_status, detect_conflicts
from mts_rag.filters import resolve_filters, scope_exclusion, temporal_exclusion
from mts_rag.fusion import reciprocal_rank_fusion
from mts_rag.lexical import (
    document_terms_from_tokens,
    query_terms_from_tokens,
    term_coverage,
    tokenize,
)

_OUTDATED_REASONS = frozenset(
    {FilterExclusionReason.STATUS_NOT_ALLOWED, FilterExclusionReason.EXPIRED}
)
_STATUSES_WITH_CHUNKS = frozenset({EvidenceStatus.SUFFICIENT, EvidenceStatus.EVIDENCE_CONFLICT})
_REVISION_NOT_FOUND = "index revision not found"
_TENANT_ID_ADAPTER: TypeAdapter[str] = TypeAdapter(TenantId)
_IDENTIFIER_ADAPTER: TypeAdapter[str] = TypeAdapter(Identifier)

# Re-exported for stub compatibility; callers may import these from mts_rag.stub.
__all__ = [
    "MAX_DEADLINE_MS",
    "InMemoryKnowledgeRetriever",
    "LexicalStubSettings",
    "_RetrievalRequest",
    "_parse_request",
    "_snippet",
    "_utc_now",
]


@dataclass(frozen=True, slots=True)
class LexicalStubSettings:
    """Stub-only settings.

    The relevance threshold is not part of RetrievalConfig because score scales differ by
    retrieval mode; it applies only to the lexical stub score in [0, 1].
    """

    min_relevance_score: float = 0.5
    config: RetrievalConfig = field(default_factory=RetrievalConfig)

    def __post_init__(self) -> None:
        if not (math.isfinite(self.min_relevance_score) and 0.0 <= self.min_relevance_score <= 1.0):
            raise ValueError("min_relevance_score must be within [0, 1]")


def _chunk_terms(chunk: ChunkMetadata) -> frozenset[str]:
    return document_terms_from_tokens(
        tokenize(" ".join((chunk.title, *chunk.section_path, chunk.text)))
    )


class InMemoryKnowledgeRetriever:
    """Lexical, in-memory KnowledgeRetriever for Stage 1 integration.

    Chunks are stored per (tenant_id, index_revision); a request only ever reads its own
    tenant's bucket. Safe for use within a single event loop, not across threads.
    """

    def __init__(
        self,
        settings: LexicalStubSettings | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._settings = settings if settings is not None else LexicalStubSettings()
        self._clock = clock
        self._now = now
        self._buckets: dict[tuple[str, str], tuple[ChunkMetadata, ...]] = {}
        self._active: dict[str, str] = {}

    @property
    def settings(self) -> LexicalStubSettings:
        return self._settings

    def publish(
        self,
        tenant_id: str,
        index_revision: str,
        chunks: Iterable[ChunkMetadata],
        *,
        activate: bool = True,
    ) -> None:
        """Store an immutable index revision for a tenant and optionally make it active."""
        _TENANT_ID_ADAPTER.validate_python(tenant_id, strict=True)
        _IDENTIFIER_ADAPTER.validate_python(index_revision, strict=True)
        if index_revision == ACTIVE_INDEX_REVISION:
            raise ValueError(f"index revision name {ACTIVE_INDEX_REVISION!r} is reserved")
        snapshot = tuple(chunks)
        if any(chunk.tenant_id != tenant_id for chunk in snapshot):
            raise TenantIsolationError("chunk tenant does not match the target tenant")
        chunk_ids = [chunk.chunk_id for chunk in snapshot]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("duplicate chunk_id in index revision")
        key = (tenant_id, index_revision)
        if key in self._buckets:
            raise ValueError("index revision already published; revisions are immutable")
        self._buckets[key] = snapshot
        if activate:
            self._active[tenant_id] = index_revision

    def activate(self, tenant_id: str, index_revision: str) -> None:
        if (tenant_id, index_revision) not in self._buckets:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        self._active[tenant_id] = index_revision

    def _resolve_revision(
        self, tenant_id: str, index_revision: str
    ) -> tuple[str, tuple[ChunkMetadata, ...]]:
        if index_revision == ACTIVE_INDEX_REVISION:
            resolved = self._active.get(tenant_id)
            if resolved is None:
                raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        else:
            resolved = index_revision
        pool = self._buckets.get((tenant_id, resolved))
        if pool is None:
            raise IndexRevisionNotFound(_REVISION_NOT_FOUND)
        return resolved, pool

    def _elapsed_ms(self, started: float, deadline_ms: int) -> int:
        elapsed_ms = (self._clock() - started) * 1000.0
        if elapsed_ms >= deadline_ms:
            raise RetrievalDeadlineExceeded("retrieval deadline exceeded")
        return int(elapsed_ms)

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
        config = self._settings.config
        threshold = self._settings.min_relevance_score
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

        resolved_revision, pool = self._resolve_revision(request.tenant_id, request.index_revision)
        self._elapsed_ms(started, deadline)
        await asyncio.sleep(0)

        resolved = resolve_filters(
            request.filters,
            tenant_id=request.tenant_id,
            language=request.language,
            audience=request.audience,
            now=self._now(),
        )
        excluded: Counter[FilterExclusionReason] = Counter()
        current: list[ChunkMetadata] = []
        outdated: list[ChunkMetadata] = []
        for chunk in pool:
            reason = scope_exclusion(chunk, resolved) or temporal_exclusion(chunk, resolved)
            if reason is None:
                current.append(chunk)
                continue
            excluded[reason] += 1
            if reason in _OUTDATED_REASONS:
                outdated.append(chunk)
        self._elapsed_ms(started, deadline)
        await asyncio.sleep(0)

        query_terms = query_terms_from_tokens(tokenize(request.query))
        scored = [(term_coverage(query_terms, _chunk_terms(c)), c) for c in current]
        candidates = sorted(
            ((score, chunk) for score, chunk in scored if score > 0.0),
            key=lambda item: (-item[0], item[1].chunk_id),
        )[: config.sparse_top_k]
        outdated_matches = sum(
            1 for c in outdated if term_coverage(query_terms, _chunk_terms(c)) >= threshold
        )
        fused = {
            item.id: item
            for item in reciprocal_rank_fusion(
                [[chunk.chunk_id for _, chunk in candidates]],
                k=config.rrf_k,
                top_k=config.rrf_top_k,
            )
        }
        relevant = [
            (score, chunk)
            for score, chunk in candidates
            if chunk.chunk_id in fused and score >= threshold
        ]
        self._elapsed_ms(started, deadline)
        await asyncio.sleep(0)

        conflicts = detect_conflicts(chunk for _, chunk in relevant)
        selected = relevant[: config.context_top_k]
        reference_time = resolved.reference_time
        stale_after = config.stale_after
        stale_ids = (
            {c.chunk_id for _, c in selected if reference_time - c.crawled_at > stale_after}
            if stale_after is not None
            else set()
        )
        evidence_status = compute_evidence_status(
            has_candidates=bool(candidates),
            relevant_count=len(relevant),
            outdated_matches=outdated_matches,
            has_conflicts=bool(conflicts),
            all_selected_stale=bool(selected) and len(stale_ids) == len(selected),
        )
        returned = selected if evidence_status in _STATUSES_WITH_CHUNKS else []

        if any(chunk.tenant_id != request.tenant_id for _, chunk in candidates):
            raise TenantIsolationError("retrieved chunk does not belong to the requesting tenant")

        returned_ids = {chunk.chunk_id for _, chunk in returned}
        diagnostics = tuple(
            CandidateDiagnostics(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                revision_id=chunk.revision_id,
                sparse_rank=sparse_rank,
                sparse_score=score,
                rrf_rank=fused[chunk.chunk_id].rank if chunk.chunk_id in fused else None,
                rrf_score=fused[chunk.chunk_id].score if chunk.chunk_id in fused else None,
                selected=chunk.chunk_id in returned_ids,
            )
            for sparse_rank, (score, chunk) in enumerate(candidates, start=1)
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

        # A ValidationError here would carry query_variants in its text, so it is suppressed
        # and replaced by a typed error raised outside any except block.
        with contextlib.suppress(ValidationError):
            return RetrievalResult(
                tenant_id=request.tenant_id,
                index_revision=resolved_revision,
                retrieval_mode=RetrievalMode.STUB_LEXICAL,
                config_version=config.version,
                query_variants=(request.query,),
                applied_filters=resolved.applied,
                candidates=diagnostics,
                chunks=retrieved,
                evidence_status=evidence_status,
                top_score=candidates[0][0] if candidates else None,
                conflicts=conflicts if evidence_status is EvidenceStatus.EVIDENCE_CONFLICT else (),
                outdated_matches=outdated_matches,
                excluded_counts=tuple(
                    (reason, count)
                    for reason, count in sorted(excluded.items(), key=lambda item: item[0].value)
                ),
                degraded=(),
                duration_ms=duration_ms,
            )
        if any(c.metadata.tenant_id != request.tenant_id for c in retrieved):
            raise TenantIsolationError("retrieved chunk does not belong to the requesting tenant")
        raise RetrievalUnavailable("retrieval result failed validation")
