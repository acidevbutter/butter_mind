import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.emails.models import EmailLog


class EmailRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def create_log(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_domain_id: uuid.UUID,
        from_email: str,
        to_addresses: list[str],
        subject: str,
        provider_message_id: str | None,
        status: str,
    ) -> EmailLog:
        email_log = EmailLog(
            tenant_id=tenant_id,
            sender_domain_id=sender_domain_id,
            from_email=from_email,
            to_addresses=to_addresses,
            subject=subject,
            provider_message_id=provider_message_id,
            status=status,
        )
        self.session.add(email_log)
        await self.session.commit()
        await self.session.refresh(email_log)
        return email_log
