"""Knowledge runtime: stub by default, Qdrant hybrid when QDRANT_URL is set."""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mts_contracts.knowledge import (
    ACTIVE_INDEX_REVISION,
    ChunkMetadata,
    KnowledgeRetriever,
    RetrievalFilters,
)
from mts_rag import InMemoryKnowledgeRetriever
from mts_rag.embeddings import DenseEmbedder, OnnxDenseEmbedder
from mts_rag.cache import RedisResultCache, ResultCache
from mts_rag.qdrant import PAYLOAD_SCHEMA, QdrantHybridRetriever
from mts_rag.qdrant_http import HttpQdrantGateway, QdrantGateway
from mts_rag.rerank import OnnxCrossEncoderReranker, Reranker
from mts_rag.sparse import SPARSE_VECTOR_NAME

from app.rag.demo_fixtures import (
    ACME_TENANT_ID,
    DEMO_INDEX_REVISION,
    MTS_TENANT_ID,
    acme_chunks,
    mts_chunks,
)
from app.security.telemetry import get_logger

_PROBE_QUERY = "probe"
_PROBE_DEADLINE_MS = 50
_SEED_QUERY = "warmup"
_EMBED_WARMUP_TIMEOUT_S = 20.0
logger = get_logger("app.rag.retriever")


@dataclass(frozen=True)
class KnowledgeRuntime:
    retriever: KnowledgeRetriever
    tenants: frozenset[str]
    backend: str = "stub"
    health_probe: Callable[[], Awaitable[dict[str, str]]] | None = None
    knowledge_details: Callable[[], Awaitable[dict[str, Any]]] | None = None
    _on_start: Callable[[], Awaitable[None]] | None = field(default=None, repr=False)
    _on_close: Callable[[], Awaitable[None]] | None = field(default=None, repr=False)

    async def start(self) -> None:
        if self._on_start is not None:
            await self._on_start()

    async def close(self) -> None:
        if self._on_close is not None:
            await self._on_close()

    async def probe(self) -> dict[str, str]:
        """Resolve the active revision for each demo tenant. Errors map to unavailable."""
        if self.health_probe is not None:
            return await self.health_probe()
        statuses: dict[str, str] = {}
        for tenant_id in sorted(self.tenants):
            try:
                await self.retriever.retrieve(
                    _PROBE_QUERY,
                    tenant_id=tenant_id,
                    language="ru",
                    audience="caller",
                    filters=RetrievalFilters(),
                    index_revision=ACTIVE_INDEX_REVISION,
                    deadline_ms=_PROBE_DEADLINE_MS,
                )
            except Exception:  # noqa: BLE001 - probe maps any retrieve failure to unavailable
                statuses[tenant_id] = "unavailable"
            else:
                statuses[tenant_id] = "ok"
        return statuses

    async def knowledge_checks(self) -> dict[str, Any]:
        if self.knowledge_details is not None:
            return await self.knowledge_details()
        tenants = await self.probe()
        return {
            "backend": self.backend,
            "qdrant": "not_configured",
            "embedder": "disabled",
            "reranker": "disabled",
            "seed": "ok",
            "expected_mode": "sparse_only",
            "tenants": tenants,
        }


def build_demo_runtime() -> KnowledgeRuntime:
    retriever = InMemoryKnowledgeRetriever()
    retriever.publish(ACME_TENANT_ID, DEMO_INDEX_REVISION, acme_chunks(), activate=True)
    retriever.publish(MTS_TENANT_ID, DEMO_INDEX_REVISION, mts_chunks(), activate=True)
    return KnowledgeRuntime(
        retriever=retriever,
        tenants=frozenset({ACME_TENANT_ID, MTS_TENANT_ID}),
        backend="stub",
    )


def seed_revision(chunks: Sequence[ChunkMetadata], *, embedder: DenseEmbedder | None) -> str:
    digest = hashlib.sha256()
    digest.update(str(PAYLOAD_SCHEMA).encode("utf-8"))
    digest.update(b"|")
    digest.update(SPARSE_VECTOR_NAME.encode("utf-8"))
    digest.update(b"|")
    if embedder is None:
        digest.update(b"none")
    else:
        digest.update(f"{embedder.vector_name}+{embedder.model_revision}".encode())
    digest.update(b"|")
    for dumped in sorted(chunk.model_dump_json() for chunk in chunks):
        digest.update(dumped.encode("utf-8"))
        digest.update(b"\n")
    return f"{DEMO_INDEX_REVISION}.{digest.hexdigest()[:12]}"


