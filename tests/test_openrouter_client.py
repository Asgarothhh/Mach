from app.orchestrator.openrouter_client import (
    GEMMA_MODEL_ID,
    STREAM_TIMEOUT_S,
    build_provider_options,
)
from app.orchestrator.dialog_flow import (
    normalize_llm_payload,
    parse_llm_json,
    resolve_llm_model_id,
)


def test_gemma_omits_zdr_even_when_required(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REQUIRE_ZDR", "true")
    provider = build_provider_options(GEMMA_MODEL_ID)
    assert provider == {"data_collection": "deny"}
    assert "zdr" not in provider


def test_zdr_attached_for_other_models_when_required(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REQUIRE_ZDR", "true")
    provider = build_provider_options("other/model")
    assert provider["zdr"] is True
    assert provider["data_collection"] == "deny"


def test_zdr_omitted_when_not_required(monkeypatch):
    monkeypatch.delenv("OPENROUTER_REQUIRE_ZDR", raising=False)
    assert "zdr" not in build_provider_options("other/model")


def test_stream_timeout_is_30s():
    assert STREAM_TIMEOUT_S == 30.0


def test_parse_llm_json_plain_and_fenced():
    payload = {"answer_text": "ok", "citation_ids": ["s1"], "answer_status": "grounded"}
    assert parse_llm_json('{"answer_text":"ok","citation_ids":["s1"],"answer_status":"grounded"}') == payload
    fenced = '```json\n{"answer_text": "ok", "citation_ids": ["s1"], "answer_status": "grounded"}\n```'
    assert parse_llm_json(fenced) == payload
    wrapped = 'Sure.\n{"answer_text": "ok", "citation_ids": ["s1"], "answer_status": "grounded"}\n'
    assert parse_llm_json(wrapped) == payload
    assert parse_llm_json("not json") is None


def test_normalize_verified_status_to_grounded():
    payload = normalize_llm_payload(
        {
            "answer_text": "Офис открыт.",
            "citation_ids": ["acme-hours-1"],
            "answer_status": "verified",
        }
    )
    assert payload["answer_status"] == "grounded"


def test_resolve_llm_model_id_stays_on_gemma(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL_ID", raising=False)
    assert resolve_llm_model_id() == GEMMA_MODEL_ID
    monkeypatch.setenv("OPENROUTER_MODEL_ID", GEMMA_MODEL_ID)
    assert resolve_llm_model_id() == GEMMA_MODEL_ID
    monkeypatch.setenv("OPENROUTER_MODEL_ID", "meta-llama/llama-3-8b-instruct")
    assert resolve_llm_model_id() == GEMMA_MODEL_ID
