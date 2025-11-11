#!/usr/bin/env python3
"""Persist a Telethon string session into the configured PostgreSQL store."""
from __future__ import annotations

import sys

from src.common.db import DatabaseManager
from src.common.session_store import SessionStore
from src.config.settings import get_settings


def main(session_key: str, session_string: str) -> None:
    settings = get_settings()
    database = DatabaseManager(settings.database.url)
    database.initialize_schema()
    store = SessionStore(database)
    store.save(session_key, session_string)
    print(f"✅ Stored session string under key '{session_key}'")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/store_session.py <session_key> <session_string>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
