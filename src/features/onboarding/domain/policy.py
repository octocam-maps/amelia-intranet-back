"""
Reglas de negocio puras del onboarding — sin SQL, sin FastAPI. Se usan desde
`application/use_cases/*` para no duplicar la ramificación por rol ni el
chequeo de "paso operable" en cada caso de uso.
"""

import re
from dataclasses import replace
from datetime import date, datetime
from typing import Optional

from typing import Any

from src.shared.auth.roles import RoleCode

from .entities import (
    EmployeeOnboardingSnapshot,
    EmployeeOnboardingSummary,
    OnboardingDocument,
    OnboardingProgress,
    OnboardingStep,
    ProfileCompletionData,
    StepDocument,
)
from .errors import (
    IncompleteProfileDataError,
    InvalidStepConfigError,
    InvalidVideoProgressError,
    ManualLockedError,
    QuizAlreadyAttemptedError,
    StepLockedError,
    StepNotAvailableForRoleError,
    StepNotOperableError,
)

# El externo-invitado hace onboarding PARCIAL: solo vídeo + manual
# (docs/permisos-roles.md § Onboarding: "parcial, sin firma/cuestionario/perfil").
# El resto de roles tiene los 5 pasos.
_EXTERNAL_GUEST_ALLOWED_TYPES = frozenset({"video", "manual"})

# El ADMINISTRADOR no está sujeto al bloqueo secuencial (decisión del team-lead,
# 2026-07-31). Sigue teniendo los 5 pasos —los necesita para revisar qué ve la
# plantilla, y el paso de perfil es suyo de verdad— pero puede abrir cualquiera
# sin haber completado el anterior.
#
# POR QUÉ ERA UN BUG: quien administra el onboarding no lo cumple. Para revisar
# el paso 3 (los manuales) Beatriz tenía que ver el vídeo entero sin poder
# adelantarlo y aprobar el cuestionario, con sus 2 intentos contados. Un
# administrador atascado en su propio cuestionario no puede arreglárselo a nadie.
#
# ES UNA EXENCIÓN DE ORDEN, NO DE PERMISO: el administrador ya tenía derecho a
# los 5 pasos; lo único que se le retira es la obligación de recorrerlos en fila.
# El externo-invitado NO entra aquí: a él se le niegan pasos enteros
# (`ensure_step_allowed_for_role`), que es otra cosa.
_ROLES_EXEMPT_FROM_SEQUENTIAL_GATING = frozenset({RoleCode.ADMINISTRADOR})


def is_exempt_from_sequential_gating(role: str) -> bool:
    """Único predicado del que cuelgan las tres puertas del onboarding: el
    estado que se devuelve en `GET /onboarding/me`, el rechazo del POST y el
    candado de la cascada de manuales.

    Uno solo, a propósito. Si el candado de la UI y la validación del POST
    consultaran reglas distintas, el administrador vería un paso abierto que
    responde 422 — o peor, uno cerrado que en realidad podía operar."""
    return role in _ROLES_EXEMPT_FROM_SEQUENTIAL_GATING

# Salto máximo (en puntos de `progress_pct`) que se admite entre dos reportes
# consecutivos del vídeo del paso 1. Cualquier salto mayor —incluido el caso
# explícito del requerimiento, 0 -> 100 de golpe— se rechaza como intento de
# saltar el vídeo sin verlo (Opción A: "no-skip"). El valor es una política de
# producto, no una medición exacta del reproductor: asumimos reportes de
# progreso frecuentes (cada pocos segundos de un vídeo corto) y dejamos
# margen para picos de red, sin permitir terminar el vídeo en un único salto.
MAX_VIDEO_PROGRESS_JUMP_PCT = 30

# Intentos máximos del cuestionario del onboarding. Decisión de producto del
# team-lead (2026-07-29): pasa de UNO a DOS.
#
# Rectifica una regla que estaba escrita como "no negociable" ("el cuestionario
# del paso 2 es de un único intento"). Motivo del cambio: con un solo intento,
# quien falla queda atascado y depende de que un admin le reinicie el intento a
# mano para poder continuar el onboarding.
#
# ESTE es el único sitio donde vive el techo. La BD no lo replica en un CHECK a
# propósito (ver `034_quiz_two_attempts.sql`): lo que sí garantiza la BD, y solo
# ella puede, es que no existan dos intentos con el mismo `attempt_number`
# (`uq_quiz_attempt_per_number`) — el blindaje contra la carrera de doble clic
# que antes daba `UNIQUE(user_id, step_id)`.
MAX_QUIZ_ATTEMPTS = 2

