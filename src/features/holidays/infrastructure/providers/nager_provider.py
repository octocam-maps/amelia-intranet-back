"""
Adaptador del puerto `IHolidayProvider` contra Nager.Date
(https://date.nager.at) — API pública, gratuita y sin API key de festivos
oficiales por país.

Filtrado para Barcelona: nos quedamos con los festivos NACIONALES de España
(`counties == null`) y los AUTONÓMICOS de Cataluña (los que incluyen `"ES-CT"`
en `counties`). Descartamos el resto de autonomías. Nager NO cubre los
festivos MUNICIPALES de Barcelona (La Mercè, Segona Pasqua) — esos se añaden a
mano (`source='manual'`).
"""

from datetime import date

import httpx

from ...domain.entities import OfficialHoliday
from ...domain.errors import HolidayProviderError

_CATALONIA_CODE = "ES-CT"
_TIMEOUT_SECONDS = 10.0


def map_nager_payload(payload: list[dict]) -> list[OfficialHoliday]:
    """Función pura: normaliza y filtra la respuesta cruda de Nager.Date a los
    festivos que aplican en Barcelona. Separada del I/O para poder testear el
    filtrado con un payload estático, sin red."""
    result: list[OfficialHoliday] = []
    for item in payload:
        counties = item.get("counties")
        if counties is None:
            scope = "nacional"
        elif _CATALONIA_CODE in counties:
            scope = "autonomico"
        else:
            # Festivo de otra autonomía — no aplica en Barcelona.
            continue

        raw_date = item.get("date")
        name = item.get("localName") or item.get("name")
        if not raw_date or not name:
            # Payload inesperado: saltamos la entrada en vez de romper todo.
            continue

        result.append(
            OfficialHoliday(day=date.fromisoformat(raw_date), name=name, scope=scope)
        )
    return result


class NagerHolidayProvider:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def fetch_official_holidays(self, year: int) -> list[OfficialHoliday]:
        url = f"{self._base_url}/api/v3/PublicHolidays/{year}/ES"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HolidayProviderError(
                "No se pudieron obtener los festivos oficiales del proveedor externo."
            ) from exc

        if not isinstance(payload, list):
            raise HolidayProviderError(
                "El proveedor externo devolvió un formato inesperado."
            )
        return map_nager_payload(payload)
