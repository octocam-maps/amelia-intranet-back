"""
Produce los PDF de los documentos FIRMABLES del paso 5 del onboarding, ya
rellenados con los datos del perfil que la persona completó en el paso 4.

Entregados por RRHH el 2026-08-06. Son cuatro, y NO se producen todos igual:

    consentimiento-imagenes      · OVERLAY sobre el PDF original de RRHH
    reconocimiento-medico        · OVERLAY sobre el CES de Som Prevenció
    rgpd-informacion             · generado (falta el PDF original)
    compromiso-confidencialidad  · generado (falta el PDF original)

DOS MODOS, Y EL OVERLAY ES EL BUENO
Decisión del team-lead (2026-08-06, rectificando la primera entrega): los
documentos se sirven TAL CUAL los entregó RRHH, no re-maquetados con la identidad
de Amelia. Así que se toma su PDF como plantilla intacta y solo se ESTAMPAN los
datos encima, en las coordenadas de sus propios huecos (`_OVERLAY_SPECS`). El
documento que firma la persona es, byte a byte en su parte fija, el que redactó
RRHH — y en el caso del CES, el que Som Prevenció espera recibir de vuelta.

Los otros dos siguen generados con `reportlab` porque de ellos NO hay PDF: RRHH
entregó `RGPD_Amelia.docx` (que además contiene los dos documentos en un solo
fichero) y sin un PDF base no hay nada sobre lo que estampar. En cuanto llegue,
pasan a overlay igual que los otros dos: añadir su entrada a `_OVERLAY_SPECS` y
quitar su builder.

POR QUÉ NO SE SIRVEN COMO FICHERO ESTÁTICO
Los manuales (`kind='manual'`) viven en `amelia-intranet-web/public/manuales/`,
que NO pasa por autenticación: son iguales para toda la plantilla, así que una
URL adivinable no expone nada. Estos cuatro llevan dentro nombre, DNI y puesto
de una persona concreta. Publicarlos en `public/` sería exponer datos personales
a cualquiera que acierte el nombre del fichero, y el filtrado por usuario tiene
que ocurrir en el backend (RGPD, alcance de datos). Por eso se rellenan al vuelo
contra el usuario autenticado y nunca tocan disco.

CÓMO SE DISTINGUEN EN LA TABLA
`onboarding_documents.storage_ref` con el prefijo `generated:` (ver
`GENERATED_REF_PREFIX`) en vez de una ruta. Se reutiliza la columna en vez de
añadir una nueva porque la pregunta que responde es la misma —"de dónde sale el
binario"— y un `kind` nuevo habría obligado a revisar cada `WHERE kind =` ya
escrito. Lo que sigue al prefijo es la clave de `RENDERERS`.

SOBRE `content_hash`
Para un fichero estático es el SHA-256 de lo que se sirve. Aquí NO puede serlo:
cada persona recibe un PDF distinto, así que un hash por fichero servido no
identificaría nada. `template_hash()` da el hash de la PLANTILLA — el del PDF
base para los overlays, el del texto fijo para los generados — y sirve para lo
mismo de siempre: saber qué documento aceptó la persona cuando cambie de versión.

`reportlab` + `pypdf` (y no un motor HTML como weasyprint) por el mismo motivo
que `absences/infrastructure/calendar_pdf_export.py`: es lo que hay instalado y
no requiere Chromium en el contenedor de producción. El merge de una capa sobre
una página existente es el mismo patrón que usa
`amelia-intranet/docs/build-manual-pdf.py` para el pie numerado.
"""

import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Tokens de marca — literales de `amelia-intranet-web/src/index.css`.
_BRAND_NAVY = colors.HexColor("#0F1729")
_BRAND_GREEN = colors.HexColor("#00D170")
_GREEN_ON_TINT = colors.HexColor("#007A42")
_MUTED_TEXT = colors.HexColor("#6B7280")
_GRID_COLOR = colors.HexColor("#E5E7EB")
_SURFACE = colors.HexColor("#F3F4F6")