# Margen (en puntos de `progress_pct`) que se admite POR ENCIMA de lo que el
# tiempo real transcurrido justificaría, para absorber picos de red/buffer
# del reproductor y el desfase entre el evento de "play" y el primer
# `POST /video-progress`. Es deliberadamente generoso (no una medición
# exacta del reproductor) para no reventar de falsos positivos con una
# conexión lenta — pero acota el bypass real: 4 requests sin esperar
# (0->29->58->87->100) violan el % de salto máximo por request o, si se
# reparten en llamadas más pequeñas, violan este techo por tiempo real,
# porque entre request y request casi no pasa tiempo de reloj.
VIDEO_PROGRESS_TIME_MARGIN_PCT = 20


def steps_applicable_to_role(
    steps: list[OnboardingStep], role: str
) -> list[OnboardingStep]:
    """Filtra el catálogo de pasos a los que el rol tiene derecho. El GET
    /onboarding/me y la inicialización de progreso SOLO consideran estos
    pasos — el externo-invitado ni siquiera llega a tener una fila de
    progreso para quiz/signature/profile."""
    if role == RoleCode.EXTERNO_INVITADO:
        return [s for s in steps if s.type in _EXTERNAL_GUEST_ALLOWED_TYPES]
    return list(steps)


def ensure_step_allowed_for_role(step: OnboardingStep, role: str) -> None:
    """Ramificación por rol validada en el backend (regla no negociable):
    escribir el endpoint a mano no le da a un externo-invitado acceso a
    quiz/signature/profile."""
    if role == RoleCode.EXTERNO_INVITADO and step.type not in _EXTERNAL_GUEST_ALLOWED_TYPES:
        raise StepNotAvailableForRoleError(
            "Tu invitación no incluye este paso del onboarding."
        )


def ensure_quiz_attempts_left(attempts_used: int) -> None:
    """Rechaza el envío si ya se gastaron los `MAX_QUIZ_ATTEMPTS` intentos.

    Es la salida rápida y con mensaje claro del caso NO concurrente; la
    garantía real bajo concurrencia sigue siendo la UNIQUE de la BD sobre
    `(user_id, step_id, attempt_number)`, porque dos peticiones simultáneas
    pueden pasar las dos por este chequeo con el mismo `attempts_used`."""
    if attempts_used >= MAX_QUIZ_ATTEMPTS:
        raise QuizAlreadyAttemptedError(
            f"Ya has agotado los {MAX_QUIZ_ATTEMPTS} intentos de este cuestionario."
        )


def incorrect_question_ids(
    config: dict[str, Any], answers: dict[str, Any]
) -> list[str]:
    """Ids de las preguntas falladas, EN EL ORDEN del cuestionario.

    Devuelve ids, nunca las respuestas correctas: el cliente ya tiene los
    enunciados (`GET /onboarding/me` manda `questions` con `correct`
    enmascarado, ver `infrastructure/mappers.py::_masked_config`), así que con
    el id puede señalar qué falló sin que el backend filtre la solución. Eso
    importa más ahora que hay un segundo intento — revelar la respuesta
    correcta tras el primero lo convertiría en un trámite.

    Una pregunta sin contestar cuenta como fallada, igual que en `_score`.
    """
    return [
        question["id"]
        for question in config.get("questions", [])
        if answers.get(question["id"]) != question.get("correct")
    ]


