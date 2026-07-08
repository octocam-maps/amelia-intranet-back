"""
Puertos (Protocols) del feature `auth`. `domain` no importa nada de
`infrastructure` ni de FastAPI — las implementaciones concretas
(asyncpg, google-auth) viven en `infrastructure` y se inyectan aquí por
duck typing estructural.
"""

from typing import Optional, Protocol

from .entities import AuthenticatedUser, PendingInvitation


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


class IGoogleIdentityVerifier(Protocol):
    def verify(self, id_token_str: str) -> GoogleIdentityProtocol: ...
