"""Traduce entidades de dominio (`Role`) a DTOs de FastAPI (Pydantic)."""

from ..domain.entities import Role
from .schemas import RoleDTO, RoleListDTO


def role_to_dto(role: Role) -> RoleDTO:
    return RoleDTO(code=role.code, name=role.name)


def roles_to_dto(roles: list[Role]) -> RoleListDTO:
    return RoleListDTO(roles=[role_to_dto(role) for role in roles])
