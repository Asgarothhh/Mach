# mts-rag

Retrieval building blocks for the MTS voice agent knowledge base (track 1): filters, RRF,
evidence status, an in-memory lexical stub, and Qdrant hybrid retrieval (dense + BM25-hash
sparse + client-side RRF).

- Distribution: `mts-rag`, import package `mts_rag`.
- Depends only on `mts-contracts-knowledge` (`mts_contracts.knowledge`). All request, result and
  error types come from there. This package never imports `mts_ingestion`.
- `mts_rag/__init__.py` does not import Qdrant or ONNX. Import `mts_rag.qdrant` when you need
  the hybrid retriever.

## SSOT references

`docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`:

- §6.3: freshness policy (stale and expired evidence must not be confirmed).
- §6.5: chunk metadata.
- §6.7: runtime retrieval (filters before ranking, RRF, top-k defaults).
- §6.8: grounding and `answer_status`.
- §7.2: `evidence_conflict`.
- §10: no unconfirmed facts on timeout.
- §14.2: `KnowledgeRetriever` protocol.

The work items are in `docs/MTS_VOICE_AGENT_4_DEVELOPERS.md` §4: MLB-RET-05, MLB-RET-06,
MLB-S1-STUB, MLB-RET-11, MLB-RET-12 (cache deferred). Architecture: `docs/adr/ADR-0002-qdrant-hybrid-retrieval.md`.

## Modules

| Module | Contents |
|---|---|
| `mts_rag.fusion` | `reciprocal_rank_fusion`, `FusedItem` (RRF, `k=60` by default) |
| `mts_rag.filters` | `resolve_filters`, `ResolvedFilter`, `scope_exclusion`, `temporal_exclusion` |
| `mts_rag.lexical` | `tokenize`, `lexical_score` |
| `mts_rag.evidence` | `detect_conflicts`, `compute_evidence_status` |
| `mts_rag.stub` | `InMemoryKnowledgeRetriever`, `LexicalStubSettings` |
| `mts_rag.qdrant` | `QdrantHybridRetriever` (import this module directly) |
| `mts_rag.qdrant_http` | `HttpQdrantGateway` (Qdrant 1.7 REST via httpx) |
| `mts_rag.sparse` | `Bm25HashSparseEncoder` (`sparse_bm25h_v2`, stemmed/concept terms) |
| `mts_rag.testing` | `HashingFakeEmbedder`, `InMemoryQdrantGateway` |

## Install and test

Install it in the same pip call as the contracts package. pip then resolves the local
distributions instead of looking for them on PyPI.

```bash
conda run -n mach pip install --no-deps --no-build-isolation \
    -e packages/contracts/knowledge -e packages/rag
```

From `packages/rag`:

```bash
conda run -n mach pytest -q
conda run -n mach ruff check .
conda run -n mach ruff format --check .
conda run -n mach mypy src tests
```

## Using the stub

```python
from mts_contracts.knowledge import KnowledgeRetriever, RetrievalFilters
from mts_rag import InMemoryKnowledgeRetriever

retriever: KnowledgeRetriever = InMemoryKnowledgeRetriever()
retriever.publish("acme-it-demo", "idx-2026-10-13", chunks)  # activates by default

result = await retriever.retrieve(
    "сколько стоит роуминг",
    tenant_id="acme-it-demo",
    language="ru",
    audience="caller",
    filters=RetrievalFilters(services=("roaming",)),
    index_revision="active",  # resolved; result.index_revision is the concrete revision
    deadline_ms=300,
)
```

Errors are typed: `InvalidRetrievalRequest`, `IndexRevisionNotFound`, `RetrievalDeadlineExceeded`,
`RetrievalUnavailable` and `TenantIsolationError`.
- An empty or low-relevance result is never an exception. It is reported through
  `evidence_status`.
- `asyncio.CancelledError` always propagates.
- On a deadline the stub raises instead of returning a partial result.

## Evidence status → LLM `answer_status`

Only `sufficient` permits a grounded answer (`RetrievalResult.is_answerable`).

| `evidence_status` | Chunks returned | Backend / LLM handling |
|---|---|---|
| `sufficient` | yes | `grounded` allowed; cite only returned chunks (§6.8) |
| `no_evidence` | no | `no_evidence` or `needs_clarification` |
| `low_relevance` | no | `no_evidence` or `needs_clarification` ("not enough confirmation") |
| `stale_only` | no | "cannot reliably confirm" (§6.3); offer an official channel or handoff |
| `evidence_conflict` | yes (diagnostics only) | safe fallback or `handoff` (§7.2); do not state the value |

`stale_only` covers three cases:
- the only relevant matches were expired (`valid_to <= reference_time`);
- the only relevant matches had a non-allowed `effective_status` (`outdated_matches > 0`);
- every selected chunk was older than `RetrievalConfig.stale_after`.

## Stub behaviour

