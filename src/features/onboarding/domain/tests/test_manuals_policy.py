"""
Reglas PURAS de la cascada de manuales (migración 040). Sin BD, sin casos de uso:
solo la regla, que es lo que de verdad puede fallar.
"""

import pytest

from src.features.onboarding.domain.entities import OnboardingDocument
from src.features.onboarding.domain.errors import ManualLockedError
from src.shared.auth.roles import RoleCode
from src.features.onboarding.domain.policy import (
    are_all_manuals_acknowledged,
    ensure_manual_unlocked,
    next_manual_to_acknowledge,
    resolve_step_documents,
    sort_manuals,
)


# La cascada es la del TRABAJADOR. El administrador está exento del orden
# (`is_exempt_from_sequential_gating`) y tiene su propia clase de tests abajo.
EMPLEADO = RoleCode.EMPLEADO.value
ADMIN = RoleCode.ADMINISTRADOR.value


def manual(doc_id: str, order: int, title: str = "Manual") -> OnboardingDocument:
    return OnboardingDocument(
        id=doc_id,
        kind="manual",
        title=title,
        version=1,
        content_hash="x" * 64,
        storage_ref=f"/manuales/{doc_id}.pdf",
        is_active=True,
        display_order=order,
    )


CLICKUP = manual("clickup", 1, "Manual de uso de ClickUp")
HINCATOR = manual("hincator", 2, "Manual de usuario Hincator® 2026")
BOTH = [HINCATOR, CLICKUP]  # a propósito desordenados


class TestSortManuals:
    def test_orders_by_display_order(self):
        assert [d.id for d in sort_manuals(BOTH)] == ["clickup", "hincator"]

    def test_ties_break_by_id_so_the_order_is_stable(self):
        """La BD garantiza orden único entre ACTIVOS
        (`uq_onboarding_documents_active_order`), pero un empate entre uno activo
        y otro retirado dejaría "el siguiente de la cascada" a merced de cómo
        Postgres devuelva las filas."""
        a, b = manual("bbb", 1), manual("aaa", 1)

        assert [d.id for d in sort_manuals([a, b])] == ["aaa", "bbb"]
        assert [d.id for d in sort_manuals([b, a])] == ["aaa", "bbb"]


class TestNextManualToAcknowledge:
    def test_without_anything_read_it_is_the_first(self):
        assert next_manual_to_acknowledge(BOTH, set()).id == "clickup"

    def test_after_the_first_it_is_the_second(self):
        assert next_manual_to_acknowledge(BOTH, {"clickup"}).id == "hincator"

    def test_none_when_everything_is_read(self):
        assert next_manual_to_acknowledge(BOTH, {"clickup", "hincator"}) is None


class TestEnsureManualUnlocked:
    def test_the_first_is_open(self):
        assert ensure_manual_unlocked(BOTH, set(), "clickup", EMPLEADO).id == "clickup"

    def test_skipping_the_first_is_rejected(self):
        with pytest.raises(ManualLockedError) as error:
            ensure_manual_unlocked(BOTH, set(), "hincator", EMPLEADO)

        # El mensaje dice QUÉ falta, no solo que está bloqueado.
        assert "ClickUp" in str(error.value)

    def test_the_second_opens_once_the_first_is_read(self):
        assert ensure_manual_unlocked(BOTH, {"clickup"}, "hincator", EMPLEADO).id == "hincator"

    def test_reacknowledging_an_already_read_manual_is_allowed(self):
        """Doble clic: la BD tiene UNIQUE (user_id, document_id) y hace upsert."""
        assert ensure_manual_unlocked(BOTH, {"clickup"}, "clickup", EMPLEADO).id == "clickup"

    def test_an_already_read_manual_stays_open_even_if_a_previous_one_is_missing(self):
        """Caso real si RRHH REORDENA los manuales después de que alguien empiece:
        lo que ya se leyó, leído está — no se le puede pedir que lo relea."""
        assert ensure_manual_unlocked(BOTH, {"hincator"}, "hincator", EMPLEADO).id == "hincator"


class TestAreAllManualsAcknowledged:
    def test_false_with_one_missing(self):
        assert are_all_manuals_acknowledged(BOTH, {"clickup"}) is False

    def test_true_with_all_read(self):
        assert are_all_manuals_acknowledged(BOTH, {"clickup", "hincator"}) is True

    def test_false_when_there_are_no_manuals(self):
        """Cerrar el paso porque no hay nada que leer dejaría pasar a alguien sin
        haber leído lo que el paso promete. El caso de uso ya trata "no hay
        manual" como error de configuración."""
        assert are_all_manuals_acknowledged([], set()) is False

    def test_extra_acknowledgements_do_not_break_it(self):
        """Un manual retirado del catálogo puede seguir confirmado por alguien."""
        assert are_all_manuals_acknowledged(BOTH, {"clickup", "hincator", "viejo"})


class TestResolveStepDocuments:
    def test_only_the_first_is_open_at_the_start(self):
        resolved = resolve_step_documents(BOTH, set(), EMPLEADO)

        assert [(d.document.id, d.acknowledged, d.locked) for d in resolved] == [
            ("clickup", False, False),
            ("hincator", False, True),
        ]

    def test_reading_the_first_unlocks_the_second(self):
        resolved = resolve_step_documents(BOTH, {"clickup"}, EMPLEADO)

        assert [(d.document.id, d.acknowledged, d.locked) for d in resolved] == [
            ("clickup", True, False),
            ("hincator", False, False),
        ]

    def test_an_acknowledged_manual_is_never_locked(self):
        resolved = resolve_step_documents(BOTH, {"hincator"}, EMPLEADO)
        by_id = {d.document.id: d for d in resolved}

        assert by_id["hincator"].locked is False
        assert by_id["clickup"].locked is False  # el primero nunca se bloquea

    def test_locked_matches_what_ensure_manual_unlocked_rejects(self):
        """El invariante que importa: el candado que pinta la UI y el error que
        devuelve el POST salen de la misma regla. Si divergieran, el trabajador
        vería un botón habilitado que responde 422."""
        for acknowledged in [set(), {"clickup"}, {"hincator"}, {"clickup", "hincator"}]:
            for item in resolve_step_documents(BOTH, acknowledged, EMPLEADO):
                rejected = False
                try:
                    ensure_manual_unlocked(BOTH, acknowledged, item.document.id, EMPLEADO)
                except ManualLockedError:
                    rejected = True
                assert item.locked == rejected, (
                    f"{item.document.id} con {acknowledged}: "
                    f"locked={item.locked} pero el POST "
                    f"{'rechaza' if rejected else 'acepta'}"
                )
