import hashlib
import secrets
import uuid

from app.core.decorators import log_errors
from app.core.exceptions import NotFoundError
from app.tenants.models import ApiKey, Tenant
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate

_KEY_PREFIX = "bm_"
_KEY_PREFIX_VISIBLE_CHARS = 8


def _generate_api_key() -> tuple[str, str, str]:
    """Returns (plaintext_key, key_prefix, key_hash). The plaintext is
    returned once to the caller and never stored -- only key_hash (sha256)
    persists, so a DB leak alone can't be used to authenticate as a tenant.
    """
    plaintext = f"{_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    prefix = plaintext[: len(_KEY_PREFIX) + _KEY_PREFIX_VISIBLE_CHARS]
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, prefix, key_hash


@log_errors
class TenantService:
    def __init__(
        self,
        repository: TenantRepository,
    ):
        self.repository = repository

    async def create_tenant_with_key(
        self,
        payload: TenantCreate,
    ) -> tuple[Tenant, str, ApiKey]:
        tenant = await self.repository.create_tenant(payload)
        plaintext, api_key = await self._issue_key(tenant.id)
        return tenant, plaintext, api_key

    async def get_tenant(
        self,
        tenant_id: uuid.UUID,
    ) -> Tenant:
        return await self.repository.get_tenant(tenant_id)

    async def list_tenants(self) -> list[Tenant]:
        return await self.repository.list_tenants()

    async def issue_key(
        self,
        tenant_id: uuid.UUID,
    ) -> tuple[str, ApiKey]:
        await self.repository.get_tenant(tenant_id)  # 404s if the tenant doesn't exist
        return await self._issue_key(tenant_id)

    async def _issue_key(
        self,
        tenant_id: uuid.UUID,
    ) -> tuple[str, ApiKey]:
        plaintext, prefix, key_hash = _generate_api_key()
        api_key = await self.repository.create_api_key(
            tenant_id=tenant_id, key_prefix=prefix, key_hash=key_hash
        )
        return plaintext, api_key

    async def list_api_keys(
        self,
        tenant_id: uuid.UUID,
    ) -> list[ApiKey]:
        return await self.repository.list_api_keys(tenant_id)

    async def revoke_key(
        self,
        *,
        tenant_id: uuid.UUID,
        key_id: uuid.UUID,
    ) -> ApiKey:
        api_key = await self.repository.get_api_key(tenant_id=tenant_id, key_id=key_id)
        return await self.repository.revoke_api_key(api_key)

    async def authenticate(
        self,
        raw_key: str,
    ) -> Tenant:
        """Resolves a plaintext X-Api-Key header to its owning tenant. Fails
        closed with NotFoundError (never a hint about which part was wrong)
        on a missing, unknown or revoked key -- mirrors require_service_api_key
        / require_internal_api_key's 404-not-401 posture."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        api_key = await self.repository.get_active_api_key_by_hash(key_hash)
        if api_key is None:
            raise NotFoundError("Not found")
        await self.repository.touch_last_used(api_key)
        return await self.repository.get_tenant(api_key.tenant_id)
