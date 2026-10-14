"""In-memory demo chunks for Stage 0. Conflict/stale indexes live only in tests."""

from __future__ import annotations

import hashlib
import unicodedata
from datetime import UTC, datetime

from mts_contracts.knowledge import (
    Audience,
    ChunkMetadata,
    EffectiveStatus,
    SourceType,
    TrustLevel,
)

DEMO_INDEX_REVISION = "demo-2026-10-13"
ACME_TENANT_ID = "acme-it-demo"
MTS_TENANT_ID = "mts-public-demo"
DEMO_CRAWLED_AT = datetime(2026, 10, 11, tzinfo=UTC)


def compute_document_id(tenant_id: str, canonical_url: str) -> str:
    return hashlib.sha256(
        b"mts-doc-v1" + tenant_id.encode("utf-8") + canonical_url.encode("utf-8")
    ).hexdigest()


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()


def _chunk(
    *,
    chunk_id: str,
    tenant_id: str,
    canonical_url: str,
    title: str,
    text: str,
    service: str,
    topic: str,
    trust_level: TrustLevel,
    source_id: str,
) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=chunk_id,
        document_id=compute_document_id(tenant_id, canonical_url),
        revision_id="rev-1",
        source_url=canonical_url,
        canonical_url=canonical_url,
        title=title,
        section_path=(title,),
        tenant_id=tenant_id,
        service=service,
        topic=topic,
        audience=Audience.CALLER,
        language="ru",
        content_hash=compute_content_hash(text),
        crawled_at=DEMO_CRAWLED_AT,
        published_at=None,
        valid_from=None,
        valid_to=None,
        effective_status=EffectiveStatus.ACTIVE,
        source_type=SourceType.HTML,
        trust_level=trust_level,
        text=text,
        source_id=source_id,
        anchor=None,
        parser_version=None,
    )


def acme_chunks() -> tuple[ChunkMetadata, ...]:
    """Synthetic business FAQ. Queries are matched via stems and synonym concepts."""
    return (
        _chunk(
            chunk_id="acme-hours-1",
            tenant_id=ACME_TENANT_ID,
            canonical_url="https://www.acme-it.example/help/hours",
            title="График работы",
            text="Офис Acme открыт понедельник пятница девять восемнадцать часов.",
            service="support",
            topic="hours",
            trust_level=TrustLevel.TENANT_APPROVED_SOURCE,
            source_id="acme-hours",
        ),
        _chunk(
            chunk_id="acme-price-1",
            tenant_id=ACME_TENANT_ID,
            canonical_url="https://www.acme-it.example/help/pricing",
            title="Прайс-лист",
            text="Лицензия Acme Professional стоит девяносто девять рублей ежемесячно.",
            service="pricing",
            topic="license",
            trust_level=TrustLevel.TENANT_APPROVED_SOURCE,
            source_id="acme-pricing",
        ),
        _chunk(
            chunk_id="acme-contacts-1",
            tenant_id=ACME_TENANT_ID,
            canonical_url="https://www.acme-it.example/help/contacts",
            title="Контакты",
            text="Поддержка Acme доступна через почту support@acme-it.example.",
            service="support",
            topic="contacts",
            trust_level=TrustLevel.TENANT_APPROVED_SOURCE,
            source_id="acme-contacts",
        ),
    )


def mts_chunks() -> tuple[ChunkMetadata, ...]:
    """Legacy public MTS help fixtures. Hosts follow C6 (www.mts.by/help only)."""
    return (
        _chunk(
            chunk_id="mts-roaming-1",
            tenant_id=MTS_TENANT_ID,
            canonical_url="https://www.mts.by/help/roaming",
            title="Роуминг в Турции",
            text="Входящие звонки в Турции стоят полтора рубля за минуту. Исходящие три рубля.",
            service="roaming",
            topic="pricing",
            trust_level=TrustLevel.LEGACY_DEMO_FIXTURE,
            source_id="mts-help-roaming",
        ),
        _chunk(
            chunk_id="mts-ussd-1",
            tenant_id=MTS_TENANT_ID,
            canonical_url="https://www.mts.by/help/",
            title="Справка МТС",
            text="Баланс проверяется командой USSD звёздочка сто решётка.",
            service="selfcare",
            topic="balance",
            trust_level=TrustLevel.LEGACY_DEMO_FIXTURE,
            source_id="mts-help-ussd",
        ),
    )