# .../src/features/onboarding/infrastructure/signable_documents.py -> .../src
_SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Logo NEGRO (el nombre del asset dice "blue", su contenido es negro — mismo
# fichero y misma nota que en `calendar_pdf_export.py`). Estos documentos se
# imprimen para firmarlos a mano, muchas veces en blanco y negro.
_LOGO_PATH = _SRC_DIR / "shared" / "assets" / "brand" / "logo-amelia-blue.png"
_LOGO_ASPECT_RATIO = 1920 / 512
_LOGO_HEIGHT_MM = 9
_LOGO_WIDTH_MM = _LOGO_HEIGHT_MM * _LOGO_ASPECT_RATIO

GENERATED_REF_PREFIX = "generated:"

# Domicilio social del grupo — el mismo que encabeza los documentos de RRHH.
_COMPANY_ADDRESS = (
    "Carretera Laurea Miró 375-377, Nave 10, 08980 Sant Feliu de Llobregat (Barcelona)"
)
_PEOPLE_EMAIL = "people@ameliahub.com"
_PEOPLE_MANAGER = "Beatriz Luna Sánchez"

# LA DECISIÓN "SOLO AMELIA LAB Y AMELIA HUB" QUEDÓ SIN EFECTO, y conviene saberlo
# antes de buscarla en el código: aquí vivía la constante que sustituía las
# sociedades del consentimiento de imágenes.
#
# El original de RRHH dice "AMELIA LAB S.L y AMELIA OPS S.L" en la autorización
# mientras su cuerpo habla de AMELIA HUB — es incoherente, y el 2026-08-06 el
# team-lead decidió dejarlo en Lab + Hub, sacando a Ops. Ese mismo día decidió
# también servir los documentos TAL CUAL los entregó RRHH, y las dos decisiones no
# caben juntas: el overlay solo rellena huecos, no reescribe párrafos.
#
# Así que el documento que se firma vuelve a autorizar a LAB y OPS. Para cambiar
# las sociedades hay que editar el .docx original y reexportar el PDF —es un
# cambio de redacción y le toca a RRHH—, no taparlo con un rectángulo blanco desde
# aquí: un documento jurídico parcheado visualmente sigue diciendo otra cosa en su
# capa de texto, y eso es peor que la incoherencia de partida.

_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

# Ancho de la línea de puntos que sustituye a un dato ausente. Ver `_value`.
_BLANK_LINE = "_" * 28


def _format_date_es(value: date) -> str:
    """`7 de abril de 2026`. `strftime('%B')` depende del locale del contenedor
    (que en producción es C/POSIX y devolvería "April"), así que el mes se
    resuelve con la tabla de arriba."""
    return f"{value.day} de {_MONTHS_ES[value.month - 1]} de {value.year}"


@dataclass(frozen=True)
class SignableDocumentData:
    """Datos del paso 4 con los que se rellenan los documentos del paso 5.

    Todo es opcional salvo el nombre y la fecha: el paso 4 puede completarse
    sin DNI o sin puesto asignado, y en ese caso el PDF sale con el hueco en
    blanco para rellenar a mano — nunca con la cadena "None" impresa.

    `issued_on` se inyecta (no se toma de `date.today()` aquí dentro) para que
    el generador sea una función pura y los tests puedan fijar la fecha."""

    full_name: str
    issued_on: date
    dni: str | None = None
    job_title: str | None = None
    entity_name: str | None = None
    city: str | None = None


def _value(raw: str | None) -> str:
    """Escapa el dato y, si no hay, devuelve una línea para rellenar a mano.

    EL ESCAPADO NO ES OPCIONAL (SEC-1, auditoría QA severidad ALTA, ver la
    misma nota en `calendar_pdf_export.py`): `full_name` lo rellena Google
    OIDC y un admin lo puede editar; `dni`/`job_title` los teclea la propia
    persona en el paso 4. `Paragraph` interpreta un subconjunto de XML, así que
    un `<b>` sin cerrar reventaría la generación y uno bien formado se
    interpretaría como formato en vez de verse literal."""
    if raw is None or not raw.strip():
        return _BLANK_LINE
    return _xml_escape(raw.strip())


def _styles() -> dict[str, ParagraphStyle]:
    """Hoja de estilos propia en vez de `getSampleStyleSheet()`: estos son
    documentos legales de una página o dos, con justificado y un cuerpo más
    compacto que el de los informes."""
    body = ParagraphStyle(
        "AmeliaSignableBody",
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        alignment=TA_JUSTIFY,
        textColor=_BRAND_NAVY,
        spaceAfter=7,
    )
    return {
        "body": body,
        "small": ParagraphStyle(
            "AmeliaSignableSmall",
            parent=body,
            fontSize=8,
            leading=11,
            spaceAfter=4,
            textColor=_MUTED_TEXT,
            alignment=TA_JUSTIFY,
        ),
        "title": ParagraphStyle(
            "AmeliaSignableTitle",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "AmeliaSignableH2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            alignment=0,
            spaceBefore=10,
            spaceAfter=5,
            textColor=_GREEN_ON_TINT,
        ),
        "place": ParagraphStyle(
            "AmeliaSignablePlace",
            parent=body,
            alignment=2,
            spaceAfter=16,
            textColor=_MUTED_TEXT,
        ),
        "label": ParagraphStyle(
            "AmeliaSignableLabel",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            alignment=0,
            spaceAfter=0,
            textColor=_GREEN_ON_TINT,
        ),
        "cell": ParagraphStyle(
            "AmeliaSignableCell",
            parent=body,
            fontSize=9,
            leading=12,
            alignment=0,
            spaceAfter=0,
        ),
    }


def _brand_header(data: SignableDocumentData) -> list:
    """Cabecera común de los tres documentos de Amelia: logo, razón social del
    grupo y domicilio. El CES NO la usa (es de otra entidad)."""
    st = _styles()
    flowables: list = []
    if _LOGO_PATH.exists():
        flowables.append(
            Image(
                str(_LOGO_PATH),
                width=_LOGO_WIDTH_MM * mm,
                height=_LOGO_HEIGHT_MM * mm,
                hAlign="LEFT",
            )
        )
        flowables.append(Spacer(1, 4))
    flowables.append(Paragraph(_COMPANY_ADDRESS, st["small"]))
    # Filete de marca bajo la cabecera, como en los manuales.
    rule = Table([[""]], colWidths=[170 * mm], rowHeights=[1.6 * mm])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _BRAND_GREEN)]))
    flowables.append(rule)
    flowables.append(Spacer(1, 12))
    return flowables


