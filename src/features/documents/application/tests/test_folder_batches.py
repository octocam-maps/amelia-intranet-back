"""
El volcado de carpetas por LOTES.

Sustituye a `test_bulk_provision_drive_folders.py`, `test_entity_folder_tree.py`
y `test_bulk_provision_concurrency.py`, que describían el diseño anterior: una
sola petición que hacía el trabajo entero, con el id de las carpetas de
sociedad cacheado en memoria y una fila de `drive_sync_runs` por ejecución.

Ese diseño provocó tres incidentes seguidos en producción —504 del proxy,
errores de TLS al paralelizar, y carpetas que nunca se recolocaban— y lo que
se prueba aquí es justo lo que los hace imposibles:

1. Que cada lote esté acotado, para que la petición no pueda expirar.
2. Que «cuántas quedan» se DERIVE del estado y no de un contador.
3. Que dos volcados simultáneos no puedan duplicar carpetas de sociedad.
4. Que quien cambia de sociedad se recoloque en vez de quedarse donde estaba.
"""

import asyncio

import pytest

from src.features.documents.application.use_cases.bulk_provision_drive_folders import (
    MAX_BATCH_LIMIT,
    MAX_CONCURRENT_PROVISIONS,
    BulkProvisionDriveFoldersUseCase,
    ProvisioningBusyError,
)

from .fakes import FakeDocumentRepository, FakeDocumentStorage


def _repositorio(count: int, entity: str = "Amelia Hub") -> FakeDocumentRepository:
    return FakeDocumentRepository(
        active_users=[(f"u{i:02d}", f"p{i:02d}@ameliahub.com", entity) for i in range(count)]
    )


def _caso(repository, storage=None) -> BulkProvisionDriveFoldersUseCase:
    return BulkProvisionDriveFoldersUseCase(repository, storage or FakeDocumentStorage())


# --- Lotes acotados ---------------------------------------------------------


@pytest.mark.asyncio
async def test_un_lote_no_procesa_mas_del_limite_pedido():
    """LA propiedad que hace que la petición no pueda expirar. Antes el volcado
    entero eran ~500 llamadas a Drive dentro de un solo HTTP."""
    repository = _repositorio(25)

    result = await _caso(repository).execute(limit=10)

    assert result.processed == 10
    assert result.remaining == 15


@pytest.mark.asyncio
async def test_el_limite_esta_acotado_por_arriba():
    """`limit` viene del cliente. Sin tope, pedir 10.000 devuelve el problema
    que el troceado venía a resolver."""
    repository = _repositorio(MAX_BATCH_LIMIT + 20)

    result = await _caso(repository).execute(limit=10_000)

    assert result.processed == MAX_BATCH_LIMIT


@pytest.mark.asyncio
async def test_lotes_sucesivos_terminan_agotando_el_trabajo():
    """El bucle del cliente, simulado: es la prueba de que el conjunto
    pendiente encoge de verdad y no devuelve siempre a la misma gente."""
    repository = _repositorio(25)
    storage = FakeDocumentStorage()
    caso = _caso(repository, storage)

    vueltas = 0
    while True:
        result = await caso.execute(limit=10)
        vueltas += 1
        if result.remaining == 0:
            break
        assert vueltas < 10, "el bucle no converge"

    assert vueltas == 3
    assert await repository.count_pending_folder_work() == 0


@pytest.mark.asyncio
async def test_un_lote_sin_trabajo_no_hace_nada():
    result = await _caso(FakeDocumentRepository()).execute()

    assert result.processed == 0
    assert result.remaining == 0


# --- El progreso se deriva, no se cuenta ------------------------------------


@pytest.mark.asyncio
async def test_quien_falla_sigue_contando_como_pendiente():
    """`remaining` NO es `total - procesadas`.

    Es la señal que necesita la UI para dejar de repetir: si alguien falla
    siempre, el lote lo devuelve una y otra vez y sin esto el bucle no
    terminaría nunca.
    """

    class _RotoParaUno(FakeDocumentStorage):
        async def get_or_create_employee_folder(self, email, *, entity_folder_id=None) -> str:
            if email == "p03@ameliahub.com":
                raise RuntimeError("Drive no responde para esta persona.")
            return await super().get_or_create_employee_folder(
                email, entity_folder_id=entity_folder_id
            )

    repository = _repositorio(5)

    result = await _caso(repository, _RotoParaUno()).execute(limit=5)

    assert result.processed == 5
    assert result.created == 4
    assert result.failed == 1
    assert result.remaining == 1


