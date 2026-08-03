from datetime import date

import pytest

from src.features.staff.application.use_cases.update_staff_member import (
    UpdateStaffMemberUseCase,
)
from src.features.staff.domain.errors import StaffMemberNotFoundError

from .fakes import (
    _DEFAULT_INVITED_BY,
    FakeSessionRevoker,
    FakeStaffRepository,
    build_create_staff_member_use_case,
)


async def _seed_member(repository: FakeStaffRepository):
    return await build_create_staff_member_use_case(repository).execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title="Project Manager",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=23,
        invited_by=_DEFAULT_INVITED_BY,
    )


@pytest.mark.asyncio
async def test_deactivating_sets_status_to_suspended():
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, is_active=False)

    assert updated.status == "suspended"


@pytest.mark.asyncio
async def test_deactivating_revokes_all_active_sessions():
    """Defensa en profundidad de AUTHN-2: suspender (`is_active=False`)
    revoca de una vez las sesiones de refresh vigentes del usuario, para no
    depender solo del corte inmediato por request (`ensure_user_is_active`)
    ni del rechazo de `/auth/refresh` a un `suspended`."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    session_revoker = FakeSessionRevoker()
    use_case = UpdateStaffMemberUseCase(repository, session_revoker)

    await use_case.execute(member.id, is_active=False)

    assert session_revoker.revoked_user_ids == [member.id]


@pytest.mark.asyncio
async def test_reactivating_does_not_revoke_sessions():
    """Reactivar (`is_active=True`) no debe disparar la revocación — solo
    suspender corta el acceso."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    session_revoker = FakeSessionRevoker()
    use_case = UpdateStaffMemberUseCase(repository, session_revoker)

    await use_case.execute(member.id, is_active=True)

    assert session_revoker.revoked_user_ids == []


@pytest.mark.asyncio
async def test_editing_other_fields_does_not_revoke_sessions():
    """Editar cualquier otro campo (sin tocar `is_active`) no debe revocar
    nada — solo la transición explícita a suspendido."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    session_revoker = FakeSessionRevoker()
    use_case = UpdateStaffMemberUseCase(repository, session_revoker)

    await use_case.execute(member.id, job_title="Senior PM")

    assert session_revoker.revoked_user_ids == []


@pytest.mark.asyncio
async def test_deactivating_without_a_session_revoker_still_suspends():
    """`session_revoker` es opcional — si no se inyecta (`None`, el
    default), suspender sigue funcionando igual que antes de AUTHN-2."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, is_active=False)

    assert updated.status == "suspended"


@pytest.mark.asyncio
async def test_partial_update_leaves_other_fields_untouched():
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, job_title="Senior PM")

    assert updated.job_title == "Senior PM"
    assert updated.vacation_days_per_year == 23
    assert updated.entity_code == "hub"
    assert updated.status == "invited"


