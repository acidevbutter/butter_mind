from pydantic import BaseModel


class EmailAddress(BaseModel):
    email: str
    name: str | None = None


class OutboundEmail(BaseModel):
    sender: EmailAddress
    to: list[EmailAddress]
    subject: str
    html_content: str | None = None
    text_content: str | None = None
    reply_to: EmailAddress | None = None


class EmailSendResult(BaseModel):
    provider_message_id: str


class DnsRecord(BaseModel):
    """One DNS record a sender domain must add -- generic across providers,
    even though the field names below happen to mirror Brevo's dns_records
    shape (host_name/type/value/status) today."""

    record_type: str
    host_name: str
    value: str
    verified: bool = False


class DomainAuthentication(BaseModel):
    """Result of registering a domain with the email provider: the provider's
    own id for it (needed to re-check verification later) plus the DNS
    records the tenant must add."""

    provider_domain_id: str
    dns_records: list[DnsRecord]


class DomainVerificationResult(BaseModel):
    verified: bool
    dns_records: list[DnsRecord]
