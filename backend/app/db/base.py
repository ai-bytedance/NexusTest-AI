from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UTC_NOW = text("TIMEZONE('utc', NOW())")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=UTC_NOW,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=UTC_NOW,
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )


class BaseModel(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Convenience mixin bundling common audit columns."""

    __abstract__ = True


# Import models so Alembic can discover them for autogeneration.
from app import models  # noqa: E402,F401
