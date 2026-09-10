from collections.abc import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse

Handler = Callable[[Request, Exception], Awaitable[JSONResponse]]
_registry: dict[type[Exception], Handler] = {}


def exception_handler(exc_type: type[Exception]):
    """Decorator that registers a handler function for an exception type.
    Collect all of these onto the app with register_exception_handlers(app).
    """
    def decorator(func: Handler) -> Handler:
        _registry[exc_type] = func
        return func
    return decorator


def register_exception_handlers(app) -> None:
    for exc_type, handler in _registry.items():
        app.add_exception_handler(exc_type, handler)


class NotFoundError(Exception):
    def __init__(self, detail: str = "Resource not found"):
        self.detail = detail


class ConflictError(Exception):
    def __init__(self, detail: str = "Conflict"):
        self.detail = detail


class ValidationDomainError(Exception):
    def __init__(self, detail: str = "Invalid request"):
        self.detail = detail


@exception_handler(NotFoundError)
async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": exc.detail})


@exception_handler(ConflictError)
async def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": exc.detail})


@exception_handler(ValidationDomainError)
async def handle_validation(request: Request, exc: ValidationDomainError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.detail}
    )
