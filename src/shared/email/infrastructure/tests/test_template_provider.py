"""
`PostgresEmailTemplateProvider`: la lectura de plantillas durante el ENVÍO.

Lo único que de verdad importa aquí es el fallback. Un correo con el texto de
fábrica es infinitamente mejor que un correo no enviado: el aviso de una ausencia
aprobada o la bienvenida de un alta no pueden depender de que una tabla de
personalización esté disponible.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.shared.email.infrastructure.template_provider import (
    PostgresEmailTemplateProvider,
)


def _row(**overrides) -> dict:
    row = {
        "template_key": "staff_invited",
        "label": "Bienvenida",
        "description": "x",
        "subject": "Bienvenida, {{full_name}}",
        "body_html": "<p>Hola</p>",
        "is_active": True,
        "updated_by": None,
        "updated_at": datetime(2026, 7, 31, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_returns_the_saved_template():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row()

    template = await PostgresEmailTemplateProvider(pool).get("staff_invited")

    assert template is not None
    assert template.subject == "Bienvenida, {{full_name}}"


@pytest.mark.asyncio
async def test_only_reads_active_templates():
    """Una plantilla restaurada al texto por defecto no debe devolverse: el
    render la interpretaría igual, pero filtrar en SQL evita traer una fila para
    descartarla."""
    pool = AsyncMock()
    pool.fetchrow.return_value = None

    assert await PostgresEmailTemplateProvider(pool).get("staff_invited") is None
    assert "is_active = TRUE" in pool.fetchrow.call_args[0][0]


@pytest.mark.asyncio
async def test_a_database_failure_falls_back_to_the_default_text():
    """EL TEST QUE IMPORTA. Con la tabla sin migrar, la BD caída o un permiso mal
    puesto, el correo SIGUE SALIENDO con el texto de fábrica."""
    pool = AsyncMock()
    pool.fetchrow.side_effect = RuntimeError(
        'relation "email_templates" does not exist'
    )

    assert await PostgresEmailTemplateProvider(pool).get("staff_invited") is None


@pytest.mark.asyncio
async def test_a_missing_template_is_not_an_error():
    pool = AsyncMock()
    pool.fetchrow.return_value = None

    assert await PostgresEmailTemplateProvider(pool).get("lo_que_sea") is None
