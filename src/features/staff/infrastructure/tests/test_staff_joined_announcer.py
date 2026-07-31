"""
`StaffJoinedAnnouncer`: resuelve el alcance configurado y dispara el fan-out.

Se testea con el pool mockeado y un `NotifyUseCase` falso — lo que se prueba es la
DECISIÓN (a quién, y si se manda), no el envío.
"""

from unittest.mock import AsyncMock

import pytest

from src.features.staff.infrastructure.staff_joined_announcer import (
    StaffJoinedAnnouncer,
)


class FakeNotify:
    def __init__(self):
        self.calls: list[dict] = []

    async def notify_announcement(self, **kwargs):
        self.calls.append(kwargs)
        return []


def _pool(audience=None, entity_id=None, *, fails=False):
    pool = AsyncMock()
    if fails:
        pool.fetchrow.side_effect = RuntimeError('column "audience" does not exist')
    else:
        pool.fetchrow.return_value = (
            None
            if audience is None and entity_id is None
            else {"audience": audience, "audience_entity_id": entity_id}
        )
    return pool


async def _announce(pool, notify, **overrides):
    payload = {
        "user_id": "user-9",
        "full_name": "Sandra Ramírez",
        "job_title": "Project Manager",
        "entity_id": "entity-hub",
        "entity_name": "hub",
    }
    payload.update(overrides)
    await StaffJoinedAnnouncer(notify, pool).announce(**payload)


@pytest.mark.asyncio
async def test_audience_all_fans_out_to_the_whole_team():
    notify = FakeNotify()

    await _announce(_pool("all"), notify)

    assert notify.calls[0]["audience"] == "all"
    assert notify.calls[0]["entity_id"] is None
    assert notify.calls[0]["type"] == "staff_joined_team"


@pytest.mark.asyncio
async def test_audience_none_sends_nothing():
    """El admin tiene que poder APAGAR el aviso al equipo sin dejar de mandar la
    bienvenida al recién llegado."""
    notify = FakeNotify()

    await _announce(_pool("none"), notify)

    assert notify.calls == []


@pytest.mark.asyncio
async def test_audience_entity_uses_the_configured_entity_not_the_new_hires():
    """Si el admin eligió "solo Amelia Lab", un alta en Hub NO debe avisar a Hub:
    eligió Lab, no "la entidad de quien entre"."""
    notify = FakeNotify()

    await _announce(
        _pool("entity", "entity-lab"), notify, entity_id="entity-hub", entity_name="hub"
    )

    assert notify.calls[0]["audience"] == "entity"
    assert notify.calls[0]["entity_id"] == "entity-lab"


@pytest.mark.asyncio
async def test_the_new_hire_is_excluded_from_their_own_announcement():
    """No tiene sentido anunciarle su propia incorporación en tercera persona,
    igual que el cumpleañero no recibe su propio cumpleaños."""
    notify = FakeNotify()

    await _announce(_pool("all"), notify, user_id="user-9")

    assert notify.calls[0]["exclude_user_ids"] == ["user-9"]


@pytest.mark.asyncio
async def test_without_configuration_it_defaults_to_the_whole_team():
    """Es lo que se pidió ("aviso a todo el equipo"). Un `None` NO debe significar
    "no avisar" en silencio: para eso está `'none'`, que el admin elige."""
    notify = FakeNotify()

    await _announce(_pool(None), notify)

    assert notify.calls[0]["audience"] == "all"


@pytest.mark.asyncio
async def test_a_database_failure_still_announces_with_the_default_audience():
    """Con la migración sin aplicar o la BD con problemas, el aviso SIGUE
    saliendo. Perder el aviso por no poder leer una preferencia sería peor que
    mandarlo al alcance por defecto."""
    notify = FakeNotify()

    await _announce(_pool(fails=True), notify)

    assert notify.calls[0]["audience"] == "all"


@pytest.mark.asyncio
async def test_the_body_mentions_the_role_and_the_company():
    notify = FakeNotify()

    await _announce(_pool("all"), notify)

    body = notify.calls[0]["body"]
    assert "Sandra Ramírez" in body
    assert "Project Manager" in body
    assert "hub" in body


@pytest.mark.asyncio
async def test_without_a_job_title_the_body_still_reads_well():
    """`job_title` es opcional en el alta: el cuerpo no puede quedar como
    "Sandra se incorpora como ." """
    notify = FakeNotify()

    await _announce(_pool("all"), notify, job_title=None)

    assert "se incorpora al equipo" in notify.calls[0]["body"]
    assert " como ." not in notify.calls[0]["body"]
