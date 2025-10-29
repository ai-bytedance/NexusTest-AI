import time
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.config import get_settings
from app.db.session import get_db
from app.services.reports.progress import get_sync_redis
from app.tasks import celery_app

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe", response_model=ResponseEnvelope)
def healthz() -> dict:
    return success_response({"status": "ok"})


@router.get("/readyz", summary="Readiness probe", response_model=ResponseEnvelope)
def readyz(db: Session = Depends(get_db)) -> JSONResponse:
    settings = get_settings()
    checks: dict[str, dict[str, Any]] = {}
    overall_ok = True

    db_check: dict[str, Any] = {"status": "ok"}
    db_start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_check["latency_ms"] = int((time.perf_counter() - db_start) * 1000)
    except Exception as exc:  # pragma: no cover - defensive
        db_check["status"] = "error"
        db_check["error"] = str(exc)
        overall_ok = False
    checks["database"] = db_check

    redis_check: dict[str, Any] = {"status": "ok"}
    redis_start = time.perf_counter()
    try:
        redis_client = get_sync_redis()
        if not redis_client.ping():  # pragma: no cover - network edge
            raise RuntimeError("Redis ping failed")
        redis_check["latency_ms"] = int((time.perf_counter() - redis_start) * 1000)
    except Exception as exc:
        redis_check["status"] = "error"
        redis_check["error"] = str(exc)
        overall_ok = False
    checks["redis"] = redis_check

    celery_check: dict[str, Any] = {"status": "ok"}
    celery_start = time.perf_counter()
    try:
        inspector = celery_app.control.inspect(timeout=settings.health_check_timeout_seconds)
        ping_result = inspector.ping(timeout=settings.health_check_timeout_seconds) if inspector else None
        if not ping_result:
            raise RuntimeError("No Celery workers responded")
        celery_check["latency_ms"] = int((time.perf_counter() - celery_start) * 1000)
        celery_check["online_workers"] = len(ping_result)
    except Exception as exc:
        celery_check["status"] = "error"
        celery_check["error"] = str(exc)
        overall_ok = False
    checks["celery"] = celery_check

    payload = {
        "status": "ready" if overall_ok else "degraded",
        "checks": checks,
    }
    status_code = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=success_response(payload))
