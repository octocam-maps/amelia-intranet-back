"""
Puerto (Protocol) del feature `departments`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from typing import Protocol

from .entities import Department


class IDepartmentRepository(Protocol):
    async def list_departments(self) -> list[Department]:
        """Todos los departamentos de la tabla `departments`, sin filtrar
        por entidad — quien consuma el listado (hoy, el Paso 5 del
        onboarding) decide si agrupa/filtra por `entity_code`."""
        ...
