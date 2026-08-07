"""
Caso de uso: baja DEFINITIVA de una persona de la plantilla.

Es un borrado lógico con anonimización, no un `DELETE`. Las dos obligaciones
que lo definen tiran en direcciones opuestas y por eso el resultado es un
punto intermedio, no una de las dos:

- **Conservar**: el registro de jornada del art. 34.9 ET se guarda 4 años, y
  `users` es el nodo raíz de fichajes, ausencias y documentos firmados. Un
  `DELETE` real dispararía `ON DELETE CASCADE` y se llevaría por delante
  justo lo que hay que conservar.
- **Minimizar** (RGPD): el DNI, el IBAN, el número de la Seguridad Social, la
  dirección o el contacto de emergencia dejan de tener finalidad en cuanto la
  persona se va. Conservarlos "por si acaso" es exactamente lo que el
  principio de minimización prohíbe.

Resultado: se marca `deleted_at`, se BORRAN los datos personales sin
finalidad, y se CONSERVAN `full_name` y el historial laboral. El nombre se
mantiene a propósito: sin él, el informe de RRHH de los últimos 4 años
mostraría filas sin dueño y dejaría de cumplir su función.

El email se LIBERA (se renombra con un sufijo) para que la misma persona pueda
volver a darse de alta si reingresa — `users.email` es UNIQUE y sin esto el
alta fallaría con un duplicado contra una ficha que ya nadie ve.

Es admin-only; el guard vive en el router (`require_role("administrador")`).
"""

import logging

from ...domain.errors import (
    CannotDeleteLastAdminError,
    CannotDeleteYourselfError,
    StaffMemberNotFoundError,
)
from ...domain.ports import ISessionRevoker, IStaffRepository

logger = logging.getLogger(__name__)


class DeleteStaffMemberUseCase:
    def __init__(self, repository: IStaffRepository, session_revoker: ISessionRevoker):
        self._repository = repository
        self._session_revoker = session_revoker

    async def execute(self, *, user_id: str, requester_id: str) -> None:
        member = await self._repository.find_by_id(user_id)
        if member is None:
            raise StaffMemberNotFoundError("No existe una persona con ese identificador.")

        if user_id == requester_id:
            raise CannotDeleteYourselfError(
                "No puedes darte de baja a ti mismo. Pídeselo a otro administrador."
            )

        # Se comprueba EXCLUYÉNDOLO a él: la pregunta no es "¿hay admins?" sino
        # "¿quedará alguno cuando este se vaya?".
        if member.role_code == "administrador":
            remaining = await self._repository.count_active_admins(excluding_user_id=user_id)
            if remaining == 0:
                raise CannotDeleteLastAdminError(
                    "Es el único administrador activo: la intranet se quedaría sin nadie "
                    "que pueda administrarla. Nombra a otro antes de darle de baja."
                )

        await self._repository.soft_delete_member(user_id)

        # Después del borrado, no antes: si el borrado falla, la persona sigue
        # de alta y no tiene sentido haberla echado de su sesión. El orden
        # inverso dejaría a alguien con la cuenta activa pero sin poder entrar.
        revoked = await self._session_revoker.revoke_all_sessions_for_user(user_id)
        logger.info(
            "Baja definitiva de user_id=%s ejecutada por %s (%s sesiones revocadas)",
            user_id,
            requester_id,
            revoked,
        )
