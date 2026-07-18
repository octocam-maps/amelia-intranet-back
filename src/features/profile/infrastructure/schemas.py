"""DTOs de request/response (Pydantic) del feature `profile`."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ProfileDTO(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str]
    role: str
    job_title: Optional[str]
    hire_date: Optional[date]
    entity_name: Optional[str]
    department_name: Optional[str]
    manager_name: Optional[str]
    is_external: bool
    phone: Optional[str]
    city: Optional[str]
    # Completados en el paso 5 del onboarding (RF §3.5) — `None` hasta que
    # el usuario termine ese paso (p.ej. un admin sembrado directamente en
    # BD, sin pasar por onboarding).
    dni_nie: Optional[str]
    birth_date: Optional[date]
    address: Optional[str]
    company_phone: Optional[str]


# Formato "razonable" de teléfono: dígitos y espacios, `+` opcional al
# inicio (prefijo de país), 6-20 caracteres — sin llegar a validación E.164
# completa (el contrato no la exige, y "Mi perfil" no es el alta laboral
# formal). Mismo criterio de `Field(pattern=...)` que
# `features/absences/infrastructure/schemas.py` (`code`).
_PHONE_PATTERN = r"^\+?[0-9 ]{6,20}$"


class UpdateMyProfileDTO(BaseModel):
    """Body de `PATCH /profile/me`. Todo opcional — PATCH parcial; solo se
    tocan los campos informados (semántica COALESCE en el repositorio).
    Nunca lleva `user_id`: RGPD, siempre se resuelve por el token."""

    phone: Optional[str] = Field(None, pattern=_PHONE_PATTERN)
    city: Optional[str] = Field(None, min_length=2, max_length=120)