@pytest.mark.asyncio
async def test_not_passing_vacation_days_override_leaves_it_untouched():
    """No informar `vacation_days_override` en absoluto (la mayoría de
    ediciones, p. ej. solo cambiar el puesto) no debe tocar el override ni
    recalcular el saldo — mismo patrón que
    `holidays.test_not_passing_entity_code_leaves_the_scope_untouched`."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)  # override=23 al crear
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, job_title="Senior PM")

    assert updated.vacation_days_override == 23
    assert updated.vacation_days_per_year == 23


@pytest.mark.asyncio
async def test_passing_vacation_days_override_none_clears_it_to_automatic():
    """`vacation_days_override=None` EXPLÍCITO (el admin vació el campo en
    el formulario) vuelve al cálculo automático desde `hire_date` — a
    diferencia de "no informarlo" (arriba), que no toca nada."""
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Marc Roig",
        email="marc@ameliahub.com",
        job_title="Backend",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=date(2020, 1, 1),  # calcularía 20
        vacation_days_override=15,  # pero el admin lo fijó a 15
        invited_by=_DEFAULT_INVITED_BY,
    )
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, vacation_days_override=None)

    assert updated.vacation_days_override is None
    assert updated.vacation_days_per_year == 20  # vuelve al cálculo automático


@pytest.mark.asyncio
async def test_passing_a_new_vacation_days_override_value_overrides_the_calculation():
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Marc Roig",
        email="marc@ameliahub.com",
        job_title="Backend",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=date(2020, 1, 1),  # calcularía 20
        vacation_days_override=None,
        invited_by=_DEFAULT_INVITED_BY,
    )
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, vacation_days_override=12)

    assert updated.vacation_days_override == 12
    assert updated.vacation_days_per_year == 12


@pytest.mark.asyncio
async def test_updating_missing_member_raises_not_found():
    repository = FakeStaffRepository()
    use_case = UpdateStaffMemberUseCase(repository)

    with pytest.raises(StaffMemberNotFoundError):
        await use_case.execute("does-not-exist", job_title="Nuevo puesto")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_code", ["administrador", "empleado", "externo_invitado", "socio", "becario"]
)
async def test_updates_a_members_role_to_each_assignable_role(role_code):
    """Misma regresión que `test_create_staff_member.py` pero para
    `PATCH /staff/{id}` — editar a alguien (aunque sea solo el puesto) no
    debe rechazar ni degradar ningún rol de la tabla `roles`."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, role_code=role_code)

    assert updated.role_code == role_code


# ─────────────────────────────────────────────────────────────────────────────
# Historial de rol y promoción Becario -> Trabajador (RF-A10.6, migración 039).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_promoting_a_becario_records_the_role_change_with_its_author():
    """Antes de la 039 el cambio de rol era destructivo: `COALESCE($5, role_id)`
    pisaba el valor y no quedaba rastro salvo `users.updated_at`, que además se
    sobreescribe en cualquier otra edición."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    await use_case.execute(member.id, role_code="becario", changed_by="admin-1")
    await use_case.execute(member.id, role_code="empleado", changed_by="admin-1")

    # Tres filas: el alta (`from_role_id=None`, escrita por
    # `create_staff_member`) y una por cada cambio real. La secuencia completa
    # es lo que hace legible "fue becario del X al Y" en la ficha.
    transitions = [
        (row["from_role_id"], row["to_role_id"]) for row in repository.role_history
    ]
    assert transitions == [
        (None, "role-empleado"),
        ("role-empleado", "role-becario"),
        ("role-becario", "role-empleado"),
    ]
    assert repository.role_history[-1]["changed_by"] == "admin-1"


@pytest.mark.asyncio
async def test_updating_without_a_role_change_writes_no_history():
    """Editar el puesto no debe generar una fila de "cambio de rol" con el mismo
    rol a los dos lados: el historial dejaría de ser legible."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    before = len(repository.role_history)
    use_case = UpdateStaffMemberUseCase(repository)

    await use_case.execute(member.id, job_title="Senior PM", changed_by="admin-1")

    assert len(repository.role_history) == before


