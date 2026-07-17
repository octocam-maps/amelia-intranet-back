"""DTOs de response (Pydantic) del feature `roles`."""

from pydantic import BaseModel


class RoleDTO(BaseModel):
    code: str
    name: str


class RoleListDTO(BaseModel):
    roles: list[RoleDTO]
