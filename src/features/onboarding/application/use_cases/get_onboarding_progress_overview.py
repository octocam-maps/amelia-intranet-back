"""
Caso de uso: `GET /onboarding/admin/progress` — progreso de onboarding de la
plantilla, una fila por usuario aunque no tenga progreso inicializado. El
cálculo de `status`/`current_step_title` es lógica de dominio pura
(`summarize_employee_onboarding`) sobre snapshots que ya trajo el repositorio
con un `LEFT JOIN` — aquí solo se resuelve cuántos pasos le tocan a CADA
usuario según su rol (el externo-invitado hace onboarding parcial, ver
`steps_applicable_to_role`).

QUIÉN NO SALE: los roles exentos del recorrido secuencial —hoy solo el
administrador—. Esta tabla es la herramienta de seguimiento de RRHH: sirve para
ver a quién hay que perseguir. El administrador no está obligado a completar el
onboarding (`is_exempt_from_sequential_gating`), así que su fila diría
"0 de 5, pendiente" para siempre y Beatriz se estaría persiguiendo a sí misma.
Antes salía, y era la misma premisa equivocada que el bug del bloqueo.
"""

from src.shared.auth.roles import ALL_ROLES

from ...domain.entities import EmployeeOnboardingSummary
from ...domain.policy import (
    is_exempt_from_sequential_gating,
    steps_applicable_to_role,
    summarize_employee_onboarding,
)
from ...domain.ports import IOnboardingRepository


class GetOnboardingProgressOverviewUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(self) -> list[EmployeeOnboardingSummary]:
        catalog = await self._repository.list_active_steps()
        total_steps_by_role = {
            role.value: len(steps_applicable_to_role(catalog, role)) for role in ALL_ROLES
        }

        snapshots = await self._repository.list_employee_progress_snapshots()
        return [
            summarize_employee_onboarding(
                snapshot, total_steps=total_steps_by_role.get(snapshot.role, len(catalog))
            )
            for snapshot in snapshots
            if not is_exempt_from_sequential_gating(snapshot.role)
        ]
