"""DTOs de request/response (Pydantic) del feature `announcements`."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Audience = Literal["all", "entity", "role"]
# Las cuatro sociedades del grupo. `hincator` se añadió el 2026-07-29
# (migración 036) y NO es opcional tenerla aquí: sin ella este endpoint
# devuelve 422 para 19 de los 36 trabajadores de la plantilla.
# Espejo del CHECK de `entities.code`; si cambia allí, cambia aquí.
EntityCode = Literal["hub", "lab", "ops", "hincator"]
# `role` NO es un `Literal` fijo (mismo criterio que `staff/infrastructure/
# schemas.py`): la fuente única de qué roles existen es la tabla `roles`
# (`GET /roles`, feature `roles`). `CreateAnnouncementUseCase`/
# `UpdateAnnouncementUseCase` ya resuelven `role_code` contra esa tabla
# (`resolve_role_id`) y devuelven `InvalidAudienceTargetError` (422) si no
# existe. Este `Literal` se había quedado desactualizado tras la migración
# 024 (nunca incluyó `socio`) — un admin no podía segmentar un anuncio por
# `audience=role, role=socio` aunque el dominio ya lo soportaba: Pydantic
# rechazaba el body con 422 antes de que el caso de uso llegara a mirarlo.


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
    role: Optional[str] = Field(None, min_length=1)
    is_pinned: bool = False
    published: bool = True


class UpdateAnnouncementDTO(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    body: Optional[str] = Field(None, min_length=1)
    audience: Optional[Audience] = None
    entity: Optional[EntityCode] = None
    role: Optional[str] = Field(None, min_length=1)
    is_pinned: Optional[bool] = None
    published: Optional[bool] = None
