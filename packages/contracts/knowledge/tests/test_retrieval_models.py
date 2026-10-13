from typing import Any

import pytest
from pydantic import ValidationError

from mts_contracts.knowledge import (
    ACTIVE_INDEX_REVISION,
    CandidateDiagnostics,
    ConflictIndicator,
    EffectiveStatus,
    EvidenceStatus,
    FilterExclusionReason,
    RetrievalConfig,
    RetrievalFilters,
    RetrievalResult,
    SourceType,
)

DOC_A = "a" * 64
DOC_C = "c" * 64


def _chunk(chunk_data: dict[str, Any], chunk_id: str, rank: int, **meta: Any) -> dict[str, Any]:
    return {
        "rank": rank,
        "score": 1.0 / rank,
        "snippet": "Roaming internet costs 5 BYN per day.",
        "metadata": {**chunk_data, "chunk_id": chunk_id, **meta},
    }


def _candidate(
    chunk_id: str, rank: int, *, selected: bool, revision: str = "rev-1"
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "document_id": DOC_A,
        "revision_id": revision,
        "sparse_rank": rank,
        "sparse_score": 1.0 / rank,
        "rrf_rank": rank,
        "rrf_score": 1.0 / (60 + rank),
        "selected": selected,
    }


def _applied(tenant_id: str = "acme-it-demo") -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "language": "ru",
        "audience": "caller",
        "services": None,
        "topics": None,
        "source_types": None,
        "document_ids": None,
        "effective_statuses": ["active"],
        "reference_time": "2026-10-13T10:00:00Z",
    }


@pytest.fixture
def result_data(chunk_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": "acme-it-demo",
        "index_revision": "idx-2026-10-13",
        "retrieval_mode": "stub_lexical",
        "config_version": "retrieval-v1",
        "query_variants": ["roaming internet price"],
        "applied_filters": _applied(),
        "candidates": [
            _candidate("chunk-1", 1, selected=True),
            _candidate("chunk-2", 2, selected=True),
            _candidate("chunk-3", 3, selected=False),
        ],
        "chunks": [_chunk(chunk_data, "chunk-1", 1), _chunk(chunk_data, "chunk-2", 2)],
        "evidence_status": "sufficient",
        "top_score": 1.0,
        "excluded_counts": {"language_mismatch": 2},
        "duration_ms": 3,
    }


