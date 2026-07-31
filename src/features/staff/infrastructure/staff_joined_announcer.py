"""
Adaptador de `IStaffJoinedAnnouncer`: el aviso al equipo cuando entra alguien
nuevo (petición del 2026-07-31).

Vive en `infrastructure` de `staff` y no en `domain` porque compone TRES features:
lee el alcance de `email_templates` (migración 042), resuelve destinatarios con el
repositorio de `notifications` y manda el fan-out con `NotifyUseCase`. Mismo
criterio que `_get_session_revoker`, que reutiliza el repositorio de `auth`.

NO SE REINVENTA EL FAN-OUT: `NotifyUseCase.notify_announcement` ya resuelve
destinatarios por audiencia (`all`/`entity`) y manda in-app + email en una sola
llamada, excluyendo SIEMPRE a `externo_invitado`. Duplicar esa lógica aquí habría
creado un segundo camino que se desincronizaría del de anuncios.
"""

from typing import Optional

from src.shared.logger import get_logger

logger = get_logger("staff.staff_joined_announcer")

_TEMPLATE_KEY = "staff_joined_team"

# Alcance por defecto si la plantilla no tiene nada configurado: avisar a toda la
# plantilla es lo que se pidió, y un `None` no debe significar "no avisar" en
# silencio — para eso está `'none'`, que el admin elige a propósito.
_DEFAULT_AUDIENCE = "all"


class StaffJoinedAnnouncer:
    def __init__(self, notify, template_provider_pool):
        self._notify = notify
        # Pool directo y no el `IEmailTemplateProvider`: ese filtra por
        # `is_active = TRUE`, y el ALCANCE tiene que leerse aunque la plantilla
        # esté usando el texto por defecto. Son dos preguntas distintas sobre la
        # misma fila: "¿qué texto uso?" y "¿a quién se lo mando?".
        self._db = template_provider_pool

    async def _resolve_audience(self) -> tuple[str, Optional[str]]:
        try:
            row = await self._db.fetchrow(
                "SELECT audience, audience_entity_id FROM email_templates "
                "WHERE template_key = $1",
                _TEMPLATE_KEY,
            )
        except Exception as exc:  # noqa: BLE001
            # Igual que el proveedor de plantillas: un fallo de lectura no puede
            # tumbar el aviso. Se degrada al alcance por defecto.
            logger.warning(
                "Could not read the team announcement audience, using the default",
                error_type=type(exc).__name__,
            )
            return _DEFAULT_AUDIENCE, None

        if row is None:
            return _DEFAULT_AUDIENCE, None
        audience = row["audience"] or _DEFAULT_AUDIENCE
        entity_id = row["audience_entity_id"]
        return audience, str(entity_id) if entity_id is not None else None

    async def announce(
        self,
        *,
        user_id: str,
        full_name: str,
        job_title: Optional[str],
        entity_id: Optional[str],
        entity_name: Optional[str],
    ) -> None:
        audience, configured_entity_id = await self._resolve_audience()

        if audience == "none":
            # El admin lo apagó a propósito. Se registra para que no parezca un
            # fallo silencioso cuando alguien pregunte por qué no llegó el aviso.
            logger.info(
                "Team announcement is disabled by configuration", user_id=user_id
            )
            return

        # Con alcance `entity`: la entidad configurada manda sobre la de la persona
        # nueva. Si el admin eligió "solo Amelia Lab", un alta en Hub no debe
        # avisar a Hub — eligió Lab, no "la entidad de quien entre".
        target_entity_id = configured_entity_id if audience == "entity" else None

        title = f"Nueva incorporación: {full_name}"
        body_parts = [full_name]
        if job_title:
            body_parts.append(f"se incorpora como {job_title}")
        else:
            body_parts.append("se incorpora al equipo")
        if entity_name:
            body_parts.append(f"en {entity_name}")
        body = " ".join(body_parts) + "."

        await self._notify.notify_announcement(
            audience=audience,
            entity_id=target_entity_id,
            role_id=None,
            type="staff_joined_team",
            title=title,
            body=body,
            data={
                "url": "/equipo",
                # Para que el fan-out pueda excluir al propio recién llegado: no
                # tiene sentido anunciarle su propia incorporación en tercera
                # persona, igual que el cumpleañero no recibe su propio aviso.
                "new_user_id": user_id,
            },
            exclude_user_ids=[user_id],
        )
