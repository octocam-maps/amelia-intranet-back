"""Router de `/profile`: ficha de "Mi perfil". RGPD: el usuario solo puede
ver/editar SU PROPIO perfil — se resuelve siempre por `current_user["sub"]`
(el id del token), nunca por un id de la URL ni del body.
Los 3 roles del producto pueden consultar su propia ficha; los 3 pueden
editar su teléfono/ciudad (Lote 2) — no hay ningún dato de "Mi perfil"
exclusivo de un rol, a diferencia de `/staff` (solo admin, sobre terceros).
`socio` [migración 024] = igual que empleado, se suma sin ningún dato extra."""

from fastapi import APIRouter, Depends

from src.shared.auth.dependencies import require_role
from src.shared.auth.roles import ALL_ROLES

from ..application.use_cases.get_my_profile import GetMyProfileUseCase
from ..application.use_cases.update_my_profile import UpdateMyProfileUseCase
from .dependencies import get_my_profile_use_case, get_update_my_profile_use_case
from .mappers import profile_to_dto
from .schemas import ProfileDTO, UpdateMyProfileDTO


def create_profile_router() -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])

    @router.get("/me", response_model=ProfileDTO)
    async def get_my_profile(
        current_user: dict = Depends(
            require_role(*ALL_ROLES)
        ),
        use_case: GetMyProfileUseCase = Depends(get_my_profile_use_case),
    ):
        profile = await use_case.execute(current_user["sub"])
        return profile_to_dto(profile)

    @router.patch("/me", response_model=ProfileDTO)
    async def update_my_profile(
        dto: UpdateMyProfileDTO,
        current_user: dict = Depends(
            require_role(*ALL_ROLES)
        ),
        use_case: UpdateMyProfileUseCase = Depends(get_update_my_profile_use_case),
    ):
        profile = await use_case.execute(
            current_user["sub"], phone=dto.phone, city=dto.city
        )
        return profile_to_dto(profile)

    return router
