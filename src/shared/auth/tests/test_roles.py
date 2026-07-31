"""
Invariantes de los GRUPOS de roles. Este fichero no prueba código con ramas —
prueba que las tuplas de `roles.py` dicen lo que la matriz de permisos
(docs/permisos-roles.md) promete. Es la red que avisa cuando entra un rol nuevo
y alguien olvida meterlo (o sacarlo) de un grupo: el síntoma en producción sería
un 403 inexplicable, o peor, un acceso que nadie pidió.
"""

from src.shared.auth.roles import (
    ADMIN_ONLY,
    ADMIN_SOCIO,
    ALL_ROLES,
    INTERNAL_ROLES,
    ROLES_WITHOUT_TIME_CLOCK,
    TIME_CLOCK_ROLES,
    RoleCode,
)


def test_all_roles_contains_every_declared_role():
    """`ALL_ROLES` debe ser el enum entero. Si entra un rol al `RoleCode` y no
    aquí, los 13 endpoints que usan `ALL_ROLES` le responden 403 sin que nada
    lo delate."""
    assert set(ALL_ROLES) == set(RoleCode)


def test_becario_is_internal_and_therefore_inherits_every_feature():
    """RF-A10: «becario tiene acceso también a todo, pero no al registro
    horario». Se implementa metiéndolo en los grupos amplios, para que las
    features futuras le den acceso por DEFECTO — un olvido debe dejarle dentro,
    que es lo pedido, no fuera en silencio."""
    assert RoleCode.BECARIO in ALL_ROLES
    assert RoleCode.BECARIO in INTERNAL_ROLES


def test_becario_cannot_use_the_time_clock():
    """La única excepción, y el motivo de que `TIME_CLOCK_ROLES` exista."""
    assert RoleCode.BECARIO not in TIME_CLOCK_ROLES


def test_becario_is_not_an_admin_and_has_no_hr_wide_visibility():
    """Un becario no aprueba ausencias ni ve el calendario global."""
    assert RoleCode.BECARIO not in ADMIN_ONLY
    assert RoleCode.BECARIO not in ADMIN_SOCIO


def test_external_guest_stays_out_of_internal_features():
    """Regresión del alcance parcial del externo-invitado: la entrada del
    becario en `INTERNAL_ROLES` no debe habérselo colado a él también."""
    assert RoleCode.EXTERNO_INVITADO not in INTERNAL_ROLES
    assert RoleCode.EXTERNO_INVITADO not in TIME_CLOCK_ROLES


def test_time_clock_roles_is_a_subset_of_internal_roles():
    """«Quién ficha» es un recorte de «quién es de uso interno», nunca al
    revés: un rol que pueda fichar pero no acceder al resto sería incoherente
    con la matriz de permisos."""
    assert set(TIME_CLOCK_ROLES) <= set(INTERNAL_ROLES)


def test_roles_without_time_clock_is_the_exact_complement():
    """`ROLES_WITHOUT_TIME_CLOCK` se DERIVA y no se escribe a mano — este test
    fija esa propiedad, que es la que evita el recordatorio diario de fichaje a
    quien recibe un 403 al intentar fichar (RF-A4.3)."""
    assert set(ROLES_WITHOUT_TIME_CLOCK) == set(ALL_ROLES) - set(TIME_CLOCK_ROLES)
    assert set(ROLES_WITHOUT_TIME_CLOCK) == {
        RoleCode.EXTERNO_INVITADO,
        RoleCode.BECARIO,
    }


def test_role_codes_compare_equal_to_plain_strings():
    """`RoleCode` hereda de `str` a propósito: el claim `role` del JWT es un
    string plano y `require_role` compara contra estas tuplas sin convertir."""
    assert RoleCode.BECARIO == "becario"
    assert "becario" in ALL_ROLES
