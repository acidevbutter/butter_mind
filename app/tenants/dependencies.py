from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header

from app.core.dependencies import DbSession
from app.core.exceptions import NotFoundError
from app.core.metrics import emit_metrics
from app.tenants.models import Tenant
from app.tenants.repository import TenantRepository
from app.tenants.service import TenantService


def get_tenant_service(
    db: DbSession,
) -> TenantService:
    return TenantService(TenantRepository(db))


TenantServiceDep = Annotated[TenantService, Depends(get_tenant_service)]


async def require_client_api_key(
    service: TenantServiceDep,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Tenant:
    """Gate for the public /emails and /sender-domains routes: each tenant's
    own app authenticates with the key DevButter issued it (see
    app.tenants.service.TenantService.authenticate). Distinct from
    require_service_api_key/require_internal_api_key, which both check a
    single shared DevButter-side secret rather than looking up a caller.
    """
    if not x_api_key:
        await emit_metrics(
            dimensions={"AuthType": "client_api_key", "Reason": "missing_key"},
            values={"AuthFailure": (1, "Count")},
        )
        raise NotFoundError("Not found")
    try:
        return await service.authenticate(x_api_key)
    except NotFoundError:
        await emit_metrics(
            dimensions={"AuthType": "client_api_key", "Reason": "invalid_key"},
            values={"AuthFailure": (1, "Count")},
        )
        raise


CurrentTenantDep = Annotated[Tenant, Depends(require_client_api_key)]
