# Amelia Intranet — Backend

FastAPI + asyncpg (SQL crudo, sin ORM). Arquitectura hexagonal por feature
(`domain` / `application` / `infrastructure`), espejo de `backend2`. Ver
`../amelia-intranet/CLAUDE.md` y `../amelia-intranet/docs/` para el contrato
funcional completo.

**Fase 1 (actual):** Autenticación (Google OIDC) + RBAC base. El resto de
tablas del esquema (onboarding, RRHH, documentos, admin/comms, notificaciones)
ya existen en las migraciones pero **no tienen endpoints todavía** — eso es
Fase 2+.

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
5. Confirmar `GOOGLE_WORKSPACE_HOSTED_DOMAIN=ameliahub.com` — es el claim `hd`
   que distingue plantilla interna de externos-invitado. **Ojo:** cualquier
   cuenta de ese Workspace que haga login y no tenga invitación pendiente se
   auto-provisiona como `empleado` (ver "Contrato de `/auth`" más abajo) —
   revisar que este dominio esté bien antes de habilitar el login en un
   entorno compartido.

### 2. Base de datos + backend (Docker)

```bash
cp .env.example .env   # rellenar GOOGLE_CLIENT_ID como mínimo
docker compose -f docker-compose.local.yaml --profile local up --build
```

Esto levanta Postgres 17 (puerto `5436` en el host) y ejecuta las 9
migraciones de `database/migrations/` automáticamente en el primer arranque
del volumen (ver `database/migrations/README.md`). El backend queda en
`http://localhost:8000` (`/docs` si `SWAGGER_ENABLED=true`).

> Si ya tenías un volumen local con las migraciones 001-008 aplicadas
> (Postgres no re-ejecuta `docker-entrypoint-initdb.d` en un volumen
> existente), aplica la 009 a mano: `psql "$DATABASE_URL" -f
> database/migrations/009_auth_sessions_family.sql`.

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

41 tests (JWT service, RBAC `require_role`, verificador de Google OIDC con
mocks, casos de uso de `auth` con fakes en memoria de `IUserRepository` /
`ISessionRepository` — auto-provisión, invitación, admin sembrado, rotación
de sesiones, **detección de reuso de refresh token con revocación de
familia**, refresh "concurrente" con el mismo jti —, tests route-level con
`TestClient` + `dependency_overrides` — **logout revoca server-side ahora
que la cookie llega con `path=/auth`** (SOFT-2170), refresh sigue
funcionando —, smoke tests de la app). Todos pasan sin necesitar Postgres
ni credenciales reales
de Google.

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
   Google, nunca el sufijo del email) coincide con
   `GOOGLE_WORKSPACE_HOSTED_DOMAIN`, se auto-provisiona como `empleado`
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

## RBAC

- `src/shared/auth/dependencies.py::get_current_user` — dependencia FastAPI
  que exige un JWT interno válido.
- `src/shared/auth/dependencies.py::require_role(*roles)` — fábrica de
  dependencia que además exige que el rol del usuario esté en la lista.
  Ejemplo: `Depends(require_role("administrador"))`.
- **Regla no negociable**: el navbar del frontend condicionado por rol es
  solo cosmético. Cada endpoint de Fase 2+ que sea exclusivo de un rol DEBE
  usar `require_role(...)` — nunca confiar en que el frontend no muestre el
  enlace.

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
- **Bootstrap del admin único** (`007_seed_initial_admin.sql`) usa un email
  placeholder (`beatriz.luna@ameliahub.com`) — sigue pendiente, actualizar
  antes de producción. La auto-provisión por dominio NO reemplaza este seed:
  sin él, Beatriz entraría como `empleado` en vez de `administrador`.
- **Limpieza de `auth_sessions`**: no hay todavía un job que borre filas
  viejas (revocadas o expiradas hace tiempo) — la tabla crece sin límite.
  No es un problema funcional en Fase 1 (bajo volumen), pero conviene un
  cron/trigger de limpieza antes de producción.
- No hay todavía tabla `schema_migrations` — ver `database/migrations/README.md`.
