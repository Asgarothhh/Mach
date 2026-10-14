"""Qdrant REST gateway via httpx.AsyncClient (Qdrant 1.7 endpoints only)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx

_MIN_VERSION = (1, 7, 0)


class GatewayUnavailable(Exception):
    """Qdrant is unreachable, returned 5xx, or the version is unsupported."""


class GatewayNotFound(Exception):
    """Collection or resource was not found (HTTP 404)."""


class GatewayVersionUnsupported(GatewayUnavailable):
    """Qdrant reported a version below 1.7.0."""


@runtime_checkable
class QdrantGateway(Protocol):
    async def get_version(self) -> str: ...

    async def get_collection(self, name: str) -> dict[str, Any]: ...

    async def put_collection(self, name: str, body: dict[str, Any]) -> None: ...

    async def delete_collection(self, name: str) -> None: ...

    async def put_index(self, collection: str, body: dict[str, Any]) -> None: ...

    async def upsert_points(self, collection: str, points: list[dict[str, Any]]) -> None: ...

    async def search_batch(
        self, collection: str, searches: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]: ...

    async def count(self, collection: str, body: dict[str, Any]) -> int: ...

    async def scroll(self, collection: str, body: dict[str, Any]) -> list[dict[str, Any]]: ...

    async def get_aliases(self) -> list[dict[str, str]]: ...

    async def list_collections(self) -> list[str]: ...

    async def post_aliases(self, actions: list[dict[str, Any]]) -> None: ...

    async def aclose(self) -> None: ...


def parse_qdrant_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in value.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def version_supported(value: str) -> bool:
    parsed = parse_qdrant_version(value)
    padded = parsed + (0,) * (len(_MIN_VERSION) - len(parsed))
    return padded[: len(_MIN_VERSION)] >= _MIN_VERSION


class HttpQdrantGateway:
    """REST client for Qdrant 1.7.4. Timeouts come from the remaining retrieval budget."""

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            limits=httpx.Limits(max_connections=20),
        )

    async def get_version(self) -> str:
        payload = await self._request("GET", "/")
        version = ""
        if isinstance(payload, dict):
            raw = payload.get("version")
            version = str(raw) if raw is not None else ""
        if not version_supported(version):
            raise GatewayVersionUnsupported()
        return version

    async def get_collection(self, name: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/collections/{name}")
        result = payload.get("result", payload) if isinstance(payload, dict) else payload
        if not isinstance(result, dict):
            raise GatewayUnavailable()
        return result

    async def put_collection(self, name: str, body: dict[str, Any]) -> None:
        await self._request("PUT", f"/collections/{name}", json=body)

    async def delete_collection(self, name: str) -> None:
        await self._request("DELETE", f"/collections/{name}")

    async def put_index(self, collection: str, body: dict[str, Any]) -> None:
        await self._request("PUT", f"/collections/{collection}/index", json=body)

    async def upsert_points(self, collection: str, points: list[dict[str, Any]]) -> None:
        await self._request(
            "PUT",
            f"/collections/{collection}/points",
            params={"wait": "true"},
            json={"points": points},
        )

    async def search_batch(
        self, collection: str, searches: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        payload = await self._request(
            "POST",
            f"/collections/{collection}/points/search/batch",
            json={"searches": searches},
        )
        return _parse_search_batch(payload)

    async def count(self, collection: str, body: dict[str, Any]) -> int:
        payload = await self._request("POST", f"/collections/{collection}/points/count", json=body)
        result = payload.get("result", payload) if isinstance(payload, dict) else {}
        if not isinstance(result, dict):
            raise GatewayUnavailable()
        return int(result.get("count", 0))

    async def scroll(self, collection: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        payload = await self._request("POST", f"/collections/{collection}/points/scroll", json=body)
        result = payload.get("result", payload) if isinstance(payload, dict) else {}
        if not isinstance(result, dict):
            raise GatewayUnavailable()
        points = result.get("points", [])
        return list(points) if isinstance(points, list) else []

    async def list_collections(self) -> list[str]:
        payload = await self._request("GET", "/collections")
        result = payload.get("result", payload) if isinstance(payload, dict) else {}
        collections = result.get("collections", []) if isinstance(result, dict) else []
        names: list[str] = []
        if isinstance(collections, list):
            for item in collections:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
        return names

    async def get_aliases(self) -> list[dict[str, str]]:
        payload = await self._request("GET", "/aliases")
        result = payload.get("result", payload) if isinstance(payload, dict) else payload
        aliases: Any = result.get("aliases", []) if isinstance(result, dict) else result
        out: list[dict[str, str]] = []
        if isinstance(aliases, list):
            for item in aliases:
                if isinstance(item, dict) and "alias_name" in item and "collection_name" in item:
                    out.append(
                        {
                            "alias_name": str(item["alias_name"]),
                            "collection_name": str(item["collection_name"]),
                        }
                    )
        return out

    async def post_aliases(self, actions: list[dict[str, Any]]) -> None:
        await self._request("POST", "/collections/aliases", json={"actions": actions})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        error: str | None = None
        payload: Any = None
        try:
            response = await self._client.request(
                method, path, json=json, params=params, timeout=timeout
            )
        except httpx.HTTPError:
            error = "unavailable"
        else:
            if response.status_code == 404:
                error = "not_found"
            elif response.status_code >= 400:
                error = "unavailable"
            elif response.content:
                try:
                    payload = response.json()
                except ValueError:
                    error = "unavailable"
            else:
                payload = {}
        if error == "not_found":
            raise GatewayNotFound()
        if error is not None:
            raise GatewayUnavailable()
        return payload


def _parse_search_batch(payload: Any) -> list[list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise GatewayUnavailable()
    result = payload.get("result", [])
    if not isinstance(result, list):
        raise GatewayUnavailable()
    out: list[list[dict[str, Any]]] = []
    for item in result:
        hits: Any = item["result"] if isinstance(item, dict) and "result" in item else item
        if not isinstance(hits, list):
            raise GatewayUnavailable()
        out.append([hit for hit in hits if isinstance(hit, dict)])
    return out
