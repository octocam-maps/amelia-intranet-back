"""
Caso de uso: crear una solicitud de ausencia.

Reglas de negocio (docs/fase-0-esquema-datos.md § 003_hr_core):
- `days_count` se calcula excluyendo fines de semana y festivos vigentes en
  el rango ("laborables, excluye finde/festivos"). Si el rango no tiene
  NINGÚN día laborable, se rechaza.
- Si el tipo `affects_balance=True`, se exige saldo disponible
  (`entitled - used - pending >= days_count`) — la baja médica
  (`affects_balance=False`) queda fuera de esta validación a propósito (ver
  `010_absence_types_defaults.sql`).
- La solicitud nace en `pending` y SUMA a `pending_days` del saldo — el
  contador en tiempo real del frontend refleja esto de inmediato, antes de
  que el admin la revise. Se traslada a `used_days` (o se libera) al
  aprobar/rechazar (ver `ReviewAbsenceRequestUseCase`).

Pendiente/no confirmado: si el rango cruza de un año a otro, el saldo
afectado es el del año de `start_date` — RRHH no ha confirmado la política
de prorrateo entre años (cuestionario pendiente, ver README).
"""

from datetime import date, timedelta
from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import AbsenceRequest
from ...domain.errors import (
    AbsenceRequestOverlapError,
    AbsenceTypeNotFoundError,
    InsufficientBalanceError,
    InvalidDateRangeError,
)
from ...domain.ports import IAbsenceRepository


class CreateAbsenceRequestUseCase:
    def __init__(self, repository: IAbsenceRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        self._notify = notify  # opcional — ver ReviewAbsenceRequestUseCase

    async def execute(
        self,
        *,
        user_id: str,
        absence_type_id: str,
        start_date: date,
        end_date: date,
        reason: Optional[str],
    ) -> AbsenceRequest:
        if end_date < start_date:
            raise InvalidDateRangeError("La fecha de fin no puede ser anterior a la de inicio.")

        # Anti-solape (bug real, auditoría QA): sin esto, nada impedía crear
        # dos solicitudes `pending`/`approved` del mismo usuario para fechas
        # que se pisan. Granularidad DEFAULT: se bloquea el solape contra
        # CUALQUIER tipo de ausencia del usuario, no solo el mismo
        # `absence_type_id` — pendiente de confirmar con RRHH si dos tipos
        # distintos (p.ej. "vacaciones" y "asuntos propios") deberían poder
        # coexistir el mismo día (ver `AbsenceRequestOverlapError`).
        overlapping = await self._repository.list_overlapping_requests(
            user_id, start_date=start_date, end_date=end_date
        )
        if overlapping:
            raise AbsenceRequestOverlapError(
                "Ya tienes una solicitud de ausencia pendiente o aprobada "
                "que solapa con estas fechas."
            )

        absence_type = await self._repository.find_type_by_id(absence_type_id)
        if absence_type is None:
            raise AbsenceTypeNotFoundError("El tipo de ausencia no existe.")

        days_count = await self._count_business_days(start_date, end_date)
        if days_count <= 0:
            raise InvalidDateRangeError(
                "El rango elegido no tiene ningún día laborable (solo fines de semana/festivos)."
            )

        year = start_date.year
        if absence_type.affects_balance:
            # Se asegura la fila de saldo (upsert) y LUEGO se reserva en un
            # único UPDATE condicionado al saldo disponible EN LA QUERY —
            # RACE-1 (auditoría QA Fase 3): comprobar el saldo en memoria y
            # escribir el ajuste en una query aparte permite que dos
            # solicitudes concurrentes del mismo usuario/tipo/año lean ambas
            # "saldo suficiente" y las dos reserven, provocando overdraft.
            # `try_reserve_balance` devuelve False si, en el momento del
            # commit, el saldo ya no cubre `days_count`.
            await self._repository.get_or_create_balance(user_id, absence_type_id, year)
            reserved = await self._repository.try_reserve_balance(
                user_id, absence_type_id, year, pending_delta=days_count
            )
            if not reserved:
                raise InsufficientBalanceError(
                    f"Saldo insuficiente para solicitar {days_count} día(s)."
                )

        request = await self._repository.create_request(
            user_id=user_id,
            absence_type_id=absence_type_id,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=reason,
        )

        if self._notify is not None:
            await self._notify.notify_admins(
                type="absence_requested",
                title="Nueva solicitud de ausencia",
                data={"request_id": request.id, "url": "/ausencias"},
            )

        return request

    async def _count_business_days(self, start_date: date, end_date: date) -> float:
        holidays = set(await self._repository.list_holiday_dates(start_date, end_date))
        count = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5 and current not in holidays:
                count += 1
            current += timedelta(days=1)
        return float(count)
