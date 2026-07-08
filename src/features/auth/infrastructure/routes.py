"""Router de `/auth`: login (intercambio de id_token de Google), refresh, logout, me."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from src.shared.auth.dependencies import get_current_user
from src.shared.config import get_settings
from src.shared.database import get_database_pool
from src.shared.errors.base import NotFoundError
from src.shared.logger import get_logger
from src.shared.middleware import limiter
from src.shared.utils.client_ip import get_client_ip

from ..application.use_cases.login_with_google import LoginWithGoogleUseCase
from ..application.use_cases.logout import LogoutUseCase
from ..application.use_cases.logout_all_sessions import LogoutAllSessionsUseCase
from ..application.use_cases.refresh_session import RefreshSessionUseCase
from .dependencies import (
    get_login_with_google_use_case,
    get_logout_all_sessions_use_case,
    get_logout_use_case,
    get_refresh_session_use_case,
)
from .mappers import login_result_to_dto, token_result_to_dto, user_to_dto
from .refresh_token_cookie import clear_refresh_token_cookie, set_refresh_token_cookie
from .repositories.user_repository import PostgresUserRepository
from .schemas import (
    AuthResponseDTO,
    LoginRequestDTO,
    LogoutAllResponseDTO,
    TokenResponseDTO,
    UserDTO,
)

logger = get_logger("controller.auth")


def create_auth_router() -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/login", response_model=AuthResponseDTO)
    @limiter.limit("10/minute")
    async def login(
        dto: LoginRequestDTO,
        request: Request,
        use_case: LoginWithGoogleUseCase = Depends(get_login_with_google_use_case),
    ):
        """Intercambia el id_token de Google (Google Identity Services) por sesión interna."""
        result = await use_case.execute(
            dto.id_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=get_client_ip(request),
        )
        logger.info("Login successful", user_id=result.user.id, role=result.user.role_code)

        body = login_result_to_dto(result.access_token, result.expires_in, result.user)
        response = JSONResponse(content=body.model_dump())
        set_refresh_token_cookie(response, result.refresh_token)
        return response

    @router.post("/refresh", response_model=TokenResponseDTO)
    @limiter.limit("30/minute")
    async def refresh(
        request: Request,
        use_case: RefreshSessionUseCase = Depends(get_refresh_session_use_case),
    ):
        """Renueva el access token a partir del refresh token (cookie HttpOnly)."""
        settings = get_settings()
        raw_cookie = request.cookies.get(settings.refresh_token_cookie_name)
        result = await use_case.execute(
            raw_cookie,
            user_agent=request.headers.get("user-agent"),
            ip_address=get_client_ip(request),
        )

        body = token_result_to_dto(result.access_token, result.expires_in)
        response = JSONResponse(content=body.model_dump())
        set_refresh_token_cookie(response, result.refresh_token)
        return response

    @router.post("/logout", status_code=204)
    async def logout(
        request: Request,
        current_user: dict = Depends(get_current_user),
        use_case: LogoutUseCase = Depends(get_logout_use_case),
    ):
        """Cierra sesión: revoca server-side el refresh token actual y borra la cookie."""
        settings = get_settings()
        raw_cookie = request.cookies.get(settings.refresh_token_cookie_name)
        await use_case.execute(raw_cookie)

        response = Response(status_code=204)
        clear_refresh_token_cookie(response)
        return response

    @router.post("/logout-all", response_model=LogoutAllResponseDTO)
    async def logout_all(
        current_user: dict = Depends(get_current_user),
        use_case: LogoutAllSessionsUseCase = Depends(get_logout_all_sessions_use_case),
    ):
        """Cierra sesión en TODOS los dispositivos (revoca todas las sesiones activas).

        Útil para incidentes RGPD (dispositivo perdido/robado). También limpia
        la cookie del dispositivo actual, ya que su refresh token queda revocado.
        """
        revoked = await use_case.execute(current_user["sub"])
        logger.info("Logout-all executed", user_id=current_user["sub"], revoked_sessions=revoked)

        response = JSONResponse(content=LogoutAllResponseDTO(revoked_sessions=revoked).model_dump())
        clear_refresh_token_cookie(response)
        return response

    @router.get("/me", response_model=UserDTO)
    async def me(current_user: dict = Depends(get_current_user)):
        """Perfil del usuario autenticado (fuente: BD, no solo el JWT)."""
        repository = PostgresUserRepository(get_database_pool())
        user = await repository.find_by_id(current_user["sub"])
        if user is None:
            raise NotFoundError("User not found")
        return user_to_dto(user)

    return router
