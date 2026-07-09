"""
Tests del filtrado/normalización de la respuesta de Nager.Date. Se ejercita
la función pura `map_nager_payload` con un payload estático (misma forma que
la API real de España), sin tocar la red — el I/O HTTP es una capa fina
encima.
"""

from datetime import date

from src.features.holidays.infrastructure.providers.nager_provider import (
    map_nager_payload,
)

# Muestra representativa de la respuesta real de /PublicHolidays/2026/ES.
_SAMPLE = [
    {"date": "2026-01-01", "localName": "Año Nuevo", "name": "New Year's Day", "counties": None},
    {"date": "2026-04-06", "localName": "Lunes de Pascua", "name": "Easter Monday", "counties": ["ES-CT", "ES-IB", "ES-VC"]},
    {"date": "2026-02-28", "localName": "Día de Andalucía", "name": "Day of Andalucía", "counties": ["ES-AN"]},
    {"date": "2026-06-24", "localName": "Sant Joan", "name": "St. John's Day", "counties": ["ES-CT", "ES-VC"]},
    {"date": "2026-09-11", "localName": "Diada Nacional de Catalunya", "name": "National Day of Catalonia", "counties": ["ES-CT"]},
    {"date": "2026-12-25", "localName": "Navidad", "name": "Christmas Day", "counties": None},
]


def test_keeps_national_and_catalonia_drops_other_regions():
    result = map_nager_payload(_SAMPLE)

    days = {h.day for h in result}
    # Andalucía queda fuera; el resto entra.
    assert date(2026, 2, 28) not in days
    assert days == {
        date(2026, 1, 1),
        date(2026, 4, 6),
        date(2026, 6, 24),
        date(2026, 9, 11),
        date(2026, 12, 25),
    }


def test_scope_is_national_when_counties_null_and_autonomico_for_catalonia():
    by_day = {h.day: h for h in map_nager_payload(_SAMPLE)}

    assert by_day[date(2026, 1, 1)].scope == "nacional"
    assert by_day[date(2026, 12, 25)].scope == "nacional"
    assert by_day[date(2026, 6, 24)].scope == "autonomico"
    assert by_day[date(2026, 9, 11)].scope == "autonomico"


def test_uses_localname_in_spanish():
    by_day = {h.day: h for h in map_nager_payload(_SAMPLE)}
    assert by_day[date(2026, 6, 24)].name == "Sant Joan"


def test_skips_entries_missing_date_or_name():
    payload = [
        {"date": None, "localName": "Sin fecha", "counties": None},
        {"date": "2026-05-01", "localName": None, "name": None, "counties": None},
        {"date": "2026-05-01", "localName": "Fiesta del trabajo", "counties": None},
    ]
    result = map_nager_payload(payload)
    assert len(result) == 1
    assert result[0].name == "Fiesta del trabajo"