def is_onboarding_complete(
    applicable_steps: list[OnboardingStep],
    progress: list[OnboardingProgress],
) -> bool:
    """¿Ha terminado este usuario TODO su onboarding? Verdad calculada sobre
    el estado real, NO inferida de "completó el paso X".

    Esta función existe porque el código anterior daba el onboarding por
    terminado dentro de `CompleteProfileUseCase`, asumiendo que el perfil era
    el último paso (`step_order=5` en el seed 020). Esa suposición se rompió
    con la reordenación de v1.1 (`033_onboarding_steps_reorder_v11.sql`), que
    movió el perfil al 4 y la documentación firmada al 5: RRHH habría
    recibido "onboarding completado" con la documentación todavía sin subir.
    Acoplar el aviso al ESTADO (todos los pasos aplicables completados) y no
    a un paso concreto lo hace inmune a la siguiente reordenación.

    `applicable_steps` DEBE venir ya filtrado por rol
    (`steps_applicable_to_role`): el externo-invitado termina con vídeo +
    manual, y compararlo contra los 5 pasos completos lo dejaría
    eternamente "sin terminar".

    Un catálogo aplicable vacío no es "completo" — es un catálogo mal
    cargado, y disparar el aviso de finalización ahí sería un falso positivo.
    """
    if not applicable_steps:
        return False

    completed_step_ids = {p.step_id for p in progress if p.status == "completed"}
    return all(step.id in completed_step_ids for step in applicable_steps)


def resolve_status_for_role(status: str, role: str) -> str:
    """Estado EFECTIVO de un paso para este rol. `onboarding_progress.status`
    guarda el bloqueo secuencial tal cual, y eso está bien: es el dato real de
    por dónde va la persona. Lo que cambia con el rol es si ese bloqueo le
    aplica.

    Se resuelve al leer y no al escribir en la BD a propósito: si mañana alguien
    deja de ser administrador, su progreso vuelve a bloquearse solo, sin ninguna
    migración de datos que arreglar. Guardar `available` en las filas del admin
    habría dejado el candado abierto para siempre."""
    if status == "locked" and is_exempt_from_sequential_gating(role):
        return "available"
    return status


def resolve_progress_for_role(
    progress: OnboardingProgress, role: str
) -> OnboardingProgress:
    """El progreso tal y como lo debe VER este rol, con el estado efectivo ya
    aplicado. Es lo que viaja en `GET /onboarding/me`, así que el riel de pasos
    del cliente no necesita conocer ninguna regla de rol: pinta el estado que
    recibe, y ese estado ya lo decidió el dominio.

    Devuelve el mismo objeto si no hay nada que cambiar (el caso de casi todo el
    mundo), para no fabricar copias por costumbre."""
    status = resolve_status_for_role(progress.status, role)
    if status == progress.status:
        return progress
    return replace(progress, status=status)


def ensure_step_operable(
    progress: Optional[OnboardingProgress], role: str
) -> OnboardingProgress:
    """Un paso solo admite operaciones (reportar progreso, firmar, confirmar
    lectura, completar perfil) si su estado EFECTIVO para el rol está en
    `available` o `in_progress`. `locked` -> bloqueo secuencial (del que el
    administrador está exento); `completed` -> ya no se repite.

    `progress is None` sigue siendo bloqueo para todo el mundo, exento o no: sin
    fila de progreso no hay paso que operar, y fabricarla aquí escondería un
    fallo de `ensure_progress_initialized`."""
    if progress is None:
        raise StepLockedError(
            "Este paso todavía está bloqueado — completa primero el paso anterior."
        )
    status = resolve_status_for_role(progress.status, role)
    if status == "locked":
        raise StepLockedError(
            "Este paso todavía está bloqueado — completa primero el paso anterior."
        )
    if status == "completed":
        raise StepNotOperableError("Este paso ya está completado.")
    return progress