def _signature_block(
    data: SignableDocumentData,
    *,
    worker_extra_rows: tuple[str, ...] = (),
    company_label: str = "Por Amelia Hub",
) -> Table:
    """Bloque de firma a dos columnas: la persona trabajadora y la empresa.

    `worker_extra_rows` añade líneas bajo el nombre (el compromiso de
    confidencialidad pide además el puesto). Se deja hueco real para firmar:
    estos PDF se imprimen, se firman a mano y se vuelven a subir — el paso 5
    es "sube tu documentación firmada", la firma nativa se eliminó en la
    migración 030."""
    st = _styles()
    date_line = f"Fecha: {_format_date_es(data.issued_on)}"

    worker_cell: list = [
        Paragraph("PERSONA TRABAJADORA", st["label"]),
        Spacer(1, 34),
        Paragraph(f"<b>{_value(data.full_name)}</b>", st["cell"]),
    ]
    for extra in worker_extra_rows:
        worker_cell.append(Paragraph(extra, st["cell"]))
    worker_cell.append(Paragraph(date_line, st["small"]))

    company_cell = [
        Paragraph(company_label.upper(), st["label"]),
        Spacer(1, 34),
        Paragraph(f"<b>{_PEOPLE_MANAGER}</b>", st["cell"]),
        Paragraph("People Manager", st["cell"]),
        Paragraph(date_line, st["small"]),
    ]

    table = Table([[worker_cell, company_cell]], colWidths=[85 * mm, 85 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, _BRAND_NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ("LEFTPADDING", (1, 0), (1, -1), 10),
            ]
        )
    )
    return table


# ── 1 · Consentimiento para la cesión de imágenes ────────────────────────────
#
# NO SE GENERA: va por OVERLAY sobre el PDF original de RRHH (ver
# `_OVERLAY_SPECS`). Aquí había un traslado del documento a la identidad visual
# de Amelia, retirado el 2026-08-06 por decisión del team-lead — los documentos
# se sirven tal cual los entregó RRHH.
#
# Se BORRÓ en vez de dejarlo desconectado: eran ~80 líneas de redacción legal
# duplicada que ya nadie renderiza, y una segunda copia del texto de un documento
# jurídico es la que acaba divergiendo del que la gente firma.


# ── 2 · Información sobre protección de datos (art. 13 RGPD) ─────────────────

_RGPD_ROWS = (
    (
        "Responsable del tratamiento",
        "Amelia Hub S.L y Amelia Lab S.L · " + _COMPANY_ADDRESS,
    ),
    ("Contacto del responsable", _PEOPLE_EMAIL),
    (
        "Delegado de Protección de Datos (DPD)",
        "Amelia Hub no cuenta actualmente con DPD designado al no estar obligada por la "
        "normativa vigente.",
    ),
    (
        "Finalidad del tratamiento",
        "Gestión de la relación laboral: formalización y ejecución del contrato de trabajo, "
        "gestión de nóminas y retribuciones, cumplimiento de obligaciones con la Seguridad "
        "Social y la Agencia Tributaria, control de presencia y registro de jornada, gestión "
        "de permisos, ausencias y vacaciones, prevención de riesgos laborales, formación y "
        "desarrollo, comunicaciones internas y otras derivadas de la relación laboral.",
    ),
    (
        "Base jurídica del tratamiento",
        "Ejecución del contrato de trabajo (art. 6.1.b RGPD). Cumplimiento de obligaciones "
        "legales aplicables al empleador (art. 6.1.c RGPD): Estatuto de los Trabajadores, Ley "
        "General de la Seguridad Social, normativa tributaria, LPRL y demás legislación "
        "laboral vigente.",
    ),
    (
        "Categorías de datos tratados",
        "Datos identificativos (nombre, DNI/NIE, dirección, teléfono, correo electrónico). "
        "Datos económicos (cuenta bancaria, retribución, IRPF). Datos de afiliación a la "
        "Seguridad Social. Datos de asistencia y control horario. Datos relativos a la salud, "
        "exclusivamente los necesarios para la gestión de IT, bajas laborales y vigilancia de "
        "la salud en el marco de la LPRL.",
    ),
    (
        "Destinatarios de los datos",
        "Administración Pública: Agencia Tributaria, Tesorería General de la Seguridad Social, "
        "Servicio Público de Empleo Estatal (SEPE) y demás organismos públicos en cumplimiento "
        "de obligaciones legales. Mutua colaboradora y servicios de prevención de riesgos "
        "laborales. Entidades financieras para el pago de nóminas. Proveedores de servicios de "
        "gestión laboral y RRHH (encargados del tratamiento con contrato según art. 28 RGPD).",
    ),
    (
        "Transferencias internacionales",
        "No se prevén transferencias internacionales de datos a países fuera del Espacio "
        "Económico Europeo, salvo que resulten necesarias para el uso de herramientas "
        "tecnológicas de gestión interna, en cuyo caso se adoptarán las garantías adecuadas "
        "conforme al RGPD.",
    ),
    (
        "Plazo de conservación",
        "Los datos se conservarán durante la vigencia de la relación laboral y, una vez "
        "extinguida, durante los plazos legalmente exigidos: 4 años para obligaciones con la "
        "Seguridad Social (art. 21 LGSS), 5 años para obligaciones tributarias (Ley General "
        "Tributaria) y hasta 5 años para documentación laboral (Estatuto de los Trabajadores), "
        "salvo que una norma específica establezca un plazo distinto.",
    ),
    (
        "Derechos del interesado",
        "Acceso, rectificación, supresión, limitación del tratamiento, portabilidad y "
        f"oposición, en los términos previstos en el RGPD y la LOPDGDD. Puede ejercerlos "
        f"dirigiéndose a {_PEOPLE_EMAIL}. Tiene derecho a presentar una reclamación ante la "
        "Agencia Española de Protección de Datos (www.aepd.es) si considera que el tratamiento "
        "no se ajusta a la normativa vigente.",
    ),
    (
        "Tratamiento de imágenes y comunicaciones internas",
        "En el ejercicio de sus funciones, la persona trabajadora podrá aparecer en "
        "fotografías, grabaciones o comunicaciones internas de la empresa (reuniones, "
        "formaciones, etc.). Estos materiales se tratarán exclusivamente con fines internos de "
        "gestión y comunicación corporativa, y no serán cedidos a terceros sin consentimiento "
        "expreso, salvo obligación legal.",
    ),
)


