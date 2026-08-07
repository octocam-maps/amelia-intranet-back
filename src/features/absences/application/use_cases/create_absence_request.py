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
- Autoaprobación del administrador (B-1c, docs/permisos-roles.md § Ausencias):
  cuando `requester_role == "administrador"`, la solicitud nace DIRECTAMENTE
  en `approved` y consume `used_days` (no `pending_days`) — nunca pasa por la
  bandeja de revisión manual. Todas las validaciones previas (solape, saldo,
  días laborables) se mantienen intactas: la autoaprobación solo salta el
  paso de revisión, no las reglas de negocio.

Pendiente/no confirmado: si el rango cruza de un año a otro, el saldo
afectado es el del año de `start_date` — RRHH no ha confirmado la política
de prorrateo entre años (cuestionario pendiente, ver README).
"""

from datetime import date, timedelta
from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase
from src.shared.auth.roles import RoleCode

from ...domain.entities import AbsenceRequest
from ...domain.errors import (
    AbsenceRequestOverlapError,
    AbsenceTypeNotFoundError,
    InsufficientBalanceError,
    InsufficientCompensationBalanceError,
    InvalidDateRangeError,
)
from ...domain.ports import IAbsenceRepository, ICompensationBalanceProvider

_AUTO_APPROVAL_NOTE = "Autoaprobado: la solicitud fue creada por el administrador."

# Tipo de ausencia con el que el técnico disfruta sus horas extra (catálogo
# v1.1 de RRHH, migración 032). Su cupo NO vive en `absence_balances`, así que
# se valida aparte — ver `ICompensationBalanceProvider`.
COMPENSATION_ABSENCE_CODE = "descanso_horas_extra"

# 8 h = 1 día (decisión del team-lead del 2026-08-06). Duplicado a propósito
# de `time_clock.domain.policy.MINUTES_PER_COMPENSATION_DAY`: importarlo aquí
# acoplaría `absences.application` al dominio de otro feature. Si cambia, hay
# un test que compara ambos y falla.
MINUTES_PER_COMPENSATION_DAY = 480


class CreateAbsenceRequestUseCase:
    def __init__(
        self,
        repository: IAbsenceRepository,
        notify: Optional[NotifyUseCase] = None,
        compensation_balance: Optional[ICompensationBalanceProvider] = None,
    ):
        self._repository = repository
        self._notify = notify  # opcional — ver ReviewAbsenceRequestUseCase
        # Opcional por el mismo motivo que `notify`: los tests que no tocan
        # descanso compensatorio no tienen que construirlo.
        self._compensation_balance = compensation_balance

    async def execute(
        self,
        *,
        user_id: str,
        requester_role: str,
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

        # Autoaprobación del administrador (B-1c): su propia solicitud no
        # pasa por `pending` — consume `used_days` directamente en vez de
        # reservar `pending_days`, para no contabilizar el mismo día dos
        # veces (reservado Y usado) cuando nunca hay una revisión manual que
        # traslade uno al otro.
        is_self_approved = requester_role == RoleCode.ADMINISTRADOR

        year = start_date.year

        # Descanso por horas extra: su cupo NO está en `absence_balances`
        # (`affects_balance = FALSE`, para no descontar de vacaciones), así que
        # sin esta comprobación se podrían pedir 40 días por 2 horas extra.
        if absence_type.code == COMPENSATION_ABSENCE_CODE:
            await self._validate_compensation_balance(user_id, year, days_count)

        if absence_type.affects_balance:
            # Se asegura la fila de saldo (upsert) y LUEGO se ajusta en un
            # único UPDATE condicionado al saldo disponible EN LA QUERY —
            # RACE-1 (auditoría QA Fase 3): comprobar el saldo en memoria y
            # escribir el ajuste en una query aparte permite que dos
            # solicitudes concurrentes del mismo usuario/tipo/año lean ambas
            # "saldo suficiente" y las dos reserven, provocando overdraft.
            # `try_reserve_balance`/`try_consume_balance` devuelven False si,
            # en el momento del commit, el saldo ya no cubre `days_count`.
            await self._repository.get_or_create_balance(user_id, absence_type_id, year)
            if is_self_approved:
                consumed = await self._repository.try_consume_balance(
                    user_id, absence_type_id, year, used_delta=days_count
                )
                if not consumed:
                    raise InsufficientBalanceError(
                        f"Saldo insuficiente para solicitar {days_count} día(s)."
                    )
            else:
                reserved = await self._repository.try_reserve_balance(
                    user_id, absence_type_id, year, pending_delta=days_count
                )
                if not reserved:
                    raise InsufficientBalanceError(
                        f"Saldo insuficiente para solicitar {days_count} día(s)."
                    )

        if is_self_approved:
            request = await self._repository.create_approved_request(
                user_id=user_id,
                absence_type_id=absence_type_id,
                start_date=start_date,
                end_date=end_date,
                days_count=days_count,
                reason=reason,
                review_note=_AUTO_APPROVAL_NOTE,
            )
        else:
            request = await self._repository.create_request(
                user_id=user_id,
                absence_type_id=absence_type_id,
                start_date=start_date,
                end_date=end_date,
                days_count=days_count,
                reason=reason,
            )

        # La bandeja de pendientes no aplica a una solicitud que nace ya
        # aprobada — no tiene sentido notificar al admin de "nueva solicitud"
        # sobre algo que ya resolvió él mismo al crearla.
        if self._notify is not None and not is_self_approved:
            await self._notify.notify_admins(
                type="absence_requested",
                title="Nueva solicitud de ausencia",
                data={"request_id": request.id, "url": "/ausencias"},
            )

        return request

    async def _validate_compensation_balance(
        self, user_id: str, year: int, days_count: float
    ) -> None:
        if self._compensation_balance is None:
            # Sin proveedor cableado no se puede saber el saldo. Se DENIEGA en
            # vez de dejar pasar: un fallo de wiring no debe traducirse en
            # descansos sin respaldo, que es lo que ocurriría con la política
            # contraria y nadie se enteraría hasta el recuento anual.
            raise InsufficientCompensationBalanceError(
                "No se ha podido comprobar tu saldo de horas extra. Inténtalo más tarde."
            )

        available = await self._compensation_balance.available_minutes(user_id, year)
        requested = int(days_count * MINUTES_PER_COMPENSATION_DAY)
        if requested > available:
            raise InsufficientCompensationBalanceError(
                f"Tu saldo de compensación ({_format_hours(available)}) no cubre "
                f"los {days_count:g} día(s) solicitados."
            )

    async def _count_business_days(self, start_date: date, end_date: date) -> float:
        holidays = set(await self._repository.list_holiday_dates(start_date, end_date))
        count = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5 and current not in holidays:
                count += 1
            current += timedelta(days=1)
        return float(count)


def _format_hours(minutes: int) -> str:
    """"12h 30m" en vez de "750 minutos": el técnico piensa su saldo en horas,
    igual que lo lee en la tarjeta del dashboard y en el Excel."""
    return f"{minutes // 60}h {minutes % 60:02d}m"
