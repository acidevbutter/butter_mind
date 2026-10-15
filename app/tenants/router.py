import uuid

from fastapi import APIRouter, status

from app.core.dependencies import RequireInternalApiKey
from app.tenants.dependencies import TenantServiceDep
from app.tenants.schemas import (
    ApiKeyIssuedRead,
    ApiKeyRead,
    TenantCreate,
    TenantRead,
    TenantWithApiKeyRead,
)

router = APIRouter(prefix="/tenants", tags=["tenants"], dependencies=[RequireInternalApiKey])


@router.post(
    "/",
    response_model=TenantWithApiKeyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new relay tenant and issue its first API key",
    description=(
        "DevButter-only: creates the client record and issues its first API key in one "
        "call. The plaintext key is returned exactly once, here -- store it now, it can't "
        "be retrieved again afterwards (only key_prefix stays visible via GET)."
    ),
)
async def create_tenant(
    payload: TenantCreate,
    service: TenantServiceDep,
) -> TenantWithApiKeyRead:
    tenant, plaintext, api_key = await service.create_tenant_with_key(payload)
    return TenantWithApiKeyRead(
        tenant=TenantRead.model_validate(tenant),
        api_key=ApiKeyIssuedRead(
            **ApiKeyRead.model_validate(api_key).model_dump(),
            api_key=plaintext,
        ),
    )


@router.get(
    "/",
    response_model=list[TenantRead],
    summary="List relay tenants",
)
async def list_tenants(
    service: TenantServiceDep,
) -> list[TenantRead]:
    tenants = await service.list_tenants()
    return [TenantRead.model_validate(t) for t in tenants]


@router.get(
    "/{tenant_id}",
    response_model=TenantRead,
    summary="Get a relay tenant",
)
async def get_tenant(
    tenant_id: uuid.UUID,
    service: TenantServiceDep,
) -> TenantRead:
    tenant = await service.get_tenant(tenant_id)
    return TenantRead.model_validate(tenant)


@router.post(
    "/{tenant_id}/api-keys",
    response_model=ApiKeyIssuedRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an additional/rotated API key for a tenant",
    description=(
        "Issues a new key without touching existing ones -- use this to rotate a key by "
        "issuing a new one, switching the client over, then revoking the old one via "
        "DELETE .../api-keys/{key_id}."
    ),
)
async def issue_api_key(
    tenant_id: uuid.UUID,
    service: TenantServiceDep,
) -> ApiKeyIssuedRead:
    plaintext, api_key = await service.issue_key(tenant_id)
    return ApiKeyIssuedRead(
        **ApiKeyRead.model_validate(api_key).model_dump(),
        api_key=plaintext,
    )


@router.get(
    "/{tenant_id}/api-keys",
    response_model=list[ApiKeyRead],
    summary="List a tenant's API keys (prefix only, never the plaintext)",
)
async def list_api_keys(
    tenant_id: uuid.UUID,
    service: TenantServiceDep,
) -> list[ApiKeyRead]:
    api_keys = await service.list_api_keys(tenant_id)
    return [ApiKeyRead.model_validate(k) for k in api_keys]


@router.delete(
    "/{tenant_id}/api-keys/{key_id}",
    response_model=ApiKeyRead,
    summary="Revoke a tenant's API key",
)
async def revoke_api_key(
    tenant_id: uuid.UUID,
    key_id: uuid.UUID,
    service: TenantServiceDep,
) -> ApiKeyRead:
    api_key = await service.revoke_key(tenant_id=tenant_id, key_id=key_id)
    return ApiKeyRead.model_validate(api_key)
