"""
Router de `/departments`: fuente única de "qué departamentos existen" para
poblar selectores — hoy, el Paso 5 del onboarding ("Completar perfil", RF
§3.5) en el frontend (`ProfileStep`). `require_role` se restringe a los
roles que completan onboarding COMPLETO (`administrador`, `empleado`,
`socio` — mismo `INTERNAL_ROLES` que
`onboarding/infrastructure/routes.py`): el externo-invitado tiene onboarding
parcial (vídeo + manual, sin perfil) y no necesita este listado. NO se deja
abierto a "cualquier autenticado" solo porque sea más simple — si otro
feature necesita esta lista con otro alcance de rol más adelante, ese guard
se amplía explícitamente ahí.
"""

from fastapi import APIRouter, Depends

from src.shared.auth.dependencies import require_role
from src.shared.auth.roles import INTERNAL_ROLES

from ..application.use_cases.list_departments import ListDepartmentsUseCase
from .dependencies import get_list_departments_use_case
from .mappers import departments_to_dto
from .schemas import DepartmentListDTO


def create_departments_router() -> APIRouter:
    router = APIRouter(prefix="/departments", tags=["departments"])

    @router.get("", response_model=DepartmentListDTO)
    async def list_departments(
        current_user: dict = Depends(require_role(*INTERNAL_ROLES)),
        use_case: ListDepartmentsUseCase = Depends(get_list_departments_use_case),
    ):
        departments = await use_case.execute()
        return departments_to_dto(departments)

    return router
