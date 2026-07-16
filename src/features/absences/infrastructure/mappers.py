from ..domain.entities import AbsenceBalance, AbsenceCalendarEntry, AbsenceRequest, AbsenceType
from .schemas import (
    AbsenceBalanceDTO,
    AbsenceBalanceListDTO,
    AbsenceCalendarEntryDTO,
    AbsenceCalendarEntryListDTO,
    AbsenceRequestDTO,
    AbsenceRequestListDTO,
    AbsenceTypeAdminDTO,
    AbsenceTypeAdminListDTO,
    AbsenceTypeDTO,
    AbsenceTypeListDTO,
)


def type_to_dto(absence_type: AbsenceType) -> AbsenceTypeDTO:
    return AbsenceTypeDTO(
        id=absence_type.id,
        code=absence_type.code,
        name=absence_type.name,
        is_paid=absence_type.is_paid,
        affects_balance=absence_type.affects_balance,
        color=absence_type.color,
    )


def types_to_dto(types: list[AbsenceType]) -> AbsenceTypeListDTO:
    return AbsenceTypeListDTO(types=[type_to_dto(t) for t in types])


def type_to_admin_dto(absence_type: AbsenceType) -> AbsenceTypeAdminDTO:
    return AbsenceTypeAdminDTO(
        id=absence_type.id,
        code=absence_type.code,
        name=absence_type.name,
        is_paid=absence_type.is_paid,
        affects_balance=absence_type.affects_balance,
        color=absence_type.color,
        default_entitled_days=absence_type.default_entitled_days,
        is_active=absence_type.is_active,
        requires_approval=absence_type.requires_approval,
        requires_justification=absence_type.requires_justification,
        max_days_per_year=absence_type.max_days_per_year,
    )


def types_to_admin_dto(types: list[AbsenceType]) -> AbsenceTypeAdminListDTO:
    return AbsenceTypeAdminListDTO(types=[type_to_admin_dto(t) for t in types])


def balance_to_dto(balance: AbsenceBalance) -> AbsenceBalanceDTO:
    return AbsenceBalanceDTO(
        absence_type_id=balance.absence_type_id,
        year=balance.year,
        entitled_days=balance.entitled_days,
        used_days=balance.used_days,
        pending_days=balance.pending_days,
        available_days=balance.available_days,
    )


def balances_to_dto(balances: list[AbsenceBalance]) -> AbsenceBalanceListDTO:
    return AbsenceBalanceListDTO(balances=[balance_to_dto(b) for b in balances])


def request_to_dto(request: AbsenceRequest) -> AbsenceRequestDTO:
    return AbsenceRequestDTO(
        id=request.id,
        user_id=request.user_id,
        absence_type_id=request.absence_type_id,
        start_date=request.start_date,
        end_date=request.end_date,
        days_count=request.days_count,
        reason=request.reason,
        status=request.status,
        reviewed_by=request.reviewed_by,
        review_note=request.review_note,
        user_full_name=request.user_full_name,
    )


def requests_to_dto(requests: list[AbsenceRequest]) -> AbsenceRequestListDTO:
    return AbsenceRequestListDTO(requests=[request_to_dto(r) for r in requests])


def calendar_entry_to_dto(entry: AbsenceCalendarEntry) -> AbsenceCalendarEntryDTO:
    return AbsenceCalendarEntryDTO(
        request_id=entry.request_id,
        user_id=entry.user_id,
        user_full_name=entry.user_full_name,
        absence_type_id=entry.absence_type_id,
        absence_type_name=entry.absence_type_name,
        absence_type_color=entry.absence_type_color,
        start_date=entry.start_date,
        end_date=entry.end_date,
        days_count=entry.days_count,
        status=entry.status,
    )


def calendar_entries_to_dto(entries: list[AbsenceCalendarEntry]) -> AbsenceCalendarEntryListDTO:
    return AbsenceCalendarEntryListDTO(entries=[calendar_entry_to_dto(e) for e in entries])
