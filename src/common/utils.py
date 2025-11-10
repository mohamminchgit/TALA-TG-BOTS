from datetime import datetime
from typing import Optional

from .constants import PERSIAN_TO_ENGLISH


def normalize_persian_numbers(value: str) -> str:
    """Convert Persian digits to ASCII digits."""
    return value.translate(PERSIAN_TO_ENGLISH)


def parse_int(value: str, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(normalize_persian_numbers(value))
    except (TypeError, ValueError):
        return default


def utc_now() -> datetime:
    return datetime.utcnow()
