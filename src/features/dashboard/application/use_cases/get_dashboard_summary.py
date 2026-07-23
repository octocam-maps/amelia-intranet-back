"""
Caso de uso: resumen del dashboard, condicionado por rol
(docs/permisos-roles.md § Inicio):
- Empleado: saldo de vacaciones, estado de su fichaje del día, próximos
  festivos.
- Admin: además, la bandeja de solicitudes de ausencia pendientes y una
  vista global (empleados con un tramo de fichaje abierto ahora mismo).

El externo-invitado NO tiene dashboard (matriz de permisos: ❌) — la ruta
que llama a este caso de uso ya lo bloquea con `require_role` antes de
llegar aquí.
"""

from src.shared.auth.roles import RoleCode
from src.shared.utils.timezone import today_in_madrid

from ...domain.entities import AdminDashboardSummary, EmployeeDashboardSummary
from ...domain.ports import IDashboardRepository

_UPCOMING_HOLIDAYS_LIMIT = 5
_PENDING_REQUESTS_LIMIT = 20


class GetDashboardSummaryUseCase:
    def __init__(self, repository: IDashboardRepository):
        self._repository = repository

    async def execute(self, *, user_id: str, role: str) -> EmployeeDashboardSummary:
        # TZ-1: "hoy" es Europe/Madrid, no la TZ del proceso (UTC) — decide
        # qué contador de vacaciones ve el usuario y si su fichaje de "hoy"
        # sigue abierto justo alrededor de la medianoche.
        today = today_in_madrid()
        vacation_balance = await self._repository.get_vacation_balance(user_id, today.year)
        clock_status = await self._repository.get_today_clock_status(user_id, today)
        holidays = await self._repository.list_upcoming_holidays(today, _UPCOMING_HOLIDAYS_LIMIT)

        if role != RoleCode.ADMINISTRADOR:
            return EmployeeDashboardSummary(
                vacation_balance=vacation_balance,
                today_clock_status=clock_status,
                upcoming_holidays=holidays,
            )

        pending_requests = await self._repository.list_pending_absence_requests(
            _PENDING_REQUESTS_LIMIT
        )
        employees_clocked_in_now = await self._repository.count_employees_clocked_in_now()

        return AdminDashboardSummary(
            vacation_balance=vacation_balance,
            today_clock_status=clock_status,
            upcoming_holidays=holidays,
            pending_absence_requests=pending_requests,
            employees_clocked_in_now=employees_clocked_in_now,
        )
