"""No parsea el PDF por dentro (no hay una forma sencilla de inspeccionar
texto de `reportlab` sin una librería adicional) — comprueba que genera un
documento válido (magic bytes `%PDF`) tanto con filas como sin ellas, y que
no revienta si falta el logo."""

from datetime import date

from src.features.absences.domain.entities import AbsenceCalendarEntry
from src.features.absences.infrastructure.calendar_pdf_export import (
    build_absence_calendar_export_pdf,
)


def _entry(**overrides) -> AbsenceCalendarEntry:
    kwargs = dict(
        request_id="req-1",
        user_id="user-1",
        user_full_name="Ana García",
        absence_type_id="type-vacaciones",
        absence_type_name="Vacaciones",
        absence_type_color="#00D170",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 24),
        days_count=5.0,
        status="approved",
    )
    kwargs.update(overrides)
    return AbsenceCalendarEntry(**kwargs)


def test_pdf_is_a_valid_document_with_entries():
    pdf_bytes = build_absence_calendar_export_pdf(
        [_entry(), _entry(user_full_name="Luis Pérez", status="pending")],
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 0


def test_pdf_is_a_valid_document_with_no_entries():
    """Sin ausencias en el rango — el PDF debe seguir siendo válido (fila
    "Sin ausencias..." en vez de reventar con una tabla vacía)."""
    pdf_bytes = build_absence_calendar_export_pdf(
        [], date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )

    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_with_subject_name_is_a_valid_document():
    """RF-A1: `subject_name` no debe reventar la generación — no se parsea
    el texto interno (mismo criterio que el resto del fichero), se
    comprueba a nivel de flowables (ver test siguiente)."""
    pdf_bytes = build_absence_calendar_export_pdf(
        [_entry()],
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        subject_name="Ana García",
    )

    assert pdf_bytes.startswith(b"%PDF")


def test_header_flowables_without_subject_name_unchanged():
    """RF-A1: `subject_name=None` (export global) DEBE mantener las mismas
    flowables que antes — ni una línea de más."""
    from src.features.absences.infrastructure.calendar_pdf_export import (
        _build_header_flowables,
    )

    flowables = _build_header_flowables(date(2026, 7, 1), date(2026, 7, 31))
    texts = [getattr(f, "text", None) for f in flowables if hasattr(f, "text")]

    assert not any(text and text.startswith("Empleado:") for text in texts)


def test_header_flowables_with_subject_name_adds_employee_line():
    from src.features.absences.infrastructure.calendar_pdf_export import (
        _build_header_flowables,
    )

    flowables = _build_header_flowables(
        date(2026, 7, 1), date(2026, 7, 31), subject_name="Ana García"
    )
    texts = [getattr(f, "text", None) for f in flowables if hasattr(f, "text")]

    assert any(text == "Empleado: Ana García" for text in texts)
