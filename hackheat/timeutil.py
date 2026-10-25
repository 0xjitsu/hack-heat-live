"""Clock and countdown helpers.

Singapore has used a fixed UTC+8 offset since 1982, so the radar does not
need the system tz database. That keeps the slim CI image and Cloud Run
image honest about Asia/Singapore without an apt package.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8), name="Asia/Singapore")
UTC = timezone.utc


def now() -> datetime:
    """Current instant, or HACKHEAT_NOW when a demo or test freezes the clock."""
    override = os.environ.get("HACKHEAT_NOW", "").strip()
    if override:
        return parse_instant(override)
    return datetime.now(UTC)


def parse_instant(value: str) -> datetime:
    """Parse an ISO instant. Date-only values are end of that UTC day.

    The board's own notes say a date with no clock should be treated as
    end of day UTC.
    """
    text = value.strip()
    if not text:
        raise ValueError("empty timestamp")
    date_only = len(text) == 10 and text[4] == "-" and text[7] == "-"
    if date_only:
        text = text + "T23:59:59+00:00"
    text = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_sgt(instant: datetime) -> datetime:
    return instant.astimezone(SGT)


def format_sgt(instant: datetime) -> str:
    local = to_sgt(instant)
    return local.strftime("%a %d %b %Y %H:%M SGT")


def countdown(target: datetime, *, as_of: datetime) -> tuple[str, int]:
    """Return a short countdown phrase and the signed seconds remaining."""
    seconds = int((target - as_of).total_seconds())
    if seconds <= 0:
        past = -seconds
        return "closed " + _span(past) + " ago", seconds
    if seconds < 60:
        return "closes in under 1m", seconds
    return "closes in " + _span(seconds), seconds


def _span(seconds: int) -> str:
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days >= 1:
        return f"{days}d {hours}h"
    if hours >= 1:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
