"""Pydantic schemas for admin user management."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class AdminUserCreate(BaseModel):
    """Create a new user (admin only)."""
    email: EmailStr
    name: str
    password: str
    role: str


class AdminUserUpdate(BaseModel):
    """Update user fields (admin only)."""
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class AdminUserOut(BaseModel):
    """User response for admin endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


class AdminUserListResponse(BaseModel):
    """Paginated list of users."""
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int
