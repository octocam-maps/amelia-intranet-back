"""Fake en memoria de `IAbsenceRepository` — permite testear los casos de
uso sin Postgres, igual que en `features/auth` y `features/time_clock`."""

import uuid
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Optional

from src.features.absences.domain.entities import AbsenceBalance, AbsenceRequest, AbsenceType


class FakeAbsenceRepository:
    def __init__(
        self,
        types: Optional[list[AbsenceType]] = None,
        balances: Optional[list[AbsenceBalance]] = None,
        requests: Optional[list[AbsenceRequest]] = None,
        holidays: Optional[list[date]] = None,
    ):
        self.types: dict[str, AbsenceType] = {t.id: t for t in (types or [])}
        self.balances: dict[tuple[str, str, int], AbsenceBalance] = {
            (b.user_id, b.absence_type_id, b.year): b for b in (balances or [])
        }
        self.requests: dict[str, AbsenceRequest] = {r.id: r for r in (requests or [])}
        self.holidays = set(holidays or [])

    async def list_types(self) -> list[AbsenceType]:
        return list(self.types.values())

    async def list_all_types(self) -> list[AbsenceType]:
        return list(self.types.values())

    async def find_type_by_id(self, absence_type_id: str) -> Optional[AbsenceType]:
        return self.types.get(absence_type_id)

    async def find_type_by_code(self, code: str) -> Optional[AbsenceType]:
        return next((t for t in self.types.values() if t.code == code), None)

    async def create_type(
        self, *, code, name, is_paid, affects_balance, default_entitled_days, color
    ) -> AbsenceType:
        type_id = str(uuid.uuid4())
        absence_type = AbsenceType(
            id=type_id,
            code=code,
            name=name,
            is_paid=is_paid,
            affects_balance=affects_balance,
            default_entitled_days=default_entitled_days,
            color=color,
            is_active=True,
        )
        self.types[type_id] = absence_type
        return absence_type

    async def update_type(
        self,
        absence_type_id,
        *,
        name,
        is_paid,
        affects_balance,
        default_entitled_days,
        color,
        is_active,
    ) -> Optional[AbsenceType]:
        existing = self.types.get(absence_type_id)
        if existing is None:
            return None
        updated = replace(
            existing,
            name=name if name is not None else existing.name,
            is_paid=is_paid if is_paid is not None else existing.is_paid,
            affects_balance=(
                affects_balance if affects_balance is not None else existing.affects_balance
            ),
            default_entitled_days=(
                default_entitled_days
                if default_entitled_days is not None
                else existing.default_entitled_days
            ),
            color=color if color is not None else existing.color,
            is_active=is_active if is_active is not None else existing.is_active,
        )
        self.types[absence_type_id] = updated
        return updated

    async def get_or_create_balance(self, user_id, absence_type_id, year) -> AbsenceBalance:
        key = (user_id, absence_type_id, year)
        if key in self.balances:
            return self.balances[key]
        absence_type = self.types[absence_type_id]
        balance = AbsenceBalance(
            id=str(uuid.uuid4()),
            user_id=user_id,
            absence_type_id=absence_type_id,
            year=year,
            entitled_days=absence_type.default_entitled_days,
            used_days=0,
            pending_days=0,
        )
        self.balances[key] = balance
        return balance

    async def list_balances_for_user(self, user_id: str, year: int) -> list[AbsenceBalance]:
        return [b for (uid, _, y), b in self.balances.items() if uid == user_id and y == year]

    async def adjust_balance(self, user_id, absence_type_id, year, *, used_delta, pending_delta):
        key = (user_id, absence_type_id, year)
        existing = self.balances[key]
        self.balances[key] = replace(
            existing,
            used_days=existing.used_days + used_delta,
            pending_days=existing.pending_days + pending_delta,
        )

    async def try_reserve_balance(self, user_id, absence_type_id, year, *, pending_delta) -> bool:
        # Espeja el UPDATE...WHERE atómico de Postgres: comprueba el saldo
        # disponible Y escribe la reserva en la misma "operación" — en el
        # fake no hay concurrencia real, pero mantiene el mismo contrato
        # (0 filas afectadas == False) para que los tests de RACE-1 no
        # dependan de un check-then-act en el use case.
        key = (user_id, absence_type_id, year)
        existing = self.balances.get(key)
        if existing is None:
            return False
        if existing.available_days < pending_delta:
            return False
        self.balances[key] = replace(existing, pending_days=existing.pending_days + pending_delta)
        return True

    async def create_request(
        self, *, user_id, absence_type_id, start_date, end_date, days_count, reason
    ) -> AbsenceRequest:
        request_id = str(uuid.uuid4())
        request = AbsenceRequest(
            id=request_id,
            user_id=user_id,
            absence_type_id=absence_type_id,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=reason,
            status="pending",
            reviewed_by=None,
            reviewed_at=None,
            review_note=None,
            created_at=datetime.now(timezone.utc),
        )
        self.requests[request_id] = request
        return request

    async def find_request_by_id(self, request_id: str) -> Optional[AbsenceRequest]:
        return self.requests.get(request_id)

    async def list_requests_for_user(self, user_id: str) -> list[AbsenceRequest]:
        return [r for r in self.requests.values() if r.user_id == user_id]

    async def list_pending_requests(self) -> list[AbsenceRequest]:
        return [r for r in self.requests.values() if r.status == "pending"]

    async def list_all_requests(self) -> list[AbsenceRequest]:
        return list(self.requests.values())

    async def update_request_status_if_pending(self, request_id, *, status, reviewed_by, review_note):
        existing = self.requests[request_id]
        if existing.status != "pending":
            return None
        updated = replace(
            existing,
            status=status,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.now(timezone.utc),
            review_note=review_note,
        )
        self.requests[request_id] = updated
        return updated

    async def list_holiday_dates(self, date_from: date, date_to: date) -> list[date]:
        return [d for d in self.holidays if date_from <= d <= date_to]
