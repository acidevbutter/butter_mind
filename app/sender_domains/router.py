import uuid

from fastapi import APIRouter, status

from app.sender_domains.dependencies import SenderDomainServiceDep
from app.sender_domains.schemas import SenderDomainCreate, SenderDomainRead
from app.tenants.dependencies import CurrentTenantDep

router = APIRouter(prefix="/sender-domains", tags=["sender-domains"])


@router.post(
    "/",
    response_model=SenderDomainRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a sending domain and get the DNS records to add",
    description=(
        "Registers a domain your app will send email from. Returns the exact DNS records "
        "(SPF/DKIM/DMARC) to add at your registrar -- the domain stays 'pending' until "
        "POST .../verify confirms they resolve, and POST /emails/send rejects a From "
        "address on an unverified domain."
    ),
)
async def register_sender_domain(
    payload: SenderDomainCreate,
    tenant: CurrentTenantDep,
    service: SenderDomainServiceDep,
) -> SenderDomainRead:
    sender_domain = await service.register(tenant_id=tenant.id, payload=payload)
    return SenderDomainRead.model_validate(sender_domain)


@router.get(
    "/",
    response_model=list[SenderDomainRead],
    summary="List your registered sender domains",
)
async def list_sender_domains(
    tenant: CurrentTenantDep,
    service: SenderDomainServiceDep,
) -> list[SenderDomainRead]:
    sender_domains = await service.list_for_tenant(tenant.id)
    return [SenderDomainRead.model_validate(d) for d in sender_domains]


@router.post(
    "/{sender_domain_id}/verify",
    response_model=SenderDomainRead,
    summary="Re-check DNS and mark the domain verified once records resolve",
)
async def verify_sender_domain(
    sender_domain_id: uuid.UUID,
    tenant: CurrentTenantDep,
    service: SenderDomainServiceDep,
) -> SenderDomainRead:
    sender_domain = await service.recheck_verification(
        tenant_id=tenant.id,
        sender_domain_id=sender_domain_id,
    )
    return SenderDomainRead.model_validate(sender_domain)
