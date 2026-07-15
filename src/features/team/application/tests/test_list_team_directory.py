import pytest

from src.features.team.application.use_cases.list_team_directory import (
    ListTeamDirectoryUseCase,
)
from src.features.team.domain.entities import TeamMember

from .fakes import FakeTeamRepository


@pytest.mark.asyncio
async def test_returns_members_from_repository():
    members = [
        TeamMember(
            id="user-1",
            full_name="Ana García",
            job_title="Técnica de RRHH",
            entity_code="hub",
            entity_name="Amelia Hub",
            phone="+34600000000",
            email="ana.garcia@ameliahub.com",
            avatar_url=None,
        )
    ]
    use_case = ListTeamDirectoryUseCase(FakeTeamRepository(members=members))

    directory = await use_case.execute()

    assert directory == members


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_members():
    use_case = ListTeamDirectoryUseCase(FakeTeamRepository())

    assert await use_case.execute() == []
