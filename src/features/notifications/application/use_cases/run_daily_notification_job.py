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
            await self._notify.notify_team_excluding_role(
                _TEAM_EXCLUDED_ROLE,
                type="birthday",
                title=f"¡Hoy es el cumpleaños de {full_name}!",
                data={"user_id": user_id, "url": "/equipo"},
            )
            birthdays_notified += 1

        anniversaries_notified = 0
        anniversary_users = await self._repository.list_anniversary_users(
            month=today.month, day=today.day
        )
        for user_id, years in anniversary_users:
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
