from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | EmailStr) -> str | EmailStr:
        if isinstance(value, str):
            return value.strip().lower()
        if isinstance(value, EmailStr):
            return str(value).lower()
        return value


class UserCreate(UserBase):
    password: str = Field(min_length=8)
    role: UserRole | None = None


class UserLogin(UserBase):
    password: str = Field(min_length=8)


class UserRead(UserBase):
    id: UUID
    role: UserRole
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
