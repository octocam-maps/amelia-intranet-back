"""
Caso de uso: intercambio del id_token de Google por sesión interna.

Reglas de negocio (docs/fase-0-esquema-datos.md, docs/permisos-roles.md):
- Sin contraseñas: la identidad la certifica Google, nunca se pide/guarda password.
- Alta:
    1. Si ya existe un `users` (por `google_sub` o `email`), se usa ese —
       cualquier rol, incluido `administrador` (así entra Beatriz, sembrada
       en la migración 007).
    2. Si no existe pero hay una `invitations` PENDIENTE para ese email, se
       da de alta con el rol/entidad de la invitación (cubre externos-invitado
       Y cualquier interno que RRHH quiera pre-asignar a un rol/entidad
       concretos antes del primer login).
    3. Si no existe ninguna de las dos y el claim `hd` (verificado por
       Google, NUNCA el sufijo del email) coincide con el Workspace de la
       empresa, se auto-provisiona como `empleado` `active` — RRHH completa
       entidad/departamento después.
    4. Si no es interno y no hay invitación, se rechaza (`NotInvitedError`).
- Primer login válido transiciona `status`: 'invited' -> 'active'.
- Cada login/refresh emite un refresh token con `jti` propio, persistido en
  `auth_sessions` para poder revocarlo server-side (logout / logout-all).
"""

import uuid

from src.shared.jwt.domain.jwt_service import IJWTService

from ...domain.entities import AuthenticatedUser
from ...domain.errors import EmailNotVerifiedError, NotInvitedError, UserSuspendedError
from ...domain.ports import IGoogleIdentityVerifier, ISessionRepository, IUserRepository
from ..results import LoginResult


class LoginWithGoogleUseCase:
    def __init__(
        self,
        user_repository: IUserRepository,
        session_repository: ISessionRepository,
        google_verifier: IGoogleIdentityVerifier,
        jwt_service: IJWTService,
    ):
        self._user_repository = user_repository
        self._session_repository = session_repository
        self._google_verifier = google_verifier
        self._jwt_service = jwt_service

    async def execute(
        self,
        google_id_token: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> LoginResult:
        identity = self._google_verifier.verify(google_id_token)

        # Defensa en profundidad (auditoría QA Fase 3): Google verifica la
        # FIRMA del id_token, pero `email_verified=false` significa que el
        # titular todavía no confirmó ese email (frecuente en cuentas
        # recién creadas) — no es una identidad en la que podamos basar alta
        # automática ni sesión.
        if not identity.email_verified:
            raise EmailNotVerifiedError(
                "Tu cuenta de Google no tiene el email verificado."
            )

        user = await self._user_repository.find_by_google_sub(identity.sub)

        if user is None:
            user = await self._user_repository.find_by_email(identity.email)

        if user is None:
            invitation = await self._user_repository.find_pending_invitation(identity.email)
            if invitation is not None:
                user = await self._user_repository.create_user_from_invitation(
                    invitation,
                    google_sub=identity.sub,
                    full_name=identity.full_name,
                    avatar_url=identity.avatar_url,
                    hosted_domain=identity.hosted_domain,
                )
            elif identity.is_internal:
                user = await self._user_repository.create_auto_provisioned_user(
                    identity.email,
                    google_sub=identity.sub,
                    full_name=identity.full_name,
                    avatar_url=identity.avatar_url,
                    hosted_domain=identity.hosted_domain,
                )
            else:
                raise NotInvitedError(
                    "No tienes una invitación pendiente. Contacta con RRHH."
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

        access_token = self._create_access_token(user)
        jti = str(uuid.uuid4())
        # Nueva familia por login — se propaga sin cambiar en cada rotación
        # posterior (ver RefreshSessionUseCase). Permite revocarla entera si
        # se detecta reuso de un jti ya rotado.
        family_id = str(uuid.uuid4())
        refresh_token = self._jwt_service.create_refresh_token({"sub": user.id, "jti": jti})

        await self._session_repository.create_session(
            user_id=user.id,
            jti=jti,
            family_id=family_id,
            expires_at=self._jwt_service.get_refresh_token_expires_at(),
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return LoginResult(
            access_token=access_token,
            refresh_token=refresh_token,
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