def _info_table(rows: tuple[tuple[str, str], ...]) -> Table:
    """Tabla etiqueta/valor de dos columnas, la de la ficha informativa del
    RGPD. La etiqueta va en verde sobre superficie gris, como en los manuales."""
    st = _styles()
    data_rows = [
        [Paragraph(label, st["label"]), Paragraph(value, st["cell"])]
        for label, value in rows
    ]
    table = Table(data_rows, colWidths=[48 * mm, 122 * mm], repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), _SURFACE),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _build_rgpd_informacion(data: SignableDocumentData) -> tuple[list, str]:
    st = _styles()
    flowables = _brand_header(data)
    flowables.append(
        Paragraph("INFORMACIÓN SOBRE PROTECCIÓN DE DATOS PERSONALES", st["title"])
    )
    flowables.append(
        Paragraph(
            "(Artículo 13 RGPD y artículo 14 LOPDGDD — Información al empleado/a)",
            ParagraphStyle("c", parent=st["small"], alignment=TA_CENTER, spaceAfter=12),
        )
    )
    flowables.append(_info_table(_RGPD_ROWS))
    flowables.append(Spacer(1, 14))
    flowables.append(
        KeepTogether(
            [
                Paragraph(
                    "He sido informado/a de los términos del tratamiento de mis datos "
                    "personales por parte de Amelia Hub y Amelia Lab, conforme a lo indicado "
                    "en el presente documento.",
                    st["body"],
                ),
                Spacer(1, 18),
                _signature_block(data, company_label="Por Amelia Hub y Amelia Lab"),
            ]
        )
    )
    return flowables, "Información sobre protección de datos personales"


# ── 3 · Compromiso de confidencialidad ───────────────────────────────────────
#
# SOLO NOMBRA A AMELIA HUB, Y NO ES UN OLVIDO. Los otros dos documentos de Amelia
# salen a nombre de Hub y Lab, así que esto parece una inconsistencia y en la
# siguiente pasada alguien intentará "arreglarlo": no lo hagas sin pedirlo.
#
# Decisión del team-lead (2026-08-06), preguntada expresamente al comprobar el
# relleno. Aquí "Amelia Hub" no es un rótulo de cabecera: es QUIÉN es el
# responsable del tratamiento ante el que la persona se obliga, y de él cuelgan el
# alcance de las instrucciones (cláusula 4), a quién se notifica una brecha
# (cláusula 3) y a quién se devuelve la documentación al cesar. Añadir Lab
# ampliaría el alcance jurídico de la firma, no solo el texto.
#
# Que este documento viniera en el mismo `.docx` que la información del art. 13
# —que sí lleva las dos sociedades— no los hace un mismo documento: son dos, con
# firma independiente y responsables distintos.

_CONFID_ACCESS = (
    "Datos de identificación y contacto de clientes y proveedores (nombre, NIF/CIF, "
    "dirección, teléfono, correo electrónico).",
    "Datos económicos y contractuales de clientes y proveedores (condiciones comerciales, "
    "facturación, cuentas bancarias).",
    "Datos técnicos de proyectos: especificaciones, documentación técnica, informes, planos y "
    "cualquier información relacionada con los proyectos desarrollados para clientes.",
    "Cualquier otro dato personal o información confidencial a la que tenga acceso en el "
    "ejercicio de sus funciones.",
)

