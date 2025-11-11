from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from psycopg.rows import dict_row

from src.common.db import DatabaseManager


@dataclass
class SessionStatus:
    session_name: str
    exists: bool
    phone_number: Optional[str]
    bot_role: Optional[str]
    updated_at: Optional[datetime]
    flood_wait_until: Optional[datetime]
    last_error: Optional[str]

    @property
    def stale(self) -> bool:
        return not self.exists


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

    def save(
        self,
        session_name: str,
        session_data: str,
        *,
        phone_number: Optional[str],
        bot_role: Optional[str],
    ) -> None:
        with self._database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO telethon_sessions (session_name, session_data, phone_number, bot_role, flood_wait_until, last_error, updated_at)
                    VALUES (%s, %s, %s, %s, NULL, NULL, CURRENT_TIMESTAMP)
                    ON CONFLICT (session_name) DO UPDATE SET
                        session_data = EXCLUDED.session_data,
                        phone_number = EXCLUDED.phone_number,
                        bot_role = EXCLUDED.bot_role,
                        flood_wait_until = NULL,
                        last_error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (session_name, session_data, phone_number, bot_role),
                )
                conn.commit()

    def update_flood_wait(self, session_name: str, seconds: int, *, error: Optional[str] = None) -> None:
        with self._database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO telethon_sessions (session_name, session_data, updated_at)
                    VALUES (%s, NULL, CURRENT_TIMESTAMP)
                    ON CONFLICT (session_name) DO NOTHING
                    """,
                    (session_name,),
                )
                cursor.execute(
                    """
                    UPDATE telethon_sessions
                    SET flood_wait_until = CURRENT_TIMESTAMP + (%s || ' seconds')::INTERVAL,
                        last_error = %s
                    WHERE session_name = %s
                    """,
                    (seconds, error, session_name),
                )
                conn.commit()

    def get_status(self, session_name: str) -> SessionStatus:
        with self._database.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT session_name,
                           session_data IS NOT NULL AS exists,
                           phone_number,
                           bot_role,
                           updated_at,
                           flood_wait_until,
                           last_error
                    FROM telethon_sessions
                    WHERE session_name = %s
                    """,
                    (session_name,),
                )
                row = cursor.fetchone()
                if not row:
                    return SessionStatus(
                        session_name=session_name,
                        exists=False,
                        phone_number=None,
                        bot_role=None,
                        updated_at=None,
                        flood_wait_until=None,
                        last_error=None,
                    )
                return SessionStatus(
                    session_name=session_name,
                    exists=bool(row["exists"]),
                    phone_number=row["phone_number"],
                    bot_role=row["bot_role"],
                    updated_at=row["updated_at"],
                    flood_wait_until=row["flood_wait_until"],
                    last_error=row["last_error"],
                )

    def get_statuses(self, session_names: list[str]) -> dict[str, SessionStatus]:
        results: dict[str, SessionStatus] = {}
        for name in session_names:
            results[name] = self.get_status(name)
        return results