def build_knowledge_runtime(
    environ: Mapping[str, str] | None = None,
    *,
    gateway: QdrantGateway | None = None,
    embedder: DenseEmbedder | None = None,
    reranker: Reranker | None = None,
) -> KnowledgeRuntime:
    env = os.environ if environ is None else environ
    url = str(env.get("QDRANT_URL") or "").strip()
    if not url and gateway is None:
        return build_demo_runtime()

    embedder_status = "disabled"
    reranker_status = "disabled"
    if embedder is None:
        embedder, embedder_status = _embedder_from_env(env)
    else:
        embedder_status = "unavailable"
    if reranker is None:
        reranker, reranker_status = _reranker_from_env(env)
    else:
        reranker_status = "unavailable"

    if gateway is None:
        gateway = HttpQdrantGateway(url)

    cache: ResultCache | None = None
    redis_url = str(env.get("REDIS_URL") or "").strip()
    if redis_url:
        cache = RedisResultCache(redis_url)

    retriever = QdrantHybridRetriever(
        gateway, embedder=embedder, reranker=reranker, cache=cache
    )
    tenants = frozenset({ACME_TENANT_ID, MTS_TENANT_ID})
    state = _QdrantRuntimeState(
        embedder=embedder_status,
        reranker=reranker_status,
        expected_mode="hybrid" if embedder is not None else "sparse_only",
    )

    async def on_start() -> None:
        if state.task is not None and not state.task.done():
            return
        state.task = asyncio.create_task(
            _seed_loop(retriever, embedder, reranker, state),
            name="mts-rag-seed",
        )

    async def on_close() -> None:
        task = state.task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await retriever.aclose()

    async def health_probe() -> dict[str, str]:
        return await _qdrant_tenant_probe(retriever, tenants)

    async def knowledge_details() -> dict[str, Any]:
        tenant_status = await health_probe()
        qdrant_status = "unavailable"
        sample_tenant = next(iter(sorted(tenants)), None)
        if sample_tenant is not None:
            failed = False
            info: dict[str, str] = {}
            try:
                async with asyncio.timeout(retriever.settings.health_timeout_s):
                    info = await retriever.health(sample_tenant)
            except Exception:  # noqa: BLE001 - health is informational
                failed = True
            if not failed:
                qdrant_status = info.get("qdrant", "unavailable")
        return {
            "backend": "qdrant",
            "qdrant": qdrant_status,
            "embedder": state.embedder,
            "reranker": state.reranker,
            "seed": state.seed,
            "expected_mode": state.expected_mode,
            "tenants": tenant_status,
        }

    return KnowledgeRuntime(
        retriever=retriever,
        tenants=tenants,
        backend="qdrant",
        health_probe=health_probe,
        knowledge_details=knowledge_details,
        _on_start=on_start,
        _on_close=on_close,
    )


@dataclass
class _QdrantRuntimeState:
    seed: str = "pending"
    embedder: str = "disabled"
    reranker: str = "disabled"
    expected_mode: str = "sparse_only"
    task: asyncio.Task[None] | None = None


def _embedder_from_env(environ: Mapping[str, str]) -> tuple[DenseEmbedder | None, str]:
    model_id = str(environ.get("EMBEDDING_MODEL_ID") or "bge-m3-onnx").strip()
    if model_id in {"", "none"}:
        return None, "disabled"
    return OnnxDenseEmbedder(Path("models/rag") / model_id), "unavailable"


def _reranker_from_env(environ: Mapping[str, str]) -> tuple[Reranker | None, str]:
    model_id = str(environ.get("RERANKER_MODEL_ID") or "none").strip()
    if model_id in {"", "none"}:
        return None, "disabled"
    return (
        OnnxCrossEncoderReranker(Path("models/rag") / model_id, model_revision=model_id),
        "unavailable",
    )


