"""
Test del caso de uso `ImportOfficialHolidaysUseCase`: orquesta un proveedor
(fake) y el repositorio (fake en memoria). Verifica el upsert idempotente:
inserta lo nuevo, refresca lo oficial, y NUNCA pisa lo manual.
"""

from datetime import date, datetime, timezone

import pytest

from src.features.holidays.application.tests.fakes import FakeHolidayRepository
from src.features.holidays.application.use_cases.import_official_holidays import (
    ImportOfficialHolidaysUseCase,
)
from src.features.holidays.domain.entities import Holiday, OfficialHoliday


class _FakeProvider:
    def __init__(self, items: list[OfficialHoliday]):
        self._items = items

    async def fetch_official_holidays(self, year: int) -> list[OfficialHoliday]:
        return self._items


def _holiday(day: date, name: str, source: str) -> Holiday:
    now = datetime.now(timezone.utc)
    return Holiday(
        id=f"hol-{day.isoformat()}",
        day=day,
        name=name,
        entity_id=None,
        entity_code=None,
        created_at=now,
        updated_at=now,
        source=source,
    )


@pytest.mark.asyncio
async def test_imports_new_refreshes_official_and_skips_manual():
    # Estado previo: un festivo oficial (se refrescará) y uno manual (intocable).
    existing_official = _holiday(date(2026, 1, 1), "Año Nuevo", "oficial")
    manual_la_merce = _holiday(date(2026, 9, 24), "La Mercè", "manual")
    repo = FakeHolidayRepository([existing_official, manual_la_merce])

    provider = _FakeProvider(
        [
            OfficialHoliday(day=date(2026, 1, 1), name="Año Nuevo", scope="nacional"),
            OfficialHoliday(day=date(2026, 9, 24), name="Otro nombre", scope="nacional"),
            OfficialHoliday(day=date(2026, 6, 24), name="Sant Joan", scope="autonomico"),
        ]
    )
    use_case = ImportOfficialHolidaysUseCase(provider, repo)

    summary = await use_case.execute(year=2026)

    assert summary.imported == 1  # Sant Joan (nuevo)
    assert summary.updated == 1  # Año Nuevo (oficial existente refrescado)
    assert summary.skipped == 1  # La Mercè (manual, no se toca)

    # El manual conserva su nombre pese a que el proveedor traía otro.
    kept = repo.holidays[manual_la_merce.id]
    assert kept.name == "La Mercè"
    assert kept.source == "manual"


@pytest.mark.asyncio
async def test_reimport_is_idempotent():
    repo = FakeHolidayRepository()
    provider = _FakeProvider(
        [OfficialHoliday(day=date(2026, 12, 25), name="Navidad", scope="nacional")]
    )
    use_case = ImportOfficialHolidaysUseCase(provider, repo)

    first = await use_case.execute(year=2026)
    second = await use_case.execute(year=2026)

    assert first.imported == 1 and first.updated == 0
    # La segunda pasada no duplica: refresca la misma fila.
    assert second.imported == 0 and second.updated == 1
    official = [h for h in repo.holidays.values() if h.day == date(2026, 12, 25)]
    assert len(official) == 1
