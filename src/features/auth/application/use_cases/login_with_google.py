"""
Caso de uso: intercambio del id_token de Google por sesión interna.

Reglas de negocio (docs/fase-0-esquema-datos.md, docs/permisos-roles.md):
- Sin contraseñas: la identidad la certifica Google, nunca se pide/guarda password.
- Alta controlada: si el email no existe en `users`, debe existir una
  `invitations` PENDIENTE para ese email (tanto para plantilla interna como
  para externos-invitado con Gmail personal) — si no, se rechaza. El claim
  `hd` por sí solo NO basta para auto-provisionar una cuenta.
- Primer login válido transiciona `status`: 'invited' -> 'active'.
"""

from src.shared.jwt.domain.jwt_service import IJWTService

from ...domain.entities import AuthenticatedUser
from ...domain.errors import NotInvitedError, UserSuspendedError
from ...domain.ports import IGoogleIdentityVerifier, IUserRepository
from ..results import LoginResult


class LoginWithGoogleUseCase:
    def __init__(
        self,
        user_repository: IUserRepository,
        google_verifier: IGoogleIdentityVerifier,
        jwt_service: IJWTService,
    ):
        self._user_repository = user_repository
        self._google_verifier = google_verifier
        self._jwt_service = jwt_service

    async def execute(self, google_id_token: str) -> LoginResult:
        identity = self._google_verifier.verify(google_id_token)

        user = await self._user_repository.find_by_google_sub(identity.sub)

        if user is None:
            user = await self._user_repository.find_by_email(identity.email)

        if user is None:
            invitation = await self._user_repository.find_pending_invitation(identity.email)
            if invitation is None:
                raise NotInvitedError(
                    "No tienes una invitación pendiente. Contacta con RRHH."
                )
            user = await self._user_repository.create_user_from_invitation(
                invitation,
                google_sub=identity.sub,
                full_name=identity.full_name,
                avatar_url=identity.avatar_url,
                hosted_domain=identity.hosted_domain,
            )
        else:
            if user.status == "suspended":
                raise UserSuspendedError("Tu cuenta está suspendida.")
            await self._user_repository.bind_google_login(
                user.id,
                google_sub=identity.sub,
                full_name=identity.full_name,
                avatar_url=identity.avatar_url,
                hosted_domain=identity.hosted_domain,
            )
            refreshed = await self._user_repository.find_by_id(user.id)
            user = refreshed or user

        return LoginResult(
            access_token=self._create_access_token(user),
            refresh_token=self._jwt_service.create_refresh_token({"sub": user.id}),
            expires_in=self._jwt_service.access_token_expire_minutes * 60,
            user=user,
        )

    def _create_access_token(self, user: AuthenticatedUser) -> str:
        return self._jwt_service.create_access_token(
            {
                "sub": user.id,
                "email": user.email,
                "role": user.role_code,
                "entity_id": user.entity_id,
                "is_external": user.is_external,
            }
        )
