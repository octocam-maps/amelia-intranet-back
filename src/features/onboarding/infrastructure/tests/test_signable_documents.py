"""Tests del generador de PDF de los documentos firmables del paso 5
(`infrastructure/signable_documents.py`, migración 046).

Lo que de verdad puede fallar aquí y hay que blindar: (1) que un dato de perfil
con markup no reviente el render ni se interprete como formato (SEC-1), (2) que
un campo vacío salga como hueco para rellenar y NO como la cadena "None", y
(3) que `template_hash` sea REPRODUCIBLE — el valor vive en una migración y un
hash que cambia entre ejecuciones no identifica nada."""

import io
from datetime import date
from pathlib import Path

from pypdf import PdfReader

import pytest

from src.features.onboarding.infrastructure.signable_documents import (
    FILENAMES,
    GENERATED_REF_PREFIX,
    SignableDocumentData,
    build_signable_document_pdf,
    code_from_ref,
    is_generated_ref,
    known_codes,
    template_hash,
)


def _pdf_text(code: str, data: SignableDocumentData) -> str:
    """Texto REAL del PDF producido, sea overlay o generado.

    Se lee el resultado final en vez de inspeccionar los flowables: es la única
    forma de comprobar los documentos que van por overlay, donde la parte fija
    viene del PDF de RRHH y no de ningún flowable nuestro."""
    pdf = build_signable_document_pdf(code, data)
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


_FULL = SignableDocumentData(
    full_name="María Jiménez Ortiz",
    issued_on=date(2026, 8, 6),
    dni="47182635Z",
    job_title="Ingeniera de Datos",
    entity_name="Amelia Lab",
    city="Sant Feliu de Llobregat",
)


@pytest.mark.parametrize("code", sorted(known_codes()))
def test_every_document_renders_a_pdf(code):
    pdf = build_signable_document_pdf(code, _FULL)
    assert pdf.startswith(b"%PDF-"), f"{code} no produjo un PDF"
    assert len(pdf) > 1000


@pytest.mark.parametrize("code", sorted(known_codes()))
def test_every_document_has_a_download_filename(code):
    """Sin nombre de fichero, el navegador guardaría el PDF con el id del
    documento — cuatro descargas indistinguibles en la carpeta de descargas."""
    assert FILENAMES[code].endswith(".pdf")


@pytest.mark.parametrize("code", sorted(known_codes()))
def test_template_hash_is_reproducible(code):
    """Dos llamadas dan el MISMO hash. Es la propiedad por la que el hash se
    calcula sobre el texto y no sobre el PDF: `reportlab` estampa
    `/CreationDate` en cada render, así que hashear el binario daba un valor
    distinto cada vez y el guardado en la migración nunca volvía a cuadrar."""
    assert template_hash(code) == template_hash(code)


def test_template_hash_differs_between_documents():
    """Cuatro documentos, cuatro hashes: si colisionaran, `content_hash` no
    distinguiría qué texto aceptó la persona."""
    hashes = {template_hash(code) for code in known_codes()}
    assert len(hashes) == len(known_codes())


@pytest.mark.parametrize("code", sorted(known_codes()))
def test_template_hash_ignores_the_personal_data(code):
    """El hash identifica la REDACCIÓN, no la copia servida: dos personas
    distintas aceptan el mismo documento, así que su hash no puede depender de
    quién lo descarga ni de cuándo."""
    before = template_hash(code)
    build_signable_document_pdf(code, _FULL)
    assert template_hash(code) == before


# ── SEC-1: datos de usuario que llegan como markup ───────────────────────────


@pytest.mark.parametrize("code", sorted(known_codes()))
def test_markup_in_profile_data_does_not_break_the_render(code):
    """`full_name` lo rellena Google OIDC y lo puede editar un admin; `dni` y
    `job_title` los teclea la persona en el paso 4. `Paragraph` interpreta un
    subconjunto de XML, así que una etiqueta sin cerrar reventaría el render."""
    hostile = SignableDocumentData(
        full_name="<b>María</b> & <i>Ortiz",
        issued_on=date(2026, 8, 6),
        dni="<font size=99>X</font>",
        job_title="Jefa de I&D <script>",
        entity_name="Amelia <Lab>",
        city="Sant Feliu & Llobregat",
    )
    pdf = build_signable_document_pdf(code, hostile)
    assert pdf.startswith(b"%PDF-")


