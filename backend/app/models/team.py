from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.organization import Organization
    from app.models.project_team_role import ProjectTeamRole
    from app.models.team_membership import TeamMembership


class Team(BaseModel, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_teams_org_slug"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped[Organization] = relationship("Organization", back_populates="teams")
    memberships: Mapped[list[TeamMembership]] = relationship(
        "TeamMembership",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    project_links: Mapped[list[ProjectTeamRole]] = relationship(
        "ProjectTeamRole",
        back_populates="team",
        cascade="all, delete-orphan",
    )


if not TYPE_CHECKING:  # pragma: no cover - runtime typing support
    from app.models.organization import Organization  # noqa: F401
    from app.models.project_team_role import ProjectTeamRole  # noqa: F401
    from app.models.team_membership import TeamMembership  # noqa: F401
