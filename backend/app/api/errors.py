"""Uniform error handling.

All error responses use the envelope documented in ``docs/API.md``. Technical
detail stays in the server log; clients get a friendly message plus a hint.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class ApiError(StarletteHTTPException):
    """An HTTP error carrying a friendly message and an actionable hint."""

    def __init__(self, status_code: int, message: str, hint: str = "") -> None:
        super().__init__(status_code=status_code, detail=message)
        self.hint = hint


# Map HTTP status codes to short machine codes.
_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def _envelope(code: str, message: str, hint: str = "") -> dict[str, object]:
    return {"error": {"code": code, "message": message, "hint": hint, "details": None}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODE_BY_STATUS.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "Произошла ошибка."
        hint = getattr(exc, "hint", "") or ""
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, message, hint),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "validation_error",
                "Проверьте введённые данные.",
                "Некоторые поля заполнены неверно.",
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        # Log the real error; never return it to the client.
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_envelope(
                "internal_error",
                "Внутренняя ошибка приложения.",
                "Подробности записаны в журнал (раздел «Логи»).",
            ),
        )
