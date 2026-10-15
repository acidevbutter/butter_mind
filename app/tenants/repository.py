import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.tenants.models import ApiKey, Tenant
from app.tenants.schemas import TenantCreate


class TenantRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def create_tenant(
        self,
        payload: TenantCreate,
    ) -> Tenant:
        tenant = Tenant(**payload.model_dump())
        self.session.add(tenant)
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def get_tenant(
        self,
        tenant_id: uuid.UUID,
    ) -> Tenant:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundError(f"Tenant {tenant_id} not found")
        return tenant

    async def list_tenants(self) -> list[Tenant]:
        result = await self.session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
        return list(result.scalars().all())

    async def create_api_key(
        self,
        *,
        tenant_id: uuid.UUID,
        key_prefix: str,
        key_hash: str,
    ) -> ApiKey:
        api_key = ApiKey(tenant_id=tenant_id, key_prefix=key_prefix, key_hash=key_hash)
        self.session.add(api_key)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Generated API key collided with an existing one") from exc
        await self.session.refresh(api_key)
        return api_key

    async def get_api_key(
        self,
        *,
        tenant_id: uuid.UUID,
        key_id: uuid.UUID,
    ) -> ApiKey:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise NotFoundError(f"API key {key_id} not found for tenant {tenant_id}")
        return api_key

    async def get_active_api_key_by_hash(
        self,
        key_hash: str,
    ) -> ApiKey | None:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_api_keys(
        self,
        tenant_id: uuid.UUID,
    ) -> list[ApiKey]:
        result = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_api_key(
        self,
        api_key: ApiKey,
    ) -> ApiKey:
        api_key.active = False
        api_key.revoked_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(api_key)
        return api_key

    async def touch_last_used(
        self,
        api_key: ApiKey,
    ) -> None:
        api_key.last_used_at = datetime.now(UTC)
        await self.session.commit()
