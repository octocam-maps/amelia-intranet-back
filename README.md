# Amelia Intranet — Backend

FastAPI + asyncpg (SQL crudo, sin ORM). Arquitectura hexagonal por feature
(`domain` / `application` / `infrastructure`), espejo de `backend2`. Ver
`../amelia-intranet/CLAUDE.md` y `../amelia-intranet/docs/` para el contrato
funcional completo.

**Fase 3 (actual):** Portal RRHH core — dashboard por rol, control horario
(fichaje por tramos manuales) y ausencias/vacaciones con aprobación del
admin. Fase 2 (onboarding) queda en STANDBY hasta que RRHH entregue
contenido — las tablas ya existen pero sin endpoints. Documentos/Drive,
equipo/organigrama y admin/notificaciones son Fase 4+.

## Stack

- Python 3.12, FastAPI, asyncpg (SQL crudo, sin ORM ni Alembic)
- Auth: Google OIDC (Sign in with Google / Workspace) — sin contraseñas
- JWT interno propio (access ~15 min + refresh en cookie HttpOnly)
- PostgreSQL 17, migraciones numeradas en `database/migrations/`

## Arrancar en local

### 1. Google Cloud Console (una vez, por proyecto)

1. Ir a [Google Cloud Console → Credenciales](https://console.cloud.google.com/apis/credentials)
   y crear (o reutilizar) un proyecto.
2. **Pantalla de consentimiento OAuth**: tipo interno si toda la plantilla usa
   Google Workspace de `ameliahub.com`; si hay externos con Gmail personal,
   tipo externo (con los scopes básicos `openid email profile`).
3. Crear credencial **OAuth 2.0 Client ID**, tipo **Web application**.
   - Orígenes de JavaScript autorizados: `http://localhost:5173` (dev) + el
     dominio de producción del frontend.
   - No hace falta "Authorized redirect URIs": el flujo usa Google Identity
     Services (`id_token` vía JS en el navegador), no redirect OAuth clásico.
4. Copiar el **Client ID** (no el secret — no se usa) a:
   - `amelia-intranet-back/.env` → `GOOGLE_CLIENT_ID`
   - `amelia-intranet-web/.env` → `VITE_GOOGLE_CLIENT_ID` (mismo valor)
5. Confirmar `GOOGLE_WORKSPACE_HOSTED_DOMAINS=ameliahub.com,octocam-maps.com`
   (CSV) — es el claim `hd` que distingue plantilla interna de
   externos-invitado. **Ojo:** cualquier cuenta de alguno de esos Workspace
   que haga login y no tenga invitación pendiente se auto-provisiona como
   `empleado` (ver "Contrato de `/auth`" más abajo) — revisar que la lista
   esté bien antes de habilitar el login en un entorno compartido.

### 2. Base de datos + backend (Docker)

```bash
cp .env.example .env   # rellenar GOOGLE_CLIENT_ID como mínimo
docker compose -f docker-compose.local.yaml --profile local up --build
```

Esto levanta Postgres 17 (puerto `5436` en el host) y ejecuta las 11
migraciones de `database/migrations/` automáticamente en el primer arranque
del volumen (ver `database/migrations/README.md`). El backend queda en
`http://localhost:8000` (`/docs` si `SWAGGER_ENABLED=true`).

> Si ya tenías un volumen local con migraciones anteriores aplicadas
> (Postgres no re-ejecuta `docker-entrypoint-initdb.d` en un volumen
> existente), aplica las que falten a mano, en orden:
> `psql "$DATABASE_URL" -f database/migrations/010_absence_types_defaults.sql`
> `psql "$DATABASE_URL" -f database/migrations/011_update_admin_seed_email.sql`

### 3. Sin Docker (venv local)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Postgres debe estar corriendo y accesible en DATABASE_URL; aplicar migraciones:
for f in database/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
python run_server.py
```

### Tests

```bash
source .venv/bin/activate
python -m pytest -v
```

79 tests (los 41 de Fase 1 — JWT service, RBAC `require_role`, verificador de
Google OIDC con mocks, casos de uso de `auth` con fakes en memoria, tests
route-level de `TestClient` + `dependency_overrides`, smoke tests de la app —
más los 38 nuevos de Fase 3: fichaje por tramos con detección de solape y
RBAC dueño/admin, cálculo de días laborables excluyendo finde/festivos,
saldo insuficiente, aprobación/rechazo con ajuste atómico de saldo,
"revisar dos veces" bloqueado, RBAC de la bandeja de pendientes/calendario
global, dashboard por rol con y sin widgets de admin, y tests route-level
que confirman que el externo-invitado recibe `403` en `/time-clock` y
`/absences` — no solo se le oculta el navbar). Todos pasan sin necesitar
Postgres ni credenciales reales de Google.

## Contrato de `/auth`

### `POST /auth/login`

Intercambia el `id_token` de Google (obtenido en el frontend vía Google
Identity Services) por una sesión interna.

```jsonc
// Request
{ "id_token": "<jwt firmado por Google>" }

// Response 200
{
  "access_token": "<jwt interno>",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "empleado@ameliahub.com",
    "full_name": "Nombre Apellido",
    "avatar_url": "https://...",
    "role": "empleado",            // administrador | empleado | externo_invitado
    "entity_id": "uuid | null",
    "department_id": "uuid | null",
    "is_external": false
  }
}
```

También fija una cookie `HttpOnly`, `Secure` (en prod), `SameSite=Strict`
llamada `amelia_intranet_refresh_token` (path `/auth`).

> **SOFT-2170 (fix):** el path era `/auth/refresh` en la primera entrega de
> Fase 1 — el navegador nunca mandaba la cookie a `/auth/logout` (path
> distinto), así que `POST /auth/logout` devolvía `204` pero NO revocaba
> nada server-side (la sesión seguía `revoked_at IS NULL` para siempre).
> `/auth` cubre ambas rutas.

**Alta de usuario** (si el email no existe todavía en `users`), en este orden:
1. Si hay una `invitations` PENDIENTE para ese email, se usa su rol/entidad
   (cubre externos-invitado y cualquier interno que RRHH quiera pre-asignar
   a un rol concreto, p.ej. un futuro admin).
2. Si no hay invitación pero el claim `hd` del id_token (verificado por
   Google, nunca el sufijo del email) coincide con alguno de
   `GOOGLE_WORKSPACE_HOSTED_DOMAINS`, se auto-provisiona como `empleado`
   `active` — entidad/departamento quedan `NULL`, RRHH los completa después.
3. Si no es interno y no hay invitación, `403 NotInvitedError`.

Errores: `403` si no hay alta posible (`NotInvitedError`) o si la cuenta está
suspendida; `401` si el `id_token` no verifica (firma/aud/iss/expirado).

### `POST /auth/refresh`

Sin body — lee el refresh token de la cookie HttpOnly. Valida su firma/expiración
Y que su `jti` siga activo en `auth_sessions` (no revocado por un logout ni por
"logout-all"). Rota la sesión: revoca el `jti` usado y persiste uno nuevo en la
MISMA familia (`family_id`). Devuelve un access token nuevo y rota la cookie.

```jsonc
// Response 200
{ "access_token": "<jwt interno>", "token_type": "bearer", "expires_in": 900 }
```

`401` si el refresh token es inválido, expiró, o su `jti` fue revocado.

**Detección de reuso (rotación OWASP):** si el `jti` presentado existe pero
YA estaba revocado (alguien reutiliza una copia de un refresh token ya
rotado — señal de robo), se revoca la FAMILIA completa (todos los `jti`
descendientes de esa cadena, no solo el reusado) y se responde `401`. El
frontend debe evitar disparar refresh concurrentes con el mismo `jti` en
primer lugar (ver `refreshSessionSingleFlight` en el frontend) — esta
detección es defensa en profundidad, no la primera línea.

### `POST /auth/logout`

Requiere `Authorization: Bearer <access_token>`. Revoca server-side TODA la
familia de sesiones del refresh token actual (no solo su `jti` puntual) y
limpia la cookie. `204 No Content`.

### `POST /auth/logout-all`

Requiere `Authorization: Bearer <access_token>`. Revoca **todas** las
sesiones activas del usuario (todos los dispositivos/refresh tokens vivos),
no solo la actual — pensado para incidentes RGPD (dispositivo perdido o
robado). También limpia la cookie del dispositivo desde el que se llama.

```jsonc
// Response 200
{ "revoked_sessions": 3 }
```

### `GET /auth/me`

Requiere `Authorization: Bearer <access_token>`. Devuelve el mismo objeto
`user` que `/auth/login`, leído en tiempo real de la base de datos (no solo
del JWT), para reflejar cambios de rol sin esperar al siguiente refresh.

## Contrato de `/dashboard` (Fase 3)

### `GET /dashboard/summary`

Requiere rol `empleado` o `administrador` (el externo-invitado no tiene
"Inicio" en la matriz de permisos — `403` si lo intenta). Resumen agregado
de solo lectura sobre `time_clock`/`absences`; nunca escribe.

```jsonc
// Response 200 (empleado)
{
  "vacation_balance": { "entitled_days": 23, "used_days": 5, "pending_days": 2, "available_days": 16 },
  "today_clock_status": { "has_open_entry": false, "worked_minutes_today": 480 },
  "upcoming_holidays": [{ "day": "2026-08-15", "name": "Asunción" }],
  "pending_absence_requests": null,
  "employees_clocked_in_now": null
}
```

Si el rol es `administrador`, `pending_absence_requests` (bandeja completa,
hasta 20) y `employees_clocked_in_now` (tramos abiertos hoy en toda la
plantilla) vienen rellenos en vez de `null`. `vacation_balance` es `null`
si el usuario todavía no tiene fila de saldo para el año (se crea
perezosamente al usar `/absences`, no aquí).

## Contrato de `/time-clock` (Fase 3)

Control horario por **selección manual de tramos** (p.ej. "de 6 a 9") — NO
es fichaje en tiempo real. Un mismo día admite varios tramos; el hueco entre
ellos actúa como pausa implícita (no se usa `time_clock_breaks` todavía).

- `POST /time-clock/entries` — crea un tramo del usuario autenticado.
  `{"work_date": "2026-07-09", "clock_in": "2026-07-09T06:00:00Z", "clock_out": "2026-07-09T09:00:00Z"}`
  (`clock_out` opcional: tramo abierto). `422` si el rango cruza de día o
  `clock_out <= clock_in`; `422` (`TimeClockOverlapError`) si se solapa con
  otro tramo del mismo usuario/día.
- `GET /time-clock/entries?user_id=&date_from=&date_to=` — historial. Sin
  `user_id`: los propios; el admin puede pasar cualquier `user_id` o, si lo
  omite, ve la vista aumentada de TODA la plantilla. `403` si un empleado
  pide el `user_id` de otro.
- `GET /time-clock/entries/export` — mismo filtro, respuesta `text/csv`.
- `PATCH /time-clock/entries/{id}` — edita horas (dueño o admin, `403` si no).
- `DELETE /time-clock/entries/{id}` — borra un tramo (dueño o admin).

## Contrato de `/absences` (Fase 3)

- `GET /absences/types` — catálogo activo (`vacaciones`, `baja_medica`,
  `asuntos_propios` — seed en `010_absence_types_defaults.sql`, editable por
  el admin en Fase 5).
- `GET /absences/balance?user_id=&year=` — contador en tiempo real
  (`entitled/used/pending/available`) por tipo, para el año dado (por
  defecto el actual). Crea la fila de saldo la primera vez que hace falta.
  Sin `user_id`: el propio; solo el admin puede consultar el de otro.
- `POST /absences/requests` — crea una solicitud. `days_count` se calcula en
  el backend excluyendo fines de semana y festivos (`holidays`, vacío hasta
  Fase 5). `422` si el rango no tiene ningún día laborable o si el saldo
  disponible no cubre los días pedidos (tipos con `affects_balance=TRUE`
  únicamente — `baja_medica` no lo exige). La solicitud nace `pending` y
  SUMA a `pending_days` de inmediato.
- `GET /absences/requests?user_id=` — propias por defecto; el admin puede
  pasar `user_id` para ver las de otro.
- `GET /absences/requests/pending` — bandeja de aprobación, **exclusiva del
  admin** (`require_role("administrador")`, `403` para cualquier otro rol).
- `GET /absences/requests/all` — calendario global, exclusivo del admin.
- `POST /absences/requests/{id}/review` — `{"decision": "approved"|"rejected", "note": "..."}`,
  exclusivo del admin. Aprobar traslada los días de `pending_days` a
  `used_days`; rechazar solo libera `pending_days`. `422` si la solicitud ya
  fue revisada (no admite una segunda decisión).

## RBAC

- `src/shared/auth/dependencies.py::get_current_user` — dependencia FastAPI
  que exige un JWT interno válido.
- `src/shared/auth/dependencies.py::require_role(*roles)` — fábrica de
  dependencia que además exige que el rol del usuario esté en la lista.
  Ejemplo: `Depends(require_role("administrador"))`.
- **Regla no negociable**: el navbar del frontend condicionado por rol es
  solo cosmético. Cada endpoint exclusivo de un rol DEBE usar
  `require_role(...)` (`/dashboard/summary`, `/absences/requests/pending`,
  `/absences/requests/all`, `/absences/requests/{id}/review`) — nunca
  confiar en que el frontend no muestre el enlace. En `/time-clock` y en
  `/absences/requests`/`/absences/balance` la autorización es más fina
  (dueño del recurso o admin) y vive dentro del caso de uso, no en la
  dependencia de ruta — ver `TimeClockForbiddenError`/`AbsenceForbiddenError`.

## Pendiente / sin verificar (honesto)

- **Concurrencia real en Postgres sin probar**: la detección de reuso está
  probada con fakes en memoria (`test_concurrent_refresh_with_same_jti_...`),
  que documentan el invariante pero no reproducen una carrera real de dos
  conexiones asyncpg simultáneas contra la misma fila. En el peor caso de
  una carrera real ganada por ambas lecturas antes de que ninguna escriba
  (poco probable con Postgres y transacciones cortas, pero no descartado sin
  un `SELECT ... FOR UPDATE` o una constraint que lo impida a nivel BD), el
  segundo `UPDATE ... WHERE jti = $1 AND revoked_at IS NULL` de
  `revoke_session` simplemente no afecta filas — no habría doble-rotación
  silenciosa, pero tampoco se ha verificado con una prueba de carga real
  contra Postgres.
- **Login real de Google no se puede probar sin credenciales** — se verificó
  con `google.oauth2.id_token.verify_oauth2_token` mockeado en tests, no
  contra la API real de Google.
- **Precedencia invitación vs. auto-provisión**: si un email interno tiene
  una invitación pendiente, esta gana sobre la auto-provisión como
  `empleado` (permite pre-asignar rol/entidad a un interno concreto). No
  estaba explícito en el encargo — es una decisión de diseño para no romper
  el flujo de invitación existente; confirmarla con el equipo si no era la
  intención.
- **Verificación de Google es bloqueante en el event loop**: `google-auth`
  hace una llamada HTTP síncrona (cacheada) para las claves públicas de
  Google. Para Fase 1 es aceptable; si el volumen de logins lo justifica,
  mover a `httpx` async o ejecutar en threadpool.
- **Bootstrap del admin único** (`007_seed_initial_admin.sql`) sembraba un
  email placeholder (`beatriz.luna@ameliahub.com`); `011_update_admin_seed_email.sql`
  (Fase 3) lo actualizó a `people@ameliahub.com` (cambio de la demo). La
  auto-provisión por dominio NO reemplaza este seed: sin él, quien inicia
  sesión con ese email entraría como `empleado` en vez de `administrador`.
- **Limpieza de `auth_sessions`**: no hay todavía un job que borre filas
  viejas (revocadas o expiradas hace tiempo) — la tabla crece sin límite.
- **Pendiente RRHH (Fase 3 — cuestionario sin responder)**: los valores de
  `010_absence_types_defaults.sql` son defaults sensatos, NO confirmados —
  vacaciones 23 laborables/año (viene del propio requerimiento), baja médica
  sin entitlement (no descuenta saldo), asuntos propios en 0 días. También
  sin confirmar: nº de tramos de fichaje permitidos por día, ventana de
  edición retroactiva del control horario, cálculo de horas extra, y qué
  saldo aplica si una solicitud de ausencia cruza de un año a otro (hoy se
  usa el año de `start_date` sin prorratear). Todo es CONFIGURABLE sin
  migración nueva salvo el propio catálogo de tipos — el admin lo edita en
  Fase 5.
- **`holidays` sigue vacía** — hasta que el admin cargue los festivos de
  Barcelona (Fase 5), el cálculo de días laborables de `absences` solo
  excluye fines de semana.
- **Sin endpoint de aprobación parcial ni cancelación de una solicitud ya
  aprobada** — `review_absence_request` solo cubre `pending -> approved|rejected`;
  cancelar una ausencia ya aprobada (p.ej. el empleado se pone enfermo antes
  de sus vacaciones) no se pidió para esta ronda y no tiene endpoint.
- **`time_clock_breaks` sin usar** — el modelo de tramos manuales hace que el
  hueco entre dos tramos actúe como pausa implícita; si RRHH pide registrar
  pausas DENTRO de un mismo tramo, esa tabla ya existe desde `003_hr_core`
  sin necesitar migración nueva.
- **`GoogleOIDCVerificationError` no mapeada en el exception handler**
  (bug preexistente de Fase 1, no de esta ronda): un `id_token` malformado
  cae al `except Exception` genérico y responde `500` en vez de `401`. Se
  detectó al hacer smoke testing manual de Fase 3 con un token falso —
  queda fuera de alcance de este cambio, pero conviene un ticket aparte
  (`src/shared/errors/handler.py` — añadir `GoogleOIDCVerificationError` a
  `_STATUS_BY_ERROR` con `401`).
  No es un problema funcional en Fase 1 (bajo volumen), pero conviene un
  cron/trigger de limpieza antes de producción.
- No hay todavía tabla `schema_migrations` — ver `database/migrations/README.md`.
