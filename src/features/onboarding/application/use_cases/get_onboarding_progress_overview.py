"""
Caso de uso: `GET /onboarding/admin/progress` — progreso de onboarding de
TODA la plantilla (administrador/empleado/externo-invitado), una fila por
usuario aunque no tenga progreso inicializado. El cálculo de `status`/
`current_step_title` es lógica de dominio pura (`summarize_employee_onboarding`)
sobre snapshots que ya trajo el repositorio con un `LEFT JOIN` — aquí solo
se resuelve cuántos pasos le tocan a CADA usuario según su rol (el
externo-invitado hace onboarding parcial, ver `steps_applicable_to_role`).
"""

from ...domain.entities import EmployeeOnboardingSummary
from ...domain.policy import steps_applicable_to_role, summarize_employee_onboarding
from ...domain.ports import IOnboardingRepository

_ROLES = ("administrador", "empleado", "externo_invitado", "socio")


class GetOnboardingProgressOverviewUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(self) -> list[EmployeeOnboardingSummary]:
        catalog = await self._repository.list_active_steps()
        total_steps_by_role = {
            role: len(steps_applicable_to_role(catalog, role)) for role in _ROLES
        }

        snapshots = await self._repository.list_employee_progress_snapshots()
        return [
            summarize_employee_onboarding(
                snapshot, total_steps=total_steps_by_role.get(snapshot.role, len(catalog))
            )
            for snapshot in snapshots
        ]
