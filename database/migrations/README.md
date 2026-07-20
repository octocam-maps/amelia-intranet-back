# Migraciones

SQL crudo, sin ORM ni Alembic. Numeradas `NNN_descripcion.sql`, cada una envuelta en
`BEGIN; ... COMMIT;`. **Nunca editar una migración ya aplicada** — los cambios van en
una migración nueva.

## Orden (Fase 1 — identidad y acceso)

| Archivo | Contenido |
|---|---|
| `001_core_identity.sql` | `entities`, `departments`, `roles`, `users`, `user_profiles`, `invitations` + seed de roles/entidades |
| `002_onboarding.sql` | Tablas de Fase 2 (aún sin endpoints en Fase 1) |
| `003_hr_core.sql` | Tablas de Fase 3 |
| `004_documents.sql` | Tablas de Fase 4 |
| `005_admin_comms.sql` | Tablas de Fase 5 (incluye `anonymous_messages`, anonimato estructural) |
| `006_notifications.sql` | Tablas de Fase 6 |
| `007_seed_initial_admin.sql` | Bootstrap del único Administrador (Beatriz Luna) — ver comentario en el archivo sobre el email placeholder |
| `008_auth_sessions.sql` | `auth_sessions` — revocación server-side de refresh tokens (aditiva, añadida tras validación de Fase 1) |
| `009_auth_sessions_family.sql` | `auth_sessions.family_id` — detección de reuso de refresh token (rotación OWASP), aditiva |
| `010_absence_types_defaults.sql` | `absence_types.default_entitled_days` (aditiva) + seed de vacaciones/baja_medica/asuntos_propios (Fase 3) |
| `011_update_admin_seed_email.sql` | Actualiza el email del admin sembrado en 007: `beatriz.luna@ameliahub.com` -> `people@ameliahub.com` (cambio de la demo) |
| `012_time_clock_no_overlap_constraint.sql` | `btree_gist` + `EXCLUDE` en `time_clock_entries` — cinturón de seguridad en BD contra el solape de tramos bajo concurrencia (RACE-3, auditoría QA Fase 3) |
| `013_absence_types_seed_expansion.sql` | Seed de `justificada`/`remoto`/`otros` (los 6 tipos del modal de nueva solicitud) + colores realineados con `docs/deck-fase3` |
| `014_mailbox_reply_status.sql` | `anonymous_messages.admin_reply`/`replied_at` (aditiva) + estado `resolved` sustituye a `archived` + CHECK de `category` (Fase 6, buzón anónimo) |
| `015_users_hire_date.sql` | `users.hire_date` (aditiva) — fecha de alta ligada al cálculo de vacaciones (Fase 6, gestión de plantilla) |
| `016_departments_unique_name.sql` | `uq_departments_entity_name` — permite el upsert de departamentos "sobre la marcha" desde el alta/edición de plantilla, sin CRUD propio todavía (Fase 6) |
| `017_holidays_updated_at.sql` | `holidays.updated_at` (aditiva) — necesario para el CRUD admin de festivos (Fase 6, ronda 2) |
| `018_holidays_source_scope.sql` | `holidays.source` (`oficial`/`manual`) + `scope` (aditivas) — importación automática de festivos oficiales desde Nager.Date sin pisar los añadidos a mano (Fase 6, ronda 2) |
| `019_absence_types_policy_fields.sql` | `absence_types.requires_approval`/`requires_justification`/`max_days_per_year` (aditivas) — políticas configurables por tipo desde el form de gestión (Fase 6, ronda 2) |
| `020_onboarding_steps_seed.sql` | Seed de Fase 2 (onboarding): los 5 `onboarding_steps` (vídeo, cuestionario "El Hincator", firma, manual, perfil) + los 2 `onboarding_documents` placeholder (firma/manual). |
| `021_time_clock_break_no_concurrent.sql` | Índice único parcial `uq_time_clock_break_one_open_per_entry` — impide dos pausas de fichaje abiertas a la vez en el mismo tramo (backstop anti-doble-clic que corrompía el contador semanal). |
| `022_user_profiles_city.sql` | `user_profiles.city` (aditiva) — "Mi perfil" editable (Lote 2): el usuario edita su propio teléfono (`user_profiles.phone`, ya existía) y ciudad desde `PATCH /profile/me`. |
| `023_time_clock_entry_notes.sql` | `time_clock_entry_notes` — incidencias/comentarios admin sobre un tramo de fichaje (B-2b, alta admin-only, lectura acotada al dueño del tramo o al admin). |
| `024_socio_role.sql` | Amplía `roles.code` CHECK + seed del rol `socio` — igual que un empleado en toda la app + visión global del calendario de vacaciones (ver/exportar PDF/Excel), sin permisos de administración. |
| `025_users_drive_folder_id.sql` | `users.drive_folder_id` (aditiva) — cachea el id de la subcarpeta de Google Drive del empleado (Fase 4 v2, Drive real: WU-A de `sdd/fase4-nominas-documentos`). |
| `026_user_profiles_company_phone.sql` | `user_profiles.company_phone` (aditiva) — último campo que faltaba de los 7 del paso 5 del onboarding ("Completar perfil", RF §3.5); el resto (`dni_nif`, `birth_date`, `phone`, `address`, `users.full_name`, `users.department_id`) ya existía desde `001_core_identity.sql`. |

