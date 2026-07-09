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

Los módulos 2-6 se crean todos en Fase 1 (según `docs/fase-0-esquema-datos.md`, ya
aprobado) para no tener que ir migrando el esquema en cada fase de producto — pero
**el backend de Fase 1 solo implementa endpoints sobre `001` (auth + RBAC)**. El resto
de tablas esperan a su fase correspondiente.

## Cómo se aplican

- **Local (Docker, base de datos nueva):** `docker-compose.local.yaml` monta
  `./database/migrations` en `/docker-entrypoint-initdb.d`. Postgres ejecuta ahí
  todo `*.sql` en orden alfabético en el PRIMER arranque del volumen (los prefijos
  `001_`…`009_` garantizan el orden numérico). Si el volumen ya existe, no se
  vuelven a ejecutar — hay que recrearlo (`docker compose down -v`) o aplicar la
  migración nueva a mano (p.ej. un entorno local que ya tenía 001-008 aplicadas
  necesita `psql "$DATABASE_URL" -f database/migrations/009_auth_sessions_family.sql`
  para tener la columna `family_id`).
- **Manual / stage / prod:** aplicar con `psql`, en orden, contra una base ya
  existente:
  ```bash
  for f in database/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
  ```
- No hay todavía una tabla de control de versión de migraciones (`schema_migrations`).
  Para Fase 1 (greenfield, un único entorno local) no es crítico; recomendado antes
  de tener stage/prod reales.
