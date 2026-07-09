from ..domain.entities import AbsenceBalance, AbsenceRequest, AbsenceType
from .schemas import (
    AbsenceBalanceDTO,
    AbsenceBalanceListDTO,
    AbsenceRequestDTO,
    AbsenceRequestListDTO,
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
