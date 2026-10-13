"""Evidence status and conflict indicators (SSOT §6.3, §6.8, §7.2)."""

from collections import defaultdict
from collections.abc import Iterable

from mts_contracts.knowledge import (
    ChunkMetadata,
    ConflictIndicator,
    ConflictReason,
    EffectiveStatus,
    EvidenceStatus,
)


def detect_conflicts(chunks: Iterable[ChunkMetadata]) -> tuple[ConflictIndicator, ...]:
    """One indicator per document that has active chunks from two or more revisions.

    Conflicting values across different documents are out of scope here (MLB-GRD-02).
    """
    by_document: dict[str, list[ChunkMetadata]] = defaultdict(list)
    for chunk in chunks:
        if chunk.effective_status is EffectiveStatus.ACTIVE:
            by_document[chunk.document_id].append(chunk)

    conflicts: list[ConflictIndicator] = []
    for document_id in sorted(by_document):
        document_chunks = by_document[document_id]
        revision_ids = {c.revision_id for c in document_chunks}
        if len(revision_ids) < 2:
            continue
        conflicts.append(
            ConflictIndicator(
                reason=ConflictReason.MULTIPLE_ACTIVE_REVISIONS,
                document_id=document_id,
                revision_ids=tuple(revision_ids),
                chunk_ids=tuple(c.chunk_id for c in document_chunks),
            )
        )
    return tuple(conflicts)


def compute_evidence_status(
    *,
    has_candidates: bool,
    relevant_count: int,
    outdated_matches: int,
    has_conflicts: bool,
    all_selected_stale: bool,
) -> EvidenceStatus:
    """Decide the evidence status; only SUFFICIENT permits a grounded answer."""
    if relevant_count == 0:
        if outdated_matches > 0:
            return EvidenceStatus.STALE_ONLY
        if has_candidates:
            return EvidenceStatus.LOW_RELEVANCE
        return EvidenceStatus.NO_EVIDENCE
    if has_conflicts:
        return EvidenceStatus.EVIDENCE_CONFLICT
    if all_selected_stale:
        return EvidenceStatus.STALE_ONLY
    return EvidenceStatus.SUFFICIENT
