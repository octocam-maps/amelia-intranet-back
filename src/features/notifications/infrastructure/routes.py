"""
Router de `/notifications`: notificaciones in-app. Cada usuario autenticado
—cualquiera de los tres roles— lee y marca SOLO las suyas: el `user_id` del
JWT decide el alcance en el backend en todas las queries, nunca un
parámetro de la request (RGPD, docs/CLAUDE.md § alcance de datos).

`POST /jobs/run` es exclusivo del admin y ejecuta a demanda la detección de
los eventos por-tiempo (cumpleaños, aniversario, fichaje sin salida). El
cron real que la dispare a diario es tarea de ops — aquí solo se deja el
endpoint protegido.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role
from src.shared.errors.base import ValidationError

from ..application.use_cases.get_unread_count import GetUnreadCountUseCase
from ..application.use_cases.list_notifications import ListNotificationsUseCase
from ..application.use_cases.mark_all_notifications_read import MarkAllNotificationsReadUseCase
from ..application.use_cases.mark_notification_read import MarkNotificationReadUseCase
from ..application.use_cases.run_clock_out_notification_job import (
    RunClockOutNotificationJobUseCase,
)
from ..application.use_cases.run_daily_notification_job import RunDailyNotificationJobUseCase
from .dependencies import (
    get_list_notifications_use_case,
    get_mark_all_notifications_read_use_case,
    get_mark_notification_read_use_case,
    get_run_clock_out_notification_job_use_case,
    get_run_daily_notification_job_use_case,
    get_unread_count_use_case,
)
from .mappers import page_to_dto
from .schemas import (
    MarkAllReadResponseDTO,
    NotificationListDTO,
    RunNotificationJobResponseDTO,
    UnreadCountDTO,
)

_ANY_AUTHENTICATED_ROLE = ("administrador", "empleado", "externo_invitado")


def create_notifications_router() -> APIRouter:
    router = APIRouter(prefix="/notifications", tags=["notifications"])

    @router.get("", response_model=NotificationListDTO)
    async def list_notifications(
        limit: int = Query(20, ge=1, le=100),
        before: Optional[datetime] = Query(None),
        current_user: dict = Depends(require_role(*_ANY_AUTHENTICATED_ROLE)),
        use_case: ListNotificationsUseCase = Depends(get_list_notifications_use_case),
    ):
        page = await use_case.execute(user_id=current_user["sub"], limit=limit, before=before)
        return page_to_dto(page)

    @router.get("/unread-count", response_model=UnreadCountDTO)
    async def get_unread_count(
        current_user: dict = Depends(require_role(*_ANY_AUTHENTICATED_ROLE)),
        use_case: GetUnreadCountUseCase = Depends(get_unread_count_use_case),
    ):
        count = await use_case.execute(user_id=current_user["sub"])
        return UnreadCountDTO(count=count)

    @router.patch("/read-all", response_model=MarkAllReadResponseDTO)
    async def mark_all_read(
        current_user: dict = Depends(require_role(*_ANY_AUTHENTICATED_ROLE)),
        use_case: MarkAllNotificationsReadUseCase = Depends(
            get_mark_all_notifications_read_use_case
        ),
    ):
        updated = await use_case.execute(user_id=current_user["sub"])
        return MarkAllReadResponseDTO(updated=updated)

    @router.patch("/{notification_id}/read", status_code=204)
    async def mark_read(
        notification_id: str,
        current_user: dict = Depends(require_role(*_ANY_AUTHENTICATED_ROLE)),
        use_case: MarkNotificationReadUseCase = Depends(get_mark_notification_read_use_case),
    ):
        """404 si la notificación no existe O es de otro usuario — el
        repositorio condiciona el UPDATE a `user_id` en la propia query
        (RGPD, ver `NotificationNotFoundError`)."""
        await use_case.execute(notification_id=notification_id, user_id=current_user["sub"])

    @router.post("/jobs/run", response_model=RunNotificationJobResponseDTO)
    async def run_job(
        job: str = Query(..., pattern="^(daily|clock_out)$"),
        current_user: dict = Depends(require_role("administrador")),
        daily_use_case: RunDailyNotificationJobUseCase = Depends(
            get_run_daily_notification_job_use_case
        ),
        clock_out_use_case: RunClockOutNotificationJobUseCase = Depends(
            get_run_clock_out_notification_job_use_case
        ),
    ):
        """Ejecución a demanda de la detección por-tiempo — pensado para un
        cron de ops (`curl -X POST .../notifications/jobs/run?job=daily`),
        no hay scheduler montado en este servicio."""
        if job == "daily":
            result = await daily_use_case.execute()
        elif job == "clock_out":
            result = await clock_out_use_case.execute()
        else:
            raise ValidationError(f"job desconocido: {job}")
        return RunNotificationJobResponseDTO(job=job, result=result)

    return router
