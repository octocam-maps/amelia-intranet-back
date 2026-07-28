"""
Caso de uso: job por-tiempo — recordatorio diario de fichaje (RF-A4,
docs/requerimientos-amelia-intranet.pdf §6). Clase HERMANA de
`RunClockOutNotificationJobUseCase` (mismo patrón: proyección de solo
lectura + idempotencia por `data` JSONB), NO un método dentro de
`RunDailyNotificationJobUseCase` — cumpleaños/aniversario y "quién no
fichó" son proyecciones de tablas distintas sin relación entre sí
(decisión de design, sdd/ampliacion-v11-rrhh/design § RF-A4 · Wiring).
"""

from datetime import date

from src.shared.utils.timezone import today_in_madrid

from ...domain.ports import INotificationRepository
from .notify import NotifyUseCase


class RunClockInReminderJobUseCase:
    def __init__(self, repository: INotificationRepository, notify: NotifyUseCase):
        self._repository = repository
        self._notify = notify

    async def execute(self, *, work_date: date | None = None) -> dict:
        # A diferencia de `clock_out` (que revisa AYER), este job evalúa el
        # día EN CURSO (RF-A4.6) — el recordatorio es "todavía no fichaste
        # HOY", no una jornada ya cerrada.
        #
        # LOGIC-1 (auditoría QA, severidad MEDIA): `today_in_madrid()`, NUNCA
        # `date.today()` — el proceso corre con `TZ=UTC` (ver
        # `src/shared/utils/timezone.py`, el ÚNICO punto que decide "qué día
        # es hoy"). Entre las 22:00 y las 24:00 UTC, Madrid ya está en el día
        # siguiente: con `date.today()` el `weekday()` salía mal en el
        # límite del fin de semana y el mensaje citaba una fecha que para
        # España ya había cerrado.
        target_date = work_date or today_in_madrid()

        # L-V únicamente (RF-A4): sábado/domingo no generan recordatorio,
        # sin tocar el repositorio — un fin de semana nunca tiene plantilla
        # "pendiente de fichar" que tenga sentido notificar.
        if target_date.weekday() >= 5:
            return {"work_date": target_date.isoformat(), "users_notified": 0}

        repository = self._repository
        work_date_iso = target_date.isoformat()
        user_ids = await repository.list_user_ids_pending_clock_in(target_date)

        users_notified = 0
        for user_id in user_ids:
            # Idempotencia (mismo criterio que `clock_out`): reejecutar el
            # job el mismo día para el mismo `work_date` no debe duplicar el
            # aviso ni reenviar el email.
            already_notified = await repository.exists_recipient_notification_with_data(
                user_id=user_id,
                type="clock_in_reminder",
                data_key="work_date",
                data_value=work_date_iso,
            )
            if already_notified:
                continue
            await self._notify.execute(
                recipient_ids=[user_id],
                type="clock_in_reminder",
                title="Registra tu jornada",
                body=f"Todavía no has fichado hoy, {target_date.strftime('%d/%m/%Y')}.",
                data={"work_date": work_date_iso, "url": "/control-horario"},
            )
            users_notified += 1

        return {"work_date": work_date_iso, "users_notified": users_notified}
