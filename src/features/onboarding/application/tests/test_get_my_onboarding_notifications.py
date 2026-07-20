"""Cableado del disparador `document_pending_signature` — en la PRIMERA
visita a `GET /onboarding/me` de un rol con paso de firma, se avisa al
trabajador de que le queda un documento pendiente de firmar (RF §6).
`NotifyUseCase.execute` en sí ya tiene su propia suite en
`features/notifications`; aquí solo se verifica que `GetMyOnboardingUseCase`
la invoca en el momento y con los datos correctos."""

import pytest

from src.features.onboarding.application.use_cases.get_my_onboarding import (
    GetMyOnboardingUseCase,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, SIGNATURE_STEP


class _RecordingNotify:
    def __init__(self, *, already_notified: bool = False):
        self.calls: list[dict] = []
        self._already_notified = already_notified

    async def already_notified_recipient(self, **kwargs):
        return self._already_notified

    async def execute(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_first_visit_notifies_pending_signature_for_a_full_onboarding_role():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    notify = _RecordingNotify()
    use_case = GetMyOnboardingUseCase(repository, notify)

    await use_case.execute(user_id="user-1", role="empleado")

    assert len(notify.calls) == 1
    call = notify.calls[0]
    assert call["type"] == "document_pending_signature"
    assert call["recipient_ids"] == ["user-1"]
    assert call["data"]["step_id"] == SIGNATURE_STEP.id


@pytest.mark.asyncio
async def test_second_visit_does_not_notify_again():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    notify = _RecordingNotify()
    use_case = GetMyOnboardingUseCase(repository, notify)

    await use_case.execute(user_id="user-1", role="empleado")
    await use_case.execute(user_id="user-1", role="empleado")

    assert len(notify.calls) == 1


@pytest.mark.asyncio
async def test_external_guest_never_triggers_the_signature_notification():
    """El externo-invitado (onboarding parcial, sin firma) no tiene ningún
    paso `signature` en su catálogo aplicable — nunca dispara este aviso."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    notify = _RecordingNotify()
    use_case = GetMyOnboardingUseCase(repository, notify)

    await use_case.execute(user_id="guest-1", role="externo_invitado")

    assert notify.calls == []


@pytest.mark.asyncio
async def test_race_between_two_first_visits_is_guarded_by_the_idempotency_check():
    """Dos "primeras visitas" casi simultáneas (dos pestañas) ya ven
    `already_notified=True` en la segunda gracias al chequeo explícito
    contra el repositorio de notificaciones."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    notify = _RecordingNotify(already_notified=True)
    use_case = GetMyOnboardingUseCase(repository, notify)

    await use_case.execute(user_id="user-1", role="empleado")

    assert notify.calls == []


@pytest.mark.asyncio
async def test_get_my_onboarding_without_a_notify_dependency_still_works():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    pairs = await use_case.execute(user_id="user-1", role="empleado")

    assert len(pairs) == len(ALL_STEPS)
