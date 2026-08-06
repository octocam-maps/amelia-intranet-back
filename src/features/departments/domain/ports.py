"""
Puerto (Protocol) del feature `departments`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from typing import Protocol

from .entities import Department


class IDepartmentRepository(Protocol):
    async def list_departments_for_user(self, user_id: str) -> list[Department]:
        """Los departamentos que este usuario puede elegir: los de SU entidad.

        FILTRA POR ENTIDAD, y antes no lo hacía. Los mismos cinco departamentos
        existen en las cuatro sociedades del grupo (`departments` tiene
        `UNIQUE(entity_id, name)`), así que el listado sin filtrar devolvía 20
        filas ordenadas por nombre y el selector del paso 4 mostraba cuatro
        «Administración» seguidas, indistinguibles entre sí. Elegir ahí era
        elegir a ciegas.

        Si el usuario NO tiene entidad (`users.entity_id IS NULL` — hoy hay un
        empleado así) devuelve TODOS. Es un fallback deliberado: filtrar a cero
        le impediría completar el paso 4 y lo dejaría atascado en su onboarding,
        que es peor que mostrarle una lista ambigua. Para ese caso el cliente
        enseña la entidad junto al nombre."""
        ...

    async def department_belongs_to_user_entity(
        self, department_id: str, user_id: str
    ) -> bool:
        """¿Ese departamento es de la entidad del usuario?

        Es la comprobación que valida el paso 4 en el BACKEND, y hace falta
        ADEMÁS del filtro del listado: ocultar las opciones de las otras
        sociedades en el selector no impide enviar el `department_id` a mano
        (regla del proyecto: ocultar ≠ proteger).

        `False` si el departamento no existe. `True` si el usuario no tiene
        entidad, por el mismo motivo que el fallback de
        `list_departments_for_user`: no dejarlo sin poder terminar."""
        ...
