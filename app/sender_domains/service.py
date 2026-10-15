import uuid
from datetime import UTC, datetime

from app.core.decorators import log_errors
from app.core.email.provider import EmailProvider
from app.sender_domains.models import SenderDomain
from app.sender_domains.repository import SenderDomainRepository
from app.sender_domains.schemas import SenderDomainCreate


@log_errors
class SenderDomainService:
    def __init__(
        self,
        repository: SenderDomainRepository,
        email_provider: EmailProvider,
    ):
        self.repository = repository
        self.email_provider = email_provider

    async def register(
        self,
        *,
        tenant_id: uuid.UUID,
        payload: SenderDomainCreate,
    ) -> SenderDomain:
        authentication = await self.email_provider.authenticate_domain(domain=payload.domain)
        return await self.repository.create(
            tenant_id=tenant_id,
            payload=payload,
            provider_domain_id=authentication.provider_domain_id,
            dns_records=[record.model_dump() for record in authentication.dns_records],
        )

    async def list_for_tenant(
        self,
        tenant_id: uuid.UUID,
    ) -> list[SenderDomain]:
        return await self.repository.list_for_tenant(tenant_id)

    async def recheck_verification(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_domain_id: uuid.UUID,
    ) -> SenderDomain:
        sender_domain = await self.repository.get(
            tenant_id=tenant_id,
            sender_domain_id=sender_domain_id,
        )
        result = await self.email_provider.verify_domain(
            domain=sender_domain.domain,
            provider_domain_id=sender_domain.provider_domain_id or "",
        )
        return await self.repository.update_verification(
            sender_domain,
            status="verified" if result.verified else "pending",
            dns_records=[record.model_dump() for record in result.dns_records],
            verified_at=datetime.now(UTC) if result.verified else None,
        )
