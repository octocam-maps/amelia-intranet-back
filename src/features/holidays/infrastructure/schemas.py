"""DTOs de request/response (Pydantic) del feature `holidays`."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

EntityCode = Literal["hub", "lab", "ops"]


class HolidayDTO(BaseModel):
    id: str
    day: date
    name: str
    entity_id: Optional[str]
    entity_code: Optional[str]  # None == aplica a las 3 entidades
    created_at: datetime
    updated_at: datetime


class HolidayListDTO(BaseModel):
    holidays: list[HolidayDTO]


class CreateHolidayDTO(BaseModel):
    day: date
    name: str = Field(..., min_length=1, max_length=120)
    entity: Optional[EntityCode] = None  # None == aplica a las 3 entidades


class UpdateHolidayDTO(BaseModel):
    day: Optional[date] = None
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    # `entity` ausente del payload -> no toca el ámbito; `entity: null`
    # explícito -> lo vacía (pasa a aplicar a las 3 entidades). La ruta
    # distingue ambos casos con `dto.model_fields_set`, no con este campo.
    entity: Optional[EntityCode] = None
