"""Les erreurs du domaine, sans HTTP : un ``service.py`` lève l'une d'elles, et le handler unique
installé par :func:`install_error_handlers` en fait la réponse - ``{"detail": <message>, "code":
<code>}`` avec le statut de la classe. Les codes HTTP sont ainsi posés à un seul endroit.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """``message`` est montré tel quel à l'utilisateur (en français) ; ``code`` le distingue pour
    le front quand une même classe recouvre plusieurs cas (``no_account``...)."""

    status = 400
    code = "invalid_request"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class Unauthorized(DomainError):
    """Pas de session : le seul cas du 401 (des identifiants refusés sont un 422)."""

    status = 401
    code = "unauthorized"


class NotFound(DomainError):
    status = 404
    code = "not_found"


class Forbidden(DomainError):
    status = 403
    code = "forbidden"


class Conflict(DomainError):
    status = 409
    code = "conflict"


class PreconditionFailed(DomainError):
    status = 412
    code = "precondition_failed"


class InvalidInput(DomainError):
    status = 422
    code = "invalid_input"


class UpstreamError(DomainError):
    status = 502
    code = "upstream_error"


class Unavailable(DomainError):
    status = 503
    code = "unavailable"


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": exc.code})


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
