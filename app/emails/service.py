import uuid

from app.core.decorators import log_errors
from app.core.email.provider import EmailProvider
from app.core.email.schemas import EmailAddress, OutboundEmail
from app.core.exceptions import ValidationDomainError
from app.emails.models import EmailLog
from app.emails.repository import EmailRepository
from app.emails.schemas import EmailSendRequest
from app.sender_domains.repository import SenderDomainRepository


def _domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


@log_errors
class EmailService:
    def __init__(
        self,
        repository: EmailRepository,
        sender_domain_repository: SenderDomainRepository,
        email_provider: EmailProvider,
    ):
        self.repository = repository
        self.sender_domain_repository = sender_domain_repository
        self.email_provider = email_provider

    async def send(
        self,
        *,
        tenant_id: uuid.UUID,
        payload: EmailSendRequest,
    ) -> EmailLog:
        domain = _domain_of(payload.from_email)
        sender_domain = await self.sender_domain_repository.get_verified_by_domain(
            tenant_id=tenant_id,
            domain=domain,
        )
        if sender_domain is None:
            raise ValidationDomainError(
                f"Domain {domain!r} is not a verified sender domain for this tenant -- "
                "register it via POST /sender-domains and verify it before sending from it"
            )

        message = OutboundEmail(
            sender=EmailAddress(email=payload.from_email, name=payload.from_name),
            to=payload.to,
            subject=payload.subject,
            html_content=payload.html_content,
            text_content=payload.text_content,
            reply_to=payload.reply_to,
        )
        result = await self.email_provider.send(message=message)

        return await self.repository.create_log(
            tenant_id=tenant_id,
            sender_domain_id=sender_domain.id,
            from_email=payload.from_email,
            to_addresses=[recipient.email for recipient in payload.to],
            subject=payload.subject,
            provider_message_id=result.provider_message_id,
            status="sent",
        )
