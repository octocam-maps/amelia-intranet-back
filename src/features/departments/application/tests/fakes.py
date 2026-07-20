"""Fake en memoria de `IDepartmentRepository` — permite testear el caso de
uso sin Postgres, igual que en `features/roles`."""

from src.features.departments.domain.entities import Department

_DEFAULT_DEPARTMENTS = [
    Department(id="dept-1", name="Recursos Humanos", entity_id="entity-hub", entity_code="hub"),
    Department(id="dept-2", name="Operaciones", entity_id="entity-ops", entity_code="ops"),
]


class FakeDepartmentRepository:
    def __init__(self, departments: list[Department] | None = None):
        self.departments = (
            list(departments) if departments is not None else list(_DEFAULT_DEPARTMENTS)
        )

    async def list_departments(self) -> list[Department]:
        return list(self.departments)
