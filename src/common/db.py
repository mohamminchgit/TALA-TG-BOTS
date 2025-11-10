import sqlite3
from pathlib import Path
from typing import Iterable


_SCHEMA_STATEMENTS: Iterable[str] = (
    """
    CREATE TABLE IF NOT EXISTS config (
        parameter_name TEXT PRIMARY KEY,
        parameter_value TEXT NOT NULL,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT UNIQUE NOT NULL,
        strategy TEXT NOT NULL,
        source_message_id INTEGER,
        destination_message_id INTEGER,
        quantity INTEGER NOT NULL,
        source_price REAL NOT NULL,
        destination_price REAL NOT NULL,
        profit REAL NOT NULL,
        status TEXT NOT NULL,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS performance_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        total_trades INTEGER DEFAULT 0,
        successful_trades INTEGER DEFAULT 0,
        emergency_exits INTEGER DEFAULT 0,
        total_profit REAL DEFAULT 0.0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_type TEXT NOT NULL,
        message TEXT NOT NULL,
        severity TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
)


class DatabaseManager:
    """Simple SQLite helper responsible for schema management."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_schema(self) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            for statement in _SCHEMA_STATEMENTS:
                cursor.executescript(statement)
            conn.commit()