@pytest.mark.asyncio
async def test_reassigning_the_same_role_writes_no_history():
    """Mandar el rol que ya tenía tampoco cuenta como cambio."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    before = len(repository.role_history)
    use_case = UpdateStaffMemberUseCase(repository)

    await use_case.execute(member.id, role_code="empleado", changed_by="admin-1")

    assert len(repository.role_history) == before


@pytest.mark.asyncio
async def test_promoting_preserves_hire_date_so_seniority_survives():
    """El pedido "que se guarde su antigüedad" NO necesitaba código: `hire_date`
    no forma parte del UPDATE del PATCH. Este test lo fija contra el día que
    alguien lo añada a la firma "por completitud" y se lleve por delante el
    cálculo de vacaciones, que depende solo de esa fecha."""
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Miquel Sala",
        email="miquel@ameliahub.com",
        job_title="Becario de operaciones",
        department=None,
        entity_code="hub",
        role_code="becario",
        hire_date=date(2026, 1, 12),
        vacation_days_override=None,
        invited_by=_DEFAULT_INVITED_BY,
    )
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(
        member.id, role_code="empleado", changed_by="admin-1"
    )

    assert updated.role_code == "empleado"
    assert updated.hire_date == date(2026, 1, 12)


@pytest.mark.asyncio
async def test_changing_role_revokes_sessions_so_the_new_permissions_apply_now():
    """El `role` viaja DENTRO del access token (15 min). Sin revocar, un becario
    recién promocionado seguiría arrastrando `role: becario`: el navbar no le
    mostraría Control horario y el backend le seguiría dando 403 con el cambio
    ya guardado. Y al revés es peor — a quien se le RETIRA un permiso, el token
    viejo se lo mantendría vivo un cuarto de hora."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    session_revoker = FakeSessionRevoker()
    use_case = UpdateStaffMemberUseCase(repository, session_revoker)

    await use_case.execute(member.id, role_code="becario", changed_by="admin-1")

    assert session_revoker.revoked_user_ids == [member.id]


@pytest.mark.asyncio
async def test_reassigning_the_same_role_does_not_revoke_sessions():
    """Un PATCH que manda el rol que ya tenía no debe echar a nadie de su
    sesión: los permisos del token siguen siendo correctos."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    session_revoker = FakeSessionRevoker()
    use_case = UpdateStaffMemberUseCase(repository, session_revoker)

    await use_case.execute(member.id, role_code="empleado", changed_by="admin-1")

    assert session_revoker.revoked_user_ids == []


# --- Fecha de alta editable (2026-08-03) ----------------------------------


@pytest.mark.asyncio
async def test_setting_hire_date_recomputes_the_vacation_entitlement():
    """EL CASO QUE MOTIVÓ EL CAMBIO: quien se sembró sin `hire_date` tenía 0
    días de vacaciones y ninguna forma de arreglarlo — no podía solicitar ni un
    día. Rellenar la fecha tiene que recalcular el saldo, no solo guardarla."""
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Beatriz Luna",
        email="people@ameliahub.com",
        job_title="People Manager",
        department=None,
        entity_code="hub",
        role_code="administrador",
        hire_date=None,  # sembrada por migración antes de existir la columna
        vacation_days_override=None,
        invited_by=_DEFAULT_INVITED_BY,
    )
    assert member.vacation_days_per_year == 0  # el bug, antes del arreglo
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, hire_date=date(2020, 1, 1))

    assert updated.hire_date == date(2020, 1, 1)
    assert updated.vacation_days_per_year == 20


@pytest.mark.asyncio
async def test_not_passing_hire_date_leaves_it_untouched():
    """`None` = "no informado" = no tocar. Editar el puesto no puede borrar la
    antigüedad de nadie — es justo lo que protegía la inmutabilidad."""
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Marc Roig",
        email="marc@ameliahub.com",
        job_title="Backend",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=date(2020, 1, 1),
        vacation_days_override=None,
        invited_by=_DEFAULT_INVITED_BY,
    )
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, job_title="Senior Backend")

    assert updated.hire_date == date(2020, 1, 1)
    assert updated.vacation_days_per_year == 20


@pytest.mark.asyncio
async def test_a_manual_override_still_wins_over_the_new_hire_date():
    """Corregir la fecha de alta de alguien con override manual NO le pisa el
    override: `resolve_vacation_entitlement_days` da prioridad al override, y
    ese orden no cambia porque ahora la fecha sea editable."""
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Marc Roig",
        email="marc@ameliahub.com",
        job_title="Backend",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=12,
        invited_by=_DEFAULT_INVITED_BY,
    )
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, hire_date=date(2020, 1, 1))

    assert updated.hire_date == date(2020, 1, 1)
    assert updated.vacation_days_per_year == 12
