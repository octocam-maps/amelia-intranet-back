"""
Router de `/roles`: fuente única de "qué roles existen" para poblar
selectores (hoy, exclusivamente `StaffForm` en "Plantilla"). `require_role`
se restringe al admin porque es el único consumidor real hoy — "Plantilla"
(`POST/PATCH /staff`) ya es admin-only (ver `staff/infrastructure/routes.py`).
Si otro feature necesita esta lista más adelante (p.ej. un selector de
`audience=role` en Anuncios), este guard se amplía explícitamente ahí — NUNCA
se generaliza a "cualquier autenticado" solo porque sea más simple.
"""

from fastapi import APIRouter, Depends

from src.shared.auth.dependencies import require_role

from ..application.use_cases.list_roles import ListRolesUseCase
from .dependencies import get_list_roles_use_case
from .mappers import roles_to_dto
from .schemas import RoleListDTO


def create_roles_router() -> APIRouter:
    router = APIRouter(prefix="/roles", tags=["roles"])

    @router.get("", response_model=RoleListDTO)
    async def list_roles(
        current_user: dict = Depends(require_role("administrador")),
        use_case: ListRolesUseCase = Depends(get_list_roles_use_case),
    ):
        roles = await use_case.execute()
        return roles_to_dto(roles)

    return router
