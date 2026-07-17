"""
Puertos (Protocols) del feature `absences`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import date
from typing import Optional, Protocol

from .entities import AbsenceBalance, AbsenceCalendarEntry, AbsenceRequest, AbsenceType


class IAbsenceRepository(Protocol):
    async def list_types(self) -> list[AbsenceType]: ...

    async def list_all_types(self) -> list[AbsenceType]:
        """Vista de gestión del admin (docs/permisos-roles.md § "Tipos de
        ausencia"): incluye los desactivados, a diferencia de `list_types`
        (que solo muestra los activos al empleado que va a solicitar una
        ausencia)."""
        ...

    async def find_type_by_id(self, absence_type_id: str) -> Optional[AbsenceType]: ...

    async def find_type_by_code(self, code: str) -> Optional[AbsenceType]: ...

    async def create_type(
        self,
        *,
        code: str,
        name: str,
        is_paid: bool,
        affects_balance: bool,
        default_entitled_days: float,
        color: Optional[str],
        requires_approval: bool = True,
        requires_justification: bool = False,
        max_days_per_year: Optional[int] = None,
    ) -> AbsenceType: ...

    async def update_type(
        self,
        absence_type_id: str,
        *,
        name: Optional[str],
        is_paid: Optional[bool],
        affects_balance: Optional[bool],
        default_entitled_days: Optional[float],
        color: Optional[str],
        is_active: Optional[bool],
        requires_approval: Optional[bool] = None,
        requires_justification: Optional[bool] = None,
        max_days_per_year: Optional[int] = None,
    ) -> Optional[AbsenceType]:
        """Actualización parcial. `code` NO es editable — `absence_balances`
        y el seed (010/013_absence_types_*.sql) referencian el código como
        identificador estable, no solo el UUID."""
        ...

    async def get_or_create_balance(
        self, user_id: str, absence_type_id: str, year: int
    ) -> AbsenceBalance:
        """Crea la fila de saldo la primera vez que un usuario la necesita,
        con `entitled_days = absence_types.default_entitled_days`."""
        ...

    async def list_balances_for_user(self, user_id: str, year: int) -> list[AbsenceBalance]: ...

    async def adjust_balance(
        self,
        user_id: str,
        absence_type_id: str,
        year: int,
        *,
        used_delta: float,
        pending_delta: float,
    ) -> None:
        """Ajusta `used_days`/`pending_days` de forma atómica (un único
        UPDATE). Solo se usa tras haber ganado `update_request_status_if_pending`
        — a esas alturas ya no hay carrera posible sobre esta solicitud."""
        ...

    async def try_reserve_balance(
        self,
        user_id: str,
        absence_type_id: str,
        year: int,
        *,
        pending_delta: float,
    ) -> bool:
        """UPDATE atómico condicionado al saldo disponible en la propia
        query: `True` si reservó `pending_delta` días, `False` si el saldo
        disponible en ese instante no lo cubría (0 filas afectadas) — evita
        el overdraft por "leer saldo, decidir, escribir" bajo concurrencia
        (RACE-1)."""
        ...

    async def try_consume_balance(
        self,
        user_id: str,
        absence_type_id: str,
        year: int,
        *,
        used_delta: float,
    ) -> bool:
        """Igual que `try_reserve_balance`, pero descuenta directamente de
        `used_days` en vez de `pending_days` — lo usa la autoaprobación del
        administrador (B-1c): su solicitud nunca pasa por `pending`, así que
        no tiene sentido reservar y luego liberar/consumir en dos pasos.
        `True` si el saldo disponible en ese instante cubría `used_delta`,
        `False` si no (0 filas afectadas) — mismo contrato anti-overdraft
        que `try_reserve_balance` (RACE-1)."""
        ...

    async def create_request(
        self,
        *,
        user_id: str,
        absence_type_id: str,
        start_date: date,
        end_date: date,
        days_count: float,
        reason: Optional[str],
    ) -> AbsenceRequest: ...

    async def create_approved_request(
        self,
        *,
        user_id: str,
        absence_type_id: str,
        start_date: date,
        end_date: date,
        days_count: float,
        reason: Optional[str],
        review_note: str,
    ) -> AbsenceRequest:
        """Crea la solicitud ya en `approved`, con `reviewed_by = user_id`
        (el propio solicitante) y `reviewed_at = CURRENT_TIMESTAMP` —
        autoaprobación del administrador (B-1c). Nunca pasa por `pending` ni
        aparece en la bandeja de aprobación."""
        ...

    async def find_request_by_id(self, request_id: str) -> Optional[AbsenceRequest]: ...

    async def list_requests_for_user(self, user_id: str) -> list[AbsenceRequest]: ...

    async def list_pending_requests(self) -> list[AbsenceRequest]:
        """Bandeja de aprobación del admin (docs/permisos-roles.md § Ausencias).
        Rellena `user_full_name` (JOIN con `users`) — la bandeja necesita el
        nombre real del solicitante, no solo su `user_id`."""
        ...

    async def list_all_requests(self) -> list[AbsenceRequest]:
        """Vista de calendario global del admin. Rellena `user_full_name`
        igual que `list_pending_requests`, por la misma razón (gantt de
        plantilla)."""
        ...

    async def update_request_status_if_pending(
        self,
        request_id: str,
        *,
        status: str,
        reviewed_by: str,
        review_note: Optional[str],
    ) -> Optional[AbsenceRequest]:
        """UPDATE atómico condicionado a `status = 'pending'` en la propia
        query: `None` si la solicitud ya no estaba pending (0 filas
        afectadas) — evita la doble aprobación bajo concurrencia (RACE-2)."""
        ...

    async def list_holiday_dates(self, date_from: date, date_to: date) -> list[date]:
        """Festivos vigentes en el rango. La tabla `holidays` está vacía hasta
        que el admin la configure (Fase 5) — no bloquea el cálculo de días
        laborables, simplemente no excluye nada todavía."""
        ...

    async def list_calendar_entries(
        self, *, date_from: date, date_to: date
    ) -> list[AbsenceCalendarEntry]:
        """"Calendario general de la plantilla" (LOTE 4) — TODOS los
        empleados, `pending`/`approved` únicamente (una solicitud `rejected`
        o `cancelled` no describe una ausencia real), cuyo rango
        [`start_date`, `end_date`] solapa con [`date_from`, `date_to`]. Ya
        viene con `user_full_name`/`absence_type_name`/`absence_type_color`
        resueltos (JOIN) — lo consume tanto la pantalla como los exports
        (XLSX/PDF), que necesitan exactamente la misma forma."""
        ...

    async def list_overlapping_requests(
        self, user_id: str, *, start_date: date, end_date: date
    ) -> list[AbsenceRequest]:
        """Solicitudes `pending`/`approved` del MISMO usuario cuyo rango
        [`start_date`, `end_date`] solapa con el rango dado — anti-solape en
        `CreateAbsenceRequestUseCase` (bug real, auditoría QA: sin esto, un
        usuario podía tener dos solicitudes de vacaciones para las mismas
        fechas). No filtra por `absence_type_id` — ver
        `AbsenceRequestOverlapError` para la granularidad pendiente de
        confirmar con RRHH."""
        ...
