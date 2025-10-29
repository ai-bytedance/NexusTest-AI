from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.test_case import TestCase
    from app.models.user import User


class DatasetType(str, enum.Enum):
    CSV = "csv"
    EXCEL = "excel"
    INLINE = "inline"


class Dataset(BaseModel, Base):
    __tablename__ = "datasets"

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[DatasetType] = mapped_column(
        Enum(DatasetType, name="dataset_type_enum", native_enum=True),
        nullable=False,
    )
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="datasets")
    creator: Mapped["User"] = relationship("User", back_populates="datasets_created")
    test_cases: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="dataset")

__all__ = ["Dataset", "DatasetType"]
