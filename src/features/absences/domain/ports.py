"""
Puertos (Protocols) del feature `absences`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import date
from typing import Optional, Protocol

from .entities import AbsenceBalance, AbsenceRequest, AbsenceType


class IAbsenceRepository(Protocol):
    async def list_types(self) -> list[AbsenceType]: ...

    async def find_type_by_id(self, absence_type_id: str) -> Optional[AbsenceType]: ...

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
        UPDATE), evitando condiciones de carrera entre solicitudes concurrentes
        del mismo usuario/tipo/año."""
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

    async def find_request_by_id(self, request_id: str) -> Optional[AbsenceRequest]: ...

    async def list_requests_for_user(self, user_id: str) -> list[AbsenceRequest]: ...

    async def list_pending_requests(self) -> list[AbsenceRequest]:
        """Bandeja de aprobación del admin (docs/permisos-roles.md § Ausencias)."""
        ...

    async def list_all_requests(self) -> list[AbsenceRequest]:
        """Vista de calendario global del admin."""
        ...

    async def update_request_status(
        self,
        request_id: str,
        *,
        status: str,
        reviewed_by: str,
        review_note: Optional[str],
    ) -> AbsenceRequest: ...

    async def list_holiday_dates(self, date_from: date, date_to: date) -> list[date]:
        """Festivos vigentes en el rango. La tabla `holidays` está vacía hasta
        que el admin la configure (Fase 5) — no bloquea el cálculo de días
        laborables, simplemente no excluye nada todavía."""
        ...
