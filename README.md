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
   que distingue plantilla interna de externos-invitado.

### 2. Base de datos + backend (Docker)

```bash
cp .env.example .env   # rellenar GOOGLE_CLIENT_ID como mínimo
docker compose -f docker-compose.local.yaml --profile local up --build
```

Esto levanta Postgres 17 (puerto `5436` en el host) y ejecuta las 7
migraciones de `database/migrations/` automáticamente en el primer arranque
del volumen (ver `database/migrations/README.md`). El backend queda en
`http://localhost:8000` (`/docs` si `SWAGGER_ENABLED=true`).

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

24 tests (JWT service, RBAC `require_role`, verificador de Google OIDC con
mocks, smoke tests de la app con `TestClient`). Todos pasan sin necesitar
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
llamada `amelia_intranet_refresh_token` (path `/auth/refresh`).

Errores: `403` si el email no tiene cuenta ni invitación pendiente
(`NotInvitedError`) o si la cuenta está suspendida; `401` si el `id_token` no
verifica (firma/aud/iss/expirado).

### `POST /auth/refresh`

Sin body — lee el refresh token de la cookie HttpOnly. Devuelve un access
token nuevo y rota la cookie.

```jsonc
// Response 200
{ "access_token": "<jwt interno>", "token_type": "bearer", "expires_in": 900 }
```

### `POST /auth/logout`

Requiere `Authorization: Bearer <access_token>`. Limpia la cookie de refresh.
`204 No Content`. **Stateless en Fase 1**: no hay tabla de revocación de
refresh tokens — ver "Pendiente" más abajo.

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

- **Login real de Google no se puede probar sin credenciales** — se verificó
  con `google.oauth2.id_token.verify_oauth2_token` mockeado en tests, no
  contra la API real de Google.
- **Revocación de refresh tokens**: es un JWT stateless (sin tabla de
  persistencia, a diferencia de `backend2`). `logout` solo borra la cookie
  del navegador — un token robado sigue siendo válido hasta que expira (7
  días por defecto). Si esto es un requisito duro, hace falta una tabla
  `refresh_tokens` (no está en `docs/fase-0-esquema-datos.md`) — decisión
  pendiente para el equipo.
- **Verificación de Google es bloqueante en el event loop**: `google-auth`
  hace una llamada HTTP síncrona (cacheada) para las claves públicas de
  Google. Para Fase 1 es aceptable; si el volumen de logins lo justifica,
  mover a `httpx` async o ejecutar en threadpool.
- **Bootstrap del admin único** (`007_seed_initial_admin.sql`) usa un email
  placeholder (`beatriz.luna@ameliahub.com`) — actualizar antes de producción.
- No hay todavía tabla `schema_migrations` — ver `database/migrations/README.md`.
