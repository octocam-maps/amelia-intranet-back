"""
TZ-1 (auditoría QA Fase 3): el proceso corre con `TZ=UTC` (ver Dockerfile),
así que `date.today()`/`datetime.now()` SIN zona explícita devuelven la
fecha en UTC — correcto para timestamps, pero NO para "qué día es hoy" de
cara al negocio: RRHH opera en horario de España, no en UTC. Entre las 00:00
y la 01:00/02:00 UTC (según horario de verano/invierno), UTC y Madrid ya
están en días distintos.

Este es el ÚNICO punto de la app que decide "qué día es hoy" para el
dashboard, el fichaje y el export — nunca usar `date.today()` directamente
en esos features.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")


def today_in_madrid() -> date:
    return datetime.now(MADRID_TZ).date()