_CONFID_DUTIES = (
    "Tratar los datos personales y la información confidencial a los que tenga acceso "
    "exclusivamente para las finalidades propias de su puesto y en el marco de las "
    "instrucciones recibidas de Amelia Hub.",
    "No comunicar, ceder, difundir ni hacer accesibles los datos a terceros no autorizados, "
    "ya sea durante la vigencia de la relación laboral o una vez extinguida esta.",
    "Adoptar las medidas técnicas y organizativas necesarias para evitar el acceso no "
    "autorizado, la pérdida, destrucción o alteración de los datos.",
    f"Notificar de inmediato a {_PEOPLE_EMAIL} cualquier incidente de seguridad o brecha de "
    "datos del que tenga conocimiento.",
    "No reproducir, copiar ni extraer datos o documentación confidencial fuera de los "
    "sistemas autorizados por la empresa, salvo autorización expresa.",
    "A la extinción de la relación laboral, devolver o destruir cualquier soporte o "
    "documentación que contenga datos personales o información confidencial de la empresa, "
    "sus clientes o proveedores.",
    "Cumplir en todo momento con el Reglamento (UE) 2016/679 (RGPD), la Ley Orgánica 3/2018 "
    "(LOPDGDD) y las políticas internas de Amelia en materia de protección de datos.",
)

_CONFID_BREACH = (
    "Responsabilidad disciplinaria conforme al Estatuto de los Trabajadores y al convenio "
    "colectivo aplicable, pudiendo constituir falta muy grave.",
    "Responsabilidad civil por los daños y perjuicios causados a Amelia Hub, a sus clientes o "
    "a terceros afectados.",
    "Responsabilidad administrativa ante la Agencia Española de Protección de Datos (AEPD).",
    "Responsabilidad penal en los supuestos tipificados en el Código Penal (arts. 197 y ss.).",
)


def _build_compromiso_confidencialidad(data: SignableDocumentData) -> tuple[list, str]:
    st = _styles()
    flowables = _brand_header(data)
    flowables.append(
        Paragraph("COMPROMISO DE CONFIDENCIALIDAD Y PROTECCIÓN DE DATOS", st["title"])
    )
    flowables.append(
        Paragraph(
            "Acceso a datos de terceros en el ejercicio del puesto de trabajo",
            ParagraphStyle(
                "c2", parent=st["small"], alignment=TA_CENTER, spaceAfter=12
            ),
        )
    )

    flowables.append(Paragraph("1. Objeto", st["h2"]))
    flowables.append(
        Paragraph(
            "El presente compromiso regula las obligaciones de confidencialidad y protección "
            "de datos de la persona trabajadora que, en el desempeño de sus funciones en "
            "Amelia, tenga acceso a datos personales o información confidencial de clientes, "
            "proveedores u otras personas físicas o jurídicas vinculadas a la empresa.",
            st["body"],
        )
    )

    flowables.append(Paragraph("2. Datos a los que tendrá acceso", st["h2"]))
    flowables.append(
        Paragraph(
            "En función de su puesto, la persona trabajadora podrá acceder a:",
            st["body"],
        )
    )
    for item in _CONFID_ACCESS:
        flowables.append(Paragraph(f"•&nbsp;&nbsp;{item}", st["body"]))

    flowables.append(Paragraph("3. Obligaciones de la persona trabajadora", st["h2"]))
    flowables.append(Paragraph("La persona trabajadora se compromete a:", st["body"]))
    for item in _CONFID_DUTIES:
        flowables.append(Paragraph(f"•&nbsp;&nbsp;{item}", st["body"]))

    flowables.append(Paragraph("4. Instrucciones de tratamiento", st["h2"]))
    flowables.append(
        Paragraph(
            "La persona trabajadora actuará únicamente conforme a las instrucciones "
            "documentadas de Amelia Hub como responsable del tratamiento. En caso de duda "
            "sobre la licitud de una instrucción o sobre cómo proceder ante una solicitud de "
            f"ejercicio de derechos por parte de un interesado, consultará previamente con "
            f"{_PEOPLE_EMAIL} antes de actuar.",
            st["body"],
        )
    )

    flowables.append(Paragraph("5. Uso de herramientas y sistemas", st["h2"]))
    flowables.append(
        Paragraph(
            "El acceso y tratamiento de datos personales se realizará exclusivamente a través "
            "de los sistemas, aplicaciones y dispositivos autorizados por Amelia Hub. Queda "
            "prohibido el uso de dispositivos, plataformas o aplicaciones no autorizadas para "
            "el tratamiento de datos de la empresa, sus clientes o proveedores.",
            st["body"],
        )
    )

    flowables.append(
        Paragraph("6. Vigencia y consecuencias del incumplimiento", st["h2"])
    )
    flowables.append(
        Paragraph(
            "Las obligaciones recogidas en el presente compromiso son de vigencia indefinida y "
            "subsisten tras la extinción de la relación laboral, en los términos previstos por "
            "la legislación aplicable.",
            st["body"],
        )
    )
    flowables.append(
        Paragraph(
            "El incumplimiento de las obligaciones aquí establecidas podrá dar lugar a:",
            st["body"],
        )
    )
    for item in _CONFID_BREACH:
        flowables.append(Paragraph(f"•&nbsp;&nbsp;{item}", st["body"]))

    flowables.append(Spacer(1, 12))
    flowables.append(
        KeepTogether(
            [
                Paragraph(
                    "Declaro haber leído, comprendido y aceptado las obligaciones contenidas "
                    "en el presente Compromiso de Confidencialidad y Protección de Datos.",
                    st["body"],
                ),
                Spacer(1, 16),
                # El puesto SÍ va en este documento: el alcance del compromiso
                # depende de a qué datos da acceso el puesto (cláusula 2).
                _signature_block(
                    data,
                    worker_extra_rows=(f"Puesto: {_value(data.job_title)}",),
                ),
            ]
        )
    )
    return flowables, "Compromiso de confidencialidad y protección de datos"


