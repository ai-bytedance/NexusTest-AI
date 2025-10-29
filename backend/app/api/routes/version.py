from fastapi import APIRouter

from app.api.response import ResponseEnvelope, success_response
from app.core.config import get_settings

router = APIRouter(tags=["version"])


@router.get("/version", response_model=ResponseEnvelope)
def read_version() -> dict:
    settings = get_settings()
    payload = {
        "version": settings.app_version,
        "git_sha": settings.git_commit_sha,
        "build_time": settings.build_time,
    }
    return success_response(payload, message="Build information")
