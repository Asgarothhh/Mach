import logging
from collections.abc import Callable

import pytest
from mts_contracts.knowledge import ChunkMetadata, InvalidRetrievalRequest, RetrievalFilters

from mts_rag.qdrant import QdrantHybridRetriever
from mts_rag.testing import InMemoryQdrantGateway

ChunkFactory = Callable[..., ChunkMetadata]
MakeQdrant = Callable[..., tuple[QdrantHybridRetriever, InMemoryQdrantGateway]]
SENTINEL_QUERY = "SECRET_QUERY_TOKEN_9f3a"
SENTINEL_CHUNK = "SECRET_CHUNK_TOKEN_7c2b"


@pytest.mark.asyncio
async def test_sentinel_query_not_in_logs_or_exceptions(
    make_chunk: ChunkFactory,
    make_qdrant: MakeQdrant,
    tenant_a: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    retriever, gateway = make_qdrant()
    await retriever.publish(
        tenant_a, "rev-1", [make_chunk(text=f"Roaming internet. {SENTINEL_CHUNK}")]
    )
    caplog.set_level(logging.DEBUG)
    await retriever.retrieve(
        SENTINEL_QUERY + " roaming internet",
        tenant_id=tenant_a,
        language="en",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    blob = " ".join(record.getMessage() for record in caplog.records)
    blob += " ".join(str(record.__dict__) for record in caplog.records)
    assert SENTINEL_QUERY not in blob
    assert SENTINEL_CHUNK not in blob

    with pytest.raises(InvalidRetrievalRequest) as exc_info:
        await retriever.retrieve(
            SENTINEL_QUERY * 200,
            tenant_id=tenant_a,
            language="??",
            audience="caller",
            filters=RetrievalFilters(),
            index_revision="active",
            deadline_ms=1000,
        )
    error = exc_info.value
    for rendered in (str(error), repr(error), repr(error.args)):
        assert SENTINEL_QUERY not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None

    gateway.down = True
    retriever._version_ok = None
    from mts_contracts.knowledge import RetrievalUnavailable

    with pytest.raises(RetrievalUnavailable) as down:
        await retriever.retrieve(
            SENTINEL_QUERY,
            tenant_id=tenant_a,
            language="en",
            audience="caller",
            filters=RetrievalFilters(),
            index_revision="active",
            deadline_ms=1000,
        )
    assert SENTINEL_QUERY not in str(down.value)
    assert SENTINEL_QUERY not in str(down.value.__context__)
    assert SENTINEL_QUERY not in str(down.value.__cause__)