Los módulos 2-6 se crean todos en Fase 1 (según `docs/fase-0-esquema-datos.md`, ya
aprobado) para no tener que ir migrando el esquema en cada fase de producto — pero
**el backend de Fase 1 solo implementa endpoints sobre `001` (auth + RBAC)**. El resto
de tablas esperan a su fase correspondiente.

## Cómo se aplican

El modelo es el mismo que en `backend2`:

- **`database/init.sql` = esquema COMPLETO autocontenido** (estado actual, con la
  estructura de creación inline). Es la fuente para inicializar una base de datos
  NUEVA de un solo golpe.
- **`database/migrations/NNN_*.sql` = registro incremental** para bases YA
  existentes. Se aplican **a mano**.

- **Local (Docker, base nueva):** `docker-compose.local.yaml` monta
  `./database/init.sql` en `/docker-entrypoint-initdb.d/00_init.sql`. Postgres lo
  ejecuta en el PRIMER arranque del volumen (vacío). Si el volumen ya existe no se
  re-ejecuta — recrearlo con `docker compose down -v` o aplicar la migración nueva
  a mano (`psql "$DATABASE_URL" -f database/migrations/NNN_*.sql`).
- **Servidor / stage / prod (base nueva):** un solo comando:
  ```bash
  psql "$DATABASE_URL" -f database/init.sql
  ```
- **Base existente + cambio nuevo:** aplicar SOLO la migración nueva, a mano:
  ```bash
  psql "$DATABASE_URL" -f database/migrations/NNN_descripcion.sql
  ```

> ⚠️ Al añadir una migración nueva hay que reflejar su cambio TAMBIÉN en
> `database/init.sql` (columna/tabla/seed en su estado final) y en la tabla de
> arriba. `init.sql` y las migraciones deben describir el mismo esquema — se
> verifica comparando `pg_dump -s` de una base creada con `init.sql` contra otra
> creada aplicando las migraciones en orden (deben coincidir salvo el orden de
> columnas que `ALTER ... ADD COLUMN` deja al final, irrelevante para la app).

- Las migraciones que crean constraints con nombre (`012` EXCLUDE, `016` UNIQUE)
  NO son re-ejecutables (Postgres no soporta `ADD CONSTRAINT IF NOT EXISTS`); si se
  corren dos veces dan error "ya existe" y abortan esa transacción, sin corromper
  nada. El resto es idempotente (`IF NOT EXISTS` / `ON CONFLICT DO NOTHING`).
- No hay todavía una tabla de control de versión (`schema_migrations`).
  Recomendado antes de tener stage/prod reales.
