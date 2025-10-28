from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe", response_model=ResponseEnvelope)
def healthz() -> dict:
    return success_response({"status": "ok"})


@router.get("/readyz", summary="Readiness probe", response_model=ResponseEnvelope)
def readyz(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return success_response({"status": "ready"})