@pytest.mark.asyncio
async def test_un_fallo_no_cancela_al_resto_del_lote():
    """Con `asyncio.gather`, una excepción sin capturar CANCELA a las hermanas:
    una persona tumbaría al lote entero."""

    class _RotoParaUno(FakeDocumentStorage):
        async def get_or_create_employee_folder(self, email, *, entity_folder_id=None) -> str:
            if email == "p00@ameliahub.com":
                raise RuntimeError("Drive no responde.")
            return await super().get_or_create_employee_folder(
                email, entity_folder_id=entity_folder_id
            )

    result = await _caso(_repositorio(10), _RotoParaUno()).execute(limit=10)

    assert result.created == 9
    assert result.failed == 1


# --- Ejecución única --------------------------------------------------------


@pytest.mark.asyncio
async def test_un_segundo_volcado_simultaneo_se_rechaza():
    """Dos a la vez resuelven por su cuenta si la carpeta de una sociedad
    existe, ninguno ve al otro, y Drive acepta dos carpetas homónimas sin dar
    error."""
    repository = _repositorio(5)
    repository.provisioning_locked = True

    with pytest.raises(ProvisioningBusyError):
        await _caso(repository).execute()


@pytest.mark.asyncio
async def test_el_volcado_rechazado_no_toca_drive():
    """Que devuelva error no basta: tiene que rechazar ANTES de escribir."""

    class _EscrituraProhibida(FakeDocumentStorage):
        async def get_or_create_employee_folder(self, email, *, entity_folder_id=None) -> str:
            raise AssertionError("no debe tocar Drive con el cerrojo cogido")

    repository = _repositorio(5)
    repository.provisioning_locked = True

    with pytest.raises(ProvisioningBusyError):
        await _caso(repository, _EscrituraProhibida()).execute()


@pytest.mark.asyncio
async def test_el_cerrojo_se_libera_al_terminar():
    """Si no se liberase, el primer volcado dejaría el sistema bloqueado para
    siempre — y un cerrojo huérfano no se ve en ninguna parte."""
    repository = _repositorio(3)
    caso = _caso(repository)

    await caso.execute()

    assert repository.provisioning_locked is False


# --- La carpeta de la sociedad vive en la base ------------------------------


@pytest.mark.asyncio
async def test_la_carpeta_de_la_sociedad_se_crea_una_vez_y_se_guarda():
    repository = _repositorio(6)
    storage = FakeDocumentStorage()

    await _caso(repository, storage).execute(limit=6)

    assert list(storage.entity_folders) == ["Amelia Hub"]
    assert repository.entity_drive_folder_ids["Amelia Hub"] == storage.entity_folders["Amelia Hub"]


@pytest.mark.asyncio
async def test_con_la_carpeta_ya_guardada_no_se_pregunta_a_drive():
    """El caché en memoria que hacía esto se retiró. Si el id está en la base,
    no hay ninguna razón para volver a preguntar."""

    class _SinBuscarEntidad(FakeDocumentStorage):
        async def get_or_create_entity_folder(self, entity_name: str) -> str:
            raise AssertionError("la carpeta de la sociedad ya estaba en la base")

    repository = _repositorio(3)
    repository.entity_drive_folder_ids["Amelia Hub"] = "carpeta-hub-ya-conocida"

    result = await _caso(repository, _SinBuscarEntidad()).execute()

    assert result.created == 3


@pytest.mark.asyncio
async def test_quien_no_tiene_sociedad_cuelga_de_la_raiz():
    """El externo-invitado. Y no puede quedarse eternamente pendiente: con
    `NULL` a ambos lados, comparar con `<>` en vez de `IS DISTINCT FROM` lo
    dejaría fuera del predicado para siempre."""
    repository = FakeDocumentRepository(active_users=[("u1", "externo@gmail.com", None)])
    storage = FakeDocumentStorage()

    primero = await _caso(repository, storage).execute()
    segundo = await _caso(repository, storage).execute()

    assert primero.created == 1
    assert segundo.processed == 0
    assert storage.entity_folders == {}


