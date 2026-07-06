from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi import Request


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or f"E{status_code}"


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "error_code": exc.error_code,
            "detail": exc.detail,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "error_code": f"E{exc.status_code}",
            "detail": exc.detail,
        },
    )
