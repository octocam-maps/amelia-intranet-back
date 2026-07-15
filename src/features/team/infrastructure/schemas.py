"""DTOs de response (Pydantic) del feature `team`."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


class TeamMemberDTO(BaseModel):
    id: str
    full_name: str
    job_title: Optional[str] = None
    entity_code: Optional[str] = None
    entity_name: Optional[str] = None
    phone: Optional[str] = None
    email: str
    avatar_url: Optional[str] = None


class TeamDirectoryDTO(BaseModel):
    members: list[TeamMemberDTO]


class TeamAbsenceEntryDTO(BaseModel):
    user_id: str
    full_name: str
    start_date: date
    end_date: date
    # NUNCA el `code` real del tipo de ausencia — solo el `kind` privacy-safe
    # (ver `domain/entities.py::AbsenceKind`). `baja_medica`/`duelo`/etc. ya
    # llegan aquí colapsados en `ausente` desde el repositorio.
    kind: Literal["vacaciones", "remoto", "ausente"]


class TeamAbsenceCalendarDTO(BaseModel):
    entries: list[TeamAbsenceEntryDTO]


class TeamBirthdayDTO(BaseModel):
    user_id: str
    full_name: str
    avatar_url: Optional[str] = None
    day: int
    month: int
    is_today: bool


class TeamBirthdaysDTO(BaseModel):
    birthdays: list[TeamBirthdayDTO]
