"""Factoría de acceso al pool de base de datos (singleton)."""

from typing import Optional

from .infrastructure.asyncpg_pool import DatabasePool

_database_pool_instance: Optional[DatabasePool] = None


def get_database_pool() -> DatabasePool:
    """Devuelve la instancia singleton de DatabasePool."""
    global _database_pool_instance
    if _database_pool_instance is None:
        _database_pool_instance = DatabasePool()
    return _database_pool_instance
