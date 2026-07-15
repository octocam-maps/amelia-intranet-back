"""DTOs de request/response (Pydantic) del feature `announcements`."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Audience = Literal["all", "entity", "role"]
EntityCode = Literal["hub", "lab", "ops"]
RoleCode = Literal["administrador", "empleado", "externo_invitado"]


class AnnouncementDTO(BaseModel):
    id: str
    title: str
    body: str
    author_id: str
    author_full_name: Optional[str]
    audience: str
    entity_id: Optional[str]
    entity_code: Optional[str]
    role_id: Optional[str]
    role_code: Optional[str]
    is_pinned: bool
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class AnnouncementListDTO(BaseModel):
    announcements: list[AnnouncementDTO]


class CreateAnnouncementDTO(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
    audience: Audience = "all"
    entity: Optional[EntityCode] = None
    role: Optional[RoleCode] = None
    is_pinned: bool = False
    published: bool = True


class UpdateAnnouncementDTO(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    body: Optional[str] = Field(None, min_length=1)
    audience: Optional[Audience] = None
    entity: Optional[EntityCode] = None
    role: Optional[RoleCode] = None
    is_pinned: Optional[bool] = None
    published: Optional[bool] = None
