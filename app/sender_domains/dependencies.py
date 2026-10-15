from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.dependencies import DbSession, EmailProviderDep
from app.sender_domains.repository import SenderDomainRepository
from app.sender_domains.service import SenderDomainService


def get_sender_domain_service(
    db: DbSession,
    email_provider: EmailProviderDep,
) -> SenderDomainService:
    return SenderDomainService(SenderDomainRepository(db), email_provider)


SenderDomainServiceDep = Annotated[SenderDomainService, Depends(get_sender_domain_service)]
