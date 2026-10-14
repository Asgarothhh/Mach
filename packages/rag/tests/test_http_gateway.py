import json

import httpx
import pytest

from mts_rag.qdrant_http import (
    GatewayNotFound,
    GatewayUnavailable,
    GatewayVersionUnsupported,
    HttpQdrantGateway,
)


def _gateway(handler: httpx.MockTransport) -> HttpQdrantGateway:
    client = HttpQdrantGateway("http://qdrant.test")
    client._client = httpx.AsyncClient(
        base_url="http://qdrant.test",
        transport=handler,
        timeout=5.0,
        limits=httpx.Limits(max_connections=20),
    )
    return client


@pytest.mark.asyncio
async def test_search_batch_json_shapes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search/batch"):
            body = json.loads(request.content)
            assert body["searches"][0]["vector"] == {"name": "dense_x", "vector": [0.1, 0.2]}
            assert body["searches"][1]["vector"] == {
                "name": "sparse_bm25h_v1",
                "vector": {"indices": [1, 2], "values": [0.5, 1.0]},
            }
            return httpx.Response(
                200,
                json={"result": [[{"id": "a", "score": 1.0, "payload": {}}], []]},
            )
        return httpx.Response(404)

    gateway = _gateway(httpx.MockTransport(handler))
    hits = await gateway.search_batch(
        "kb__acme-it-demo__rev-1",
        [
            {"vector": {"name": "dense_x", "vector": [0.1, 0.2]}, "limit": 30},
            {
                "vector": {
                    "name": "sparse_bm25h_v1",
                    "vector": {"indices": [1, 2], "values": [0.5, 1.0]},
                },
                "limit": 30,
            },
        ],
    )
    assert len(hits) == 2
    await gateway.aclose()


@pytest.mark.asyncio
async def test_version_gate_rejects_1_6() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"version": "1.6.1"})

    gateway = _gateway(httpx.MockTransport(handler))
    with pytest.raises(GatewayVersionUnsupported):
        await gateway.get_version()
    await gateway.aclose()


@pytest.mark.asyncio
async def test_version_accepts_1_7_4() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"version": "1.7.4"})

    gateway = _gateway(httpx.MockTransport(handler))
    assert await gateway.get_version() == "1.7.4"
    await gateway.aclose()


@pytest.mark.asyncio
async def test_404_and_5xx_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/missing"):
            return httpx.Response(404, json={"status": {"error": "not found"}})
        return httpx.Response(503, json={"status": {"error": "down"}})

    gateway = _gateway(httpx.MockTransport(handler))
    with pytest.raises(GatewayNotFound):
        await gateway.get_collection("missing")
    with pytest.raises(GatewayUnavailable):
        await gateway.get_collection("other")
    await gateway.aclose()


@pytest.mark.asyncio
async def test_upsert_uses_wait_true() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"result": {"status": "ok"}})

    gateway = _gateway(httpx.MockTransport(handler))
    await gateway.upsert_points("c1", [{"id": "1", "vector": {}, "payload": {}}])
    assert any("wait=true" in url for url in seen)
    await gateway.aclose()
