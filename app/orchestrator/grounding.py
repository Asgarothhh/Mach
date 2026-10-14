"""Pure grounding helpers: abstention mapping, evidence block, retrieval-event payload."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from enum import StrEnum

from mts_contracts.knowledge import EvidenceStatus, RetrievalResult, RetrievedChunk

RETRIEVAL_EVENT_KEYS = frozenset(
    {
        "event_id",
        "turn_id",
        "session_id",
        "tenant_id",
        "index_revision",
        "retrieval_mode",
        "config_version",
        "evidence_status",
        "outcome",
        "error_code",
        "query_sha256",
        "query_chars",
        "applied_filters",
        "candidates",
        "selected_source_ids",
        "cited_source_ids",
        "conflict_chunk_ids",
        "excluded_counts",
        "degraded",
        "top_score",
        "outdated_matches",
        "duration_ms",
    }
)

_TEXT_NO_EVIDENCE = (
    "К сожалению, подтверждённых данных по этому вопросу у меня нет. "
    "Можете спросить по-другому или задать другой вопрос."
)
_TEXT_CLARIFY = (
    "Уточните, пожалуйста, что именно вас интересует — так будет проще найти точный ответ."
)
_TEXT_STALE = (
    "Не могу надёжно подтвердить эту информацию: она могла устареть. "
    "Лучше уточнить в официальном канале поддержки."
)
_TEXT_CONFLICT = (
    "В источниках есть расхождения, поэтому точный ответ дать не могу. "
    "Могу перевести вас на специалиста."
)
_TEXT_UNAVAILABLE = (
    "Сейчас не получается обратиться к базе знаний. Могу перевести вас на специалиста."
)
_TEXT_TIMEOUT = "Поиск ответа занял слишком много времени. Могу перевести вас на специалиста."
_TEXT_INVALID = "Не удалось разобрать вопрос. Повторите его, пожалуйста."
_TEXT_ISOLATION = "Произошла ошибка. Могу перевести вас на специалиста."
_TEXT_VALIDATION = "Не получилось подтвердить ответ по базе знаний. Попробуйте задать вопрос иначе."
_TEXT_LLM = "Извините, возникла техническая проблема. Могу перевести вас на специалиста."
_TEXT_BLOCKED = "С этим запросом помочь не могу. Могу перевести вас на специалиста."

_ALTERNATIVES: dict[str, str] = {
    _TEXT_NO_EVIDENCE: (
        "Об этом в базе знаний ничего не нашлось. Попробуйте сформулировать вопрос иначе."
    ),
    _TEXT_CLARIFY: "Можете рассказать чуть подробнее, о какой услуге или ситуации речь?",
    _TEXT_INVALID: "Простите, вопрос не удалось разобрать. Скажите, пожалуйста, ещё раз.",
    _TEXT_VALIDATION: "Подтвердить ответ по базе знаний не вышло. Можете переформулировать вопрос?",
}


def vary_text(text: str, previous_answers: Sequence[str]) -> str:
    """Use the alternative phrasing when the same fallback was just said."""
    alternative = _ALTERNATIVES.get(text)
    if alternative is not None and previous_answers and previous_answers[-1].endswith(text):
        return alternative
    return text


class FallbackReason(StrEnum):
    NO_EVIDENCE = "no_evidence"
    LOW_RELEVANCE = "low_relevance"
    STALE_ONLY = "stale_only"
    EVIDENCE_CONFLICT = "evidence_conflict"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    RETRIEVAL_TIMEOUT = "retrieval_timeout"
    INVALID_REQUEST = "invalid_request"
    ISOLATION_VIOLATION = "isolation_violation"
    OUTPUT_VALIDATION_FAILED = "output_validation_failed"
    LLM_UNAVAILABLE = "llm_unavailable"
    BLOCKED = "blocked"


def abstention_for(
    status: EvidenceStatus | FallbackReason,
) -> tuple[str, FallbackReason, str]:
    """Map evidence_status or a retrieval/LLM failure to a safe user-facing outcome."""
    if status is EvidenceStatus.NO_EVIDENCE or status is FallbackReason.NO_EVIDENCE:
        return "no_evidence", FallbackReason.NO_EVIDENCE, _TEXT_NO_EVIDENCE
    if status is EvidenceStatus.LOW_RELEVANCE or status is FallbackReason.LOW_RELEVANCE:
        return "needs_clarification", FallbackReason.LOW_RELEVANCE, _TEXT_CLARIFY
    if status is EvidenceStatus.STALE_ONLY or status is FallbackReason.STALE_ONLY:
        return "handoff", FallbackReason.STALE_ONLY, _TEXT_STALE
    if (
        status is EvidenceStatus.EVIDENCE_CONFLICT
        or status is FallbackReason.EVIDENCE_CONFLICT
    ):
        return "handoff", FallbackReason.EVIDENCE_CONFLICT, _TEXT_CONFLICT
    if status is FallbackReason.RETRIEVAL_TIMEOUT:
        return "handoff", FallbackReason.RETRIEVAL_TIMEOUT, _TEXT_TIMEOUT
    if status is FallbackReason.RETRIEVAL_UNAVAILABLE:
        return "handoff", FallbackReason.RETRIEVAL_UNAVAILABLE, _TEXT_UNAVAILABLE
    if status is FallbackReason.INVALID_REQUEST:
        return "needs_clarification", FallbackReason.INVALID_REQUEST, _TEXT_INVALID
    if status is FallbackReason.ISOLATION_VIOLATION:
        return "handoff", FallbackReason.ISOLATION_VIOLATION, _TEXT_ISOLATION
    if status is FallbackReason.OUTPUT_VALIDATION_FAILED:
        return "no_evidence", FallbackReason.OUTPUT_VALIDATION_FAILED, _TEXT_VALIDATION
    if status is FallbackReason.LLM_UNAVAILABLE:
        return "handoff", FallbackReason.LLM_UNAVAILABLE, _TEXT_LLM
    if status is FallbackReason.BLOCKED:
        return "handoff", FallbackReason.BLOCKED, _TEXT_BLOCKED
    raise ValueError(f"no abstention mapping for {status!r}")


def _fmt_dt(value) -> str:
    if value is None:
        return ""
    return value.isoformat()


def build_evidence_block(chunks: Sequence[RetrievedChunk]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        meta = chunk.metadata
        parts.append(
            f"[{meta.chunk_id}] title={meta.title} url={meta.canonical_url} "
            f"crawled_at={_fmt_dt(meta.crawled_at)} valid_to={_fmt_dt(meta.valid_to)}\n"
            f"content={chunk.snippet}"
        )
    return "\n".join(parts)


def query_sha256(redacted_text: str) -> str:
    return hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()


def build_retrieval_event(
    *,
    event_id: str,
    turn_id: str,
    session_id: str,
    tenant_id: str,
    redacted_query: str,
    result: RetrievalResult | None,
    outcome: str,
    error_code: str | None,
    cited_source_ids: Iterable[str] = (),
    duration_ms: int | None = None,
) -> dict[str, object]:
    """Allowlist-only payload. Never includes query text or query_variants."""
    cited = list(cited_source_ids)
    if result is None:
        payload: dict[str, object] = {
            "event_id": event_id,
            "turn_id": turn_id,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "index_revision": None,
            "retrieval_mode": None,
            "config_version": None,
            "evidence_status": None,
            "outcome": outcome,
            "error_code": error_code,
            "query_sha256": query_sha256(redacted_query),
            "query_chars": len(redacted_query),
            "applied_filters": None,
            "candidates": [],
            "selected_source_ids": [],
            "cited_source_ids": cited,
            "conflict_chunk_ids": [],
            "excluded_counts": [],
            "degraded": [],
            "top_score": None,
            "outdated_matches": 0,
            "duration_ms": duration_ms,
        }
        return payload

    payload = {
        "event_id": event_id,
        "turn_id": turn_id,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "index_revision": result.index_revision,
        "retrieval_mode": result.retrieval_mode.value,
        "config_version": result.config_version,
        "evidence_status": result.evidence_status.value,
        "outcome": outcome,
        "error_code": error_code,
        "query_sha256": query_sha256(redacted_query),
        "query_chars": len(redacted_query),
        "applied_filters": result.applied_filters.model_dump(mode="json"),
        "candidates": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "revision_id": item.revision_id,
                "sparse_rank": item.sparse_rank,
                "sparse_score": item.sparse_score,
                "rrf_rank": item.rrf_rank,
                "rrf_score": item.rrf_score,
                "selected": item.selected,
            }
            for item in result.candidates
        ],
        "selected_source_ids": [item.chunk_id for item in result.candidates if item.selected],
        "cited_source_ids": cited,
        "conflict_chunk_ids": [
            chunk_id for conflict in result.conflicts for chunk_id in conflict.chunk_ids
        ],
        "excluded_counts": [
            [reason.value, count] for reason, count in result.excluded_counts
        ],
        "degraded": [item.value for item in result.degraded],
        "top_score": result.top_score,
        "outdated_matches": result.outdated_matches,
        "duration_ms": result.duration_ms if duration_ms is None else duration_ms,
    }
    return payload


def sources_from_citations(
    chunks: Sequence[RetrievedChunk], citation_ids: Sequence[str]
) -> list[dict[str, object]]:
    by_id = {chunk.metadata.chunk_id: chunk for chunk in chunks}
    sources: list[dict[str, object]] = []
    for citation_id in citation_ids:
        chunk = by_id.get(citation_id)
        if chunk is None:
            continue
        meta = chunk.metadata
        sources.append(
            {
                "chunk_id": meta.chunk_id,
                "title": meta.title,
                "canonical_url": meta.canonical_url,
                "crawled_at": meta.crawled_at,
                "valid_to": meta.valid_to,
            }
        )
    return sources
