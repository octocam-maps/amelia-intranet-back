"""
Router de `/manuals`: la biblioteca de manuales de uso.

PREFIJO PROPIO y no `/onboarding/manuals` porque ya no es solo del onboarding: la
biblioteca incluye el manual de uso de la intranet, que se consulta en cualquier
momento y no forma parte de ningún paso. Vive en el feature `onboarding` porque la
tabla (`onboarding_documents`) es suya — mismo criterio que `documents`
reutilizando el repositorio de `staff`.

`ALL_ROLES`: "todos los usuarios de la plataforma", incluido el externo-invitado.
Es coherente con lo que ya tenía — su onboarding parcial es vídeo + manuales, así
que los manuales nunca fueron material restringido.
"""

from fastapi import APIRouter, Depends

from src.shared.auth.dependencies import require_role
from src.shared.auth.roles import ALL_ROLES

from ..application.use_cases.list_manuals_library import ListManualsLibraryUseCase
from .dependencies import get_list_manuals_library_use_case
from .mappers import manuals_library_to_dto
from .schemas import ManualsLibraryDTO


def create_manuals_router() -> APIRouter:
    router = APIRouter(prefix="/manuals", tags=["manuals"])

    @router.get("", response_model=ManualsLibraryDTO)
    async def list_manuals(
        current_user: dict = Depends(require_role(*ALL_ROLES)),
        use_case: ListManualsLibraryUseCase = Depends(
            get_list_manuals_library_use_case
        ),
    ):
        """Manuales de consulta, con marca de los que este usuario ya confirmó.

        Sin cascada: aquí no se bloquea ninguno. La puerta de lectura obligatoria
        aplica DENTRO del paso 3 del onboarding — negarle a alguien abrir un PDF que
        necesita para trabajar no protegería nada.
        """
        manuals = await use_case.execute(user_id=current_user["sub"])
        return manuals_library_to_dto(manuals)

    return router
