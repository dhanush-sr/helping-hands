"""API errors, returned as ``{"code": "...", "message": "..."}`` as the SAD specifies.

Raise ``ApiError`` from services or endpoints; the handler turns it into the JSON response.
FastAPI's own errors (unknown route, wrong method, invalid input) are given the same shape.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

HTTP_ERROR_CODES = {
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def validation_message(errors: list[dict]) -> str:
    """e.g. "Invalid input: slots: Input should be greater than or equal to 1".

    Only field names and the rule broken; the submitted values are never echoed back.
    """
    problems = []
    for error in errors:
        field = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        problems.append(f"{field}: {error['msg']}" if field else error["msg"])
    return "Invalid input: " + "; ".join(problems)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> Response:
        headers = getattr(exc, "headers", None)
        if exc.status_code in (204, 304):  # these must not have a body
            return Response(status_code=exc.status_code, headers=headers)
        code = HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "The request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": message},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": "VALIDATION_ERROR", "message": validation_message(exc.errors())},
        )
