from ..domain.entities import Holiday
from .schemas import HolidayDTO, HolidayListDTO


def holiday_to_dto(holiday: Holiday) -> HolidayDTO:
    return HolidayDTO(
        id=holiday.id,
        day=holiday.day,
        name=holiday.name,
        entity_id=holiday.entity_id,
        entity_code=holiday.entity_code,
        created_at=holiday.created_at,
        updated_at=holiday.updated_at,
        source=holiday.source,
        scope=holiday.scope,
    )


def holidays_to_dto(holidays: list[Holiday]) -> HolidayListDTO:
    return HolidayListDTO(holidays=[holiday_to_dto(h) for h in holidays])
