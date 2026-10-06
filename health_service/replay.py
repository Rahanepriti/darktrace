from __future__ import annotations

from datetime import datetime


def is_replayed(message_timestamp: datetime, now: datetime, max_age_seconds: int) -> bool:
    age_seconds = (now - message_timestamp).total_seconds()
    return age_seconds > max_age_seconds or age_seconds < -max_age_seconds
