"""
Pool de conexiones asyncpg. SQL crudo — sin ORM, sin Alembic (regla no
negociable del proyecto). Instalar codecs JSON/JSONB para que las columnas
JSONB se serialicen/deserialicen de forma transparente entre dict <-> texto.
"""

import json
import os
from typing import Any, Optional

import asyncpg


def _encode_jsonb(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _decode_jsonb(value: str) -> Any:
    return json.loads(value)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=_encode_jsonb,
        decoder=_decode_jsonb,
        schema="pg_catalog",
        format="text",
    )
    await conn.set_type_codec(
        "json",
        encoder=_encode_jsonb,
        decoder=_decode_jsonb,
        schema="pg_catalog",
        format="text",
    )


class DatabasePool:
    """Wrapper singleton sobre `asyncpg.Pool`."""

    _instance: Optional["DatabasePool"] = None
    _pool: Optional[asyncpg.Pool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self, connection_string: Optional[str] = None) -> None:
        if self._pool is not None:
            return

        if connection_string is None:
            connection_string = os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5436/postgres",
            )

        self._pool = await asyncpg.create_pool(
            connection_string,
            min_size=1,
            max_size=10,
            command_timeout=60,
            init=_init_connection,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call initialize() first.")
        return self._pool

    def acquire(self):
        """Context manager async sobre una conexión pooled (para transacciones)."""
        return self.pool.acquire()

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Optional[Any]:
        async with self.pool.acquire() as connection:
            return await connection.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        async with self.pool.acquire() as connection:
            return await connection.execute(query, *args)