def ensure_video_progress_matches_elapsed_time(
    *,
    progress: OnboardingProgress,
    step: OnboardingStep,
    new_pct: int,
    now: datetime,
) -> None:
    """Valida el `new_pct` reportado contra el TIEMPO REAL transcurrido desde
    `progress.started_at` — el chequeo de salto máximo por request
    (`MAX_VIDEO_PROGRESS_JUMP_PCT`) por sí solo no evita el bypass real: 4
    requests rápidas y consecutivas (0->29->58->87->100), cada una dentro del
    30% permitido, completan el vídeo sin haberlo visto.

    `progress.started_at is None` significa que este es el PRIMER reporte de
    progreso de este usuario para este paso — todavía no hay una base
    temporal contra la que medir, así que aquí no se valida nada (solo aplica
    el chequeo de salto de `ensure_step_operable`/`MAX_VIDEO_PROGRESS_JUMP_PCT`
    en el use case). El propio UPDATE del repositorio es quien fija
    `started_at` en ese primer reporte.

    Si el paso no trae `duration` en su `config` (no debería pasar para
    `type=video`, pero `config` es JSONB data-driven y no lo garantiza el
    tipo), no se puede calcular el techo — se deja pasar sin validar en vez
    de romper el flujo por un dato de catálogo mal cargado.
    """
    if progress.started_at is None:
        return

    duration_seconds = step.config.get("duration")
    if not duration_seconds:
        return

    elapsed_seconds = (now - progress.started_at).total_seconds()
    allowed_pct = (elapsed_seconds / duration_seconds) * 100 + VIDEO_PROGRESS_TIME_MARGIN_PCT
    if new_pct > allowed_pct:
        raise InvalidVideoProgressError(
            "El progreso reportado va por delante del tiempo real de "
            "reproducción — el vídeo no se puede saltar."
        )


def validate_step_config(step_type: str, config: dict[str, Any]) -> None:
    """Valida coherencia mínima del `config` (JSONB) que el admin edita vía
    `PATCH /onboarding/admin/steps/{id}` — data-driven por `type`, así que
    no hay columna/constraint de BD que lo garantice; se valida aquí antes
    de persistir. Los tipos sin shape obligatorio (`signature`, `manual`,
    `profile`) no se validan: su `config` hoy no se usa para nada crítico."""
    if step_type == "quiz":
        _validate_quiz_config(config)
    elif step_type == "video":
        _validate_video_config(config)


def _validate_quiz_config(config: dict[str, Any]) -> None:
    questions = config.get("questions")
    if not isinstance(questions, list) or not questions:
        raise InvalidStepConfigError(
            "El cuestionario necesita al menos una pregunta en `questions`."
        )

    for question in questions:
        if not isinstance(question, dict):
            raise InvalidStepConfigError("Cada pregunta debe ser un objeto.")

        missing = [
            key for key in ("id", "text", "options", "correct") if key not in question
        ]
        if missing:
            raise InvalidStepConfigError(
                f"Falta el campo {', '.join(missing)} en una pregunta del cuestionario."
            )

        options = question["options"]
        if not isinstance(options, list) or not options:
            raise InvalidStepConfigError(
                "Cada pregunta necesita al menos una opción en `options`."
            )
        if question["correct"] not in options:
            raise InvalidStepConfigError(
                "La respuesta correcta (`correct`) debe ser una de las `options`."
            )

    threshold = config.get("threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise InvalidStepConfigError(
            "El cuestionario necesita un `threshold` numérico entre 0 y 1."
        )
    if not (0 <= threshold <= 1):
        raise InvalidStepConfigError("El `threshold` debe estar entre 0 y 1.")


def _validate_video_config(config: dict[str, Any]) -> None:
    url = config.get("url")
    if not isinstance(url, str) or not url:
        raise InvalidStepConfigError("El vídeo necesita una `url` no vacía.")

    duration = config.get("duration")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or duration <= 0
    ):
        raise InvalidStepConfigError(
            "El vídeo necesita una `duration` numérica positiva (segundos)."
        )


# DNI: 8 dígitos + letra. NIE: X/Y/Z + 7 dígitos + letra. Valida solo el
# FORMATO (no la letra de control real, que requiere el algoritmo módulo 23
# del BOE) — decisión deliberada: el requerimiento (RF §3.5) solo pide "sin
# campos vacíos", no una validación notarial del documento, y el proyecto no
# tiene hoy un helper de letra de control. Si en el futuro se necesita
# verificar la letra, este es el único punto a tocar.
_DNI_NIE_PATTERN = re.compile(r"^(\d{8}[A-Za-z]|[XYZxyz]\d{7}[A-Za-z])$")

# Los 6 campos de texto obligatorios del paso 5 (RF §3.5) — `company_phone`
# es el único opcional ("si aplica") y por eso no está en esta lista.
_REQUIRED_PROFILE_TEXT_FIELDS = (
    "full_name",
    "dni_nie",
    "personal_phone",
    "address",
    "department_id",
)


