from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:?cache=shared")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.config import get_settings

get_settings.cache_clear()

from app.db import session as session_module  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

session_module.engine = engine
session_module.SessionLocal = TestingSessionLocal

app = create_app()


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fake_redis_clients(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from app.services.reports import progress as progress_service

    server = fakeredis.FakeServer()
    sync_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    async_client = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)

    monkeypatch.setattr(progress_service, "get_sync_redis", lambda: sync_client)
    monkeypatch.setattr(progress_service, "get_async_redis", lambda: async_client)
    yield


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
