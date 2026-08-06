"""Fake en memoria de `IDepartmentRepository` — permite testear el caso de
uso sin Postgres, igual que en `features/roles`."""

from src.features.departments.domain.entities import Department

_DEFAULT_DEPARTMENTS = [
    Department(id="dept-1", name="Recursos Humanos", entity_id="entity-hub", entity_code="hub"),
    Department(id="dept-2", name="Operaciones", entity_id="entity-ops", entity_code="ops"),
]


class FakeDepartmentRepository:
    def __init__(
        self,
        departments: list[Department] | None = None,
        entity_by_user: dict[str, str | None] | None = None,
    ):
        self.departments = (
            list(departments) if departments is not None else list(_DEFAULT_DEPARTMENTS)
        )
        # `user_id -> entity_id`. Un usuario ausente del mapa, o con valor `None`,
        # modela `users.entity_id IS NULL`: el caso del empleado sin sociedad
        # asignada, que ve TODOS los departamentos en vez de ninguno.
        self.entity_by_user: dict[str, str | None] = dict(entity_by_user or {})

    async def list_departments_for_user(self, user_id: str) -> list[Department]:
        entity_id = self.entity_by_user.get(user_id)
        if entity_id is None:
            return list(self.departments)
        return [d for d in self.departments if d.entity_id == entity_id]

    async def department_belongs_to_user_entity(
        self, department_id: str, user_id: str
    ) -> bool:
        target = next((d for d in self.departments if d.id == department_id), None)
        if target is None:
            return False
        entity_id = self.entity_by_user.get(user_id)
        return entity_id is None or target.entity_id == entity_id
