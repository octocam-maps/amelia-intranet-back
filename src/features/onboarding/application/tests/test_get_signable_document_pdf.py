"""Tests de `GetSignableDocumentPdfUseCase` — la descarga de los documentos del
paso 5 rellenados con los datos del perfil.

POR QUÉ EXISTE ESTE FICHERO: no existía, y su ausencia dejó pasar a producción un
fallo que rompía los CUATRO documentos. El caso de uso validaba el documento contra
`BUILDERS` (los que se generan desde cero) y no contra `known_codes()` (esos MÁS los
que van por overlay sobre el PDF de RRHH). El día que los cuatro pasaron a overlay,
`BUILDERS` se quedó vacío y el endpoint empezó a responder "El documento «…» está
mal configurado" a peticiones perfectamente válidas.

Había 33 tests del GENERADOR (`test_signable_documents.py`) y todos seguían verdes:
`build_signable_document_pdf` funcionaba de maravilla. Lo que nadie probaba era el
camino que va de una fila de `onboarding_documents` hasta ese generador — y ahí
estaba el fallo.

De ahí que estos tests usen los `storage_ref` REALES que siembra la migración 046 y
no un `generated:cualquier-cosa`: el valor de este fichero está en recorrer la
misma configuración que hay en la base de datos.
"""

from dataclasses import replace
from datetime import date

import pytest

from src.features.onboarding.application.use_cases.get_signable_document_pdf import (
    GetSignableDocumentPdfUseCase,
)
from src.features.onboarding.domain.entities import OnboardingDocument
from src.features.onboarding.domain.errors import OnboardingDocumentNotFoundError
from src.features.profile.domain.entities import UserProfile

# Los CUATRO documentos tal como los siembra `046_documentos_rrhh_2026.sql`, con su
# `storage_ref` literal. Si alguien añade un quinto a la migración y no lo añade
# aquí, `test_every_seeded_document_is_downloadable` no lo cubrirá — pero el que
# vigila que no falte ninguno es
# `test_signable_documents.py::test_every_builder_code_is_reachable_from_a_storage_ref`.
SEEDED_DOCUMENTS = [
    ("generated:rgpd-informacion", "Información sobre protección de datos personales"),
    (
        "generated:compromiso-confidencialidad",
        "Compromiso de confidencialidad y protección de datos",
    ),
    (
        "generated:consentimiento-imagenes",
        "Consentimiento para la cesión de imágenes y datos personales",
    ),
    ("generated:reconocimiento-medico", "Consentimiento para el examen de salud"),
]

_MANUAL = OnboardingDocument(
    id="doc-manual",
    kind="manual",
    title="Protocolo de prevención del acoso",
    version=1,
    content_hash="ab" * 32,
    storage_ref="/manuales/protocolo-acoso-amelia-2026.pdf",
    is_active=True,
    display_order=4,
)


def _document(storage_ref: str, title: str, **overrides) -> OnboardingDocument:
    base = OnboardingDocument(
        id=f"doc-{storage_ref.split(':')[-1]}",
        kind="signature",
        title=title,
        version=1,
        content_hash="cd" * 32,
        storage_ref=storage_ref,
        is_active=True,
    )
    return replace(base, **overrides) if overrides else base


class _FakeOnboardingRepository:
    def __init__(self, documents: list[OnboardingDocument]):
        self._documents = documents

    async def find_active_documents(self, kind: str) -> list[OnboardingDocument]:
        return [d for d in self._documents if d.kind == kind and d.is_active]


class _FakeProfileRepository:
    def __init__(self, profile: UserProfile | None):
        self._profile = profile

    async def find_profile_by_user_id(self, user_id: str) -> UserProfile | None:
        return self._profile


