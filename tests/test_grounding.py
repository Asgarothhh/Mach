import pytest
from mts_contracts.knowledge import EvidenceStatus, RetrievedChunk

from app.orchestrator.grounding import (
    FallbackReason,
    abstention_for,
    build_evidence_block,
    build_retrieval_event,
    query_sha256,
)
from tests.conftest import make_test_chunk


def test_mapping_no_evidence():
    status, reason, text = abstention_for(EvidenceStatus.NO_EVIDENCE)
    assert status == "no_evidence"
    assert reason is FallbackReason.NO_EVIDENCE
    assert text


def test_mapping_low_relevance():
    status, reason, _ = abstention_for(EvidenceStatus.LOW_RELEVANCE)
    assert status == "needs_clarification"
    assert reason is FallbackReason.LOW_RELEVANCE


def test_mapping_stale_only():
    status, reason, text = abstention_for(EvidenceStatus.STALE_ONLY)
    assert status == "handoff"
    assert reason is FallbackReason.STALE_ONLY
    assert "надёжно подтвердить" in text


def test_mapping_evidence_conflict():
    status, reason, text = abstention_for(EvidenceStatus.EVIDENCE_CONFLICT)
    assert status == "handoff"
    assert reason is FallbackReason.EVIDENCE_CONFLICT
    assert "расхождения" in text


@pytest.mark.parametrize(
    ("failure", "answer_status", "reason"),
    [
        (FallbackReason.RETRIEVAL_TIMEOUT, "handoff", FallbackReason.RETRIEVAL_TIMEOUT),
        (FallbackReason.RETRIEVAL_UNAVAILABLE, "handoff", FallbackReason.RETRIEVAL_UNAVAILABLE),
        (FallbackReason.INVALID_REQUEST, "needs_clarification", FallbackReason.INVALID_REQUEST),
        (FallbackReason.ISOLATION_VIOLATION, "handoff", FallbackReason.ISOLATION_VIOLATION),
        (FallbackReason.OUTPUT_VALIDATION_FAILED, "no_evidence", FallbackReason.OUTPUT_VALIDATION_FAILED),
        (FallbackReason.LLM_UNAVAILABLE, "handoff", FallbackReason.LLM_UNAVAILABLE),
        (FallbackReason.BLOCKED, "handoff", FallbackReason.BLOCKED),
    ],
)
def test_mapping_failures(failure, answer_status, reason):
    status, mapped, _ = abstention_for(failure)
    assert status == answer_status
    assert mapped is reason


def test_sufficient_has_no_abstention():
    with pytest.raises(ValueError):
        abstention_for(EvidenceStatus.SUFFICIENT)


def test_evidence_block_uses_metadata_not_content_attr():
    chunk = RetrievedChunk(
        rank=1,
        score=1.0,
        snippet="Офис открыт понедельник.",
        metadata=make_test_chunk(),
    )
    block = build_evidence_block([chunk])
    assert "[chunk-1]" in block
    assert "title=График работы" in block
    assert "url=https://www.acme-it.example/help/hours" in block
    assert "crawled_at=" in block
    assert "valid_to=" in block
    assert "content=Офис открыт понедельник." in block
    assert "c.content" not in block


def test_fallback_reason_values_are_controlled():
    values = {item.value for item in FallbackReason}
    assert values == {
        "no_evidence",
        "low_relevance",
        "stale_only",
        "evidence_conflict",
        "retrieval_unavailable",
        "retrieval_timeout",
        "invalid_request",
        "isolation_violation",
        "output_validation_failed",
        "llm_unavailable",
        "blocked",
    }


def test_build_retrieval_event_hashes_redacted_query():
    payload = build_retrieval_event(
        event_id="e1",
        turn_id="t1",
        session_id="s1",
        tenant_id="acme-it-demo",
        redacted_query="график [PHONE_REDACTED]",
        result=None,
        outcome="unavailable",
        error_code="retrieval_unavailable",
        duration_ms=12,
    )
    assert payload["query_sha256"] == query_sha256("график [PHONE_REDACTED]")
    assert "query" not in payload
    assert "query_variants" not in payload
    assert payload["query_chars"] == len("график [PHONE_REDACTED]")
