"""
Disparador compartido `payslip_available`/`document_uploaded` (RF §6):
`UploadDocumentUseCase` (el admin sube a mano) y `SyncDocumentsUseCase`
(RRHH coloca el archivo en Drive y el sync concilia) crean la MISMA fila de
`employee_documents` vía `IDocumentRepository.create` — este helper evita que
el mapeo categoría->tipo de notificación diverja entre ambos flujos.

Nunca hay doble email por el mismo archivo: cada llamada a `.create()`
inserta una fila NUEVA (un documento nuevo), y ambos use cases ya garantizan
que solo se llama una vez por archivo realmente nuevo (`SyncDocumentsUseCase`
excluye `existing_drive_file_ids` ANTES de llamar a `create`) — así que este
disparador se invoca exactamente una vez por documento creado, nunca dos
veces para el mismo archivo.
"""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ..domain.models import Document

_PAYSLIP_TITLE = "Ya tienes disponible una nueva nómina"
_DOCUMENT_TITLE = "Se subió un nuevo documento a tu carpeta"


async def notify_document_created(notify: Optional[NotifyUseCase], document: Document) -> None:
    if notify is None:
        return

    is_payslip = document.category == "payslip"
    await notify.execute(
        recipient_ids=[document.user_id],
        type="payslip_available" if is_payslip else "document_uploaded",
        title=_PAYSLIP_TITLE if is_payslip else _DOCUMENT_TITLE,
        data={
            "document_id": document.id,
            "category": document.category,
            "title": document.title,
            "url": "/documentos",
        },
    )
