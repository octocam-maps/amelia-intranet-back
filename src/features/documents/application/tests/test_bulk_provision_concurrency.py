"""
El volcado de carpetas provisiona a las personas EN PARALELO.

En serie eran ~14 llamadas a Drive por persona, una detrás de otra: con la
plantilla completa la petición HTTP pasaba de dos minutos y el proxy la
cortaba antes de terminar.

El paralelismo, sin embargo, abre una puerta que en serie no existía: dos
corrutinas preguntando a la vez "¿existe ya la carpeta de Hincator?" reciben
las dos que no, y crean DOS carpetas con el mismo nombre. Drive lo permite —
no tiene unicidad por nombre— así que nadie da un error: simplemente media
plantilla acaba colgando de una y media de la otra.

Estos tests fijan las dos mitades: que de verdad va en paralelo, y que el
paralelismo no duplica nada.
"""

import asyncio

import pytest

from src.features.documents.application.use_cases.bulk_provision_drive_folders import (
    MAX_CONCURRENT_PROVISIONS,
    BulkProvisionDriveFoldersUseCase,
)

from .fakes import FakeDocumentRepository, FakeDocumentStorage


class _ConcurrencyTracker(FakeDocumentStorage):
    """Registra cuánta gente se provisiona a la vez y cuántas veces se pregunta
    por cada carpeta de sociedad."""

    def __init__(self):
        super().__init__()
        # Secuencia de llamadas, para poder afirmar ORDEN y no solo cuántas.
        self.call_log: list[str] = []
        self.current = 0
        self.max_concurrent = 0

    async def get_or_create_entity_folder(self, entity_name: str) -> str:
        self.call_log.append(f"entidad:{entity_name}")
        return await super().get_or_create_entity_folder(entity_name)

    async def get_or_create_employee_folder(self, email, *, entity_name=None) -> str:
        self.call_log.append(f"empleado:{email}")
        return await super().get_or_create_employee_folder(email, entity_name=entity_name)

    async def get_or_create_category_folder(self, employee_folder_id: str, category: str) -> str:
        # Es la llamada más repetida (cinco por persona), así que es donde
        # mejor se mide el solapamiento real.
        self.current += 1
        self.max_concurrent = max(self.max_concurrent, self.current)
        try:
            # Cede el control: sin un await de verdad, las corrutinas se
            # ejecutarían enteras una tras otra y el test no mediría nada.
            await asyncio.sleep(0)
            return await super().get_or_create_category_folder(employee_folder_id, category)
        finally:
            self.current -= 1


def _repository(count: int, entity: str = "Amelia Hub") -> FakeDocumentRepository:
    return FakeDocumentRepository(
        active_users=[(f"u{i}", f"p{i}@ameliahub.com", entity) for i in range(count)]
    )


@pytest.mark.asyncio
async def test_people_are_provisioned_in_parallel():
    storage = _ConcurrencyTracker()

    await BulkProvisionDriveFoldersUseCase(_repository(12), storage).execute()

    assert storage.max_concurrent > 1


@pytest.mark.asyncio
async def test_the_parallelism_stays_bounded():
    """Soltar la plantilla entera a la vez es la forma más rápida de que
    Google conteste `rateLimitExceeded`. Como el batch es best-effort, esa
    persona se contaría como fallida y habría que repetir: lo que se gana
    quitando el tope se pierde entero."""
    storage = _ConcurrencyTracker()

    await BulkProvisionDriveFoldersUseCase(_repository(40), storage).execute()

    assert storage.max_concurrent <= MAX_CONCURRENT_PROVISIONS


@pytest.mark.asyncio
async def test_every_entity_folder_exists_before_the_fan_out_starts():
    """LA garantía que hace seguro el paralelismo.

    Si las carpetas de sociedad se resolvieran dentro del fan-out, dos
    corrutinas simultáneas de la misma entidad crearían dos carpetas
    homónimas. Por eso se crean antes, y de una en una: cuando arranca el
    paralelismo ya no queda ninguna decisión compartida que tomar."""
    repository = FakeDocumentRepository(
        active_users=[
            ("u1", "ana@ameliahub.com", "Amelia Hub"),
            ("u2", "luis@amelialab.com", "Amelia Lab"),
            ("u3", "eva@ameliahub.com", "Amelia Hub"),
        ]
    )
    storage = _ConcurrencyTracker()

    await BulkProvisionDriveFoldersUseCase(repository, storage).execute()

    primer_empleado = next(
        i for i, llamada in enumerate(storage.call_log) if llamada.startswith("empleado:")
    )
    entidades_antes = {
        llamada for llamada in storage.call_log[:primer_empleado] if llamada.startswith("entidad:")
    }
    assert entidades_antes == {"entidad:Amelia Hub", "entidad:Amelia Lab"}


@pytest.mark.asyncio
async def test_a_single_failure_does_not_abort_the_rest():
    """Con `asyncio.gather` un fallo sin capturar cancela a los hermanos: la
    persona 3 tumbaría a las 34 restantes. En serie el `continue` bastaba."""

    class _BrokenForOne(FakeDocumentStorage):
        async def get_or_create_employee_folder(self, email, *, entity_name=None) -> str:
            if email == "p3@ameliahub.com":
                raise RuntimeError("Drive no responde para esta persona.")
            return await super().get_or_create_employee_folder(email, entity_name=entity_name)

    result = await BulkProvisionDriveFoldersUseCase(_repository(10), _BrokenForOne()).execute()

    assert result.failed == 1
    assert result.created == 9
    assert result.sync_run.status == "partial"
