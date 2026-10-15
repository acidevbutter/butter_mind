from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import exception_handler


class EmailProviderError(Exception):
    def __init__(
        self,
        detail: str = "The email provider failed to respond",
    ):
        self.detail = detail


class EmailProviderNotConfiguredError(Exception):
    def __init__(
        self,
        detail: str = "No email provider API key is configured",
    ):
        self.detail = detail


@exception_handler(EmailProviderError)
async def handle_email_provider_error(
    request: Request,
    exc: EmailProviderError,
) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": exc.detail})


@exception_handler(EmailProviderNotConfiguredError)
async def handle_email_provider_not_configured_error(
    request: Request,
    exc: EmailProviderNotConfiguredError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": exc.detail}
    )
