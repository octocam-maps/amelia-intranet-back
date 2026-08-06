"""Caso de uso: listar los departamentos que un usuario puede elegir.

Ya NO es un pass-through: el listado depende de QUIÉN pregunta, porque los mismos
departamentos existen en las cuatro sociedades del grupo y a cada persona solo le
corresponden los de la suya. El filtro vive en la query
(`list_departments_for_user`), igual que antes vivía ahí el `ORDER BY`."""

from ...domain.entities import Department
from ...domain.ports import IDepartmentRepository


class ListDepartmentsUseCase:
    def __init__(self, repository: IDepartmentRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> list[Department]:
        """`user_id` SIEMPRE del JWT, nunca de un parámetro de la petición: si
        viajara en la query string, cualquiera podría listar los departamentos de
        otra sociedad cambiando un id en la URL."""
        return await self._repository.list_departments_for_user(user_id)
