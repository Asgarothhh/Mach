from collections.abc import Callable

import pytest
from mts_contracts.knowledge import ChunkMetadata, ConflictReason, EvidenceStatus

from mts_rag.evidence import compute_evidence_status, detect_conflicts

ChunkFactory = Callable[..., ChunkMetadata]


def test_two_active_revisions_same_document_is_conflict(make_chunk: ChunkFactory) -> None:
    chunks = [
        make_chunk(chunk_id="c2", revision_id="rev-2"),
        make_chunk(chunk_id="c1", revision_id="rev-1"),
        make_chunk(chunk_id="c3", revision_id="rev-2"),
    ]
    (conflict,) = detect_conflicts(chunks)
    assert conflict.reason is ConflictReason.MULTIPLE_ACTIVE_REVISIONS
    assert conflict.document_id == "a" * 64
    assert conflict.revision_ids == ("rev-1", "rev-2")
    assert conflict.chunk_ids == ("c1", "c2", "c3")


def test_same_revision_is_not_conflict(make_chunk: ChunkFactory) -> None:
    chunks = [make_chunk(chunk_id="c1"), make_chunk(chunk_id="c2")]
    assert detect_conflicts(chunks) == ()


def test_different_documents_are_not_conflict(make_chunk: ChunkFactory) -> None:
    chunks = [
        make_chunk(chunk_id="c1", revision_id="rev-1"),
        make_chunk(chunk_id="c2", revision_id="rev-2", document_id="d" * 64),
    ]
    assert detect_conflicts(chunks) == ()


def test_superseded_revision_is_not_conflict(make_chunk: ChunkFactory) -> None:
    chunks = [
        make_chunk(chunk_id="c1", revision_id="rev-1", effective_status="superseded"),
        make_chunk(chunk_id="c2", revision_id="rev-2"),
    ]
    assert detect_conflicts(chunks) == ()


def test_conflicts_sorted_by_document(make_chunk: ChunkFactory) -> None:
    chunks = [
        make_chunk(chunk_id=f"{doc}-{rev}", document_id=doc * 64, revision_id=f"rev-{rev}")
        for doc in ("e", "c")
        for rev in (1, 2)
    ]
    assert [c.document_id for c in detect_conflicts(chunks)] == ["c" * 64, "e" * 64]


@pytest.mark.parametrize(
    ("has_candidates", "relevant", "outdated", "conflicts", "all_stale", "expected"),
    [
        (False, 0, 0, False, False, EvidenceStatus.NO_EVIDENCE),
        (True, 0, 0, False, False, EvidenceStatus.LOW_RELEVANCE),
        (False, 0, 1, False, False, EvidenceStatus.STALE_ONLY),
        (True, 0, 2, False, False, EvidenceStatus.STALE_ONLY),
        (True, 2, 0, True, False, EvidenceStatus.EVIDENCE_CONFLICT),
        (True, 2, 0, True, True, EvidenceStatus.EVIDENCE_CONFLICT),
        (True, 1, 0, False, True, EvidenceStatus.STALE_ONLY),
        (True, 1, 3, False, False, EvidenceStatus.SUFFICIENT),
    ],
)
def test_compute_evidence_status_table(
    has_candidates: bool,
    relevant: int,
    outdated: int,
    conflicts: bool,
    all_stale: bool,
    expected: EvidenceStatus,
) -> None:
    assert (
        compute_evidence_status(
            has_candidates=has_candidates,
            relevant_count=relevant,
            outdated_matches=outdated,
            has_conflicts=conflicts,
            all_selected_stale=all_stale,
        )
        is expected
    )
