from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel
from app.models.project_member import ProjectRole


class ProjectTeamRole(BaseModel, Base):
    __tablename__ = "project_team_roles"
    __table_args__ = (
        UniqueConstraint("project_id", "team_id", name="uq_project_team_roles_project_team"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, name="project_role_enum", native_enum=True),
        nullable=False,
        default=ProjectRole.MEMBER,
        server_default=text("'member'::project_role_enum"),
    )

    project: Mapped["Project"] = relationship("Project", back_populates="team_roles")
    team: Mapped["Team"] = relationship("Team", back_populates="project_links")
