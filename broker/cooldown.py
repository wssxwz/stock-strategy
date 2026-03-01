"""Cooldown policy.

We use rolling wall-clock time (e.g. 24h) after a stop-out event.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def iso_after_hours(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=float(hours))).isoformat(timespec='seconds')
