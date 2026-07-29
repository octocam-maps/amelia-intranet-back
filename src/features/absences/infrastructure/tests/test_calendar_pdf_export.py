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


def test_pdf_with_a_real_markup_tag_in_subject_name_does_not_crash():
    """SEC-1 (auditoría QA, severidad ALTA): `subject_name` viene de
    `users.full_name` — Google OIDC lo rellena y cualquier admin puede
    editarlo a mano al gestionar la plantilla, no está bajo control.
    `Paragraph(f"Empleado: {subject_name}", ...)` interpola ese valor sin
    escapar y `reportlab` interpreta un subconjunto real de XML/mini-HTML
    dentro de `Paragraph` — una etiqueta real como `<b>` revienta la
    generación con un `ValueError` (500 genérico, no controlado), rompiendo
    para siempre el export PDF individual de esa persona. Un `<` suelto NO
    basta para reproducirlo — reportlab solo revienta cuando la etiqueta
    de verdad intenta parsear (aquí, un `<b>` SIN cerrar: el cierre
    implícito de `</para>` no encaja con él)."""
    pdf_bytes = build_absence_calendar_export_pdf(
        [_entry()],
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        subject_name="Ana <b>x Garcia",
    )

    assert pdf_bytes.startswith(b"%PDF")


def test_header_flowables_escape_special_chars_and_render_them_literal():
    """El nombre debe aparecer LITERAL en el documento — ni una etiqueta
    real, ni entidades sin escapar, ni un `ValueError` a mitad de camino."""
    from src.features.absences.infrastructure.calendar_pdf_export import (
        _build_header_flowables,
    )

    malicious_name = 'Ana <b>x</b> & <font color="red">Garcia</font> & Cía'
    flowables = _build_header_flowables(
        date(2026, 7, 1), date(2026, 7, 31), subject_name=malicious_name
    )
    texts = [getattr(f, "text", None) for f in flowables if hasattr(f, "text")]

    assert any(
        text == "Empleado: Ana &lt;b&gt;x&lt;/b&gt; &amp; "
        '&lt;font color="red"&gt;Garcia&lt;/font&gt; &amp; Cía'
        for text in texts
    )