# --- Recolocación por cambio de sociedad ------------------------------------


@pytest.mark.asyncio
async def test_cambiar_de_sociedad_mueve_la_carpeta_conservando_su_id():
    """Antes esto era invisible: el provisioning cortaba al ver un
    `drive_folder_id` cacheado, así que la carpeta se quedaba bajo la sociedad
    antigua para siempre y sin error."""
    repository = FakeDocumentRepository(active_users=[("u1", "ana@ameliahub.com", "Amelia Hub")])
    storage = FakeDocumentStorage()
    await _caso(repository, storage).execute()
    carpeta = repository.drive_folder_ids["u1"]

    # RRHH corrige la sociedad en la ficha.
    repository.active_users = [("u1", "ana@ameliahub.com", "Amelia Lab")]

    result = await _caso(repository, storage).execute()

    assert result.relocated == 1
    # El id NO cambia: `users.drive_folder_id` sigue siendo válido y los
    # documentos que hubiera dentro viajan con la carpeta.
    assert repository.drive_folder_ids["u1"] == carpeta
    assert storage.parent_by_folder[carpeta] == storage.entity_folders["Amelia Lab"]


@pytest.mark.asyncio
async def test_recolocar_no_deja_a_la_persona_pendiente_para_siempre():
    repository = FakeDocumentRepository(active_users=[("u1", "ana@ameliahub.com", "Amelia Hub")])
    storage = FakeDocumentStorage()
    await _caso(repository, storage).execute()
    repository.active_users = [("u1", "ana@ameliahub.com", "Amelia Lab")]

    await _caso(repository, storage).execute()

    assert await repository.count_pending_folder_work() == 0


@pytest.mark.asyncio
async def test_si_la_carpeta_ya_estaba_en_su_sitio_solo_se_corrige_el_dato():
    """Hace inofensivo el backfill optimista de la migración 055: si la columna
    mentía, se descubre al verificar el padre real y NO se escribe en Drive."""
    repository = FakeDocumentRepository(active_users=[("u1", "ana@ameliahub.com", "Amelia Lab")])
    storage = FakeDocumentStorage()
    destino = await storage.get_or_create_entity_folder("Amelia Lab")
    repository.entity_drive_folder_ids["Amelia Lab"] = destino
    carpeta = await storage.get_or_create_employee_folder(
        "ana@ameliahub.com", entity_folder_id=destino
    )
    # La carpeta está bien colocada, pero la columna dice otra cosa.
    repository.drive_folder_ids["u1"] = carpeta
    repository.drive_folder_entity_ids["u1"] = "Amelia Hub"
    storage.moved.clear()

    result = await _caso(repository, storage).execute()

    assert result.relocated == 1
    assert storage.moved == []
    assert repository.drive_folder_entity_ids["u1"] == "Amelia Lab"


# --- El paralelismo es una optimización, no un requisito --------------------


@pytest.mark.asyncio
async def test_el_paralelismo_esta_acotado():
    class _Contador(FakeDocumentStorage):
        def __init__(self):
            super().__init__()
            self.actuales = 0
            self.maximo = 0

        async def get_or_create_category_folder(self, employee_folder_id, category) -> str:
            self.actuales += 1
            self.maximo = max(self.maximo, self.actuales)
            try:
                await asyncio.sleep(0)
                return await super().get_or_create_category_folder(
                    employee_folder_id, category
                )
            finally:
                self.actuales -= 1

    storage = _Contador()
    await _caso(_repositorio(MAX_BATCH_LIMIT), storage).execute(limit=MAX_BATCH_LIMIT)

    assert storage.maximo <= MAX_CONCURRENT_PROVISIONS


@pytest.mark.asyncio
async def test_todo_funciona_igual_sin_paralelismo(monkeypatch):
    """La corrección no puede depender de la velocidad. Fue justo al revés
    —paralelizar para ganar tiempo— lo que rompió el volcado en producción."""
    monkeypatch.setattr(
        "src.features.documents.application.use_cases.bulk_provision_drive_folders."
        "MAX_CONCURRENT_PROVISIONS",
        1,
    )
    repository = _repositorio(5)

    result = await _caso(repository).execute(limit=5)

    assert result.created == 5
    assert result.remaining == 0
