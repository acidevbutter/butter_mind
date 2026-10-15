from fastapi import APIRouter, status

from app.emails.dependencies import EmailServiceDep
from app.emails.schemas import EmailSendRead, EmailSendRequest
from app.tenants.dependencies import CurrentTenantDep

router = APIRouter(prefix="/emails", tags=["emails"])


@router.post(
    "/send",
    response_model=EmailSendRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a transactional email on your verified sender domain",
    description=(
        "Requires the X-Api-Key header issued to your tenant. `from_email` must belong to "
        "a domain you've registered and verified via POST /sender-domains -- sending from "
        "an unverified domain is rejected with 422."
    ),
)
async def send_email(
    payload: EmailSendRequest,
    tenant: CurrentTenantDep,
    service: EmailServiceDep,
) -> EmailSendRead:
    email_log = await service.send(tenant_id=tenant.id, payload=payload)
    return EmailSendRead.model_validate(email_log)
