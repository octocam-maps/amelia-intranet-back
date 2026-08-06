"""
Caso de uso: completar el paso de documentación subiendo el PDF ya firmado
FUERA de la plataforma (sustituye a la firma nativa, `sign_document.py`,
eliminado — sdd/docs-firmados-upload-drive).

Desde la reordenación de v1.1 (`033_onboarding_steps_reorder_v11.sql`) este
es EL ÚLTIMO paso (`step_order=5`, antes era el 3): el trabajador llega aquí
habiendo visto el vídeo, aprobado el cuestionario, leído los manuales y
completado su perfil, y al subir su documentación firmada CIERRA el
onboarding. De ahí la llamada a `NotifyOnboardingCompletedUseCase` al final
—que comprueba el estado real, no asume que este paso sea el último—.

El binario/categoría/MIME/tamaño/Drive los
resuelve `UploadDocumentUseCase` COMPLETO (feature `documents`), inyectado
aquí como servicio de aplicación (D1: reuso cruzado de un "Open Host
Service", mismo criterio que `documents` ya reutiliza
`PostgresStaffRepository` de `staff`) — este caso de uso NO duplica
folder-caching, persistencia de `employee_documents` ni la notificación.

Lo único propio de onboarding es el enlace `onboarding_document_uploads`
(D3): sin él, `employee_documents.category='signed'` no distingue "esto
satisfizo el paso de documentación de ESTE usuario" de un `signed` suelto que
un admin subiera vía `POST /documents` por otro motivo.

`user_id` SIEMPRE llega del JWT (nunca de un campo del payload) — este caso
de uso ni siquiera declara un parámetro alternativo para el dueño del
documento, así que no hay canal para suplantar a otro usuario.
"""

from typing import Optional

