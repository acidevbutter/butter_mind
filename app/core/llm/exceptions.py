from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import exception_handler


class LLMProviderError(Exception):
    def __init__(self, detail: str = "The language model provider failed to respond"):
        self.detail = detail


class LLMRateLimitError(Exception):
    def __init__(self, detail: str = "The language model provider is rate-limiting requests"):
        self.detail = detail


@exception_handler(LLMProviderError)
async def handle_llm_provider_error(request: Request, exc: LLMProviderError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": exc.detail})


@exception_handler(LLMRateLimitError)
async def handle_llm_rate_limit_error(request: Request, exc: LLMRateLimitError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": exc.detail})