# ── 4 · Consentimiento examen de salud (CES · Som Prevenció) ─────────────────
#
# NO SE GENERA: va por OVERLAY sobre el PDF de Som Prevenció (ver
# `_OVERLAY_SPECS`). Aquí había una RÉPLICA de su formulario dibujada con
# reportlab —su naranja, su cabecera REV/CES, el nombre en texto donde va su
# logotipo— retirada el 2026-08-06: el documento se remite firmado a ese servicio
# de prevención para su archivo, así que tiene que llegarles siendo el suyo, no
# una reconstrucción parecida.


# ── Overlay sobre los PDF originales de RRHH ─────────────────────────────────
#
# El modo BUENO (ver el docstring del módulo): el PDF de RRHH se usa intacto como
# plantilla y solo se estampan los datos en sus propios huecos.

_TEMPLATES_DIR = Path(__file__).resolve().parent / "document_templates"


@dataclass(frozen=True)
class _Field:
    """Un dato estampado sobre la plantilla.

    `x`/`y` en puntos PDF y con el origen ABAJO-izquierda, que es el sistema de
    `reportlab`. Se derivaron de la posición REAL de los huecos y las etiquetas en
    el PDF original (medidas con `pdftotext -bbox`, cuyo eje Y va al revés: los
    valores de aquí son `alto_de_página - yMax`). No son números inventados a ojo,
    pero sí dependen del fichero: si RRHH entrega otra versión del documento hay
    que volver a medirlos, y por eso `template_hash` vigila el PDF base."""

    page: int
    x: float
    y: float
    value: Callable[[SignableDocumentData], str | None]
    size: float = 9.5


def _plain(raw: str | None) -> str | None:
    """El dato tal cual para dibujar en el canvas, o `None` si no hay.

    NO escapa XML —a diferencia de `_value`— porque `canvas.drawString` pinta la
    cadena literal, no interpreta markup: aquí un `<b>` no puede convertirse en
    negrita ni reventar el render. Y devolver `None` en vez de una línea de
    subrayado es lo correcto en el overlay: el hueco del documento original ya
    trae su propia línea para rellenar a mano."""
    if raw is None or not raw.strip():
        return None
    return raw.strip()


