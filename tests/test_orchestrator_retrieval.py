import asyncio
import json

import pytest
from mts_contracts.knowledge import (
    ACTIVE_INDEX_REVISION,
    IndexRevisionNotFound,
    InvalidRetrievalRequest,
    RetrievalDeadlineExceeded,
    RetrievalFilters,
    RetrievalUnavailable,
    TenantIsolationError,
)

from app.orchestrator.state_machine import SessionState
from app.security.guardrails import GuardrailDecision, GuardrailsService
from tests.conftest import (
    ACME_ASKING_MTS_QUERY,
    ACME_SUFFICIENT_QUERY,
    NO_EVIDENCE_QUERY,
    bind_session,
    conflict_retriever,
    injection_retriever,
    make_orchestrator,
    stale_retriever,
)
from tests.fakes import CountingLLM, HangingRetriever, RaisingRetriever, SpyRetriever


@pytest.mark.asyncio
async def test_retrieve_keyword_only_and_tenant_from_binding(demo_runtime, counting_llm):
    spy = SpyRetriever(demo_runtime.retriever)
    orch, manager, _store, _ = make_orchestrator(spy, llm=counting_llm)
    bind_session(manager, tenant_id="acme-it-demo")
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert len(spy.calls) == 1
    call = spy.calls[0]
    assert call["query"] == ACME_SUFFICIENT_QUERY
    assert call["tenant_id"] == "acme-it-demo"
    assert call["language"] == "ru"
    assert call["audience"] == "caller"
    assert isinstance(call["filters"], RetrievalFilters)
    assert call["index_revision"] == ACTIVE_INDEX_REVISION
    assert 150 <= call["deadline_ms"] <= 250
    assert outcome.answer_status == "grounded"
    assert outcome.citation_ids


@pytest.mark.asyncio
async def test_isolation_real_stub_both_fixtures(demo_runtime, counting_llm):
    orch, manager, store, llm = make_orchestrator(demo_runtime.retriever, llm=counting_llm)
    bind_session(manager, tenant_id="acme-it-demo")
    outcome = await orch.run_turn("s1", ACME_ASKING_MTS_QUERY, channel="text")
    assert outcome.answer_status == "no_evidence"
    assert outcome.citation_ids == []
    assert outcome.sources == []
    assert llm.calls == 0
    event = store.retrieval_events[0]
    candidate_ids = [item["chunk_id"] for item in (event.candidates or [])]
    assert all(not cid.startswith("mts-") for cid in candidate_ids)


@pytest.mark.asyncio
async def test_cancel_during_retrieve_raises_cancelled_no_pending(counting_llm):
    hanging = HangingRetriever()
    orch, manager, _, llm = make_orchestrator(hanging, llm=counting_llm)
    bind_session(manager)
    task = asyncio.create_task(orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text"))
    await hanging.started.wait()
    manager.active_turns["s1"].cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    current = asyncio.current_task()
    leftover = [item for item in asyncio.all_tasks() if item is not current and not item.done()]
    assert leftover == []
    assert llm.calls == 0
    assert manager.active_sessions["s1"] == SessionState.INTERRUPTED


@pytest.mark.asyncio
async def test_deadline_exceeded_handoff_no_llm(counting_llm):
    retriever = RaisingRetriever(RetrievalDeadlineExceeded("retrieval deadline exceeded"))
    orch, manager, _store, llm = make_orchestrator(retriever, llm=counting_llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == "handoff"
    assert outcome.fallback_reason == "retrieval_timeout"
    assert outcome.sources == []
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_outer_timeout_maps_to_timeout(counting_llm, monkeypatch):
    from app.orchestrator import dialog_flow

    monkeypatch.setattr(dialog_flow, "RETRIEVE_TIMEOUT_S", 0.05)
    hanging = HangingRetriever()
    orch, manager, _, llm = make_orchestrator(hanging, llm=counting_llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == "handoff"
    assert outcome.fallback_reason == "retrieval_timeout"
    assert llm.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "status", "reason"),
    [
        (RetrievalUnavailable("down"), "handoff", "retrieval_unavailable"),
        (IndexRevisionNotFound("index revision not found"), "handoff", "retrieval_unavailable"),
        (InvalidRetrievalRequest(("query",)), "needs_clarification", "invalid_request"),
        (TenantIsolationError("cross tenant"), "handoff", "isolation_violation"),
    ],
)
async def test_error_mapping(exc, status, reason, counting_llm):
    orch, manager, _, llm = make_orchestrator(RaisingRetriever(exc), llm=counting_llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == status
    assert outcome.fallback_reason == reason
    assert outcome.sources == []
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_llm_not_called_for_no_evidence(demo_runtime, counting_llm):
    orch, manager, _, llm = make_orchestrator(demo_runtime.retriever, llm=counting_llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", NO_EVIDENCE_QUERY, channel="text")
    assert outcome.answer_status == "no_evidence"
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_llm_not_called_for_conflict(counting_llm):
    orch, manager, store, llm = make_orchestrator(conflict_retriever(), llm=counting_llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == "handoff"
    assert outcome.fallback_reason == "evidence_conflict"
    assert outcome.sources == []
    assert llm.calls == 0
    event = store.retrieval_events[0]
    assert "acme-conflict-a" in (event.conflict_chunk_ids or [])


@pytest.mark.asyncio
async def test_llm_not_called_for_stale(counting_llm):
    orch, manager, _, llm = make_orchestrator(stale_retriever(), llm=counting_llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == "handoff"
    assert outcome.fallback_reason == "stale_only"
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_empty_citations_rejected(demo_runtime):
    llm = CountingLLM(
        chunks=[
            json.dumps(
                {"answer_text": "факт", "citation_ids": [], "answer_status": "grounded"},
                ensure_ascii=False,
            )
        ]
    )
    orch, manager, _, _ = make_orchestrator(demo_runtime.retriever, llm=llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == "no_evidence"
    assert outcome.fallback_reason == "output_validation_failed"
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_invented_citation_rejected(demo_runtime):
    llm = CountingLLM(
        chunks=[
            json.dumps(
                {
                    "answer_text": "факт",
                    "citation_ids": ["invented-id"],
                    "answer_status": "grounded",
                },
                ensure_ascii=False,
            )
        ]
    )
    orch, manager, _, _ = make_orchestrator(demo_runtime.retriever, llm=llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == "no_evidence"
    assert outcome.fallback_reason == "output_validation_failed"


@pytest.mark.asyncio
async def test_injected_snippet_dropped(counting_llm):
    orch, manager, _, llm = make_orchestrator(injection_retriever(), llm=counting_llm)
    bind_session(manager)
    outcome = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert outcome.answer_status == "no_evidence"
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_block_path_uses_human_handoff():
    class BlockingGuardrails(GuardrailsService):
        def process_input(self, text: str) -> GuardrailDecision:
            return GuardrailDecision(
                decision="block",
                redacted_text=text,
                categories=["injection"],
                reason_codes=["BLOCK"],
            )

    orch, manager, _, _ = make_orchestrator(
        RaisingRetriever(AssertionError("retrieve must not run")),
        guardrails=BlockingGuardrails(),
    )
    bind_session(manager)
    outcome = await orch.run_turn("s1", "bad", channel="text")
    assert outcome.answer_status == "handoff"
    assert outcome.fallback_reason == "blocked"
    assert manager.active_sessions["s1"] == SessionState.HUMAN_HANDOFF
