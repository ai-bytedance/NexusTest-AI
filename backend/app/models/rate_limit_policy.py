from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.api_token import ApiToken
    from app.models.project import Project

class RateLimitPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rate_limit_policies"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rules: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))

    project: Mapped[Project | None] = relationship(
        "Project",
        back_populates="rate_limit_policies",
    )
    api_tokens: Mapped[list[ApiToken]] = relationship(
        "ApiToken",
        back_populates="rate_limit_policy",
    )

if not TYPE_CHECKING:  # pragma: no cover - runtime typing support
    from app.models.api_token import ApiToken  # noqa: F401
    from app.models.project import Project  # noqa: F401
