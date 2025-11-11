from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import psycopg
from psycopg import Cursor
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


@dataclass
class Migration:
    name: str
    apply: Callable[[Cursor], None]


def _migration_initial_schema(cursor: Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            parameter_name TEXT PRIMARY KEY,
            parameter_value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_history (
            id BIGSERIAL PRIMARY KEY,
            trade_id TEXT UNIQUE NOT NULL,
            strategy TEXT NOT NULL,
            source_message_id BIGINT,
            destination_message_id BIGINT,
            quantity INTEGER NOT NULL,
            source_price NUMERIC(18, 4) NOT NULL,
            destination_price NUMERIC(18, 4) NOT NULL,
            profit NUMERIC(18, 4) NOT NULL,
            status TEXT NOT NULL,
            executed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_stats (
            id BIGSERIAL PRIMARY KEY,
            date DATE UNIQUE NOT NULL,
            total_trades INTEGER DEFAULT 0,
            successful_trades INTEGER DEFAULT 0,
            emergency_exits INTEGER DEFAULT 0,
            total_profit NUMERIC(18, 4) DEFAULT 0,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_log (
            id BIGSERIAL PRIMARY KEY,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _migration_session_store(cursor: Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS telethon_sessions (
            session_name TEXT PRIMARY KEY,
            session_data TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


_MIGRATIONS: Iterable[Migration] = (
    Migration("0001_initial_schema", _migration_initial_schema),
    Migration("0002_session_store", _migration_session_store),
)


class DatabaseManager:
    """PostgreSQL helper that exposes a pooled connection and applies migrations."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool = ConnectionPool(
            conninfo=self._dsn,
            kwargs={"autocommit": False, "row_factory": dict_row},
        )

    def connect(self) -> psycopg.Connection:
        return self._pool.connection()

    def close(self) -> None:
        self._pool.close()

    def initialize_schema(self) -> None:
        with self.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        name TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.commit()

        for migration in _MIGRATIONS:
            self._apply_migration(migration)

    def _apply_migration(self, migration: Migration) -> None:
        with self.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM schema_migrations WHERE name = %s",
                    (migration.name,),
                )
                if cursor.fetchone():
                    return
                migration.apply(cursor)
                cursor.execute(
                    "INSERT INTO schema_migrations (name) VALUES (%s)",
                    (migration.name,),
                )
                conn.commit()