_OVERLAY_SPECS: dict[str, tuple[str, str, tuple[_Field, ...]]] = {
    # (fichero base, título, campos)
    "consentimiento-imagenes": (
        "consentimiento-imagenes.pdf",
        "Consentimiento para la cesión de imágenes y datos personales",
        (
            # Párrafo "Don ______ con DNI ______, autorizo a ..."
            _Field(0, 96.0, 289.0, lambda d: _plain(d.full_name)),
            _Field(0, 248.0, 289.0, lambda d: _plain(d.dni)),
            # Pie "Fdo. Dn ______"
            _Field(0, 112.0, 91.0, lambda d: _plain(d.full_name)),
        ),
    ),
    # El CES es el formulario del servicio de prevención AJENO Som Prevenció, y
    # el propio texto ordena remitirlo "a este Servicio de Vigilancia de la Salud
    # para su archivo". Precisamente por eso va por overlay y no re-maquetado:
    # llega a ellos siendo su documento.
    "reconocimiento-medico": (
        "reconocimiento-medico.pdf",
        "Consentimiento examen de salud",
        (
            _Field(0, 175.0, 728.9, lambda d: _plain(d.entity_name)),
            _Field(0, 175.0, 710.8, lambda d: _plain(d.full_name)),
            _Field(0, 175.0, 692.8, lambda d: _format_date_es(d.issued_on)),
            _Field(0, 175.0, 670.4, lambda d: _plain(d.job_title)),
            _Field(0, 435.0, 673.2, lambda d: _plain(d.dni)),
        ),
    ),
    # Los dos que venían dentro de `RGPD_Amelia.pdf`, ya separados en dos
    # plantillas: son documentos con FIRMA INDEPENDIENTE y la persona sube cada
    # uno por su lado, así que servirlos juntos obligaría a subir el mismo PDF dos
    # veces para satisfacer dos requisitos distintos.
    #
    # El bloque de firma está en la SEGUNDA página de cada plantilla (`page=1`).
    # La fecha se estampa en los TRES segmentos de su hueco `___/___/______` para
    # no pisar las barras que ya trae el documento.
    #
    # Solo se rellena la fecha de la PERSONA TRABAJADORA (columna izquierda). La de
    # la derecha es de la empresa y la pone Beatriz al firmar — el documento ya
    # trae su firma y su cargo impresos.
    "rgpd-informacion": (
        "rgpd-informacion.pdf",
        "Información sobre protección de datos personales",
        (
            _Field(1, 137.0, 385.0, lambda d: _plain(d.full_name)),
            _Field(1, 164.0, 339.0, lambda d: f"{d.issued_on.day:02d}", 8.5),
            _Field(1, 183.0, 339.0, lambda d: f"{d.issued_on.month:02d}", 8.5),
            _Field(1, 203.0, 339.0, lambda d: str(d.issued_on.year), 8.5),
        ),
    ),
    "compromiso-confidencialidad": (
        "compromiso-confidencialidad.pdf",
        "Compromiso de confidencialidad y protección de datos",
        (
            _Field(1, 137.0, 390.0, lambda d: _plain(d.full_name)),
            # El puesto SÍ va en este documento: el alcance del compromiso depende
            # de a qué datos da acceso el puesto (su cláusula 2).
            _Field(1, 149.0, 358.0, lambda d: _plain(d.job_title)),
            _Field(1, 164.0, 345.0, lambda d: f"{d.issued_on.day:02d}", 8.5),
            _Field(1, 183.0, 345.0, lambda d: f"{d.issued_on.month:02d}", 8.5),
            _Field(1, 203.0, 345.0, lambda d: str(d.issued_on.year), 8.5),
        ),
    ),
}


def _render_overlay(code: str, data: SignableDocumentData) -> bytes:
    """Estampa los datos sobre el PDF original y devuelve el resultado.

    La plantilla NO se modifica en disco: se lee, se le fusiona una capa con los
    textos y el resultado se escribe en memoria."""
    filename, _title, fields = _OVERLAY_SPECS[code]
    base_path = _TEMPLATES_DIR / filename
    if not base_path.exists():
        raise FileNotFoundError(
            f"Falta la plantilla {base_path.name} en {_TEMPLATES_DIR}"
        )

    # `clone_from` y NO `PdfReader` + `add_page`: las páginas tienen que estar YA
    # asignadas al writer antes de fusionarles nada encima. Hacerlo al revés
    # (mergear sobre páginas del reader y luego añadirlas) está deprecado desde
    # pypdf 6 —desaparece en la 7— y su propio aviso dice que "ha demostrado ser
    # poco fiable", que en un documento que se firma no es un riesgo aceptable.
    writer = PdfWriter(clone_from=str(base_path))

    for index, page in enumerate(writer.pages):
        page_fields = [f for f in fields if f.page == index]
        if not page_fields:
            continue
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        buffer = io.BytesIO()
        layer = canvas.Canvas(buffer, pagesize=(width, height))
        layer.setFillColor(_BRAND_NAVY)
        for field in page_fields:
            text = field.value(data)
            if not text:
                # Sin dato: se deja el hueco del original intacto, con su línea,
                # para rellenarlo a mano.
                continue
            layer.setFont("Helvetica", field.size)
            layer.drawString(field.x, field.y, text)
        layer.save()
        buffer.seek(0)
        page.merge_page(PdfReader(buffer).pages[0])

    # Los metadatos del original se pierden en `PdfWriter`, así que se reponen —
    # sin ellos el visor muestra el nombre del fichero temporal como título.
    writer.add_metadata(
        {
            "/Title": _title,
            "/Author": "Amelia Hub",
            "/Subject": "Documentación laboral del onboarding",
        }
    )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ── Registro y entrada pública ───────────────────────────────────────────────

# VACÍO desde que RRHH entregó `RGPD_Amelia.pdf` (2026-08-06): los CUATRO
# documentos van ya por overlay sobre su PDF original, que es el modo bueno.
#
# El diccionario se conserva —y con él el camino de generación de
# `build_signable_document_pdf`— porque es la vía para un documento nuevo del que
# solo haya texto, no PDF. Si se queda vacío para siempre, se borra junto con la
# rama que lo consume; mientras siga aquí, `known_codes()` lo tiene en cuenta.
BUILDERS: dict[str, Callable[[SignableDocumentData], tuple[list, str]]] = {}

# Nombre de fichero sugerido en la descarga, por código.
FILENAMES: dict[str, str] = {
    "consentimiento-imagenes": "consentimiento-cesion-imagenes.pdf",
    "rgpd-informacion": "informacion-proteccion-datos.pdf",
    "compromiso-confidencialidad": "compromiso-confidencialidad.pdf",
    "reconocimiento-medico": "consentimiento-examen-salud.pdf",
}


