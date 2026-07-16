"""
Puerto (Protocol) del feature `roles`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from typing import Protocol

from .entities import Role


class IRoleRepository(Protocol):
    async def list_roles(self) -> list[Role]:
        """Todos los roles de la tabla `roles`, sin filtrar. Incluye
        `administrador` — es responsabilidad de quien consuma el listado
        (hoy, `StaffForm` en el frontend) decidir si lo ofrece como opción
        asignable; el backend no restringe la unicidad del rol admin en
        ningún punto todavía (fuera de alcance de este feature)."""
        ...