def test_user_data_with_markup_is_stamped_literally_on_the_overlay():
    """Sobre el PDF original los datos se dibujan con `canvas.drawString`, que
    pinta la cadena tal cual — un `<b>` no puede convertirse en negrita ni romper
    el render. Se comprueba que llega literal al PDF, no escapado a entidades."""
    hostile = SignableDocumentData(
        full_name="<b>María</b>", issued_on=date(2026, 8, 6), dni="1<2"
    )
    text = _pdf_text("consentimiento-imagenes", hostile)
    assert "<b>María</b>" in text
    assert "&lt;b&gt;" not in text


# ── Campos ausentes ──────────────────────────────────────────────────────────


def test_missing_fields_render_a_blank_line_never_the_string_none():
    """El paso 4 puede completarse sin puesto asignado. Un PDF que imprimiera
    "None" donde va el DNI es un documento que nadie puede firmar."""
    minimal = SignableDocumentData(full_name="María Ortiz", issued_on=date(2026, 8, 6))
    for code in known_codes():
        # Se lee el PDF final y no los flowables: los que van por overlay no tienen
        # flowables, y son justo los que podrían estampar un "None" encima del
        # documento de RRHH.
        assert "None" not in _pdf_text(code, minimal), f"{code} imprimió 'None'"


def test_blank_strings_leave_the_originals_own_blank_untouched():
    """Un campo de solo espacios es tan inservible como uno vacío: no se estampa
    nada y el hueco del documento de RRHH queda intacto, con su línea, para
    rellenarlo a mano.

    Se comprueba que la línea del original SIGUE ahí — si se hubiera escrito un
    espacio encima daría igual, pero si algún día se estampa un "None" o una línea
    nuestra sobre la suya, este test lo ve."""
    blank = SignableDocumentData(
        full_name="María Ortiz", issued_on=date(2026, 8, 6), dni="   ", job_title="   "
    )
    text = " ".join(_pdf_text("compromiso-confidencialidad", blank).split())
    assert "Puesto:" in text
    assert "None" not in text


# ── Contenido acordado con RRHH ──────────────────────────────────────────────


def test_image_consent_keeps_the_companies_of_the_original():
    """SIGUE DICIENDO "AMELIA LAB S.L y AMELIA OPS S.L", y es lo correcto ahora.

    El 2026-08-06 el team-lead decidió sacar a Amelia Ops de la autorización, y
    ese mismo día decidió servir los documentos TAL CUAL los entregó RRHH. Las dos
    cosas no caben juntas: el overlay rellena huecos, no reescribe párrafos. Gana
    "tal cual", así que cambiar las sociedades le toca a RRHH en el .docx.

    Este test existe para que el día que el PDF base cambie se vea aquí, en vez de
    descubrirlo en un documento ya firmado."""
    # Se normalizan los saltos: el párrafo está justificado y la extracción de
    # texto lo devuelve partido en varias líneas.
    text = " ".join(_pdf_text("consentimiento-imagenes", _FULL).split())
    assert "AMELIA LAB S.L y AMELIA OPS" in text


def test_rgpd_information_names_only_the_company_of_the_original():
    """SOLO dice "Amelia Hub", y es lo que toca ahora.

    El team-lead pidió el 2026-08-06 que el RGPD saliera a nombre de Amelia Hub Y
    Amelia Lab, y ese mismo día decidió servir los documentos TAL CUAL los entregó
    RRHH. Su PDF nombra únicamente a Amelia Hub como responsable del tratamiento,
    y el overlay rellena huecos sin reescribir párrafos, así que gana "tal cual".

    Añadir Amelia Lab significa cambiar QUIÉN es el responsable del tratamiento —
    contenido jurídico, no un rótulo— y le toca a RRHH en el .docx. Este test
    documenta el estado real para que la discrepancia no se descubra en un
    documento ya firmado."""
    text = " ".join(_pdf_text("rgpd-informacion", _FULL).split())
    assert "Responsable del tratamiento Amelia Hub" in text
    assert "Amelia Lab" not in text


def test_medical_form_stamps_the_five_profile_fields():
    """El CES de Som Prevenció se rellena con empresa, nombre, fecha, puesto y
    DNI — los cinco huecos de su cabecera."""
    text = _pdf_text("reconocimiento-medico", _FULL)
    for expected in (
        "Amelia Lab",
        "María Jiménez Ortiz",
        "Ingeniera de Datos",
        "47182635Z",
        "6 de agosto de 2026",
    ):
        assert expected in text, f"falta {expected!r}"