from src.features.documents.application.use_cases.upload_document import (
    UploadDocumentUseCase,
)
from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import OnboardingDocumentUpload
from ...domain.errors import (
    OnboardingDocumentNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import (
    are_all_documents_satisfied,
    ensure_step_allowed_for_role,
    ensure_step_operable,
)
from ...domain.ports import IOnboardingRepository
from .notify_onboarding_completed import NotifyOnboardingCompletedUseCase


def _drive_filename(title: str, fallback: str) -> str:
    """Nombre del PDF firmado dentro de `{email}/Firmados/` en Drive.

    Se deriva del título del documento para que la carpeta sea legible: quien la
    abre (RRHH) tiene que poder decir de un vistazo qué documento es cada fichero,
    y el nombre que trae el navegador no lo dice.

    `fallback` es el nombre que subió el cliente, y se usa solo si el título no
    da un nombre utilizable (vacío o de solo espacios). No se ignora del todo a
    propósito: un parámetro que nunca se usa hace creer al siguiente que lea la
    ruta que el nombre del cliente se respeta.

    Solo se sanean `/` y `\\`: en Drive un nombre con barra no crea jerarquía pero
    se muestra escapado y confunde. Los acentos y los espacios se conservan a
    propósito — es un nombre para leerlo, no un identificador."""
    safe = title.replace("/", "-").replace("\\", "-").strip()
    if not safe:
        return fallback
    return f"{safe}.pdf"


class UploadSignedOnboardingDocumentUseCase:
    def __init__(
        self,
        repository: IOnboardingRepository,
        upload_document_use_case: UploadDocumentUseCase,
        notify: Optional[NotifyUseCase] = None,
    ):
        self._repository = repository
        self._upload_document = upload_document_use_case
        # Opcional (mismo criterio que el resto de los casos de uso con
        # notificación) para no obligar a los tests que solo verifican la
        # subida a construir un notificador.
        self._notify_completion = (
            NotifyOnboardingCompletedUseCase(repository, notify)
            if notify is not None
            else None
        )

    async def execute(
        self,
        *,
        user_id: str,
        role: str,
        step_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
        document_id: Optional[str] = None,
    ) -> OnboardingDocumentUpload:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "signature":
            raise WrongStepTypeError("Este paso no es de tipo firma.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current, role)

        signature_documents = await self._repository.find_active_documents("signature")
        if not signature_documents:
            raise OnboardingDocumentNotFoundError(
                "Todavía no hay un documento de firma configurado."
            )

        # `document_id` opcional por compatibilidad: hasta la migración 046 el paso
        # tenía UN solo documento y el cliente no tenía nada que elegir, así que
        # una llamada sin id sigue resolviéndose sola mientras haya exactamente
        # uno. Con varios, adivinar sería peor que fallar — subir el consentimiento
        # de imágenes y que el sistema lo apunte como el RGPD deja el paso cerrado
        # con documentos cruzados y sin forma de detectarlo.
        if document_id is None:
            if len(signature_documents) > 1:
                raise OnboardingDocumentNotFoundError(
                    "Indica a qué documento corresponde el archivo firmado."
                )
            document = signature_documents[0]
        else:
            document = next(
                (d for d in signature_documents if d.id == document_id), None
            )
            if document is None:
                raise OnboardingDocumentNotFoundError(
                    "Ese documento no forma parte de este paso."
                )

        # Delega TODA la validación (categoría/MIME/tamaño), Drive y
        # `employee_documents` en el use case compartido — si lanza
        # (MIME inválido, archivo demasiado grande), el paso NO se completa
        # y no se crea ningún enlace: mismo criterio "todo o nada por
        # intento" que ya tenía el flujo admin.
        uploaded = await self._upload_document.execute(
            user_id=user_id,
            uploaded_by=user_id,
            category="signed",
            title=document.title,
            period=None,
            # Nombre derivado del DOCUMENTO, no el que traiga el navegador.
            #
            # `UploadDocumentUseCase` usa este `filename` tal cual como nombre del
            # fichero en Drive (`{email}/Firmados/{filename}`). Con un único
            # documento daba igual, pero desde la 046 son CUATRO: si alguien sube
            # sus cuatro escaneos llamados `scan.pdf`, la carpeta queda con cuatro
            # PDF indistinguibles — y Drive no los sobrescribe, admite nombres
            # repetidos, así que RRHH se encuentra cuatro ficheros ambiguos sin
            # saber cuál es el RGPD y cuál el consentimiento de imágenes.
            #
            # En `employee_documents` sí se distinguen (por `title`), así que el
            # problema solo se ve en Drive — que es justo donde lo mira RRHH.
            filename=_drive_filename(document.title, filename),
            content=content,
            mime_type=mime_type,
        )

        upload = await self._repository.create_document_upload(
            user_id=user_id,
            onboarding_document_id=document.id,
            employee_document_id=uploaded.id,
        )

        # El paso NO se cierra con la primera subida: desde la migración 046 son
        # cuatro documentos y hay que subirlos todos. Es la misma regla que el paso
        # 3 aplica a los manuales (`are_all_documents_satisfied`), y por eso es la
        # misma función — antes de la 046 el paso se cerraba con la primera subida
        # porque no había más que un documento.
        #
        # La consulta va DESPUÉS del INSERT a propósito, así que incluye el que se
        # acaba de subir. El orden no importa: solo se pregunta si están todos.
        uploaded_ids = await self._repository.list_uploaded_document_ids(user_id)
        if not are_all_documents_satisfied(signature_documents, uploaded_ids):
            return upload

        completed = await self._repository.mark_step_completed_if_operable(
            user_id, step_id, data={"employee_document_id": uploaded.id}
        )
        if completed is not None:
            await self._repository.unlock_next_step(user_id, step.step_order)

            # Este es el paso que cierra el onboarding completo. Se llama
            # SOLO si el paso pasó de verdad a `completed` (no en un reintento
            # sobre un paso ya cerrado), que es lo que hace innecesaria una
            # guarda de idempotencia aparte.
            if self._notify_completion is not None:
                await self._notify_completion.execute(user_id=user_id, role=role)

        return upload
