"""
Caso de uso: job por-tiempo diario — cumpleaños y aniversarios laborales
(docs/requerimientos-amelia-intranet.pdf §6). Pensado para un cron externo;
aquí solo vive la detección + el disparo — el cron real es tarea de ops (ver
`POST /notifications/jobs/run?job=daily` en `infrastructure/routes.py`).
"""

from datetime import date
from typing import Optional

from ...domain.ports import INotificationRepository
from .notify import NotifyUseCase

# Cumpleaños/aniversario son eventos sociales del equipo — se asume la misma
# audiencia que "Inicio"/anuncios (toda la plantilla activa salvo
# externo_invitado, que no tiene dashboard, docs/permisos-roles.md § Inicio: ❌).
_TEAM_EXCLUDED_ROLE = "externo_invitado"


class RunDailyNotificationJobUseCase:
    def __init__(self, repository: INotificationRepository, notify: NotifyUseCase):
        self._repository = repository
        self._notify = notify

    async def execute(self, *, today: Optional[date] = None) -> dict:
        today = today or date.today()

        birthdays_notified = 0
        birthday_users = await self._repository.list_birthday_user_ids(
            month=today.month, day=today.day
        )
        for user_id, full_name in birthday_users:
            # Idempotencia (bug real, auditoría QA): reejecutar el job el
            # mismo día no debe duplicar el lote de notificaciones a todo el
            # equipo ni reenviar el email. Se comprueba por el SUJETO del
            # cumpleaños (`data['user_id']`), no por destinatario — el lote
            # completo se genera de una sola vez o no se genera.
            already_notified = await self._repository.exists_event_notification_with_data(
                type="birthday", data_key="user_id", data_value=user_id
            )
            if already_notified:
                continue
            await self._notify.notify_team_excluding_role(
                _TEAM_EXCLUDED_ROLE,
                type="birthday",
                title=f"¡Hoy es el cumpleaños de {full_name}!",
                data={"user_id": user_id, "url": "/equipo"},
                # El cumpleañero no recibe su propia notificación en tercera
                # persona ("¡Hoy es el cumpleaños de Ana!" no tiene sentido
                # si Ana es quien la lee) — bug real, auditoría QA.
                exclude_user_ids=[user_id],
            )
            birthdays_notified += 1

        anniversaries_notified = 0
        anniversary_users = await self._repository.list_anniversary_users(
            month=today.month, day=today.day
        )
        for user_id, years in anniversary_users:
            # Idempotencia: el destinatario ES el sujeto del aniversario, así
            # que basta comprobar por destinatario + `years` — `years` es
            # estable durante todo el día de hoy y distinto de cualquier
            # aniversario anterior del mismo usuario (aumenta cada año).
            already_notified = await self._repository.exists_recipient_notification_with_data(
                user_id=user_id, type="work_anniversary", data_key="years", data_value=str(years)
            )
            if already_notified:
                continue
            plural = "s" if years != 1 else ""
            await self._notify.execute(
                recipient_ids=[user_id],
                type="work_anniversary",
                title=f"¡Hoy cumples {years} año{plural} en Amelia!",
                data={"years": years, "url": "/perfil"},
            )
            anniversaries_notified += 1

        return {
            "birthdays_notified": birthdays_notified,
            "anniversaries_notified": anniversaries_notified,
        }
