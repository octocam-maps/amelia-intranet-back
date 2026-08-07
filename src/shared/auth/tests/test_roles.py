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
    DAILY_TIME_LOG_ROLES,
    INTERNAL_ROLES,
    ROLES_WITHOUT_TIME_TRACKING,
    TECHNICIAN_ROLES,
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


def test_roles_without_time_tracking_is_the_exact_complement():
    """`ROLES_WITHOUT_TIME_TRACKING` se DERIVA y no se escribe a mano — este
    test fija esa propiedad, que es la que evita el recordatorio diario a quien
    no tiene dónde registrar su jornada (RF-A4.3)."""
    expected = set(ALL_ROLES) - set(DAILY_TIME_LOG_ROLES)
    assert set(ROLES_WITHOUT_TIME_TRACKING) == expected
    assert set(ROLES_WITHOUT_TIME_TRACKING) == {
        RoleCode.EXTERNO_INVITADO,
        RoleCode.BECARIO,
    }


def test_tecnico_is_internal_and_therefore_inherits_every_feature():
    """Migración 051: el técnico accede a todo lo que ve un empleado. Lo único
    distinto es CÓMO registra su jornada."""
    assert RoleCode.TECNICO in ALL_ROLES
    assert RoleCode.TECNICO in INTERNAL_ROLES


def test_tecnico_does_not_use_the_tramo_based_time_clock():
    """El técnico cumplimenta un parte diario, no ficha por tramos: nada de
    reloj en vivo ni de alta en lote."""
    assert RoleCode.TECNICO not in TIME_CLOCK_ROLES
    assert RoleCode.TECNICO in TECHNICIAN_ROLES


def test_tecnico_still_gets_the_daily_reminder():
    """LA regresión de la migración 051, y la razón de que
    `DAILY_TIME_LOG_ROLES` exista como grupo propio.

    El recordatorio diario se derivaba de `TIME_CLOCK_ROLES`. Como el técnico
    NO ficha por tramos, sacarlo de ahí sin más lo habría dejado fuera del
    recordatorio — justo a quien el parte le es OBLIGATORIO cada día. El fallo
    habría sido silencioso: nadie echa de menos un email que nunca llegó."""
    assert RoleCode.TECNICO in DAILY_TIME_LOG_ROLES
    assert RoleCode.TECNICO not in ROLES_WITHOUT_TIME_TRACKING


def test_daily_time_log_roles_is_a_subset_of_internal_roles():
    """Registrar jornada es un recorte de «quién es de uso interno», igual que
    lo es fichar: un rol que registre jornada sin acceder al resto del producto
    sería incoherente con la matriz de permisos."""
    assert set(DAILY_TIME_LOG_ROLES) <= set(INTERNAL_ROLES)


def test_role_codes_compare_equal_to_plain_strings():
    """`RoleCode` hereda de `str` a propósito: el claim `role` del JWT es un
    string plano y `require_role` compara contra estas tuplas sin convertir."""
    assert RoleCode.BECARIO == "becario"
    assert "becario" in ALL_ROLES
