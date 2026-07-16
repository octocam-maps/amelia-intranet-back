"""
Construye el PDF del "Calendario general de la plantilla"
(`GET /absences/calendar/export.pdf`, LOTE 4). `reportlab` vive SOLO aquí —
mismo criterio que `calendar_xlsx_export.py`/`time_clock/infrastructure/
xlsx_export.py`: es un detalle de formato de salida (infraestructura), el
caso de uso (`GetAbsenceCalendarUseCase`) no sabe que el resultado termina
en un PDF.

No había ninguna librería de PDF instalada en el backend — se añade
`reportlab` (`requirements.txt`) porque es la opción estándar para generar
PDFs desde cero con Python puro (sin depender de un motor de renderizado
HTML/Chromium como weasyprint, que no estaba disponible en el entorno).
"""

import io
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..domain.entities import AbsenceCalendarEntry

_BRAND_NAVY = colors.HexColor("#0F1729")
_MUTED_TEXT = colors.HexColor("#6B7280")
_ROW_ALT_BG = colors.HexColor("#F9FAFB")
_GRID_COLOR = colors.HexColor("#E5E7EB")

# .../src/features/absences/infrastructure/calendar_pdf_export.py -> .../src
_SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Logo negro (no el de color) — el PDF exportado se imprime a menudo en
# blanco y negro / se usa fuera de la UI de marca, así que este export usa
# `logo-amelia-blue.png` (nombre de archivo heredado del asset, pero su
# contenido es el logo NEGRO) en vez del `logo-amelia.png` de color que sí
# usa el XLSX (`calendar_xlsx_export.py`/`time_clock/infrastructure/
# xlsx_export.py`).
_LOGO_PATH = _SRC_DIR / "shared" / "assets" / "brand" / "logo-amelia-blue.png"
# Proporción propia del PNG negro (1920x512 = 3.75:1) — distinta a la del
# logo de color (1920x400 = 4.8:1) que usan XLSX. Se deriva el ancho desde
# la altura fija para no deformarlo.
_LOGO_ASPECT_RATIO = 1920 / 512
_LOGO_HEIGHT_MM = 10
_LOGO_WIDTH_MM = _LOGO_HEIGHT_MM * _LOGO_ASPECT_RATIO

_STATUS_LABELS = {"pending": "Pendiente", "approved": "Aprobada"}

TITLE = "Calendario de ausencias — toda la plantilla"


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status.capitalize())


def _build_header_flowables(date_from: date, date_to: date) -> list:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AmeliaCalendarTitle",
        parent=styles["Heading1"],
        fontSize=14,
        textColor=_BRAND_NAVY,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "AmeliaCalendarSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=_MUTED_TEXT,
        spaceAfter=10,
    )

    flowables: list = []
    if _LOGO_PATH.exists():
        # Ancho derivado de `_LOGO_ASPECT_RATIO` (ver arriba) para no
        # deformar el PNG negro, que tiene una relación de aspecto distinta
        # a la del logo de color que usa el XLSX.
        flowables.append(
            Image(str(_LOGO_PATH), width=_LOGO_WIDTH_MM * mm, height=_LOGO_HEIGHT_MM * mm)
        )
        flowables.append(Spacer(1, 6))
    flowables.append(Paragraph(TITLE, title_style))
    flowables.append(
        Paragraph(
            f"Del {date_from.strftime('%d/%m/%Y')} al {date_to.strftime('%d/%m/%Y')}",
            subtitle_style,
        )
    )
    return flowables


def _build_table(entries: list[AbsenceCalendarEntry]) -> Table:
    header = ["Empleado", "Tipo de ausencia", "Inicio", "Fin", "Días", "Estado"]
    data = [header]
    for entry in entries:
        data.append(
            [
                entry.user_full_name,
                entry.absence_type_name,
                entry.start_date.strftime("%d/%m/%Y"),
                entry.end_date.strftime("%d/%m/%Y"),
                f"{entry.days_count:g}",
                _status_label(entry.status),
            ]
        )
    if not entries:
        data.append(["Sin ausencias en el rango seleccionado.", "", "", "", "", ""])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[55 * mm, 45 * mm, 28 * mm, 28 * mm, 18 * mm, 28 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _BRAND_NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT_BG]),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def build_absence_calendar_export_pdf(
    entries: list[AbsenceCalendarEntry], *, date_from: date, date_to: date
) -> bytes:
    """Genera el PDF completo en memoria (nunca toca disco salvo para leer
    el PNG estático del logo). Mismo alcance que la pantalla y el XLSX
    (`calendar_xlsx_export.py`): TODA la plantilla, `pending`/`approved`,
    dentro del rango `[date_from, date_to]`."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=18 * mm,
        bottomMargin=14 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=TITLE,
    )

    elements = _build_header_flowables(date_from, date_to)
    elements.append(_build_table(entries))
    doc.build(elements)
    return buffer.getvalue()
