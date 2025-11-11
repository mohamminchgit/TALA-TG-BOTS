from __future__ import annotations

from typing import Optional

from src.common.db import DatabaseManager


class SessionStore:
    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    def load(self, session_name: str) -> Optional[str]:
        with self._database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT session_data FROM telethon_sessions WHERE session_name = %s",
                    (session_name,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return row["session_data"]

    def save(self, session_name: str, session_data: str) -> None:
        with self._database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO telethon_sessions (session_name, session_data, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (session_name) DO UPDATE SET
                        session_data = EXCLUDED.session_data,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (session_name, session_data),
                )
                conn.commit()
