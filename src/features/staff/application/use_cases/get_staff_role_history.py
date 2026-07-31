"""Caso de uso: historial de cambios de rol de una persona de la plantilla
(`user_role_history`, migración 039).

Existe para la pregunta que RRHH hace cuando un becario promociona: "¿desde
cuándo es trabajador?". La antigüedad LABORAL no está aquí — vive en
`users.hire_date`, que es inmutable tras el alta y es lo que alimenta el cálculo
de vacaciones. Esto es la antigüedad EN EL ROL, que antes de la 039 no se podía
reconstruir porque el `UPDATE` pisaba el valor anterior sin dejar rastro.
"""

from ...domain.entities import RoleChange
from ...domain.errors import StaffMemberNotFoundError
from ...domain.ports import IStaffRepository


class GetStaffRoleHistoryUseCase:
    def __init__(self, repository: IStaffRepository):
        self._repository = repository

    async def execute(self, user_id: str) -> list[RoleChange]:
        # Se comprueba la existencia ANTES de leer el historial: una persona que
        # no existe debe dar 404, no una lista vacía. `list_role_history`
        # devuelve `[]` en los dos casos a propósito (ver su docstring), así que
        # distinguirlos es responsabilidad de esta capa.
        member = await self._repository.find_by_id(user_id)
        if member is None:
            raise StaffMemberNotFoundError("La persona no existe.")

        return await self._repository.list_role_history(user_id)
