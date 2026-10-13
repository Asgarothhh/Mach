import inspect
import typing

import pytest
from pydantic import BaseModel, TypeAdapter

import mts_contracts.knowledge as knowledge
from mts_contracts.knowledge import (
    AppliedFilters,
    EvidenceStatus,
    KnowledgeRetriever,
    RetrievalFilters,
    RetrievalMode,
    RetrievalResult,
)

SSOT_14_2_PARAMS = (
    ("query", str),
    ("tenant_id", str),
    ("language", str),
    ("audience", str),
    ("filters", RetrievalFilters),
    ("index_revision", str),
    ("deadline_ms", int),
)
ANNOTATED_TYPE_EXPORTS = (
    "AbsoluteHttpUrl",
    "HostName",
    "Identifier",
    "LanguageCode",
    "PathPrefix",
    "Sha256Hex",
    "ShortText",
    "Slug",
    "TenantId",
    "UtcDatetime",
)


def test_protocol_signature_matches_ssot() -> None:
    retrieve = KnowledgeRetriever.retrieve
    assert inspect.iscoroutinefunction(retrieve)
    params = list(inspect.signature(retrieve).parameters.values())
    assert params[0].name == "self"
    assert [p.name for p in params[1:]] == [name for name, _ in SSOT_14_2_PARAMS]
    assert params[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params[2:])
    assert all(p.default is inspect.Parameter.empty for p in params)
    hints = typing.get_type_hints(retrieve)
    for name, annotation in SSOT_14_2_PARAMS:
        assert hints[name] is annotation
    assert hints["return"] is RetrievalResult


class _EmptyRetriever:
    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        language: str,
        audience: str,
        filters: RetrievalFilters,
        index_revision: str,
        deadline_ms: int,
    ) -> RetrievalResult:
        return RetrievalResult(
            tenant_id=tenant_id,
            index_revision="idx-1",
            retrieval_mode=RetrievalMode.STUB_LEXICAL,
            config_version="retrieval-v1",
            query_variants=(query,),
            applied_filters=AppliedFilters.model_validate(
                {
                    **filters.model_dump(exclude={"reference_time"}),
                    "tenant_id": tenant_id,
                    "language": language,
                    "audience": audience,
                    "reference_time": "2026-10-13T10:00:00Z",
                }
            ),
            candidates=(),
            chunks=(),
            evidence_status=EvidenceStatus.NO_EVIDENCE,
            top_score=None,
            duration_ms=0,
        )


@pytest.mark.asyncio
async def test_structural_implementation_satisfies_protocol() -> None:
    retriever: KnowledgeRetriever = _EmptyRetriever()
    result = await retriever.retrieve(
        "roaming price",
        tenant_id="acme-it-demo",
        language="ru",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=800,
    )
    assert result.evidence_status is EvidenceStatus.NO_EVIDENCE
    assert not result.is_answerable


def test_all_exports_have_json_schema() -> None:
    assert len(set(knowledge.__all__)) == len(knowledge.__all__)
    for name in knowledge.__all__:
        assert hasattr(knowledge, name), name
    models = [
        obj
        for name in knowledge.__all__
        if isinstance(obj := getattr(knowledge, name), type) and issubclass(obj, BaseModel)
    ]
    assert len(models) == 16
    for model in models:
        schema = model.model_json_schema()
        assert schema["additionalProperties"] is False, model.__name__
        assert model.model_config.get("frozen") is True, model.__name__
    for name in ANNOTATED_TYPE_EXPORTS:
        assert TypeAdapter(getattr(knowledge, name)).json_schema()
