"""Entidades de dominio del feature `auth`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AuthenticatedUser:
    """Proyección de `users` necesaria para emitir el JWT y responder `/auth/me`."""

    id: str
    email: str
    full_name: str
    avatar_url: Optional[str]
    role_code: str
    role_id: str
    entity_id: Optional[str]
    department_id: Optional[str]
    manager_id: Optional[str]
    job_title: Optional[str]
    status: str
    is_external: bool


@dataclass(frozen=True)
class PendingInvitation:
    """Proyección de `invitations` usada para dar de alta en el primer login."""

    id: str
    email: str
    role_id: str
    role_code: str
    entity_id: Optional[str]


@dataclass(frozen=True)
class SessionRecord:
    """
    Proyección de `auth_sessions` para un `jti` concreto. `family_id` es
    constante a través de toda una cadena de rotaciones (login -> refresh ->
    refresh -> ...) — es lo que permite revocar de un golpe todos los
    descendientes de una sesión cuando se detecta reuso de un `jti` ya
    rotado (patrón OWASP de "refresh token family revocation").
    """

    id: str
    user_id: str
    jti: str
    family_id: str
    is_revoked: bool
