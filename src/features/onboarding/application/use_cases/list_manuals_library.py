"""
Caso de uso: biblioteca de manuales de uso, accesible a TODOS los usuarios
(petición del 2026-07-31).

Distinto del paso 3 del onboarding en dos cosas, y las dos importan:

1. **Alcance**: todos los manuales activos, incluidos los que no hay que confirmar
   (`requires_acknowledgement = FALSE`, migración 043). El paso 3 solo ve la
   cascada obligatoria.
2. **Sin cascada**: aquí no se bloquea nada. El team-lead eligió que la puerta de
   ClickUp aplique DENTRO del paso 3, no a la consulta — y tiene sentido: la
   acreditación de lectura sigue exigiéndose en orden en el onboarding, pero
   negarle a alguien abrir un PDF que ya leyó, o que necesita consultar para
   trabajar, no protegería nada.

Se marca cuáles ya confirmó el usuario, que es información suya y le sirve para
saber qué le queda pendiente de su onboarding.
"""

from ...domain.entities import OnboardingDocument
from ...domain.ports import IOnboardingRepository


class ListManualsLibraryUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self, *, user_id: str
    ) -> list[tuple[OnboardingDocument, bool]]:
        documents = await self._repository.list_manuals_library()
        if not documents:
            return []

        # Los ids confirmados son de ESTE usuario: nadie ve el progreso de lectura
        # de otro desde aquí.
        acknowledged_ids = await self._repository.list_acknowledged_document_ids(
            user_id, "manual"
        )
        return [(document, document.id in acknowledged_ids) for document in documents]
