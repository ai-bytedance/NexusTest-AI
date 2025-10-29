from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from app.core.config import Settings, get_settings
from app.observability.metrics import metrics_response

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def get_metrics(settings: Settings = Depends(get_settings)) -> Response:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics endpoint is disabled")
    return metrics_response()
