from app.core.dependencies import get_email_provider, require_internal_api_key
from app.core.email.schemas import DomainVerificationResult
from app.main import app
from tests.factories import FakeEmailProvider


async def _create_tenant_and_key(client) -> str:
    app.dependency_overrides[require_internal_api_key] = lambda: None
    created = await client.post(
        "/tenants/", json={"name": "Acme", "contact_email": "ops@acme.test"}
    )
    return created.json()["api_key"]["api_key"]


async def test_register_sender_domain_returns_dns_records(client):
    api_key = await _create_tenant_and_key(client)
    fake_email = FakeEmailProvider()
    app.dependency_overrides[get_email_provider] = lambda: fake_email

    response = await client.post(
        "/sender-domains/", json={"domain": "acme.com"}, headers={"X-Api-Key": api_key}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["domain"] == "acme.com"
    assert body["status"] == "pending"
    assert body["verified_at"] is None
    assert body["dns_records"][0]["host_name"] == "mail._domainkey.acme.com"
    assert fake_email.authenticated_domains == ["acme.com"]


async def test_verify_sender_domain_marks_it_verified(client):
    api_key = await _create_tenant_and_key(client)
    app.dependency_overrides[get_email_provider] = lambda: FakeEmailProvider()

    registered = await client.post(
        "/sender-domains/", json={"domain": "acme.com"}, headers={"X-Api-Key": api_key}
    )
    domain_id = registered.json()["id"]

    verified = await client.post(
        f"/sender-domains/{domain_id}/verify", headers={"X-Api-Key": api_key}
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"
    assert verified.json()["verified_at"] is not None


async def test_verify_sender_domain_stays_pending_until_dns_resolves(client):
    api_key = await _create_tenant_and_key(client)
    not_verified = DomainVerificationResult(verified=False, dns_records=[])
    app.dependency_overrides[get_email_provider] = lambda: FakeEmailProvider(
        verify_result=not_verified
    )

    registered = await client.post(
        "/sender-domains/", json={"domain": "acme.com"}, headers={"X-Api-Key": api_key}
    )
    domain_id = registered.json()["id"]

    verified = await client.post(
        f"/sender-domains/{domain_id}/verify", headers={"X-Api-Key": api_key}
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "pending"
    assert verified.json()["verified_at"] is None


async def test_duplicate_domain_registration_returns_409(client):
    api_key = await _create_tenant_and_key(client)
    app.dependency_overrides[get_email_provider] = lambda: FakeEmailProvider()

    first = await client.post(
        "/sender-domains/", json={"domain": "acme.com"}, headers={"X-Api-Key": api_key}
    )
    assert first.status_code == 201

    second = await client.post(
        "/sender-domains/", json={"domain": "acme.com"}, headers={"X-Api-Key": api_key}
    )
    assert second.status_code == 409


async def test_verify_domain_owned_by_another_tenant_returns_404(client):
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

    registered = await client.post(
        "/sender-domains/", json={"domain": "acme.com"}, headers={"X-Api-Key": key_a}
    )
    domain_id = registered.json()["id"]

    response = await client.post(
        f"/sender-domains/{domain_id}/verify", headers={"X-Api-Key": key_b}
    )
    assert response.status_code == 404
