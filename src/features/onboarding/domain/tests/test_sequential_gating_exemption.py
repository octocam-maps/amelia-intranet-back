"""
El ADMINISTRADOR está exento del bloqueo secuencial del onboarding.

Reglas PURAS: sin BD y sin casos de uso. Lo que se fija aquí es que la exención
sea UNA sola, consultada por las tres puertas —el estado que se devuelve, el
rechazo del POST y el candado de la cascada de manuales—, porque el fallo que
importa no es que una puerta esté mal: es que dos digan cosas distintas.
"""

import pytest

from src.shared.auth.roles import ALL_ROLES, RoleCode
from src.features.onboarding.domain.entities import OnboardingDocument, OnboardingProgress
from src.features.onboarding.domain.errors import ManualLockedError, StepLockedError, StepNotOperableError
from src.features.onboarding.domain.policy import (
    ensure_manual_unlocked,
    ensure_step_operable,
    is_exempt_from_sequential_gating,
    resolve_progress_for_role,
    resolve_status_for_role,
    resolve_step_documents,
)

ADMIN = RoleCode.ADMINISTRADOR.value
EMPLEADO = RoleCode.EMPLEADO.value
BECARIO = RoleCode.BECARIO.value
SOCIO = RoleCode.SOCIO.value
EXTERNO = RoleCode.EXTERNO_INVITADO.value

SUBJECT_TO_GATING = [EMPLEADO, BECARIO, SOCIO, EXTERNO]


def progress(status: str) -> OnboardingProgress:
    return OnboardingProgress(
        id="p1",
        user_id="u1",
        step_id="s1",
        status=status,
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )


def manual(doc_id: str, order: int) -> OnboardingDocument:
    return OnboardingDocument(
        id=doc_id,
        kind="manual",
        title=doc_id,
        version=1,
        content_hash="x" * 64,
        storage_ref=f"/manuales/{doc_id}.pdf",
        is_active=True,
        display_order=order,
    )


BOTH = [manual("clickup", 1), manual("hincator", 2)]


class TestIsExemptFromSequentialGating:
    def test_only_the_administrator_is_exempt(self):
        assert is_exempt_from_sequential_gating(ADMIN) is True
        for role in SUBJECT_TO_GATING:
            assert is_exempt_from_sequential_gating(role) is False, role

    def test_every_known_role_gets_an_answer(self):
        # Un rol nuevo añadido a ALL_ROLES sin pasar por aquí quedaría sujeto al
        # bloqueo por defecto, que es el lado seguro — este test lo documenta en
        # vez de dejarlo a la interpretación de quien lo lea.
        for role in ALL_ROLES:
            assert isinstance(is_exempt_from_sequential_gating(role.value), bool)

    def test_an_unknown_role_is_not_exempt(self):
        # Defensa: un valor que no es un rol del sistema nunca abre candados.
        assert is_exempt_from_sequential_gating("supervisor") is False
        assert is_exempt_from_sequential_gating("") is False


class TestResolveStatusForRole:
    def test_locked_becomes_available_for_the_administrator(self):
        assert resolve_status_for_role("locked", ADMIN) == "available"

    def test_locked_stays_locked_for_everyone_else(self):
        for role in SUBJECT_TO_GATING:
            assert resolve_status_for_role("locked", role) == "locked", role

    @pytest.mark.parametrize("status", ["available", "in_progress", "completed"])
    def test_no_other_status_is_touched(self, status):
        # La exención abre lo bloqueado; NO convierte un paso completado en
        # pendiente ni reabre el cuestionario ya aprobado del administrador.
        assert resolve_status_for_role(status, ADMIN) == status
        assert resolve_status_for_role(status, EMPLEADO) == status


class TestResolveProgressForRole:
    def test_the_administrator_sees_a_locked_step_as_available(self):
        assert resolve_progress_for_role(progress("locked"), ADMIN).status == "available"

    def test_it_does_not_mutate_the_original(self):
        # La fila de la BD sigue diciendo `locked`: si mañana deja de ser
        # administrador, su progreso vuelve a bloquearse sin migrar nada.
        original = progress("locked")
        resolve_progress_for_role(original, ADMIN)
        assert original.status == "locked"

    def test_it_returns_the_same_object_when_there_is_nothing_to_change(self):
        original = progress("available")
        assert resolve_progress_for_role(original, EMPLEADO) is original


class TestEnsureStepOperable:
    def test_the_administrator_can_operate_a_locked_step(self):
        assert ensure_step_operable(progress("locked"), ADMIN).status == "locked"

    def test_everyone_else_is_rejected_on_a_locked_step(self):
        for role in SUBJECT_TO_GATING:
            with pytest.raises(StepLockedError):
                ensure_step_operable(progress("locked"), role)

    def test_a_completed_step_is_not_repeatable_not_even_for_the_administrator(self):
        # La exención es de ORDEN, no un permiso para rehacer pasos: si el admin
        # pudiera reenviar el cuestionario ya aprobado, `MAX_QUIZ_ATTEMPTS`
        # dejaría de significar nada para ella.
        with pytest.raises(StepNotOperableError):
            ensure_step_operable(progress("completed"), ADMIN)

    def test_a_missing_progress_row_blocks_everyone(self):
        # Sin fila no hay paso que operar. Fabricarla aquí esconderría un fallo
        # de `ensure_progress_initialized`.
        for role in [ADMIN, *SUBJECT_TO_GATING]:
            with pytest.raises(StepLockedError):
                ensure_step_operable(None, role)


class TestManualsCascadeExemption:
    def test_the_administrator_can_confirm_the_second_manual_first(self):
        assert ensure_manual_unlocked(BOTH, set(), "hincator", ADMIN).id == "hincator"

    def test_an_employee_cannot(self):
        with pytest.raises(ManualLockedError):
            ensure_manual_unlocked(BOTH, set(), "hincator", EMPLEADO)

    def test_no_manual_is_locked_for_the_administrator(self):
        for item in resolve_step_documents(BOTH, set(), ADMIN):
            assert item.locked is False

    def test_a_manual_that_does_not_exist_is_still_rejected(self):
        # Lo que se relaja es el ORDEN, no la existencia: un id inventado sigue
        # siendo un error para el administrador.
        with pytest.raises(ManualLockedError):
            ensure_manual_unlocked(BOTH, set(), "inventado", ADMIN)

    def test_the_ui_lock_and_the_post_agree_for_every_role(self):
        # EL test que importa. Recorre los dos lados de las tres puertas: lo que
        # `resolve_step_documents` pinta con candado tiene que ser EXACTAMENTE lo
        # que `ensure_manual_unlocked` rechaza. Si divergieran, el administrador
        # vería un botón habilitado que responde 422 — o al contrario.
        for role in [ADMIN, *SUBJECT_TO_GATING]:
            for acknowledged in [set(), {"clickup"}, {"hincator"}, {"clickup", "hincator"}]:
                for item in resolve_step_documents(BOTH, acknowledged, role):
                    if item.locked:
                        with pytest.raises(ManualLockedError):
                            ensure_manual_unlocked(
                                BOTH, acknowledged, item.document.id, role
                            )
                    else:
                        assert (
                            ensure_manual_unlocked(
                                BOTH, acknowledged, item.document.id, role
                            ).id
                            == item.document.id
                        )
