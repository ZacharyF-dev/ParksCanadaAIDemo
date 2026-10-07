from __future__ import annotations

from datetime import datetime


def get_current_local_time() -> str:
    """Return the host's current local date and time with its UTC offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")
