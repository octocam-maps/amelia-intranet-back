import pytest

from src.features.mailbox.application.use_cases.submit_anonymous_message import (
    SubmitAnonymousMessageUseCase,
)

from .fakes import FakeMailboxRepository


@pytest.mark.asyncio
async def test_submit_message_returns_reference_code_without_identity():
    repository = FakeMailboxRepository()
    use_case = SubmitAnonymousMessageUseCase(repository)

    message = await use_case.execute(category="sugerencia", subject="Parking", body="¿Habrá plazas?")

    assert message.reference_code
    assert message.status == "new"
    # La entidad de dominio no tiene ningún campo de identidad que se
    # pudiera rellenar por accidente — el anonimato es estructural, no una
    # convención de código que dependa de "no usar" un campo.
    assert not hasattr(message, "user_id")
    assert not hasattr(message, "ip_address")


@pytest.mark.asyncio
async def test_each_submission_gets_a_distinct_reference_code():
    repository = FakeMailboxRepository()
    use_case = SubmitAnonymousMessageUseCase(repository)

    first = await use_case.execute(category="consulta", subject=None, body="¿Hay festivo local?")
    second = await use_case.execute(category="incidencia", subject=None, body="El ascensor no va")

    assert first.reference_code != second.reference_code
