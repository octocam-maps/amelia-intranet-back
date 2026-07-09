"""
TZ-1 (auditoría QA Fase 3): los DTOs de fichaje exigen offset explícito en
`clock_in`/`clock_out` — un datetime naive es ambiguo (¿hora local del
navegador o ya UTC?) y no debe llegar a la capa de aplicación.
"""

import pytest
from pydantic import ValidationError

from src.features.time_clock.infrastructure.schemas import (
    CreateTimeClockEntryDTO,
    UpdateTimeClockEntryDTO,
)


def test_create_dto_accepts_datetime_with_offset():
    dto = CreateTimeClockEntryDTO(
        work_date="2026-07-09",
        clock_in="2026-07-09T09:00:00Z",
        clock_out="2026-07-09T13:00:00+00:00",
    )

    assert dto.clock_in.tzinfo is not None
    assert dto.clock_out.tzinfo is not None


def test_create_dto_rejects_naive_clock_in():
    with pytest.raises(ValidationError):
        CreateTimeClockEntryDTO(work_date="2026-07-09", clock_in="2026-07-09T09:00:00")


def test_create_dto_rejects_naive_clock_out():
    with pytest.raises(ValidationError):
        CreateTimeClockEntryDTO(
            work_date="2026-07-09",
            clock_in="2026-07-09T09:00:00Z",
            clock_out="2026-07-09T13:00:00",
        )


def test_update_dto_rejects_naive_datetimes():
    with pytest.raises(ValidationError):
        UpdateTimeClockEntryDTO(clock_in="2026-07-09T09:00:00")
