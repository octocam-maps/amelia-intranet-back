"""Entidad de dominio del feature `profile` ("Mi perfil"): ficha del usuario
autenticado. Sin dependencias de framework/SQL.

Lote 2: la ficha ya no es 100% de solo lectura — `phone`/`city` viven en
`user_profiles` (no en `users`) y el propio usuario puede editarlos vía
`UpdateMyProfileUseCase`. Se les da default `None` para no romper los sitios
que ya construían `UserProfile` antes de Lote 2 (tests existentes).

`dni_nie`/`birth_date`/`address`/`company_phone`: los completa el paso 5 del
onboarding (`CompleteProfileUseCase`, RF §3.5) — este feature solo los
EXPONE en `GET /profile/me` (mismo criterio de default `None` que Lote 2,
para no romper los sitios que ya construían `UserProfile` sin ellos)."""

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
    dni_nie: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    company_phone: Optional[str] = None
