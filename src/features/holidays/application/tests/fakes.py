"""Fake en memoria de `IHolidayRepository` — permite testear los casos de
uso sin Postgres, igual que en `features/staff`/`features/announcements`."""

import uuid
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Optional

from src.features.holidays.domain.entities import (
    Holiday,
    ImportSummary,
    OfficialHoliday,
)

_ENTITY_IDS = {"hub": "entity-hub", "lab": "entity-lab", "ops": "entity-ops"}


class FakeHolidayRepository:
    def __init__(self, holidays: Optional[list[Holiday]] = None):
        self.holidays: dict[str, Holiday] = {h.id: h for h in (holidays or [])}

    async def list_holidays(
        self, *, year: Optional[int], entity_code: Optional[str]
    ) -> list[Holiday]:
        items = list(self.holidays.values())
        if year is not None:
            items = [h for h in items if h.day.year == year]
        if entity_code is not None:
            entity_id = _ENTITY_IDS.get(entity_code)
            items = [h for h in items if h.entity_id in (entity_id, None)]
        return sorted(items, key=lambda h: h.day)

    async def find_by_id(self, holiday_id: str) -> Optional[Holiday]:
        return self.holidays.get(holiday_id)

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]:
        return _ENTITY_IDS.get(entity_code)

    async def create_holiday(
        self, *, day: date, name: str, entity_id: Optional[str]
    ) -> Holiday:
        holiday_id = str(uuid.uuid4())
        entity_code = next((k for k, v in _ENTITY_IDS.items() if v == entity_id), None)
        now = datetime.now(timezone.utc)
        holiday = Holiday(
            id=holiday_id,
            day=day,
            name=name,
            entity_id=entity_id,
            entity_code=entity_code,
            created_at=now,
            updated_at=now,
        )
        self.holidays[holiday_id] = holiday
        return holiday

    async def update_holiday(
        self,
        holiday_id: str,
        *,
        day: Optional[date],
        name: Optional[str],
        entity_id: Optional[str],
        clear_entity: bool,
    ) -> Optional[Holiday]:
        existing = self.holidays.get(holiday_id)
        if existing is None:
            return None
        new_entity_id = None if clear_entity else (entity_id or existing.entity_id)
        new_entity_code = next((k for k, v in _ENTITY_IDS.items() if v == new_entity_id), None)
        updated = replace(
            existing,
            day=day if day is not None else existing.day,
            name=name if name is not None else existing.name,
            entity_id=new_entity_id,
            entity_code=new_entity_code,
            updated_at=datetime.now(timezone.utc),
        )
        self.holidays[holiday_id] = updated
        return updated

    async def delete_holiday(self, holiday_id: str) -> bool:
        if holiday_id not in self.holidays:
            return False
        del self.holidays[holiday_id]
        return True

    async def import_official_holidays(
        self, items: list[OfficialHoliday]
    ) -> ImportSummary:
        imported = updated = skipped = 0
        for item in items:
            existing = next(
                (
                    h
                    for h in self.holidays.values()
                    if h.day == item.day and h.entity_id is None
                ),
                None,
            )
            if existing is None:
                holiday_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc)
                self.holidays[holiday_id] = Holiday(
                    id=holiday_id,
                    day=item.day,
                    name=item.name,
                    entity_id=None,
                    entity_code=None,
                    created_at=now,
                    updated_at=now,
                    source="oficial",
                    scope=item.scope,
                )
                imported += 1
            elif existing.source == "manual":
                skipped += 1
            else:
                self.holidays[existing.id] = replace(
                    existing,
                    name=item.name,
                    scope=item.scope,
                    updated_at=datetime.now(timezone.utc),
                )
                updated += 1
        return ImportSummary(imported=imported, updated=updated, skipped=skipped)