async def _qdrant_tenant_probe(
    retriever: QdrantHybridRetriever, tenants: frozenset[str]
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for tenant_id in sorted(tenants):
        failed = False
        info: dict[str, str] = {}
        try:
            async with asyncio.timeout(retriever.settings.health_timeout_s):
                info = await retriever.health(tenant_id)
        except Exception:  # noqa: BLE001 - probe must not raise
            failed = True
        if failed:
            statuses[tenant_id] = "unavailable"
            continue
        count = 0
        try:
            count = int(info.get("points") or 0)
        except ValueError:
            count = 0
        ok = info.get("qdrant") == "ok" and info.get("alias") == "ok" and count > 0
        statuses[tenant_id] = "ok" if ok else "unavailable"
    return statuses


async def _seed_loop(
    retriever: QdrantHybridRetriever,
    embedder: DenseEmbedder | None,
    reranker: Reranker | None,
    state: _QdrantRuntimeState,
) -> None:
    delay = 1.0
    while True:
        try:
            await _seed_once(retriever, embedder, reranker, state)
            state.seed = "ok"
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - retry until cancelled
            state.seed = "failed"
            logger.info(
                "knowledge_seed_retry",
                error_class=exc.__class__.__name__,
                delay_s=delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


async def _warmup_embedder(embedder: DenseEmbedder, timeout_s: float) -> bool:
    try:
        async with asyncio.timeout(timeout_s):
            await asyncio.to_thread(embedder.embed, [_SEED_QUERY], kind="query")
    except TimeoutError:
        logger.warning("embedder_warmup_timeout", timeout_s=timeout_s)
        return False
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - missing/broken weights degrade to sparse-only
        logger.info("embedder_warmup_failed", error_class=exc.__class__.__name__)
        return False
    return True


async def _publish_demo_corpora(
    retriever: QdrantHybridRetriever,
    embedder: DenseEmbedder | None,
) -> None:
    corpora = (
        (ACME_TENANT_ID, acme_chunks()),
        (MTS_TENANT_ID, mts_chunks()),
    )
    errors: list[BaseException] = []
    for tenant_id, chunks in corpora:
        revision = seed_revision(chunks, embedder=embedder)
        try:
            await retriever.publish(tenant_id, revision, chunks, activate=True)
        except Exception as exc:  # noqa: BLE001 - try the other tenant before giving up
            errors.append(exc)
            logger.warning(
                "knowledge_seed_tenant_failed",
                tenant_id=tenant_id,
                error_class=exc.__class__.__name__,
            )
            continue
        try:
            await retriever.retrieve(
                _SEED_QUERY,
                tenant_id=tenant_id,
                language="ru",
                audience="caller",
                filters=RetrievalFilters(),
                index_revision=ACTIVE_INDEX_REVISION,
                deadline_ms=1_000,
            )
        except Exception as exc:  # noqa: BLE001 - alias is already live
            logger.warning(
                "knowledge_seed_smoke_failed",
                tenant_id=tenant_id,
                error_class=exc.__class__.__name__,
            )
    if errors:
        raise errors[0]


async def _seed_once(
    retriever: QdrantHybridRetriever,
    embedder: DenseEmbedder | None,
    reranker: Reranker | None,
    state: _QdrantRuntimeState,
) -> None:
    # Sparse first so /health/ready and retrieve do not wait on BGE-M3 / torch.
    retriever.set_embedder(None)
    state.embedder = "unavailable" if embedder is not None else "disabled"
    state.expected_mode = "sparse_only"
    await _publish_demo_corpora(retriever, None)

    if reranker is not None:
        rerank_failed = False
        try:
            await asyncio.to_thread(reranker.score, _SEED_QUERY, [_SEED_QUERY])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - optional reranker
            rerank_failed = True
        state.reranker = "unavailable" if rerank_failed else "ok"

    if embedder is None:
        return
    if not await _warmup_embedder(embedder, _EMBED_WARMUP_TIMEOUT_S):
        return
    retriever.set_embedder(embedder)
    try:
        await _publish_demo_corpora(retriever, embedder)
    except Exception as exc:  # noqa: BLE001 - keep the sparse alias
        retriever.set_embedder(None)
        logger.warning("hybrid_seed_failed_keeping_sparse", error_class=exc.__class__.__name__)
        return
    state.embedder = "ok"
    state.expected_mode = "hybrid"
