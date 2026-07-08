"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.database import get_database_pool
from src.shared.google_oidc import get_google_oidc_verifier
from src.shared.jwt import get_jwt_service

from ..application.use_cases.login_with_google import LoginWithGoogleUseCase
from ..application.use_cases.logout import LogoutUseCase
from ..application.use_cases.logout_all_sessions import LogoutAllSessionsUseCase
from ..application.use_cases.refresh_session import RefreshSessionUseCase
from .repositories.session_repository import PostgresSessionRepository
from .repositories.user_repository import PostgresUserRepository


def _get_user_repository() -> PostgresUserRepository:
    return PostgresUserRepository(get_database_pool())


def _get_session_repository() -> PostgresSessionRepository:
    return PostgresSessionRepository(get_database_pool())


def get_login_with_google_use_case() -> LoginWithGoogleUseCase:
    return LoginWithGoogleUseCase(
        user_repository=_get_user_repository(),
        session_repository=_get_session_repository(),
        google_verifier=get_google_oidc_verifier(),
        jwt_service=get_jwt_service(),
    )


def get_refresh_session_use_case() -> RefreshSessionUseCase:
    return RefreshSessionUseCase(
        user_repository=_get_user_repository(),
        session_repository=_get_session_repository(),
        jwt_service=get_jwt_service(),
    )


def get_logout_use_case() -> LogoutUseCase:
    return LogoutUseCase(
        session_repository=_get_session_repository(),
        jwt_service=get_jwt_service(),
    )


def get_logout_all_sessions_use_case() -> LogoutAllSessionsUseCase:
    return LogoutAllSessionsUseCase(session_repository=_get_session_repository())