def ensure_profile_data_complete(profile: ProfileCompletionData) -> None:
    """Anti-vacío server-side del paso 5 ("Completar perfil", RF §3.5):
    rechaza cualquier campo obligatorio ausente, vacío o de solo espacios —
    un `str` de Pydantic no basta por sí solo, y este chequeo es la SEGUNDA
    barrera (además del DTO) para que el use case no dependa únicamente de
    la validación HTTP. "Ocultar ≠ proteger": esto es lo que de verdad
    bloquea el paso, no el formulario del frontend."""
    missing = [
        field
        for field in _REQUIRED_PROFILE_TEXT_FIELDS
        if not str(getattr(profile, field) or "").strip()
    ]
    if missing:
        raise IncompleteProfileDataError(
            "Faltan campos obligatorios del perfil: " + ", ".join(missing) + "."
        )

    if profile.birth_date is None:
        raise IncompleteProfileDataError(
            "La fecha de nacimiento es obligatoria."
        )
    if profile.birth_date >= date.today():
        raise IncompleteProfileDataError(
            "La fecha de nacimiento no es válida."
        )

    if not _DNI_NIE_PATTERN.match(profile.dni_nie.strip()):
        raise IncompleteProfileDataError(
            "El DNI/NIE no tiene un formato válido "
            "(8 dígitos + letra, o X/Y/Z + 7 dígitos + letra)."
        )


# Estados de progreso que cuentan como "todavía sin empezar" a efectos del
# panel de admin — sin filas de progreso (nunca inicializado) o con todas
# sus filas en `locked` (inicializado pero sin tocar ningún paso).
_NOT_STARTED_STATUSES = frozenset({"locked"})
_OPERABLE_STATUSES = frozenset({"available", "in_progress"})


