"""FastAPI app factory."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from hwai.config import get_settings
from hwai.errors import ApiError
from hwai.routes import chats, exports, hand, health, messages, renders


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="handwriting-ai")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        detail = f" ({where}: {first['msg']})" if first.get("msg") else ""
        return error_response(422, "validation_error", f"The request was not valid{detail}.")

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
        return error_response(500, "internal", "Something went wrong on our side.")

    app.include_router(health.router)
    app.include_router(hand.router)
    app.include_router(chats.router)
    app.include_router(renders.router)
    app.include_router(exports.router)
    app.include_router(messages.router)
    return app


app = create_app()
