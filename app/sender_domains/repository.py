import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.sender_domains.models import SenderDomain
from app.sender_domains.schemas import SenderDomainCreate


class SenderDomainRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        payload: SenderDomainCreate,
        provider_domain_id: str,
        dns_records: list[dict[str, object]],
    ) -> SenderDomain:
        sender_domain = SenderDomain(
            tenant_id=tenant_id,
            domain=payload.domain,
            provider_domain_id=provider_domain_id,
            dns_records=dns_records,
        )
        self.session.add(sender_domain)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"Domain {payload.domain!r} is already registered") from exc
        await self.session.refresh(sender_domain)
        return sender_domain

    async def get(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_domain_id: uuid.UUID,
    ) -> SenderDomain:
        result = await self.session.execute(
            select(SenderDomain).where(
                SenderDomain.id == sender_domain_id,
                SenderDomain.tenant_id == tenant_id,
            )
        )
        sender_domain = result.scalar_one_or_none()
        if sender_domain is None:
            raise NotFoundError(f"Sender domain {sender_domain_id} not found")
        return sender_domain

    async def list_for_tenant(
        self,
        tenant_id: uuid.UUID,
    ) -> list[SenderDomain]:
        result = await self.session.execute(
            select(SenderDomain)
            .where(SenderDomain.tenant_id == tenant_id)
            .order_by(SenderDomain.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_verified_by_domain(
        self,
        *,
        tenant_id: uuid.UUID,
        domain: str,
    ) -> SenderDomain | None:
        result = await self.session.execute(
            select(SenderDomain).where(
                SenderDomain.tenant_id == tenant_id,
                SenderDomain.domain == domain,
                SenderDomain.status == "verified",
            )
        )
        return result.scalar_one_or_none()

    async def update_verification(
        self,
        sender_domain: SenderDomain,
        *,
        status: str,
        dns_records: list[dict[str, object]],
        verified_at: datetime | None,
    ) -> SenderDomain:
        sender_domain.status = status
        sender_domain.dns_records = dns_records
        sender_domain.verified_at = verified_at
        await self.session.commit()
        await self.session.refresh(sender_domain)
        return sender_domain
