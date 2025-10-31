from app.core.celery import celery_app as _celery_app

celery_app = _celery_app
celery = _celery_app
app = _celery_app

__all__ = ("celery_app", "celery", "app")
