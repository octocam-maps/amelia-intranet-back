"""Entidad de dominio del feature `profile` ("Mi perfil"): ficha de solo
lectura del usuario autenticado. Sin dependencias de framework/SQL."""

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
