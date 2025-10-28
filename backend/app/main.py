from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health
from app.core.config import get_settings
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

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("application_started", environment=settings.app_env)

    return app


app = create_app()