def test_medical_form_is_the_providers_own_document():
    """Es el formulario de Som Prevenció, no una réplica: se comprueba por su
    código de revisión y su marca, que solo pueden venir del PDF original.

    Importa porque el documento se les remite firmado para su archivo, y una
    reconstrucción parecida —que es lo que había antes— pueden rechazarla."""
    # Espacios normalizados: el original justifica el texto y la extracción lo
    # devuelve partido, así que "DOY MI CONSENTIMIENTO" llega con un salto en medio.
    text = " ".join(_pdf_text("reconocimiento-medico", _FULL).split())
    assert "CES" in text
    assert "prevenció" in text.lower()
    # Las DOS casillas (SÍ y NO) están presentes y ninguna marcada: el Art. 22
    # LPRL exige que el consentimiento sea voluntario, así que el sistema no puede
    # presuponer la respuesta.
    assert text.count("DOY MI CONSENTIMIENTO") == 2


def test_dates_are_written_in_spanish_regardless_of_locale():
    """El mes se resuelve con una tabla propia y no con `strftime('%B')`, que en
    el contenedor de producción (locale C) devolvería "August"."""
    text = _pdf_text("reconocimiento-medico", _FULL)
    assert "6 de agosto de 2026" in text
    assert "August" not in text


# ── Helpers de `storage_ref` ─────────────────────────────────────────────────


def test_is_generated_ref_distinguishes_generated_from_static():
    assert is_generated_ref(f"{GENERATED_REF_PREFIX}rgpd-informacion") is True
    assert is_generated_ref("/manuales/manual-clickup-2026-ES.pdf") is False
    assert is_generated_ref(None) is False
    assert is_generated_ref("") is False


def test_code_from_ref_strips_the_prefix():
    assert code_from_ref("generated:rgpd-informacion") == "rgpd-informacion"


def test_every_builder_code_is_reachable_from_a_storage_ref():
    """Cada generador tiene que ser alcanzable desde el `storage_ref` que
    siembra la migración 046 — un documento al que no apunte ninguna fila es
    código muerto, y una fila sin documento es un 404 en producción."""
    for code in known_codes():
        assert code_from_ref(f"{GENERATED_REF_PREFIX}{code}") == code


def test_template_hashes_match_the_ones_seeded_in_the_database():
    """El `content_hash` sembrado tiene que ser el que produce el código HOY, para
    LOS CUATRO documentos.

    Itera sobre `known_codes()` y no sobre `BUILDERS`: cuando el consentimiento y
    el CES pasaron a overlay salieron de `BUILDERS`, y este test —que entonces
    recorría ese diccionario— dejó de cubrirlos sin que nada avisara. Justo el tipo
    de pérdida de cobertura que el test pretende evitar en los datos.

    Se busca en TODAS las migraciones porque los hashes se han corregido en varias:
    la 046 los sembró y la 048 corrigió los dos que pasaron a overlay. Basta con que
    el valor vigente aparezca en alguna.

    El fallo que previene es silencioso: quien retoque la redacción de un documento
    generado, o sustituya un PDF base por otra versión de RRHH, cambia su hash y
    deja la fila apuntando a algo que ya no existe, sin que nada se rompa en
    ejecución. Si este test falla, hay que añadir una migración que actualice el
    hash Y reflejarlo en `init.sql` — nunca editar una migración ya aplicada."""
    migrations = Path(__file__).resolve().parents[4].parent / "database" / "migrations"
    sql = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(migrations.glob("*.sql"))
    )
    init = (
        Path(__file__).resolve().parents[4].parent / "database" / "init.sql"
    ).read_text(encoding="utf-8")

    for code in sorted(known_codes()):
        digest = template_hash(code)
        assert digest in sql, (
            f"El hash de «{code}» ({digest[:12]}…) no está en ninguna migración. "
            "Si el documento cambió a propósito, añade una migración que actualice "
            "su content_hash."
        )
        # `init.sql` es lo que crea una base NUEVA: si se queda con el hash viejo,
        # producción y un entorno recién levantado dejan de coincidir.
        assert digest in init, (
            f"El hash de «{code}» ({digest[:12]}…) falta en init.sql, que es lo que "
            "inicializa una base de datos nueva."
        )
