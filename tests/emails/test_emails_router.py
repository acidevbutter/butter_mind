from app.core.dependencies import get_email_provider, require_internal_api_key
from app.main import app
from tests.factories import FakeEmailProvider


async def _create_tenant_and_key(client) -> str:
    app.dependency_overrides[require_internal_api_key] = lambda: None
    created = await client.post(
        "/tenants/", json={"name": "Acme", "contact_email": "ops@acme.test"}
    )
    return created.json()["api_key"]["api_key"]


async def _register_and_verify_domain(client, api_key: str) -> None:
    await client.post(
        "/sender-domains/", json={"domain": "acme.com"}, headers={"X-Api-Key": api_key}
    )
    domains = await client.get("/sender-domains/", headers={"X-Api-Key": api_key})
    domain_id = domains.json()[0]["id"]
    await client.post(f"/sender-domains/{domain_id}/verify", headers={"X-Api-Key": api_key})


async def test_send_email_from_verified_domain(client):
    api_key = await _create_tenant_and_key(client)
    fake_email = FakeEmailProvider()
    app.dependency_overrides[get_email_provider] = lambda: fake_email
    await _register_and_verify_domain(client, api_key)

    response = await client.post(
        "/emails/send",
        json={
            "from_email": "noreply@acme.com",
            "from_name": "Acme",
            "to": [{"email": "user@example.com"}],
            "subject": "Hello",
            "html_content": "<p>Hi</p>",
        },
        headers={"X-Api-Key": api_key},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "sent"
    assert body["provider_message_id"] == "<fake-message-id@relay.test>"
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].sender.email == "noreply@acme.com"
    assert fake_email.sent[0].to[0].email == "user@example.com"


async def test_send_email_from_unverified_domain_is_rejected(client):
    api_key = await _create_tenant_and_key(client)
    app.dependency_overrides[get_email_provider] = lambda: FakeEmailProvider()

    response = await client.post(
        "/emails/send",
        json={
            "from_email": "noreply@unregistered.com",
            "to": [{"email": "user@example.com"}],
            "subject": "Hello",
            "html_content": "<p>Hi</p>",
        },
        headers={"X-Api-Key": api_key},
    )
    assert response.status_code == 422
    assert "unregistered.com" in response.json()["detail"]


async def test_send_email_from_another_tenants_verified_domain_is_rejected(client):
    app.dependency_overrides[require_internal_api_key] = lambda: None
    app.dependency_overrides[get_email_provider] = lambda: FakeEmailProvider()

    tenant_a = (
        await client.post("/tenants/", json={"name": "Acme", "contact_email": "a@acme.test"})
    ).json()
    tenant_b = (
        await client.post("/tenants/", json={"name": "Beta", "contact_email": "b@beta.test"})
    ).json()
    key_a = tenant_a["api_key"]["api_key"]
    key_b = tenant_b["api_key"]["api_key"]
    await _register_and_verify_domain(client, key_a)

    response = await client.post(
        "/emails/send",
        json={
            "from_email": "noreply@acme.com",
            "to": [{"email": "user@example.com"}],
            "subject": "Hello",
            "html_content": "<p>Hi</p>",
        },
        headers={"X-Api-Key": key_b},
    )
    assert response.status_code == 422


async def test_send_email_requires_html_or_text_content(client):
    api_key = await _create_tenant_and_key(client)

    response = await client.post(
        "/emails/send",
        json={
            "from_email": "noreply@acme.com",
            "to": [{"email": "user@example.com"}],
            "subject": "Hello",
        },
        headers={"X-Api-Key": api_key},
    )
    assert response.status_code == 422
