"""Entidad de dominio del feature `announcements` (tablón de anuncios,
docs/permisos-roles.md § "Anuncios" — el admin crea/publica, el empleado
solo lee en su dashboard). Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Announcement:
    id: str
    title: str
    body: str
    author_id: str
    # Solo lo rellena el repositorio (JOIN con `users`) — la lista de
    # gestión del admin necesita el nombre real del autor, no solo su id.
    author_full_name: Optional[str]
    audience: str  # 'all' | 'entity' | 'role'
    entity_id: Optional[str]
    entity_code: Optional[str]
    role_id: Optional[str]
    role_code: Optional[str]
    is_pinned: bool
    # `None` == borrador, todavía no visible en el feed. Hoy el admin
    # "crea/publica" como una sola acción (permisos-roles.md), así que se
    # rellena al crear salvo que se pida explícitamente lo contrario.
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
