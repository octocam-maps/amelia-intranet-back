BEGIN;

-- Fase 6 (gestión de plantilla): `departments` no tiene CRUD propio
-- todavía — el admin los va nombrando libremente al dar de alta/editar
-- personas (`POST /staff`, `PATCH /staff/{id}`). Sin esta UNIQUE, escribir
-- "Operaciones" dos veces crearía dos filas distintas en la misma entidad;
-- con ella, `get_or_create_department_id` puede hacer un upsert seguro
-- (mismo patrón que `uq_balance_user_type_year` en 003_hr_core.sql).
ALTER TABLE departments
    ADD CONSTRAINT uq_departments_entity_name UNIQUE (entity_id, name);

COMMIT;
