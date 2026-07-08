"""
Puertos (Protocols) del feature `auth`. `domain` no importa nada de
`infrastructure` ni de FastAPI — las implementaciones concretas
(asyncpg, google-auth) viven en `infrastructure` y se inyectan aquí por
duck typing estructural.
"""

from datetime import datetime
from typing import Optional, Protocol

from .entities import AuthenticatedUser, PendingInvitation, SessionRecord


class IUserRepository(Protocol):
    async def find_by_google_sub(self, google_sub: str) -> Optional[AuthenticatedUser]: ...

    async def find_by_email(self, email: str) -> Optional[AuthenticatedUser]: ...

    async def find_by_id(self, user_id: str) -> Optional[AuthenticatedUser]: ...

    async def find_pending_invitation(self, email: str) -> Optional[PendingInvitation]: ...

    async def create_user_from_invitation(
        self,
        invitation: PendingInvitation,
        *,
        google_sub: str,
        full_name: str,
        avatar_url: Optional[str],
        hosted_domain: Optional[str],
    ) -> AuthenticatedUser: ...

    async def create_auto_provisioned_user(
        self,
        email: str,
        *,
        google_sub: str,
        full_name: str,
        avatar_url: Optional[str],
        hosted_domain: Optional[str],
    ) -> AuthenticatedUser:
        """Alta automática de un interno (`hd` verificado) sin invitación previa.

        Rol fijo `empleado`, `entity_id`/`department_id`/`manager_id` en NULL
        — el admin los completa después en la gestión de plantilla (Fase 5).
        """
        ...

    async def bind_google_login(
        self,
        user_id: str,
        *,
        google_sub: str,
        full_name: str,
        avatar_url: Optional[str],
        hosted_domain: Optional[str],
    ) -> None: ...


class GoogleIdentityProtocol(Protocol):
    """Forma estructural de `GoogleIdentity` (evita importar `shared.google_oidc`)."""

    sub: str
    email: str
    email_verified: bool
    full_name: str
    avatar_url: Optional[str]
    hosted_domain: Optional[str]
    is_internal: bool


class IGoogleIdentityVerifier(Protocol):
    def verify(self, id_token_str: str) -> GoogleIdentityProtocol: ...


class ISessionRepository(Protocol):
    """
    Sesiones de refresh token (revocación server-side). Cada refresh JWT
    lleva un claim `jti` único; esta tabla es la única fuente de verdad de
    si ese `jti` sigue vivo — el JWT por sí solo (firma + exp) no basta para
    saber si el usuario cerró sesión o si un admin revocó el dispositivo.

    `family_id` identifica la cadena de rotaciones completa (constante desde
    el login hasta el logout); ver `revoke_family`.
    """

    async def create_session(
        self,
        *,
        user_id: str,
        jti: str,
        family_id: str,
        expires_at: datetime,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> None: ...

    async def find_session(self, jti: str) -> Optional[SessionRecord]:
        """`None` si el `jti` nunca existió. Incluye si ya está revocado."""
        ...

    async def revoke_session(self, jti: str) -> None: ...

    async def revoke_family(self, family_id: str) -> int:
        """
        Revoca TODAS las sesiones (activas o no) de una familia. Se dispara
        cuando se detecta reuso de un `jti` ya revocado (posible robo de
        refresh token): no basta con revocar el `jti` reusado, hay que matar
        también cualquier descendiente que la rotación legítima ya hubiera
        creado, porque no sabemos hasta dónde llegó el atacante.
        """
        ...

    async def revoke_all_sessions_for_user(self, user_id: str) -> int:
        """Revoca todas las sesiones activas del usuario. Devuelve cuántas."""
        ...
