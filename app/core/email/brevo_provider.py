from typing import Any

import httpx

from app.core.email.exceptions import EmailProviderError, EmailProviderNotConfiguredError
from app.core.email.schemas import (
    DnsRecord,
    DomainAuthentication,
    DomainVerificationResult,
    EmailSendResult,
    OutboundEmail,
)


def _dns_records_from_payload(payload: dict[str, Any]) -> list[DnsRecord]:
    """Brevo returns dns_records as a dict keyed by record name (brevo_code,
    dkim_record, dmarc_record, ...), each shaped {host_name, type, value,
    status}. Flatten it into our provider-agnostic list."""
    records = payload.get("dns_records") or {}
    return [
        DnsRecord(
            record_type=record["type"],
            host_name=record["host_name"],
            value=record["value"],
            verified=bool(record.get("status", False)),
        )
        for record in records.values()
    ]


class BrevoProvider:
    """Wraps the Brevo transactional email + sender domain authentication
    API (https://developers.brevo.com). Only this module talks to Brevo's
    HTTP API directly -- domain services depend on the EmailProvider
    Protocol, never on this class.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _require_configured(self) -> None:
        if not self._api_key:
            raise EmailProviderNotConfiguredError()

    async def _request(
        self,
        *,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_configured()
        headers = {
            "api-key": self._api_key,
            "content-type": "application/json",
            "accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
                response = await client.request(method, path, json=json, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text or str(exc)
            raise EmailProviderError(f"Brevo request to {path} failed: {detail}") from exc
        except httpx.HTTPError as exc:
            raise EmailProviderError(f"Brevo request to {path} failed: {exc}") from exc
        return response.json() if response.content else {}

    async def send(
        self,
        *,
        message: OutboundEmail,
    ) -> EmailSendResult:
        body: dict[str, Any] = {
            "sender": message.sender.model_dump(exclude_none=True),
            "to": [recipient.model_dump(exclude_none=True) for recipient in message.to],
            "subject": message.subject,
        }
        if message.html_content:
            body["htmlContent"] = message.html_content
        if message.text_content:
            body["textContent"] = message.text_content
        if message.reply_to:
            body["replyTo"] = message.reply_to.model_dump(exclude_none=True)

        payload = await self._request(method="POST", path="/smtp/email", json=body)
        return EmailSendResult(provider_message_id=payload["messageId"])

    async def authenticate_domain(
        self,
        *,
        domain: str,
    ) -> DomainAuthentication:
        payload = await self._request(
            method="POST", path="/senders/domains", json={"name": domain}
        )
        return DomainAuthentication(
            provider_domain_id=str(payload["id"]),
            dns_records=_dns_records_from_payload(payload),
        )

    async def verify_domain(
        self,
        *,
        domain: str,
        provider_domain_id: str,
    ) -> DomainVerificationResult:
        # Triggers Brevo's own DNS check; its response carries only a
        # confirmation message, not per-record status, so the current status
        # is re-read from the domain resource right after.
        await self._request(method="PUT", path=f"/senders/domains/{domain}/authenticate")
        payload = await self._request(method="GET", path=f"/senders/domains/{domain}")
        dns_records = _dns_records_from_payload(payload)
        verified = bool(dns_records) and all(record.verified for record in dns_records)
        return DomainVerificationResult(verified=verified, dns_records=dns_records)
