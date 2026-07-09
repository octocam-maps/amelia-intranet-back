"""
Puerto (Protocol) del feature `holidays`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.

Nota: `features/absences` sigue leyendo directamente la tabla `holidays`
(`list_holiday_dates`, para excluir festivos del cómputo de días
laborables) — este feature es la superficie de GESTIÓN (CRUD admin), no
sustituye esa lectura interna.
"""

from datetime import date
from typing import Optional, Protocol

from .entities import Holiday, ImportSummary, OfficialHoliday


class IHolidayProvider(Protocol):
    """Puerto de salida hacia un proveedor externo de festivos oficiales. El
    adaptador concreto (Nager.Date, httpx) vive en `infrastructure`. Devuelve
    los festivos ya filtrados a lo que aplica en Barcelona (nacional España +
    autonómico Cataluña)."""

    async def fetch_official_holidays(self, year: int) -> list[OfficialHoliday]: ...


class IHolidayRepository(Protocol):
    async def list_holidays(
        self, *, year: Optional[int], entity_code: Optional[str]
    ) -> list[Holiday]: ...

    async def import_official_holidays(
        self, items: list[OfficialHoliday]
    ) -> ImportSummary:
        """Upsert idempotente de festivos oficiales (todos con
        `entity_id IS NULL`). Por cada día: si no existe, inserta como
        'oficial'; si ya existe una fila 'oficial', la refresca; si existe una
        fila 'manual', NO la toca (los manuales mandan). Devuelve el recuento."""
        ...

    async def find_by_id(self, holiday_id: str) -> Optional[Holiday]: ...

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]: ...

    async def create_holiday(
        self, *, day: date, name: str, entity_id: Optional[str], scope: Optional[str] = None
    ) -> Holiday: ...

    async def update_holiday(
        self,
        holiday_id: str,
        *,
        day: Optional[date],
        name: Optional[str],
        entity_id: Optional[str],
        clear_entity: bool,
        scope: Optional[str] = None,
    ) -> Optional[Holiday]:
        """Actualización parcial. `clear_entity` vacía `entity_id` cuando el
        admin pasa el festivo de "una entidad" a "todas" — `COALESCE` no
        distingue "no tocar" de "vaciar" (mismo patrón que `announcements`)."""
        ...

    async def delete_holiday(self, holiday_id: str) -> bool:
        """Borrado físico: nada referencia `holidays` con FK (`list_holiday_dates`
        solo lee por rango de fecha), así que no hace falta soft-delete."""
        ...