def is_generated_ref(storage_ref: str | None) -> bool:
    """`True` si el documento se genera al vuelo en vez de servirse estático."""
    return bool(storage_ref) and storage_ref.startswith(GENERATED_REF_PREFIX)


def code_from_ref(storage_ref: str) -> str:
    """`generated:rgpd-informacion` -> `rgpd-informacion`."""
    return storage_ref[len(GENERATED_REF_PREFIX) :]


def _footer(canvas, doc, label: str) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(_MUTED_TEXT)
    width = doc.pagesize[0]
    canvas.drawString(18 * mm, 11 * mm, label)
    canvas.drawRightString(width - 18 * mm, 11 * mm, f"Página {canvas.getPageNumber()}")
    canvas.setStrokeColor(_GRID_COLOR)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.restoreState()


def known_codes() -> frozenset[str]:
    """Todos los códigos servibles, sea por overlay o generados. Es lo que mira
    quien valida una fila de `onboarding_documents` antes de intentar servirla."""
    return frozenset(_OVERLAY_SPECS) | frozenset(BUILDERS)


def build_signable_document_pdf(code: str, data: SignableDocumentData) -> bytes:
    """PDF del documento `code` rellenado con `data`, en memoria.

    Dos caminos según el documento (ver el docstring del módulo): OVERLAY sobre el
    PDF original de RRHH cuando existe —el caso bueno— y generación desde cero
    mientras no lo haya.

    `KeyError` si el `code` no está en ninguno de los dos registros — lo traduce a
    un error de dominio quien la llama, porque significa que una fila de
    `onboarding_documents` apunta a un documento que no existe."""
    if code in _OVERLAY_SPECS:
        return _render_overlay(code, data)

    builder = BUILDERS[code]
    flowables, title = builder(data)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=title,
        author="Amelia Hub",
        subject="Documentación laboral del onboarding",
    )
    # El pie lleva el título del documento y el número de página: estos PDF se
    # imprimen y se firman, y una hoja suelta sin identificar no vale de nada.
    doc.build(
        flowables,
        onFirstPage=lambda c, d: _footer(c, d, title),
        onLaterPages=lambda c, d: _footer(c, d, title),
    )
    return buffer.getvalue()


def _collect_text(flowables: list) -> list[str]:
    """Texto de todos los `Paragraph` del árbol, en orden de aparición.

    Recursivo porque el texto no está solo al primer nivel: las fichas del RGPD
    y los bloques de firma son `Table` con párrafos dentro de las celdas, y los
    bloques que no deben partirse van envueltos en `KeepTogether`."""
    texts: list[str] = []
    for item in flowables:
        if isinstance(item, Paragraph):
            texts.append(item.text)
        elif isinstance(item, Table):
            # `_cellvalues` es la rejilla tal como se pasó al constructor: filas
            # de celdas, y una celda puede ser un str, un flowable o una lista.
            for row in item._cellvalues:
                for cell in row:
                    if isinstance(cell, str):
                        texts.append(cell)
                    elif isinstance(cell, list):
                        texts.extend(_collect_text(cell))
                    else:
                        texts.extend(_collect_text([cell]))
        elif isinstance(item, KeepTogether):
            texts.extend(_collect_text(list(item._content)))
    return texts


def template_hash(code: str) -> str:
    """SHA-256 de la PLANTILLA de `code` — nunca del PDF servido.

    Es lo que se guarda en `onboarding_documents.content_hash` para poder
    responder después a "qué documento aceptó esta persona" cuando cambie de
    versión.

    Dos fuentes, según cómo se produzca el documento:

    - OVERLAY: el hash del PDF BASE de RRHH, tal cual está en disco. Es el ideal
      —es el documento de verdad, byte a byte— y encima vigila lo que más importa
      vigilar: si RRHH entrega otra versión del fichero, el hash cambia y avisa de
      que hay que volver a medir las coordenadas de `_OVERLAY_SPECS`, que están
      atadas a ESE fichero.

    - GENERADO: el hash del TEXTO producido con datos vacíos y fecha fija. NO del
      PDF, y no es un detalle: `reportlab` estampa `/CreationDate` y `/ModDate` en
      cada render, así que dos ejecuciones del mismo documento dan binarios
      distintos y el valor guardado en la migración dejaría de cuadrar al día
      siguiente. (Se descartó `invariant=1` de reportlab, que quita los
      timestamps: seguiría atando el hash al LAYOUT, y mover un margen no cambia
      lo que la persona acepta.)

    En los dos casos el resultado depende solo del documento: ni de quién lo
    descarga, ni de cuándo."""
    if code in _OVERLAY_SPECS:
        filename, _title, _fields = _OVERLAY_SPECS[code]
        return hashlib.sha256((_TEMPLATES_DIR / filename).read_bytes()).hexdigest()

    flowables, title = BUILDERS[code](
        SignableDocumentData(full_name="", issued_on=date(2026, 1, 1))
    )
    payload = "\n".join([title, *_collect_text(flowables)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
