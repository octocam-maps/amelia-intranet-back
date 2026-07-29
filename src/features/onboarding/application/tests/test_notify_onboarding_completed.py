"""El aviso `onboarding_completed` se dispara por ESTADO (todos los pasos
aplicables al rol completados), no porque se haya completado un paso concreto.

Esta suite es la red que faltaba: el código anterior notificaba desde
`CompleteProfileUseCase` asumiendo que el perfil era el paso 5 y último. La
reordenación de v1.1 (`033_onboarding_steps_reorder_v11.sql`) movió el perfil
al 4 y la documentación firmada al 5, y con la lógica vieja RRHH habría
recibido "onboarding completado" con la documentación todavía sin subir.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.features.onboarding.application.use_cases.notify_onboarding_completed import (
    NotifyOnboardingCompletedUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, QUIZ_STEP, SIGNATURE_STEP, VIDEO_STEP

NOW = datetime(2026, 7, 29, 10, 30, tzinfo=timezone.utc)


class _RecordingNotify:
    def __init__(self):
        self.admin_calls: list[dict] = []

    async def notify_admins(self, **kwargs):
        self.admin_calls.append(kwargs)


def _completed(step_id: str, *, data: dict | None = None, minutes: int = 0):
    return OnboardingProgress(
        id=f"progress-{step_id}",
        user_id="user-1",
        step_id=step_id,
        status="completed",
        progress_pct=100,
        data=data or {},
        started_at=NOW,
        completed_at=NOW + timedelta(minutes=minutes),
    )


def _pending(step_id: str, status: str = "available"):
    return OnboardingProgress(
        id=f"progress-{step_id}",
        user_id="user-1",
        step_id=step_id,
        status=status,
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )


def _repository(*progress: OnboardingProgress) -> FakeOnboardingRepository:
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS,
        users={"user-1": {"full_name": "Sandra Ramírez", "email": "s@x.es", "role": "empleado"}},
    )
    for p in progress:
        repository.progress[("user-1", p.step_id)] = p
    return repository


@pytest.mark.asyncio
async def test_no_notifica_si_falta_la_documentacion_aunque_el_perfil_este_hecho():
    """El caso exacto que rompía la lógica vieja: perfil completado pero
    documentación pendiente. RRHH NO debe recibir "onboarding completado"."""
    repository = _repository(
        _completed(VIDEO_STEP.id),
        _completed(QUIZ_STEP.id, data={"score": 75.0}),
        _completed(MANUAL_STEP.id),
        _completed("step-profile"),
        _pending(SIGNATURE_STEP.id),
    )
    notify = _RecordingNotify()

    notificado = await NotifyOnboardingCompletedUseCase(repository, notify).execute(
        user_id="user-1", role="empleado"
    )

    assert notificado is False
    assert notify.admin_calls == []


@pytest.mark.asyncio
async def test_notifica_cuando_la_documentacion_cierra_el_flujo():
    repository = _repository(
        _completed(VIDEO_STEP.id),
        _completed(QUIZ_STEP.id, data={"score": 75.0}),
        _completed(MANUAL_STEP.id),
        _completed("step-profile"),
        _completed(SIGNATURE_STEP.id, data={"employee_document_id": "doc-1"}, minutes=5),
    )
    notify = _RecordingNotify()

    notificado = await NotifyOnboardingCompletedUseCase(repository, notify).execute(
        user_id="user-1", role="empleado"
    )

    assert notificado is True
    call = notify.admin_calls[0]
    assert call["type"] == "onboarding_completed"
    assert call["data"]["full_name"] == "Sandra Ramírez"
    assert call["data"]["quiz_score"] == 75.0
    assert call["data"]["documents_signed"] is True
    # Fecha de finalización = el `completed_at` más tardío de TODOS los pasos,
    # no el del primero que se encuentre.
    assert call["data"]["completed_at"] == (NOW + timedelta(minutes=5)).isoformat()


@pytest.mark.asyncio
async def test_el_externo_invitado_termina_con_solo_video_y_manual():
    """Su onboarding parcial no incluye cuestionario, perfil ni documentación
    (`steps_applicable_to_role`), así que confirmar los manuales lo cierra —
    compararlo contra los 5 pasos lo dejaría eternamente sin terminar."""
    repository = _repository(_completed(VIDEO_STEP.id), _completed(MANUAL_STEP.id))
    notify = _RecordingNotify()

    notificado = await NotifyOnboardingCompletedUseCase(repository, notify).execute(
        user_id="user-1", role="externo_invitado"
    )

    assert notificado is True
    # Nunca hubo cuestionario ni documentación que firmar: el copy lo refleja
    # en vez de inventarse una nota.
    assert notify.admin_calls[0]["data"]["quiz_score"] is None
    assert notify.admin_calls[0]["data"]["documents_signed"] is False
    assert "N/D" in notify.admin_calls[0]["body"]


@pytest.mark.asyncio
async def test_un_empleado_con_solo_video_y_manual_no_ha_terminado():
    """Mismo progreso que el externo del test anterior, pero con rol empleado:
    a él le faltan cuestionario, perfil y documentación. El rol es lo que
    decide el catálogo aplicable, no el progreso existente."""
    repository = _repository(
        _completed(VIDEO_STEP.id),
        _completed(MANUAL_STEP.id),
        _pending("step-profile", "locked"),
        _pending(SIGNATURE_STEP.id, "locked"),
    )
    notify = _RecordingNotify()

    notificado = await NotifyOnboardingCompletedUseCase(repository, notify).execute(
        user_id="user-1", role="empleado"
    )

    assert notificado is False
    assert notify.admin_calls == []


@pytest.mark.asyncio
async def test_un_catalogo_vacio_no_cuenta_como_onboarding_terminado():
    """Sin pasos activos no hay nada completado — es un catálogo mal cargado,
    y notificar ahí sería un falso positivo."""
    repository = FakeOnboardingRepository(steps=[], users={"user-1": {"full_name": "X", "email": "x@x.es", "role": "empleado"}})
    notify = _RecordingNotify()

    notificado = await NotifyOnboardingCompletedUseCase(repository, notify).execute(
        user_id="user-1", role="empleado"
    )

    assert notificado is False
    assert notify.admin_calls == []


@pytest.mark.asyncio
async def test_sin_nombre_de_usuario_el_aviso_no_revienta():
    """Rama defensiva: si el usuario no aparece en `users` (borrado en medio),
    el aviso sale con un genérico en vez de con `None` interpolado."""
    repository = _repository(
        _completed(VIDEO_STEP.id),
        _completed(QUIZ_STEP.id, data={"score": 100.0}),
        _completed(MANUAL_STEP.id),
        _completed("step-profile"),
        _completed(SIGNATURE_STEP.id),
    )
    repository.users.clear()
    notify = _RecordingNotify()

    await NotifyOnboardingCompletedUseCase(repository, notify).execute(
        user_id="user-1", role="empleado"
    )

    assert "None" not in notify.admin_calls[0]["title"]
    assert notify.admin_calls[0]["data"]["full_name"] == "Un trabajador"
