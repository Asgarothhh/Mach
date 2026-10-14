# ADR-0002: Qdrant hybrid retrieval for track 1

- Status: accepted
- Date: 2026-10-14
- Owner: ML + Backend (RAG)
- SSOT: `docs/SPEC_MTS_VOICE_AGENT_TRACK1.md` §6.5–6.9, §14.2, FR-09, NFR-11

## Context

Group 1 shipped an in-memory lexical `KnowledgeRetriever` stub. This ADR connects Qdrant
hybrid retrieval (dense + sparse + client-side RRF) without a live crawler: demo chunks are
published at API startup when `QDRANT_URL` is set.

## Decisions (L1–L9)

1. **Modules.** New code lives in `packages/rag/src/mts_rag/` (`qdrant.py`, `qdrant_http.py`,
   `sparse.py`, `query.py`, `embeddings.py`, `rerank.py`, `_bounded.py`, `_request.py`,
   `testing.py`). `mts_rag/__init__.py` does not import Qdrant or ONNX. `IndexPublishError`
   is local to `mts_rag.qdrant`.
2. **Qdrant.** Image `qdrant/qdrant:v1.7.4` (sparse vectors; 1.6.1 cannot). REST via
   `httpx.AsyncClient`. No `qdrant-client`. Version below 1.7.0 is rejected.
3. **Collections.** One collection per `(tenant, revision)` named `kb__{tenant}__{revision}`.
   Alias `kb__{tenant}__active` is switched atomically. Isolation: name from requesting
   tenant, alias prefix check, `tenant_id` filter, payload post-check, publish rejects
   foreign chunks.
4. **Seed.** Only when `QDRANT_URL` is set. Revision
   `{DEMO_INDEX_REVISION}.{fp12}` from schema, sparse id, dense identity, and chunk dumps.
   Background task with backoff. Without `QDRANT_URL` the stub is unchanged. The orchestrator
   keeps the retriever instance created at import.
5. **Tests without weights.** `HashingFakeEmbedder` (dim 64), `InMemoryQdrantGateway`, and
   other fakes in `mts_rag.testing`.
6. **Embeddings.** BGE-M3 ONNX, lazy `onnxruntime`/`tokenizers`. Missing weights = unavailable.
   Sparse is client-side BM25-hash (`sparse_bm25h_v2`: tokens are stemmed and mapped to
   service-desk synonym concepts via `mts_rag.lexical.index_terms`; the name change changes
   the seed fingerprint, so a new collection is published). Reranker default `none`.
7. **Fallback.** No silent stub fallback when Qdrant is configured but down. Embedder/reranker
   failures degrade (`SPARSE_ONLY` / keep RRF). Overall deadline raises, no partial result.
   `excluded_counts` is empty in Qdrant mode.
8. **Retrieve cache.** Key is `sha256(tenant|revision|language|audience|filters|query)`.
   Stored JSON replaces `query_variants` with `cached`. Degraded results are not cached.
   Memory cache is default; `REDIS_URL` selects Redis. TTL 30s. New index revision changes
   the key, so activate invalidates naturally.
9. **API image.** `requirements-rag.txt` (`onnxruntime`, `tokenizers`) is installed only in
   `apps/api/Dockerfile`. No torch. Weights mounted read-only.

## Deviations from SSOT / earlier compose

- Qdrant bumped from v1.6.1 to v1.7.4 (sparse vectors; wget healthcheck replaced).
- BM25 IDF is computed client-side (1.7 has no IDF modifier).
- Fail-closed `RetrievalUnavailable` instead of serving a cached FAQ when Qdrant is down.
- Retrieve cache is on (memory or Redis); raw query is hashed, not stored.
- `excluded_counts` comes from a bounded payload scroll of the tenant collection.
- Demo-locked thresholds in `config/eval_thresholds.yaml` (MLB-GRD-01 still needed for production).
- After activate, unaliased older collections for the tenant are deleted (`keep_revisions=2`).
- No live crawler.
- Failed embed warmup detaches the embedder and fingerprints a sparse-only revision (enabling dense later creates a new revision); intentional reranker=none is not a degradation reason. If an attached embedder fails on document vectors, publish raises `IndexPublishError` and does not create a sparse collection under a hybrid revision name.

## Consequences

- Compose demo with `QDRANT_URL` uses hybrid retrieval after seed; unit tests keep the stub
  by unsetting `QDRANT_URL`.
- CPU BGE-M3 may exceed `embed_timeout_ms=120` and degrade to sparse-only until measured.
- Old collections are not garbage-collected automatically.
