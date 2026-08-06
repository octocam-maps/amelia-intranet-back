"""
Caso de uso: descargar uno de los documentos del paso 5 ya RELLENADO con los
datos del perfil de quien lo pide.

Es la contrapartida de `upload_signed_document.py`: aquí se entrega el PDF que
la persona tiene que imprimir y firmar, y allí se recibe el firmado. El
contenido se genera al vuelo (`infrastructure/signable_documents.py`) porque
lleva dentro nombre, DNI y puesto de una persona concreta — un fichero estático
en `public/` sería datos personales en una URL adivinable, y el filtrado por
usuario tiene que ocurrir en el backend.

`user_id` SIEMPRE llega del JWT: no hay parámetro para pedir el documento de
otra persona, así que no existe canal para descargarse el DNI de un compañero.
Los datos del perfil los lee este caso de uso con el `user_id` autenticado, no
los recibe.

Depende del PORT de `profile` (no de su implementación): mismo criterio de reuso
cruzado entre features que ya usa `upload_signed_document.py` con
`UploadDocumentUseCase`. El perfil es el dueño legítimo de "los datos de esta
persona" y duplicar esa consulta aquí habría creado una segunda verdad.
"""

from datetime import date

from src.features.profile.domain.ports import IProfileRepository

from ...domain.errors import OnboardingDocumentNotFoundError
from ...domain.ports import IOnboardingRepository
from ...infrastructure.signable_documents import (
    BUILDERS,
    FILENAMES,
    SignableDocumentData,
    build_signable_document_pdf,
    code_from_ref,
    is_generated_ref,
)


class GetSignableDocumentPdfUseCase:
    def __init__(
        self,
        repository: IOnboardingRepository,
        profile_repository: IProfileRepository,
    ):
        self._repository = repository
        self._profiles = profile_repository

    async def execute(
        self, *, user_id: str, document_id: str, today: date | None = None
    ) -> tuple[bytes, str]:
        """Devuelve `(pdf, filename)`.

        `today` se inyecta para que los tests puedan fijar la fecha que sale
        impresa; en producción lo resuelve `date.today()`.

        Solo sirve documentos que estén ENTRE LOS ACTIVOS del paso: pedir por id
        uno retirado o de otro tipo responde "no encontrado". Que el id sea un
        UUID no lo convierte en descargable.
        """
        documents = await self._repository.find_active_documents("signature")
        document = next((d for d in documents if d.id == document_id), None)
        if document is None:
            raise OnboardingDocumentNotFoundError(
                "Ese documento no está disponible en este paso."
            )

        if not is_generated_ref(document.storage_ref):
            # Documento con fichero propio (o sin publicar todavía): no es de los
            # que se rellenan. Quien llama debe servir `storage_ref` tal cual o
            # decir que RRHH aún no lo ha publicado — generar aquí un PDF vacío
            # ocultaría una fila mal configurada.
            raise OnboardingDocumentNotFoundError(
                "Este documento no se genera desde la plataforma."
            )

        code = code_from_ref(document.storage_ref)
        if code not in BUILDERS:
            # La fila apunta a un generador que no existe: es un error de
            # configuración (una migración que quedó a medias), no una petición
            # inválida del usuario.
            raise OnboardingDocumentNotFoundError(
                f"El documento «{document.title}» está mal configurado."
            )

        profile = await self._profiles.find_profile_by_user_id(user_id)
        if profile is None:
            raise OnboardingDocumentNotFoundError("No se encuentra tu perfil.")

        data = SignableDocumentData(
            full_name=profile.full_name,
            issued_on=today or date.today(),
            dni=profile.dni_nie,
            job_title=profile.job_title,
            entity_name=profile.entity_name,
            city=profile.city,
        )
        pdf = build_signable_document_pdf(code, data)
        return pdf, FILENAMES.get(code, f"{code}.pdf")