def _profile(**overrides) -> UserProfile:
    defaults = dict(
        id="user-1",
        email="lucia.serrano@ameliahub.com",
        full_name="Lucía Serrano Peña",
        avatar_url=None,
        role_code="empleado",
        job_title="Técnica de Inspección Solar",
        hire_date=date(2026, 3, 2),
        entity_name="Amelia Lab",
        department_name="Operaciones",
        manager_name="Beatriz Luna Sánchez",
        is_external=False,
        phone="600111222",
        city="Sant Feliu de Llobregat",
        dni_nie="46982317K",
        birth_date=date(1994, 5, 11),
        address="Carrer Major 14",
        company_phone=None,
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


# Centinela para distinguir "no me pasaron perfil" de "me pasaron None A PROPÓSITO".
# Con `profile=None` como default, el `or _profile()` de antes convertía el None
# intencionado en un perfil válido y el test del perfil ausente no probaba nada:
# pasaba en verde sin ejercitar la rama.
_OMITIDO = object()


def _use_case(documents=None, profile=_OMITIDO) -> GetSignableDocumentPdfUseCase:
    docs = (
        documents
        if documents is not None
        else [_document(ref, title) for ref, title in SEEDED_DOCUMENTS] + [_MANUAL]
    )
    return GetSignableDocumentPdfUseCase(
        _FakeOnboardingRepository(docs),
        _FakeProfileRepository(_profile() if profile is _OMITIDO else profile),
    )


# ── El caso que se rompió ────────────────────────────────────────────────────


@pytest.mark.parametrize("storage_ref,title", SEEDED_DOCUMENTS)
@pytest.mark.asyncio
async def test_every_seeded_document_is_downloadable(storage_ref, title):
    """LOS CUATRO documentos de la migración se sirven. Este es el test que
    faltaba: con la validación contra `BUILDERS` los cuatro respondían "está mal
    configurado", y los 33 tests del generador seguían en verde."""
    use_case = _use_case()

    pdf, filename = await use_case.execute(
        user_id="user-1",
        document_id=f"doc-{storage_ref.split(':')[-1]}",
        today=date(2026, 8, 6),
    )

    assert pdf.startswith(b"%PDF-"), f"{title} no devolvió un PDF"
    assert len(pdf) > 1000
    assert filename.endswith(".pdf")


@pytest.mark.asyncio
async def test_the_pdf_carries_the_profile_data():
    """Lo que hace útil la descarga: que el PDF llegue RELLENADO. Se comprueba en
    el CES, que es el que recoge los cinco campos."""
    from io import BytesIO

    from pypdf import PdfReader

    use_case = _use_case()
    pdf, _ = await use_case.execute(
        user_id="user-1",
        document_id="doc-reconocimiento-medico",
        today=date(2026, 8, 6),
    )
    text = " ".join(
        " ".join((p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages).split()
    )

    for expected in (
        "Amelia Lab",
        "Lucía Serrano Peña",
        "Técnica de Inspección Solar",
        "46982317K",
        "6 de agosto de 2026",
    ):
        assert expected in text, f"falta {expected!r} en el PDF servido"


# ── Lo que NO debe servirse ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_manual_is_not_downloadable_from_here():
    """Este endpoint es solo para los `signature`. Los manuales se sirven como
    asset estático desde `public/manuales/`, y pedirlos por aquí no debe colarse
    aunque el id exista."""
    use_case = _use_case()

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(user_id="user-1", document_id="doc-manual")


@pytest.mark.asyncio
async def test_unknown_document_id_is_rejected():
    use_case = _use_case()

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(user_id="user-1", document_id="no-existe")


@pytest.mark.asyncio
async def test_inactive_document_is_not_served():
    """Un documento retirado (`is_active=False`) no se descarga aunque se pida por
    su id: es lo que hace la migración 046 con el placeholder anterior."""
    retirado = _document(
        "generated:consentimiento-imagenes",
        "Consentimiento para la cesión de imágenes y datos personales",
        is_active=False,
    )
    use_case = _use_case(documents=[retirado])

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(user_id="user-1", document_id=retirado.id)


@pytest.mark.asyncio
async def test_document_without_generated_ref_is_not_served():
    """Una fila `signature` con `storage_ref` a NULL es el placeholder de "RRHH
    todavía no lo ha publicado": no hay nada que generar y se dice, en vez de
    devolver un PDF vacío que oculte una fila a medio configurar."""
    sin_publicar = OnboardingDocument(
        id="doc-sin-publicar",
        kind="signature",
        title="Documentación laboral",
        version=1,
        content_hash="de" * 32,
        storage_ref=None,
        is_active=True,
    )
    use_case = _use_case(documents=[sin_publicar])

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(user_id="user-1", document_id=sin_publicar.id)


@pytest.mark.asyncio
async def test_ref_pointing_to_a_document_that_does_not_exist_is_rejected():
    """`generated:` con un código que no está en ningún registro: una migración a
    medias. Es el error que el mensaje "está mal configurado" SÍ debe describir."""
    roto = _document("generated:documento-inventado", "Documento inventado")
    use_case = _use_case(documents=[roto])

    with pytest.raises(OnboardingDocumentNotFoundError, match="mal configurado"):
        await use_case.execute(user_id="user-1", document_id=roto.id)


@pytest.mark.asyncio
async def test_missing_profile_is_rejected():
    """Sin perfil no hay datos con los que rellenar. Pasa si el usuario se borra
    entre que se emite el JWT y se pide el documento."""
    use_case = _use_case(profile=None)

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(
            user_id="user-1", document_id="doc-reconocimiento-medico"
        )


@pytest.mark.asyncio
async def test_incomplete_profile_still_produces_a_pdf():
    """El paso 4 puede completarse sin puesto o sin DNI. El documento se sirve
    igual, con el hueco del original intacto para rellenarlo a mano — negarle la
    descarga por un dato ausente lo dejaría atascado sin poder terminar."""
    use_case = _use_case(profile=_profile(dni_nie=None, job_title=None, city=None))

    pdf, _ = await use_case.execute(
        user_id="user-1", document_id="doc-consentimiento-imagenes"
    )

    assert pdf.startswith(b"%PDF-")
