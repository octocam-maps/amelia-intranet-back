"""Fake en memoria de `IRoleRepository` — permite testear el caso de uso
sin Postgres, igual que en `features/staff` y `features/team`."""

from src.features.roles.domain.entities import Role

_DEFAULT_ROLES = [
    Role(id="role-administrador", code="administrador", name="Administrador"),
    Role(id="role-empleado", code="empleado", name="Empleado"),
    Role(id="role-externo_invitado", code="externo_invitado", name="Externo-invitado"),
    Role(id="role-socio", code="socio", name="Socio"),
]


class FakeRoleRepository:
    def __init__(self, roles: list[Role] | None = None):
        self.roles = list(roles) if roles is not None else list(_DEFAULT_ROLES)

    async def list_roles(self) -> list[Role]:
        return list(self.roles)
