from typing import Protocol

from app.core.email.schemas import (
    DomainAuthentication,
    DomainVerificationResult,
    EmailSendResult,
    OutboundEmail,
)


class EmailProvider(Protocol):
    async def send(
        self,
        *,
        message: OutboundEmail,
    ) -> EmailSendResult:
        ...

    async def authenticate_domain(
        self,
        *,
        domain: str,
    ) -> DomainAuthentication:
        ...

    async def verify_domain(
        self,
        *,
        domain: str,
        provider_domain_id: str,
    ) -> DomainVerificationResult:
        ...
