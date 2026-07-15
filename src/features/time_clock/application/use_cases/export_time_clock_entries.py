"""Caso de uso: generar el informe de fichajes (XLSX) de TODA la plantilla
interna en un rango de fechas.

No repite el chequeo de rol aquí — el único llamador es
`GET /time-clock/entries/export.xlsx`, ya protegido con
`require_role("administrador")` en la capa de FastAPI (regla del proyecto:
"ocultar ≠ proteger", la autorización real vive en el router/dependencia,
nunca solo en la UI)."""

from datetime import date

from ...domain.entities import TimeClockExportRow
from ...domain.ports import ITimeClockRepository


class ExportTimeClockEntriesUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, date_from: date, date_to: date) -> list[TimeClockExportRow]:
        return await self._repository.list_export_rows_for_all(
            date_from=date_from, date_to=date_to
        )
