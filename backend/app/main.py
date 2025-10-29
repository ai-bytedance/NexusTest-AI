from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import ai, apis, auth, execution, health, importers, progress, projects, reports, test_cases, test_suites
from app.core.config import get_settings
from app.core.errors import ErrorCode, create_error_detail
from app.logging import RequestIdMiddleware, configure_logging, get_logger

load_dotenv()
configure_logging()
logger = get_logger()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="API Automation Platform", version="0.1.0")

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")

    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(ai.router, prefix="/api/v1")
    app.include_router(apis.router, prefix="/api/v1")
    app.include_router(test_cases.router, prefix="/api/v1")
    app.include_router(test_suites.router, prefix="/api/v1")
    app.include_router(execution.router, prefix="/api/v1")
    app.include_router(importers.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(progress.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        content = create_error_detail(ErrorCode.VALIDATION_ERROR.value, "Validation error", exc.errors())
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=content)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and {"code", "message"}.issubset(detail.keys()):
            content = detail if "data" in detail else {**detail, "data": None}
        else:
            message = detail if isinstance(detail, str) else "An unexpected error occurred"
            code_value: str | ErrorCode | None
            if isinstance(detail, dict):
                code_value = detail.get("code")
            else:
                code_value = ErrorCode.BAD_REQUEST.value
            if isinstance(code_value, ErrorCode):
                code_value = code_value.value
            if not isinstance(code_value, str):
                code_value = str(code_value) if code_value is not None else ErrorCode.BAD_REQUEST.value
            content = create_error_detail(code_value, message)
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("application_started", environment=settings.app_env)

    return app


app = create_app()
