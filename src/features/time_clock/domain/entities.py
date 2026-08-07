"""Entidades de dominio del feature `time_clock`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class TimeClockSource(str, Enum):  # noqa: UP042 — mismo mixin deliberado que `RoleCode`
    """Origen de un tramo de fichaje (LOGIC-2, pentest ético, severidad ALTA):
    antes del fix, tanto el alta manual (`CreateTimeClockEntryUseCase`) como
    el fichaje en vivo (`ClockInUseCase`) escribían el mismo valor histórico
    `"web"`, así que RRHH no podía auditar cuántas horas eran autodeclaradas
    frente a fichadas en tiempo real. Hereda de `str` para que comparaciones
    contra la columna `source` (un string plano en BD/DTOs) sigan funcionando
    sin cambios, igual que `RoleCode`.

    Los valores históricos `"web"`/`"mobile"` (CHECK de `time_clock_entries`,
    migración inicial) siguen siendo válidos para filas YA existentes — no se
    migran datos viejos, solo se deja de escribirlos en flujos nuevos."""

    MANUAL = "manual"
    LIVE = "live"


class TimeClockBatchOmissionReason(str, Enum):  # noqa: UP042 — mismo mixin que `TimeClockSource`
    """Motivo por el que un día del rango del alta en lote (RF-A3) no
    genera un tramo, sin que eso tumbe el resto del lote. Orden de
    evaluación estricto, primer match gana — ver
    `CreateTimeClockEntriesBatchUseCase` para el razonamiento completo
    (LOGIC-2, pentest ético, severidad ALTA): `fin_de_semana` -> `festivo`
    (escopado por entidad) -> `ausencia` (aprobada, propia) ->
    `ya_registrado` -> `fuera_de_ventana`. Un día "futuro" sin ninguna de
    estas exclusiones NO tiene motivo de omisión: tumba el lote entero en
    vez de aparecer aquí."""

    FIN_DE_SEMANA = "fin_de_semana"
    FESTIVO = "festivo"
    AUSENCIA = "ausencia"
    YA_REGISTRADO = "ya_registrado"
    FUERA_DE_VENTANA = "fuera_de_ventana"


@dataclass(frozen=True)
class TimeClockEntry:
    """Un tramo de fichaje (entrada/salida elegidas manualmente por el usuario).

    El control horario de Amelia intranet es por SELECCIÓN MANUAL DE TRAMOS
    (p.ej. "de 6 a 9"), no un fichaje en tiempo real con pulsación de botón
    (decisión cerrada en la demo). Un mismo `work_date` puede tener varios
    tramos (mañana/tarde); el hueco entre dos tramos YA actúa como pausa
    implícita, así que este feature no usa todavía `time_clock_breaks` (existe
    desde 003_hr_core, sin endpoints) — si RRHH pide registrar pausas DENTRO
    de un mismo tramo, se retoma sin migración nueva.
    """

    id: str
    user_id: str
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime]
    source: str
    created_at: datetime
    updated_at: datetime
    # Solo lo rellenan los listados (`list_entries_for_user`/`list_entries_
    # for_all`, JOIN a `users` — mismo patrón que `TimeClockExportRow`). El
    # resto de rutas (alta, edición, solape, tramo abierto) no lo necesitan y
    # lo dejan en `None` — no es un dato transaccional del tramo en sí.
    full_name: Optional[str] = None

    @property
    def worked_minutes(self) -> Optional[int]:
        """`None` si el tramo sigue abierto (`clock_out` sin fijar todavía)."""
        if self.clock_out is None:
            return None
        return int((self.clock_out - self.clock_in).total_seconds() // 60)


@dataclass(frozen=True)
class TimeClockExportRow:
    """Una fila del informe de fichajes exportable a XLSX (vista admin,
    TODA la plantilla interna — `docs/permisos-roles.md` § Control horario).

    A diferencia de `TimeClockEntry`, esta forma SÍ conoce identidad/contacto
    porque es el resultado de un informe de RRHH (join con `users` +
    `user_profiles`), no la entidad transaccional del fichaje. Mismo patrón
    que `UserProfile` en el feature `profile`: un join resuelto en el
    repositorio, expuesto como forma de dominio porque el puerto
    (`ITimeClockRepository`) vive en `domain`.

    `full_name` es un único campo de texto en `users` (no hay columnas
    Nombre/Apellido separadas) — la capa de infraestructura que construye el
    libro XLSX reparte "Nombre = primera palabra, Apellido = el resto"
    (`infrastructure/xlsx_export.py::_split_full_name`), la MISMA heurística
    que ya usa `ORDER BY` en el repositorio para que la fila y el orden
    coincidan.
    """

    user_id: str
    full_name: str
    dni_nif: Optional[str]
    phone: Optional[str]
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime]
    # LOGIC-2 (pentest ético): sin este campo, el informe XLSX de RRHH no
    # podía distinguir horas autodeclaradas (alta manual) de fichadas en vivo
    # — ver `TimeClockSource`.
    source: str

    @property
    def worked_minutes(self) -> Optional[int]:
        """`None` si el tramo sigue abierto (fichaje en curso, sin salida)."""
        if self.clock_out is None:
            return None
        return int((self.clock_out - self.clock_in).total_seconds() // 60)


@dataclass(frozen=True)
class TimeClockEntryNote:
    """Incidencia/comentario que el admin deja sobre un tramo de fichaje
    (p.ej. "olvidó fichar salida, corregido a mano tras confirmarlo con la
    persona" — B-2b). Registro de auditoría ADD-ONLY: no hay endpoint de
    edición ni borrado, así que no lleva `updated_at` (mismo criterio que
    `TimeClockBreak`, que tampoco lo lleva).
    """

    id: str
    entry_id: str
    # `None` si el autor fue eliminado (`ON DELETE SET NULL` en la FK) — la
    # incidencia sigue siendo un registro válido del fichaje sin su autor.
    author_id: Optional[str]
    body: str
    created_at: datetime
    # Solo lo rellena `list_notes_for_entry` (JOIN a `users`), mismo patrón
    # que `TimeClockEntry.full_name`. `None` si el autor fue eliminado.
    author_full_name: Optional[str] = None


class OvernightStay(str, Enum):  # noqa: UP042 — mismo mixin que `TimeClockSource`
    """Dónde pernoctó el técnico (requerimiento v1.2 §M1: «si ha habido
    pernocta o no» y «en caso de pernocta, si ha sido en España o fuera»).

    RRHH lo pide como DOS preguntas y la UI las hace en dos pasos, pero en el
    modelo es UN solo campo a propósito: con un booleano `had_overnight_stay`
    más un `location` aparte, el estado "no hubo pernocta pero fue en España"
    sería representable, y alguien acabaría escribiéndolo. Aquí no se puede.
    """

    NINGUNA = "ninguna"
    ESPANA = "espana"
    EXTRANJERO = "extranjero"

    @property
    def counts_as_overnight(self) -> bool:
        return self is not OvernightStay.NINGUNA


class ProductCategory(str, Enum):  # noqa: UP042 — mismo mixin que `OvernightStay`
    """Línea de producto a la que se imputa la jornada.

    Es un eje DISTINTO del departamento, aunque desde el catálogo de 2026
    existan también departamentos llamados Software y Hardware (colgando de
    Producto): alguien del departamento de Hardware puede pasar una jornada
    imputada a Software. Por eso se pregunta en cada parte y NUNCA se deriva
    de `users.department_id`.
    """

    SOFTWARE = "software"
    HARDWARE = "hardware"


@dataclass(frozen=True)
class Project:
    """Proyecto al que se imputa un parte. Catálogo cerrado a propósito: con
    texto libre, a los tres meses hay ocho formas de escribir "Guadix" y el
    resumen mensual que pide RRHH no puede agrupar por nada."""

    id: str
    code: str
    name: str
    is_active: bool


@dataclass(frozen=True)
class TechnicianDailyLog:
    """Parte diario de un técnico (requerimiento v1.2 §M1).

    A diferencia del fichaje por tramos, aquí hay UNO por técnico y día
    (`uq_technician_daily_logs_one_per_day`), la jornada PUEDE cruzar la
    medianoche y la pausa se declara como un total de minutos en vez de como
    tramos de `time_clock_breaks`.

    El tramo padre en `time_clock_entries` sigue existiendo y es el que hace
    que el técnico aparezca en el registro legal de jornada (art. 34.9 ET) y
    en el informe XLSX de RRHH — esta entidad solo añade el detalle de campo.
    """

    entry_id: str
    user_id: str
    work_date: date
    # `started_at`/`ended_at` son el `clock_in`/`clock_out` del tramo padre.
    # Se exponen con otro nombre porque en el parte NO son "fichajes": son la
    # hora de salida y la de llegada al parque/hotel que declara la persona.
    started_at: datetime
    ended_at: datetime
    project_id: str
    work_location: str
    had_break: bool
    break_minutes: int
    overnight_stay: OvernightStay
    product_category: ProductCategory
    created_at: datetime
    updated_at: datetime
    # Resueltos por JOIN solo en los listados, mismo patrón que
    # `TimeClockEntry.full_name`.
    project_name: Optional[str] = None
    full_name: Optional[str] = None

    @property
    def worked_minutes(self) -> int:
        """Jornada efectiva: bruto menos pausa. Nunca es `Optional` —el parte
        se guarda cerrado, con hora de fin— y NUNCA se acepta del cliente."""
        gross = int((self.ended_at - self.started_at).total_seconds() // 60)
        return gross - self.break_minutes


@dataclass(frozen=True)
class TimeClockBreak:
    """Una pausa DENTRO de un tramo abierto — modelo "en vivo" (botón
    Pausa/Reanudar del dashboard, docs/deck-fase3/01-home-empleado.png).

    A diferencia del fichaje manual por tramos (donde el hueco ENTRE dos
    tramos ya actúa como pausa implícita, ver `TimeClockEntry`), aquí sí se
    usa `time_clock_breaks` porque la pausa ocurre DENTRO de un mismo tramo
    que sigue abierto — parar el timer sin cerrar la jornada.
    """

    id: str
    entry_id: str
    break_start: datetime
    break_end: Optional[datetime]

    @property
    def is_open(self) -> bool:
        return self.break_end is None
