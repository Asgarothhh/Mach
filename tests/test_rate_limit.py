from tests.conftest import ACME_SUFFICIENT_QUERY


def _create_session(client) -> str:
    response = client.post(
        "/api/v1/sessions",
        json={"tenant_id": "acme-it-demo", "channel": "text", "language": "ru"},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def test_create_session_11th_in_a_minute_is_429(api_client):
    payload = {"tenant_id": "acme-it-demo", "channel": "text", "language": "ru"}
    for _ in range(10):
        response = api_client.post("/api/v1/sessions", json=payload)
        assert response.status_code == 200, response.text
    blocked = api_client.post("/api/v1/sessions", json=payload)
    assert blocked.status_code == 429


def test_text_turns_session_limit_does_not_block_another_session(api_client):
    first = _create_session(api_client)
    for _ in range(20):
        response = api_client.post(
            f"/api/v1/sessions/{first}/turns/text",
            json={"text": ACME_SUFFICIENT_QUERY},
        )
        assert response.status_code == 200, response.text
    blocked = api_client.post(
        f"/api/v1/sessions/{first}/turns/text",
        json={"text": ACME_SUFFICIENT_QUERY},
    )
    assert blocked.status_code == 429

    second = _create_session(api_client)
    other = api_client.post(
        f"/api/v1/sessions/{second}/turns/text",
        json={"text": ACME_SUFFICIENT_QUERY},
    )
    assert other.status_code == 200, other.text
