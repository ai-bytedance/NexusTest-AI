from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.observability.metrics import instrument_engine

settings = get_settings()

connect_args: dict[str, str] = {}
engine_kwargs: dict[str, any] = {
    "future": True,
    "connect_args": connect_args,
}

if settings.database_url.startswith(("postgresql", "postgres")):
    connect_args["options"] = "-c timezone=utc"
    # PostgreSQL-specific pool settings
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    })
elif settings.database_url.startswith("sqlite"):
    # SQLite-specific settings (no pooling)
    engine_kwargs.update({
        "connect_args": {"check_same_thread": False},
    })

engine = create_engine(settings.database_url, **engine_kwargs)

instrument_engine(engine)

SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
