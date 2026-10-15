from app.core.dependencies import get_email_provider, require_internal_api_key
from app.main import app
from tests.factories import FakeEmailProvider


async def test_create_tenant_issues_a_first_api_key(client):
    app.dependency_overrides[require_internal_api_key] = lambda: None

    response = await client.post(
        "/tenants/", json={"name": "Acme", "contact_email": "ops@acme.test"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tenant"]["name"] == "Acme"
    assert body["api_key"]["api_key"].startswith("bm_")
    assert body["api_key"]["key_prefix"] == body["api_key"]["api_key"][:11]
    assert body["api_key"]["active"] is True


async def test_issued_key_authenticates_client_routes(client):
    app.dependency_overrides[require_internal_api_key] = lambda: None
    app.dependency_overrides[get_email_provider] = lambda: FakeEmailProvider()

    created = await client.post(
        "/tenants/", json={"name": "Acme", "contact_email": "ops@acme.test"}
    )
    api_key = created.json()["api_key"]["api_key"]

    response = await client.get("/sender-domains/", headers={"X-Api-Key": api_key})
    assert response.status_code == 200
    assert response.json() == []


async def test_missing_api_key_is_rejected(client):
    response = await client.get("/sender-domains/")
    assert response.status_code == 404


async def test_unknown_api_key_is_rejected(client):
    response = await client.get("/sender-domains/", headers={"X-Api-Key": "bm_not-a-real-key"})
    assert response.status_code == 404


async def test_revoked_key_no_longer_authenticates(client):
    app.dependency_overrides[require_internal_api_key] = lambda: None

    created = await client.post(
        "/tenants/", json={"name": "Acme", "contact_email": "ops@acme.test"}
    )
    tenant_id = created.json()["tenant"]["id"]
    key_id = created.json()["api_key"]["id"]
    api_key = created.json()["api_key"]["api_key"]

    revoke = await client.delete(f"/tenants/{tenant_id}/api-keys/{key_id}")
    assert revoke.status_code == 200
    assert revoke.json()["active"] is False

    response = await client.get("/sender-domains/", headers={"X-Api-Key": api_key})
    assert response.status_code == 404


async def test_issue_additional_key_does_not_revoke_the_first(client):
    app.dependency_overrides[require_internal_api_key] = lambda: None
    app.dependency_overrides[get_email_provider] = lambda: FakeEmailProvider()

    created = await client.post(
        "/tenants/", json={"name": "Acme", "contact_email": "ops@acme.test"}
    )
    tenant_id = created.json()["tenant"]["id"]
    first_key = created.json()["api_key"]["api_key"]

    issued = await client.post(f"/tenants/{tenant_id}/api-keys")
    assert issued.status_code == 201
    second_key = issued.json()["api_key"]

    keys = await client.get(f"/tenants/{tenant_id}/api-keys")
    assert len(keys.json()) == 2

    first_still_works = await client.get("/sender-domains/", headers={"X-Api-Key": first_key})
    second_also_works = await client.get("/sender-domains/", headers={"X-Api-Key": second_key})
    assert first_still_works.status_code == 200
    assert second_also_works.status_code == 200
