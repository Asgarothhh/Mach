# mts-rag

Retrieval building blocks for the MTS voice agent knowledge base (track 1), plus an in-memory
lexical `KnowledgeRetriever` stub. The stub lets the orchestrator and backend integrate against the
SSOT §14.2 contract before Qdrant, dense embeddings and the reranker exist.

- Distribution: `mts-rag`, import package `mts_rag`.
- Depends only on `mts-contracts-knowledge` (`mts_contracts.knowledge`). All request, result and
  error types come from there. This package never imports `mts_ingestion`.

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
MLB-S1-STUB and MLB-RET-11.

## Modules

| Module | Contents |
|---|---|
| `mts_rag.fusion` | `reciprocal_rank_fusion`, `FusedItem` (RRF, `k=60` by default) |
| `mts_rag.filters` | `resolve_filters`, `ResolvedFilter`, `scope_exclusion`, `temporal_exclusion` |
| `mts_rag.lexical` | `tokenize`, `lexical_score` |
| `mts_rag.evidence` | `detect_conflicts`, `compute_evidence_status` |
| `mts_rag.stub` | `InMemoryKnowledgeRetriever`, `LexicalStubSettings` |

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
- **Scoring:** the score is `|query terms ∩ chunk terms| / |query terms|`. The terms come from
  NFC + casefold + `\w+` tokens over the title, `section_path` and text. Candidates are chunks
  with score > 0, ordered by score descending, then `chunk_id`, and capped at `sparse_top_k`.
  Diagnostics fill `sparse_*` and `rrf_*`; `dense_*` and `rerank_*` stay `None`, and the mode is
  `stub_lexical`. The relevance threshold is `LexicalStubSettings.min_relevance_score`
  (default 0.5). It applies to the lexical score scale only and is not part of
  `RetrievalConfig`.
- **Determinism:** time comes from the injected `clock` (deadline, `duration_ms`) and `now`
  (default reference time). Results are deterministic for identical inputs.

## Known limitations

- Lexical only: no dense retrieval, sparse model or reranker yet, so paraphrases without shared
  words are not found. There is no stemming, so Russian inflections such as
  "роуминг"/"роуминга" don't match, and there is no ASR variant expansion.
- The stub uses a single query variant, the whitespace-normalised query.
- Conflict detection only covers several active revisions of the *same* document
  (`multiple_active_revisions`). Conflicting prices or terms across *different* documents are
  deferred to MLB-GRD-02.
- The threshold is not calibrated. MLB-GRD-01 will calibrate thresholds per retrieval mode.
- Crawl-age staleness is measured against the resolved reference time
  (`filters.reference_time`, or `now()` when it is not set).

## Privacy

`RetrievalResult.query_variants` contains raw user text. It is excluded from `repr`, but it is
still in `model_dump()`/JSON. Do not log or persist it unredacted; store only a redacted form or a
hash (SSOT §7.1, §8.3 `retrieval_events`). Error messages never include query or chunk text.
