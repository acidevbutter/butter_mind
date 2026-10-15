from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.dependencies import DbSession, EmailProviderDep
from app.emails.repository import EmailRepository
from app.emails.service import EmailService
from app.sender_domains.repository import SenderDomainRepository


def get_email_service(
    db: DbSession,
    email_provider: EmailProviderDep,
) -> EmailService:
    return EmailService(EmailRepository(db), SenderDomainRepository(db), email_provider)


EmailServiceDep = Annotated[EmailService, Depends(get_email_service)]
