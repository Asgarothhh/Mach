from typing import Any

import pytest

DOCUMENT_ID = "a" * 64
CONTENT_HASH = "b" * 64


@pytest.fixture
def chunk_data() -> dict[str, Any]:
    return {
        "chunk_id": "chunk-1",
        "document_id": DOCUMENT_ID,
        "revision_id": "rev-1",
        "source_url": "https://www.acme-it.example/help/roaming?utm_source=x",
        "canonical_url": "https://www.acme-it.example/help/roaming",
        "title": "Roaming",
        "section_path": ["Help", "Roaming"],
        "tenant_id": "acme-it-demo",
        "service": "roaming",
        "topic": "pricing",
        "audience": "caller",
        "language": "ru",
        "content_hash": CONTENT_HASH,
        "crawled_at": "2026-10-11T00:00:00Z",
        "published_at": None,
        "valid_from": None,
        "valid_to": None,
        "effective_status": "active",
        "source_type": "html",
        "trust_level": "tenant_approved_source",
        "text": "Roaming internet costs 5 BYN per day.",
    }


@pytest.fixture
def source_data() -> dict[str, Any]:
    return {
        "source_id": "acme-help",
        "tenant_id": "acme-it-demo",
        "url": "https://www.acme-it.example/help/",
        "kind": "web_section",
        "priority": "P0",
        "allow_path_prefixes": ["/help"],
        "deny_path_prefixes": ["/help/internal"],
        "refresh_interval": "P1D",
        "freshness_class": "service_page",
        "language": "ru",
        "audience": "caller",
        "status": "active",
        "owner": "role.business-owner",
        "approval": {
            "status": "approved",
            "approved_by": "role.business-owner",
            "approved_at": "2026-10-12T09:00:00Z",
        },
    }


@pytest.fixture
def registry_data(source_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": "acme-it-demo",
        "registry_version": 1,
        "display_name": "Acme IT (synthetic demo tenant)",
        "updated_at": "2026-10-13T10:00:00Z",
        "allowed_hosts": ["www.acme-it.example"],
        "manual_exclusions": [
            {
                "exclusion_id": "mx-001",
                "match": "prefix",
                "url": "https://www.acme-it.example/help/archive/",
                "reason": "Promotions archive 2024",
                "created_by": "role.business-owner",
                "created_at": "2026-10-12T08:00:00Z",
            }
        ],
        "sources": [source_data],
    }
