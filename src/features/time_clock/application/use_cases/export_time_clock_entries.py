"""Caso de uso: generar el informe de fichajes (XLSX) en un rango de fechas —
de TODA la plantilla interna (admin) o SOLO del propio usuario (empleado,
alcance RGPD).

No repite el chequeo de rol aquí — el único llamador es
`GET /time-clock/entries/export.xlsx`, ya protegido con
`require_role("administrador", "empleado")` en la capa de FastAPI (regla del
proyecto: "ocultar ≠ proteger", la autorización real vive en el
router/dependencia, nunca solo en la UI). El router es también quien decide
el alcance (`user_id`) según el rol — este caso de uso solo ejecuta la
consulta que le pidan."""

from datetime import date
from typing import Optional

from ...domain.entities import TimeClockExportRow
from ...domain.ports import ITimeClockRepository


class ExportTimeClockEntriesUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self, *, date_from: date, date_to: date, user_id: Optional[str] = None
    ) -> list[TimeClockExportRow]:
        # `user_id=None` -> informe admin (toda la plantilla). Con `user_id`
        # -> RGPD: solo los fichajes de ESE usuario. El router nunca debe
        # pasar el `user_id` de otro usuario cuando el requester es empleado.
        if user_id is None:
            return await self._repository.list_export_rows_for_all(
                date_from=date_from, date_to=date_to
            )
        return await self._repository.list_export_rows_for_user(
            user_id, date_from=date_from, date_to=date_to
        )
