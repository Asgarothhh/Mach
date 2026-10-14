from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from mts_contracts.knowledge import (
    Audience,
    ChunkMetadata,
    EffectiveStatus,
    RetrievalFilters,
    SourceType,
)

from mts_rag.filters import resolve_filters, scope_exclusion, temporal_exclusion
from mts_rag.qdrant import _datetime_to_us, build_search_filter
from mts_rag.testing import matches_filter


def _payload(chunk: ChunkMetadata) -> dict[str, Any]:
    data: dict[str, Any] = chunk.model_dump(mode="json")
    data["valid_from_us"] = _datetime_to_us(chunk.valid_from)
    data["valid_to_us"] = _datetime_to_us(chunk.valid_to)
    data["payload_schema"] = 1
    return data


def test_filter_evaluator_matches_scope_and_temporal(
    make_chunk: Callable[..., ChunkMetadata], now: datetime
) -> None:
    resolved = resolve_filters(
        RetrievalFilters(
            services=("roaming",),
            source_types=(SourceType.HTML,),
            effective_statuses=(EffectiveStatus.ACTIVE,),
        ),
        tenant_id="acme-it-demo",
        language="en",
        audience=Audience.CALLER,
        now=now,
    )
    clause = build_search_filter(resolved, "acme-it-demo", outdated=False)
    cases = [
        make_chunk(),
        make_chunk(language="ru"),
        make_chunk(valid_to=now - timedelta(days=1)),
        make_chunk(valid_from=now + timedelta(days=1)),
        make_chunk(valid_to=now),
        make_chunk(valid_from=None, valid_to=None),
        make_chunk(audience="internal"),
        make_chunk(service="tv"),
    ]
    for chunk in cases:
        qdrant_ok = matches_filter(_payload(chunk), clause)
        local_ok = (
            scope_exclusion(chunk, resolved) is None and temporal_exclusion(chunk, resolved) is None
        )
        assert qdrant_ok is local_ok
