import pytest

from src.features.roles.application.use_cases.list_roles import ListRolesUseCase
from src.features.roles.domain.entities import Role

from .fakes import FakeRoleRepository


@pytest.mark.asyncio
async def test_list_roles_returns_every_role_including_administrador():
    """Decisión: `GET /roles` NO excluye `administrador` — el frontend
    (`StaffForm`) ya lo ofrece hoy como rol asignable desde "Plantilla" y el
    backend no impone unicidad del rol admin en ningún punto (fuera de
    alcance); excluirlo aquí cambiaría un comportamiento existente sin que
    nadie lo pidiera. Si RRHH decide más adelante que el admin es
    verdaderamente único, ese filtro se añade en este caso de uso."""
    repository = FakeRoleRepository()
    use_case = ListRolesUseCase(repository)

    roles = await use_case.execute()

    codes = {role.code for role in roles}
    assert codes == {"administrador", "empleado", "externo_invitado", "socio"}


@pytest.mark.asyncio
async def test_list_roles_is_a_pure_pass_through_of_the_repository():
    custom_roles = [Role(id="role-x", code="futuro_rol", name="Futuro rol")]
    repository = FakeRoleRepository(custom_roles)
    use_case = ListRolesUseCase(repository)

    roles = await use_case.execute()

    assert roles == custom_roles
