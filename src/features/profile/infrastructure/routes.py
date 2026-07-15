"""Router de `/profile`: ficha de solo lectura de "Mi perfil". RGPD: el
usuario solo puede ver SU PROPIO perfil — se resuelve siempre por
`current_user["sub"]` (el id del token), nunca por un id de la URL.
Los 3 roles del producto pueden consultar su propia ficha."""

from fastapi import APIRouter, Depends

from src.shared.auth.dependencies import require_role

from ..application.use_cases.get_my_profile import GetMyProfileUseCase
from .dependencies import get_my_profile_use_case
from .mappers import profile_to_dto
from .schemas import ProfileDTO


def create_profile_router() -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])

    @router.get("/me", response_model=ProfileDTO)
    async def get_my_profile(
        current_user: dict = Depends(
            require_role("administrador", "empleado", "externo_invitado")
        ),
        use_case: GetMyProfileUseCase = Depends(get_my_profile_use_case),
    ):
        profile = await use_case.execute(current_user["sub"])
        return profile_to_dto(profile)

    return router