def summarize_employee_onboarding(
    snapshot: EmployeeOnboardingSnapshot, *, total_steps: int
) -> EmployeeOnboardingSummary:
    """Resume el progreso de un empleado para `GET /onboarding/admin/progress`
    — pura lógica de negocio sobre las filas ya unidas por el repositorio
    (`domain` no toca SQL). `total_steps` viene de
    `steps_applicable_to_role` sobre el catálogo — así el externo-invitado
    (onboarding parcial) no aparece eternamente `in_progress` por comparar
    contra los 5 pasos completos."""
    completed_steps = sum(1 for s in snapshot.steps if s.status == "completed")

    not_started = not snapshot.steps or all(
        s.status in _NOT_STARTED_STATUSES for s in snapshot.steps
    )

    if not_started:
        status = "not_started"
    elif completed_steps >= total_steps:
        status = "completed"
    else:
        status = "in_progress"

    current_step = next(
        (
            s
            for s in sorted(snapshot.steps, key=lambda s: s.step_order)
            if s.status in _OPERABLE_STATUSES
        ),
        None,
    )

    return EmployeeOnboardingSummary(
        user_id=snapshot.user_id,
        full_name=snapshot.full_name,
        email=snapshot.email,
        avatar_url=snapshot.avatar_url,
        status=status,
        completed_steps=completed_steps,
        total_steps=total_steps,
        current_step_title=current_step.title if current_step else None,
        # Ordenado por `step_order`: el cliente lo pinta como una fila de estados
        # y no debe tener que reordenarlo.
        steps=sorted(snapshot.steps, key=lambda s: s.step_order),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cascada de manuales del paso 3 (migración 040). Funciones PURAS: reciben los
# documentos y los ids ya confirmados, y no tocan BD. Así la regla —que es lo
# que de verdad puede fallar— se prueba sin Postgres.
# ─────────────────────────────────────────────────────────────────────────────


def sort_manuals(documents: list[OnboardingDocument]) -> list[OnboardingDocument]:
    """Orden de lectura: `display_order` y, a igualdad, `id` para que sea
    ESTABLE. La BD ya garantiza orden único entre manuales activos
    (`uq_onboarding_documents_active_order`), pero un empate entre uno activo y
    otro retirado dejaría el orden a merced de cómo Postgres devuelva las filas,
    y "el siguiente de la cascada" no puede depender de eso."""
    return sorted(documents, key=lambda d: (d.display_order, d.id))


def next_manual_to_acknowledge(
    documents: list[OnboardingDocument], acknowledged_ids: set[str]
) -> Optional[OnboardingDocument]:
    """El primer manual de la cascada que aún no se ha confirmado, o `None` si
    ya están todos. Es el ÚNICO que el trabajador puede confirmar ahora."""
    return next(
        (d for d in sort_manuals(documents) if d.id not in acknowledged_ids), None
    )


def ensure_manual_unlocked(
    documents: list[OnboardingDocument],
    acknowledged_ids: set[str],
    document_id: str,
    role: str,
) -> OnboardingDocument:
    """Puerta del paso 3: solo se puede confirmar el siguiente manual pendiente
    de la cascada. Devuelve el documento validado para que el caso de uso no
    tenga que volver a buscarlo.

    El administrador está exento del ORDEN (`is_exempt_from_sequential_gating`),
    igual que del bloqueo entre pasos: puede abrir el manual que quiera. Lo que
    NO se relaja para nadie es que el documento exista y esté activo.

    Vive en el backend y no solo en el candado de la UI porque un POST directo
    al endpoint de confirmación se saltaría el candado — misma razón por la que
    `ensure_step_allowed_for_role` existe (regla del proyecto: ocultar ≠
    proteger).

    Confirmar dos veces el MISMO manual no es un error: `document_acknowledgements`
    tiene `UNIQUE (user_id, document_id)` y el repositorio hace upsert, así que un
    doble clic es idempotente. Lo que se rechaza es SALTARSE uno.
    """
    ordered = sort_manuals(documents)
    target = next((d for d in ordered if d.id == document_id), None)
    if target is None:
        # Documento que no es un manual activo del paso: lo trata el caso de uso
        # como "no encontrado", no como bloqueado.
        raise ManualLockedError("Ese manual no está disponible en este paso.")

    if document_id in acknowledged_ids or is_exempt_from_sequential_gating(role):
        return target

    pending = [
        d
        for d in ordered
        if d.display_order < target.display_order and d.id not in acknowledged_ids
    ]
    if pending:
        raise ManualLockedError(
            f"Antes de confirmar «{target.title}» tienes que leer "
            f"«{pending[0].title}»."
        )
    return target


def are_all_manuals_acknowledged(
    documents: list[OnboardingDocument], acknowledged_ids: set[str]
) -> bool:
    """RF-A6.3: el paso 3 se cierra solo cuando TODOS los manuales activos están
    confirmados. Antes de la 040 el paso se cerraba con la primera confirmación,
    porque no había más que una.

    Sin manuales configurados devuelve `False`: cerrar el paso porque no hay nada
    que leer dejaría pasar a alguien sin haber leído lo que el paso promete, y el
    caso de uso ya trata "no hay manual" como error de configuración.
    """
    if not documents:
        return False
    return all(d.id in acknowledged_ids for d in documents)


def resolve_step_documents(
    documents: list[OnboardingDocument], acknowledged_ids: set[str], role: str
) -> list[StepDocument]:
    """Los documentos del paso en orden de lectura, cada uno con su estado en la
    cascada para este usuario.

    `locked` es "queda algo anterior sin confirmar", que es EXACTAMENTE la
    condición que rechaza `ensure_manual_unlocked` — incluida la exención del
    administrador, que aquí se consulta con el MISMO predicado. Se derivan de la
    misma función de orden para que no puedan divergir: si el candado dijera una
    cosa y el POST otra, el trabajador vería un botón habilitado que devuelve 422.

    Un documento ya confirmado nunca sale `locked`, aunque falte uno anterior
    (caso posible si RRHH reordena los manuales después de que alguien empiece):
    lo que ya se leyó, leído está.
    """
    ordered = sort_manuals(documents)
    exempt = is_exempt_from_sequential_gating(role)
    result: list[StepDocument] = []
    for index, document in enumerate(ordered):
        acknowledged = document.id in acknowledged_ids
        locked = (
            not acknowledged
            and not exempt
            and any(
                previous.id not in acknowledged_ids for previous in ordered[:index]
            )
        )
        result.append(
            StepDocument(document=document, acknowledged=acknowledged, locked=locked)
        )
    return result
