"""
Esqueleto arquitectónico del adaptador SendGrid — deja el hueco para un
proveedor real SIN implementarlo. Restricción dura del proyecto para esta
fase: la API key de SendGrid es de RRHH, no se lee ni se usa, y este
adaptador NO hace ninguna petición de red. `factory.get_email_sender()` no
lo instancia — solo existe para que el día que se habilite un proveedor real
el cambio sea "implementar `send()` aquí", no rediseñar el puerto.
"""

from typing import Any, Optional

from ..domain.entities import EmailResult


class SendGridEmailSender:
    def __init__(self, api_key: str, from_email: str):
        raise NotImplementedError(
            "SendGridEmailSender no está implementado en esta fase — la API key de "
            "SendGrid es de RRHH y no se toca. Usa EMAIL_PROVIDER=mock (default)."
        )

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        raise NotImplementedError