- **Tenant isolation:** chunks are stored per `(tenant_id, index_revision)`, and a request only
  reads its own bucket. Other tenants' chunks are never tokenised, scored or counted. `publish`
  rejects chunks from another tenant, and a post-check raises `TenantIsolationError` if a foreign
  chunk ever reaches the candidates. An unknown revision and a revision owned by another tenant
  produce the same `IndexRevisionNotFound` message.
- **Revisions:** revisions are immutable, and the name `active` is reserved. `activate()` switches
  the active revision atomically. Each call takes a snapshot of its revision, so a concurrent
  `activate()` cannot mix two revisions in one result. The stub is safe within a single event
  loop, not across threads.
- **Filters** run before ranking, and the first matching reason is counted in `excluded_counts`:
  1. language, audience (exact match);
  2. services, topics, source types, document IDs;
  3. status, `valid_from > t` (not yet valid), `valid_to <= t` (expired). The validity
     interval is half-open.
- **Scoring:** the score is `term_coverage(query_terms(query), document_terms(chunk))`: the
  share of query content terms found in the chunk. Terms come from NFC + casefold + `\w+`
  tokens over the title, `section_path` and text, then a light Russian stemmer and a few
  service-desk synonym concepts (price, hours, contact, support, balance). On the query side,
  politeness fillers, question words, pronouns and prepositions are not counted, and neither
  are negation particles (they stay in the query text). Stems of 4+ characters also match by
  shared prefix. Candidates are chunks
  with score > 0, ordered by score descending, then `chunk_id`, and capped at `sparse_top_k`.
  Diagnostics fill `sparse_*` and `rrf_*`; `dense_*` and `rerank_*` stay `None`, and the mode is
  `stub_lexical`. The relevance threshold is `LexicalStubSettings.min_relevance_score`
  (default 0.5). It applies to the lexical score scale only and is not part of
  `RetrievalConfig`.
- **Determinism:** time comes from the injected `clock` (deadline, `duration_ms`) and `now`
  (default reference time). Results are deterministic for identical inputs.

## Qdrant hybrid (when `QDRANT_URL` is set)

The API process chooses the backend in `build_knowledge_runtime()`:

| Condition | Backend |
|---|---|
| `QDRANT_URL` unset | lexical stub (demo chunks in memory) |
| `QDRANT_URL` set | `QdrantHybridRetriever`; no silent stub fallback if Qdrant is down |

Compose pins `qdrant/qdrant:v1.7.4` and sets `QDRANT_URL=http://qdrant:6333`. Seed runs in a
lifespan background task (`acme_chunks` / `mts_chunks`, `activate=True`) with retry 1s→30s.
The `DialogOrchestrator` keeps the retriever instance created at import.

```bash
# Host Qdrant (optional; compose already starts the service)
docker compose --profile demo up -d qdrant
# API image installs onnxruntime/tokenizers; weights are NOT downloaded.
# Place BGE-M3 ONNX under models/rag/bge-m3-onnx/ (model.onnx + tokenizer.json).
# Without weights the retriever degrades to sparse-only (`SPARSE_ONLY` + `EMBEDDER_UNAVAILABLE`).
```

Ready (`GET /health/ready`) `checks.knowledge.backend` is `qdrant` or `stub`. In Qdrant mode
`checks.retriever=ok` requires every demo tenant: version ≥ 1.7, alias resolves, point count > 0.
No embedding is done on the health path.

## Known limitations

- Retrieve cache stores hashed keys and omits query text; Redis is used when `REDIS_URL` is set.
- `excluded_counts` is computed by scrolling the tenant collection (cap `exclusion_scroll_limit`).
- Demo-locked gates live in `config/eval_thresholds.yaml`; production calibration is MLB-GRD-01.
- No live crawler: only demo fixtures are published at startup.
- If Qdrant is configured but down / 5xx / version < 1.7, retrieve raises `RetrievalUnavailable`
  (HTTP 503 on ready). There is no silent stub fallback.
- The stub remains lexical-only (stemming and synonym concepts, no embeddings). Because
  coverage ignores function words, a query with a partly different entity (another country or
  product) can pass the 0.5 gate; the orchestrator prompt then requires the model to say the
  data is missing. The synonym concepts are generic and small; tenant vocabularies are not
  modelled.
- Conflict detection only covers several active revisions of the *same* document
  (`multiple_active_revisions`). Conflicting prices or terms across *different* documents are
  deferred to MLB-GRD-02.
- Crawl-age staleness is measured against the resolved reference time
  (`filters.reference_time`, or `now()` when it is not set).

## Privacy

`RetrievalResult.query_variants` contains raw user text. It is excluded from `repr`, but it is
still in `model_dump()`/JSON. Do not log or persist it unredacted; store only a redacted form or a
hash (SSOT §7.1, §8.3 `retrieval_events`). Error messages never include query or chunk text.
