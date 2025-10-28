from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8)
    role: UserRole | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserRead(UserBase):
    id: UUID
    role: UserRole
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