@pytest.mark.parametrize("field", ["tenant_id", "language", "audience"])
def test_filters_forbid_tenant_language_audience_fields(field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        RetrievalFilters.model_validate({field: "x"})


@pytest.mark.parametrize(
    "field", ["services", "topics", "source_types", "document_ids", "effective_statuses"]
)
def test_filters_reject_empty_tuple(field: str) -> None:
    with pytest.raises(ValidationError):
        RetrievalFilters.model_validate({field: []})


def test_filters_defaults() -> None:
    filters = RetrievalFilters()
    assert filters.services is None
    assert filters.effective_statuses == (EffectiveStatus.ACTIVE,)
    assert filters.reference_time is None


def test_filters_sorted_unique_serialization_is_deterministic() -> None:
    first = RetrievalFilters.model_validate(
        {
            "services": ["roaming", "internet", "roaming"],
            "source_types": ["pdf", "html"],
            "document_ids": [DOC_C, DOC_A],
            "effective_statuses": ["superseded", "active"],
        }
    )
    second = RetrievalFilters.model_validate(
        {
            "services": ["internet", "roaming"],
            "source_types": ["html", "pdf", "html"],
            "document_ids": [DOC_A, DOC_C],
            "effective_statuses": ["active", "superseded"],
        }
    )
    assert first.model_dump_json() == second.model_dump_json()
    assert first.services == ("internet", "roaming")
    assert first.source_types == (SourceType.HTML, SourceType.PDF)
    assert first.document_ids == (DOC_A, DOC_C)


def test_config_defaults_match_ssot_6_7() -> None:
    config = RetrievalConfig()
    assert (
        config.dense_top_k,
        config.sparse_top_k,
        config.rrf_top_k,
        config.rerank_top_k,
        config.context_top_k,
    ) == (30, 30, 30, 20, 6)
    assert config.rrf_k == 60
    assert config.max_query_variants == 3
    assert config.version == "retrieval-v1"
    assert config.stale_after is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"context_top_k": 21},
        {"rerank_top_k": 31},
        {"dense_top_k": 10, "sparse_top_k": 10},
        {"max_query_variants": 4},
        {"stale_after": "PT0S"},
    ],
)
def test_config_rejects_inconsistent_top_k(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(overrides)


def test_candidate_rank_score_pairing() -> None:
    base = _candidate("chunk-1", 1, selected=False)
    CandidateDiagnostics.model_validate(base)
    for missing in ["sparse_score", "rrf_rank"]:
        with pytest.raises(ValidationError, match="set together"):
            CandidateDiagnostics.model_validate({**base, missing: None})
    with pytest.raises(ValidationError, match="dense or sparse"):
        CandidateDiagnostics.model_validate({**base, "sparse_rank": None, "sparse_score": None})
    dense_only = CandidateDiagnostics.model_validate(
        {**base, "sparse_rank": None, "sparse_score": None, "dense_rank": 1, "dense_score": 0.9}
    )
    assert dense_only.rerank_rank is None
    with pytest.raises(ValidationError):
        CandidateDiagnostics.model_validate({**base, "sparse_score": float("nan")})


def test_result_valid_baseline(result_data: dict[str, Any]) -> None:
    result = RetrievalResult.model_validate(result_data)
    assert result.is_answerable
    assert result.schema_version == 1


def test_result_rejects_foreign_tenant_chunk(
    result_data: dict[str, Any], chunk_data: dict[str, Any]
) -> None:
    result_data["chunks"][1] = _chunk(chunk_data, "chunk-2", 2, tenant_id="other-tenant")
    with pytest.raises(ValidationError, match="tenant"):
        RetrievalResult.model_validate(result_data)
    result_data["chunks"][1] = _chunk(chunk_data, "chunk-2", 2)
    result_data["applied_filters"] = _applied("other-tenant")
    with pytest.raises(ValidationError, match=r"applied_filters\.tenant_id"):
        RetrievalResult.model_validate(result_data)


@pytest.mark.parametrize("status", ["no_evidence", "low_relevance", "stale_only"])
def test_result_chunks_empty_unless_sufficient_or_conflict(
    result_data: dict[str, Any], status: str
) -> None:
    with pytest.raises(ValidationError, match="chunks must be non-empty"):
        RetrievalResult.model_validate({**result_data, "evidence_status": status})
    for candidate in result_data["candidates"]:
        candidate["selected"] = False
    empty = RetrievalResult.model_validate({**result_data, "evidence_status": status, "chunks": []})
    assert not empty.is_answerable
    with pytest.raises(ValidationError, match="chunks must be non-empty"):
        RetrievalResult.model_validate({**result_data, "chunks": []})


def test_result_conflict_iff_evidence_conflict(result_data: dict[str, Any]) -> None:
    conflict = {
        "reason": "multiple_active_revisions",
        "document_id": DOC_A,
        "revision_ids": ["rev-2", "rev-1"],
        "chunk_ids": ["chunk-2", "chunk-1"],
    }
    with pytest.raises(ValidationError, match="conflicts must be non-empty"):
        RetrievalResult.model_validate({**result_data, "conflicts": [conflict]})
    with pytest.raises(ValidationError, match="conflicts must be non-empty"):
        RetrievalResult.model_validate({**result_data, "evidence_status": "evidence_conflict"})
    result = RetrievalResult.model_validate(
        {**result_data, "evidence_status": "evidence_conflict", "conflicts": [conflict]}
    )
    assert result.evidence_status is EvidenceStatus.EVIDENCE_CONFLICT
    assert not result.is_answerable
    assert result.conflicts[0].revision_ids == ("rev-1", "rev-2")
    unknown = {**conflict, "chunk_ids": ["chunk-1", "chunk-404"]}
    with pytest.raises(ValidationError, match="reference candidates"):
        RetrievalResult.model_validate(
            {**result_data, "evidence_status": "evidence_conflict", "conflicts": [unknown]}
        )


def test_conflict_requires_two_distinct_revisions() -> None:
    with pytest.raises(ValidationError):
        ConflictIndicator.model_validate(
            {
                "reason": "multiple_active_revisions",
                "document_id": DOC_A,
                "revision_ids": ["rev-1", "rev-1"],
                "chunk_ids": ["chunk-1", "chunk-2"],
            }
        )


def test_result_selected_flags_match_chunks(result_data: dict[str, Any]) -> None:
    result_data["candidates"][2]["selected"] = True
    with pytest.raises(ValidationError, match="selected candidates"):
        RetrievalResult.model_validate(result_data)
    result_data["candidates"][2]["selected"] = False
    result_data["candidates"][1]["selected"] = False
    with pytest.raises(ValidationError, match="selected candidates"):
        RetrievalResult.model_validate(result_data)


def test_result_rejects_duplicate_ids(result_data: dict[str, Any]) -> None:
    result_data["candidates"].append(_candidate("chunk-3", 4, selected=False))
    with pytest.raises(ValidationError, match="candidate chunk_ids must be unique"):
        RetrievalResult.model_validate(result_data)


def test_result_ranks_contiguous(result_data: dict[str, Any]) -> None:
    result_data["chunks"][1]["rank"] = 3
    with pytest.raises(ValidationError, match="ranks"):
        RetrievalResult.model_validate(result_data)
    result_data["chunks"][0]["rank"], result_data["chunks"][1]["rank"] = 2, 1
    with pytest.raises(ValidationError, match="ranks"):
        RetrievalResult.model_validate(result_data)


def test_result_top_score_null_iff_no_candidates(result_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="top_score"):
        RetrievalResult.model_validate({**result_data, "top_score": None})
    empty = {
        **result_data,
        "candidates": [],
        "chunks": [],
        "evidence_status": "no_evidence",
        "top_score": None,
    }
    RetrievalResult.model_validate(empty)
    with pytest.raises(ValidationError, match="top_score"):
        RetrievalResult.model_validate({**empty, "top_score": 0.0})


def test_result_rejects_active_alias_and_zero_counts(result_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="concrete"):
        RetrievalResult.model_validate({**result_data, "index_revision": ACTIVE_INDEX_REVISION})
    with pytest.raises(ValidationError, match="excluded_counts"):
        RetrievalResult.model_validate({**result_data, "excluded_counts": {"expired": 0}})


def test_retrieved_chunk_stale_flag_consistency(
    result_data: dict[str, Any], chunk_data: dict[str, Any]
) -> None:
    result_data["chunks"][0] = {**_chunk(chunk_data, "chunk-1", 1), "is_stale": True}
    with pytest.raises(ValidationError, match="stale_reasons"):
        RetrievalResult.model_validate(result_data)
    result_data["chunks"][0]["stale_reasons"] = ["crawl_age_exceeded"]
    assert RetrievalResult.model_validate(result_data).chunks[0].is_stale


def test_result_repr_excludes_query_variants(result_data: dict[str, Any]) -> None:
    result_data["query_variants"] = ["my secret roaming question"]
    result = RetrievalResult.model_validate(result_data)
    assert "my secret roaming question" not in repr(result)
    assert "my secret roaming question" not in str(result)
    assert "query_variants" not in repr(result)


def test_result_json_roundtrip(result_data: dict[str, Any]) -> None:
    result_data["degraded"] = ["reranker_unavailable", "dense_unavailable", "reranker_unavailable"]
    result = RetrievalResult.model_validate(result_data)
    restored = RetrievalResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.model_dump_json() == result.model_dump_json()
    assert [d.value for d in restored.degraded] == ["dense_unavailable", "reranker_unavailable"]


def test_result_is_frozen(result_data: dict[str, Any]) -> None:
    result = RetrievalResult.model_validate(result_data)
    with pytest.raises(ValidationError):
        result.evidence_status = EvidenceStatus.NO_EVIDENCE  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs"):
        RetrievalResult.model_validate({**result_data, "debug": True})


def test_result_excluded_counts_hashable_and_immutable(result_data: dict[str, Any]) -> None:
    result = RetrievalResult.model_validate(result_data)
    assert result.excluded_counts == ((FilterExclusionReason.LANGUAGE_MISMATCH, 2),)
    assert hash(result) == hash(result)
    with pytest.raises(TypeError):
        result.excluded_counts[0] = (FilterExclusionReason.EXPIRED, 99)  # type: ignore[index]
    reordered = RetrievalResult.model_validate(
        {**result_data, "excluded_counts": {"expired": 1, "language_mismatch": 2}}
    )
    same_counts = RetrievalResult.model_validate(
        {**result_data, "excluded_counts": {"language_mismatch": 2, "expired": 1}}
    )
    assert reordered.excluded_counts == (
        (FilterExclusionReason.EXPIRED, 1),
        (FilterExclusionReason.LANGUAGE_MISMATCH, 2),
    )
    assert reordered.excluded_counts == same_counts.excluded_counts
    assert hash(reordered) == hash(same_counts)
