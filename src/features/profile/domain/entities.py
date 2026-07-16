"""Entidad de dominio del feature `profile` ("Mi perfil"): ficha del usuario
autenticado. Sin dependencias de framework/SQL.

Lote 2: la ficha ya no es 100% de solo lectura — `phone`/`city` viven en
`user_profiles` (no en `users`) y el propio usuario puede editarlos vía
`UpdateMyProfileUseCase`. Se les da default `None` para no romper los sitios
que ya construían `UserProfile` antes de Lote 2 (tests existentes)."""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class UserProfile:
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str]
    role_code: str
    job_title: Optional[str]
    hire_date: Optional[date]
    entity_name: Optional[str]
    department_name: Optional[str]
    manager_name: Optional[str]
    is_external: bool
    phone: Optional[str] = None
    city: Optional[str] = None
