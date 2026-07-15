"""
Caso de uso: reportar el progreso del vídeo del paso 1 (Opción A del
requerimiento: "no-skip"). Solo acepta progreso monotónico creciente, con
saltos razonables por request Y acorde al tiempo real transcurrido desde que
empezó a reportarse — un salto de golpe a 100 desde un valor bajo (el caso
explícito del requerimiento: 0 -> 100), o varias requests rápidas que
encadenan saltos pequeños sin dejar pasar tiempo real, se rechazan como
intento de saltar el vídeo sin verlo. Al llegar a ~100 marca el paso
`completed` y desbloquea el siguiente.
"""

from datetime import datetime, timezone

from ...domain.entities import OnboardingProgress
from ...domain.errors import (
    InvalidVideoProgressError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import (
    MAX_VIDEO_PROGRESS_JUMP_PCT,
    ensure_step_allowed_for_role,
    ensure_step_operable,
    ensure_video_progress_matches_elapsed_time,
)
from ...domain.ports import IOnboardingRepository


class UpdateVideoProgressUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self, *, user_id: str, role: str, step_id: str, new_pct: int
    ) -> OnboardingProgress:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "video":
            raise WrongStepTypeError("Este paso no es de tipo vídeo.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        current = ensure_step_operable(current)

        if new_pct < current.progress_pct:
            raise InvalidVideoProgressError(
                "El progreso del vídeo no puede retroceder."
            )

        jump = new_pct - current.progress_pct
        if jump > MAX_VIDEO_PROGRESS_JUMP_PCT:
            raise InvalidVideoProgressError(
                "El salto de progreso reportado no es válido"
                " — el vídeo no se puede saltar."
            )

        ensure_video_progress_matches_elapsed_time(
            progress=current,
            step=step,
            new_pct=new_pct,
            now=datetime.now(timezone.utc),
        )

        updated = await self._repository.update_video_progress(
            user_id, step_id, new_pct=new_pct
        )
        if updated is None:
            # El paso pasó a no-operable entre el chequeo y el UPDATE (p.ej.
            # otra petición concurrente ya lo completó) — mismo contrato que
            # el resto de UPDATE atómicos condicionados del proyecto.
            raise InvalidVideoProgressError(
                "El paso ya no admite actualizaciones de progreso."
            )

        if updated.status == "completed":
            await self._repository.unlock_next_step(user_id, step.step_order)

        return updated
